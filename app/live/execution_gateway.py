"""Live Execution Gateway (PR113 - Live Execution v0).

The SINGLE entry point for every real order. Strategy / Telegram / AI may
NOT call the Binance execution adapter directly; they must go through
this gateway, which enforces:

    LiveOrderIntent
      -> LivePathIsolationGuard        (only OrderSource.LIVE may pass)
      -> AI refusal                    (ai_trade_authority is forbidden)
      -> order validation              (exchangeInfo precision / minNotional)
      -> evaluate_execution_permission (the 15-point gate)
      -> BinanceExecutionAdapter       (compose + send, or refuse)
      -> LiveOrderResult / LiveFillEvent
      -> LiveOrderLedger
      -> Telegram payload

A real order request only leaves the system when EVERY gate is true:
  1. runtime_mode = LIVE_LIMITED
  2. live_limited_confirmed = True
  3. capital profile allows real orders (e.g. L1_10U_PROBE)
  4. exchange_live_orders = True
  5. trade_authority = True
  6. Binance private trade enabled by config
  7. LiveRiskDecision.approved = True
  8. LiveRiskDecision.real_order_allowed = True
  9. kill switch not active
  10. source = LIVE (no path isolation violation)
  11. client_order_id present
  12. order passes exchangeInfo precision / minNotional
  13. order notional / leverage within profile
  14. stop / exit plan present (or a documented emergency exception)
  15. account capital within the profile cap (or operator-acknowledged)

The DEFAULT posture is safe: LIVE_SHADOW, exchange_live_orders=False,
trade_authority=False, ai_trade_authority=False, no real order. PR112's
dry :class:`LiveRiskDecision` always carries ``real_order_allowed=False``;
only :func:`authorize_real_order` (itself gated on a fully-armed context)
can ever flip it, and the gate STILL re-checks every flag afterwards.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.clock import now_ms
from app.core.enums import Direction, LiveRuntimeMode, OrderSource
from app.core.events import Event, EventType
from app.live.binance_execution_adapter import BinanceExecutionAdapter
from app.live.capital_profile import (
    CapitalProfile,
    CapitalProfileId,
    detect_profile_mismatch,
    get_profile,
)
from app.live.execution_errors import AiTradeAuthorityForbidden
from app.live.execution_models import (
    LiveExecutionStatus,
    LiveOrderIntent,
    LiveOrderResult,
    OrderValidationResult,
)
from app.live.execution_telegram import (
    PAYLOAD_LIVE_EXECUTION_BLOCKED,
    PAYLOAD_LIVE_ORDER_FILLED,
    PAYLOAD_LIVE_ORDER_PARTIALLY_FILLED,
    PAYLOAD_LIVE_ORDER_REJECTED,
    PAYLOAD_LIVE_ORDER_SUBMITTED,
    build_execution_telegram_payload,
)
from app.live.order_ledger import LiveOrderLedger
from app.live.path_isolation import (
    LiveOrderIntent as IsolationIntent,
    LivePathIsolationGuard,
)

LIVE_EXECUTION_GATEWAY_MODULE = "live.execution_gateway"

# Profiles that explicitly allow a real order to be authorised by default.
DEFAULT_ALLOWED_REAL_ORDER_PROFILES: tuple[CapitalProfileId, ...] = (
    CapitalProfileId.L1_10U_PROBE,
)


class ExecutionRejectReason:
    """Closed taxonomy of execution-permission reject reasons (PR113)."""

    RUNTIME_MODE_NOT_LIVE_LIMITED = "runtime_mode_not_live_limited"
    LIVE_LIMITED_NOT_CONFIRMED = "live_limited_not_confirmed"
    EXCHANGE_LIVE_ORDERS_DISABLED = "exchange_live_orders_disabled"
    TRADE_AUTHORITY_DISABLED = "trade_authority_disabled"
    AI_TRADE_AUTHORITY_FORBIDDEN = "ai_trade_authority_forbidden"
    PRIVATE_TRADE_DISABLED_BY_CONFIG = "private_trade_disabled_by_config"
    SOURCE_NOT_LIVE = "source_not_live"
    RISK_DECISION_MISSING = "risk_decision_missing"
    RISK_DECISION_NOT_APPROVED = "risk_decision_not_approved"
    REAL_ORDER_NOT_ALLOWED = "real_order_not_allowed"
    PROFILE_INVALID = "capital_profile_invalid"
    PROFILE_REAL_ORDERS_NOT_ALLOWED = "profile_real_orders_not_allowed"
    PROFILE_NOT_IN_ALLOWED_SET = "profile_not_in_allowed_set"
    PROFILE_MISMATCH_HARD_BLOCK = "profile_mismatch_hard_block"
    ACCOUNT_CAPITAL_EXCEEDS_CAP_NOT_ACKED = "account_capital_exceeds_cap_not_acked"
    MISSING_CLIENT_ORDER_ID = "missing_client_order_id"
    MISSING_STOP_OR_EXIT_PLAN = "missing_stop_or_exit_plan"
    KILL_SWITCH_ACTIVE = "kill_switch_active"
    ORDER_VALIDATION_FAILED = "order_validation_failed"
    NOTIONAL_EXCEEDS_PROFILE_MAX = "order_notional_exceeds_profile_max"
    LEVERAGE_EXCEEDS_PROFILE_MAX = "order_leverage_exceeds_profile_max"


def _env(name: str, default: str, environ: dict[str, str] | None) -> str:
    import os

    source = environ if environ is not None else os.environ
    raw = source.get(name, default)
    return ("" if raw is None else str(raw)).strip()


def _env_bool(name: str, default: bool, environ: dict[str, str] | None) -> bool:
    raw = _env(name, "", environ)
    if raw == "":
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ExecutionPermissionContext:
    """Operator / system flags the execution gate consults.

    All of the unsafe-enabling flags default False so a bare construction
    blocks every real order.
    """

    runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_SHADOW
    live_limited_confirmed: bool = False
    exchange_live_orders: bool = False
    trade_authority: bool = False
    ai_trade_authority: bool = False
    private_trade_enabled: bool = False
    kill_switch_active: bool = False
    profile_operator_acknowledged: bool = False
    hard_block_on_profile_mismatch: bool = True
    account_equity_usdt: float | None = None
    allowed_profile_ids: tuple[CapitalProfileId, ...] = DEFAULT_ALLOWED_REAL_ORDER_PROFILES

    @property
    def fully_armed(self) -> bool:
        """True only when every operator/system gate is set for a real order."""
        return (
            self.runtime_mode is LiveRuntimeMode.LIVE_LIMITED
            and self.live_limited_confirmed
            and self.exchange_live_orders
            and self.trade_authority
            and self.private_trade_enabled
            and not self.ai_trade_authority
            and not self.kill_switch_active
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_mode": self.runtime_mode.value,
            "live_limited_confirmed": self.live_limited_confirmed,
            "exchange_live_orders": self.exchange_live_orders,
            "trade_authority": self.trade_authority,
            "ai_trade_authority": self.ai_trade_authority,
            "private_trade_enabled": self.private_trade_enabled,
            "kill_switch_active": self.kill_switch_active,
            "profile_operator_acknowledged": self.profile_operator_acknowledged,
            "hard_block_on_profile_mismatch": self.hard_block_on_profile_mismatch,
            "account_equity_usdt": self.account_equity_usdt,
            "allowed_profile_ids": [p.value for p in self.allowed_profile_ids],
        }

    @classmethod
    def from_config(
        cls, config: Any, *, environ: dict[str, str] | None = None
    ) -> "ExecutionPermissionContext":
        """Build a context from a ``LiveApiConfig`` + env flags.

        Reads the new PR113 execution flags from the environment; all of
        them default False so a bare environment blocks every real order.
        ``runtime_mode`` / ``private_trade_enabled`` come from the config.
        """
        runtime_mode = getattr(config, "live_runtime_mode", LiveRuntimeMode.LIVE_SHADOW)
        private_trade = bool(getattr(getattr(config, "binance", None), "enable_private_trade", False))
        return cls(
            runtime_mode=runtime_mode,
            live_limited_confirmed=_env_bool("AMA_LIVE_LIMITED_CONFIRMED", False, environ),
            exchange_live_orders=_env_bool("AMA_LIVE_EXCHANGE_LIVE_ORDERS", False, environ),
            trade_authority=_env_bool("AMA_LIVE_TRADE_AUTHORITY", False, environ),
            ai_trade_authority=_env_bool("AMA_LIVE_AI_TRADE_AUTHORITY", False, environ),
            private_trade_enabled=private_trade,
            kill_switch_active=_env_bool("AMA_LIVE_KILL_SWITCH_ACTIVE", False, environ),
            profile_operator_acknowledged=_env_bool(
                "AMA_LIVE_PROFILE_OPERATOR_ACK", False, environ
            ),
        )


@dataclass(frozen=True)
class ExecutionPermissionDecision:
    """Output of :func:`evaluate_execution_permission`."""

    allowed: bool
    reject_reason: str | None
    reject_reasons: tuple[str, ...]
    audit_event: str
    sanitized_detail: dict[str, Any]
    real_order_allowed: bool = False
    decided_at: int = field(default_factory=now_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reject_reason": self.reject_reason,
            "reject_reasons": list(self.reject_reasons),
            "audit_event": self.audit_event,
            "sanitized_detail": self.sanitized_detail,
            "real_order_allowed": self.real_order_allowed,
            "decided_at": self.decided_at,
            # PR113 safety markers.
            "exchange_live_orders": False if not self.allowed else True,
            "trade_authority": self.sanitized_detail.get("trade_authority", False),
            "ai_trade_authority": False,
        }


def authorize_real_order(decision: Any, context: ExecutionPermissionContext) -> Any:
    """Flip a PR112 dry :class:`LiveRiskDecision`'s ``real_order_allowed`` True.

    ONLY when the decision is approved AND the context is fully armed. PR112's
    own ``evaluate_live_order_risk`` always returns ``real_order_allowed=False``;
    this is the single place that may authorise a real order, and the
    execution gate STILL independently re-checks every flag afterwards.
    Returns the decision unchanged when not eligible.
    """
    if decision is None:
        return decision
    approved = bool(getattr(decision, "approved", False))
    if approved and context.fully_armed:
        try:
            return dataclasses.replace(decision, real_order_allowed=True)
        except Exception:  # pragma: no cover - non-dataclass decisions
            return decision
    return decision


def _resolve_profile(profile_id: CapitalProfileId) -> CapitalProfile | None:
    try:
        return get_profile(profile_id)
    except (KeyError, ValueError):
        return None


def evaluate_execution_permission(
    intent: LiveOrderIntent,
    risk_decision: Any | None,
    context: ExecutionPermissionContext,
    *,
    validation: OrderValidationResult | None = None,
    profile: CapitalProfile | None = None,
) -> ExecutionPermissionDecision:
    """The 15-point execution gate. Deterministic; never sends an order."""
    reasons: list[str] = []

    # --- Mode / operator gates ------------------------------------------
    if context.runtime_mode is not LiveRuntimeMode.LIVE_LIMITED:
        reasons.append(ExecutionRejectReason.RUNTIME_MODE_NOT_LIVE_LIMITED)
    if not context.live_limited_confirmed:
        reasons.append(ExecutionRejectReason.LIVE_LIMITED_NOT_CONFIRMED)
    if not context.exchange_live_orders:
        reasons.append(ExecutionRejectReason.EXCHANGE_LIVE_ORDERS_DISABLED)
    if not context.trade_authority:
        reasons.append(ExecutionRejectReason.TRADE_AUTHORITY_DISABLED)
    if context.ai_trade_authority:
        reasons.append(ExecutionRejectReason.AI_TRADE_AUTHORITY_FORBIDDEN)
    if not context.private_trade_enabled:
        reasons.append(ExecutionRejectReason.PRIVATE_TRADE_DISABLED_BY_CONFIG)
    if context.kill_switch_active:
        reasons.append(ExecutionRejectReason.KILL_SWITCH_ACTIVE)

    # --- Provenance ------------------------------------------------------
    if intent.source is not OrderSource.LIVE:
        reasons.append(ExecutionRejectReason.SOURCE_NOT_LIVE)

    # --- Risk decision ---------------------------------------------------
    if risk_decision is None:
        reasons.append(ExecutionRejectReason.RISK_DECISION_MISSING)
    else:
        if not bool(getattr(risk_decision, "approved", False)):
            reasons.append(ExecutionRejectReason.RISK_DECISION_NOT_APPROVED)
        if not bool(getattr(risk_decision, "real_order_allowed", False)):
            reasons.append(ExecutionRejectReason.REAL_ORDER_NOT_ALLOWED)

    # --- Client order id + plan ------------------------------------------
    if not intent.client_order_id:
        reasons.append(ExecutionRejectReason.MISSING_CLIENT_ORDER_ID)
    if (
        intent.is_opening_order
        and not intent.has_stop_and_exit_plan
        and not intent.emergency_exception
    ):
        reasons.append(ExecutionRejectReason.MISSING_STOP_OR_EXIT_PLAN)

    # --- Capital profile -------------------------------------------------
    prof = profile or _resolve_profile(intent.capital_profile_id)
    if prof is None:
        reasons.append(ExecutionRejectReason.PROFILE_INVALID)
    else:
        if not prof.real_orders_allowed:
            reasons.append(ExecutionRejectReason.PROFILE_REAL_ORDERS_NOT_ALLOWED)
        if (
            context.allowed_profile_ids
            and prof.profile_id not in context.allowed_profile_ids
        ):
            reasons.append(ExecutionRejectReason.PROFILE_NOT_IN_ALLOWED_SET)

        # Notional / leverage within profile (defence-in-depth re-check).
        if (
            prof.max_position_notional_usdt > 0
            and float(intent.notional_usdt) > prof.max_position_notional_usdt
        ):
            reasons.append(ExecutionRejectReason.NOTIONAL_EXCEEDS_PROFILE_MAX)
        max_lev = prof.max_leverage
        if prof.right_tail_boost_allowed:
            max_lev = max(max_lev, prof.right_tail_max_leverage)
        if float(intent.planned_leverage) > max_lev:
            reasons.append(ExecutionRejectReason.LEVERAGE_EXCEEDS_PROFILE_MAX)

        # Account capital cap (>cap requires explicit operator ack).
        if (
            context.account_equity_usdt is not None
            and prof.max_account_capital_usdt > 0
            and float(context.account_equity_usdt) > prof.max_account_capital_usdt
            and not context.profile_operator_acknowledged
        ):
            reasons.append(ExecutionRejectReason.ACCOUNT_CAPITAL_EXCEEDS_CAP_NOT_ACKED)

        # Profile / equity-band mismatch hard block (if configured).
        if (
            context.hard_block_on_profile_mismatch
            and context.account_equity_usdt is not None
        ):
            mismatch = detect_profile_mismatch(
                prof.profile_id, float(context.account_equity_usdt)
            )
            if mismatch.mismatch:
                reasons.append(ExecutionRejectReason.PROFILE_MISMATCH_HARD_BLOCK)

    # --- Exchange validation --------------------------------------------
    if validation is not None and not validation.ok:
        reasons.append(ExecutionRejectReason.ORDER_VALIDATION_FAILED)

    # De-duplicate, preserve order.
    seen: set[str] = set()
    ordered = tuple(r for r in reasons if not (r in seen or seen.add(r)))
    allowed = len(ordered) == 0

    detail = {
        "runtime_mode": context.runtime_mode.value,
        "live_limited_confirmed": context.live_limited_confirmed,
        "exchange_live_orders": context.exchange_live_orders,
        "trade_authority": context.trade_authority,
        "ai_trade_authority": context.ai_trade_authority,
        "private_trade_enabled": context.private_trade_enabled,
        "kill_switch_active": context.kill_switch_active,
        "capital_profile_id": intent.capital_profile_id.value,
        "source": intent.source.value,
        "client_order_id_present": bool(intent.client_order_id),
        "validation_ok": validation.ok if validation is not None else None,
        "validation_reasons": list(validation.reasons) if validation is not None else [],
    }

    return ExecutionPermissionDecision(
        allowed=allowed,
        reject_reason=(None if allowed else ordered[0]),
        reject_reasons=ordered,
        audit_event=(
            EventType.LIVE_ORDER_SUBMIT_REQUESTED.value
            if allowed
            else EventType.LIVE_EXECUTION_BLOCKED.value
        ),
        sanitized_detail=detail,
        real_order_allowed=allowed,
    )


class LiveExecutionGateway:
    """The single real-order entry point (PR113)."""

    def __init__(
        self,
        *,
        adapter: BinanceExecutionAdapter,
        ledger: LiveOrderLedger | None = None,
        isolation_guard: LivePathIsolationGuard | None = None,
        event_repo: Any | None = None,
        clock: Callable[[], int] = now_ms,
    ) -> None:
        self._adapter = adapter
        self._ledger = ledger if ledger is not None else LiveOrderLedger(event_repo=event_repo)
        self._isolation = isolation_guard or LivePathIsolationGuard(event_repo=event_repo)
        self._event_repo = event_repo
        self._clock = clock

    @property
    def ledger(self) -> LiveOrderLedger:
        return self._ledger

    # ------------------------------------------------------------------
    # Permission (delegates to the pure function)
    # ------------------------------------------------------------------
    def evaluate(
        self,
        intent: LiveOrderIntent,
        risk_decision: Any | None,
        context: ExecutionPermissionContext,
        *,
        validation: OrderValidationResult | None = None,
        profile: CapitalProfile | None = None,
    ) -> ExecutionPermissionDecision:
        return evaluate_execution_permission(
            intent, risk_decision, context, validation=validation, profile=profile
        )

    # ------------------------------------------------------------------
    # Isolation + AI guard (raises)
    # ------------------------------------------------------------------
    def _assert_admissible(self, intent: LiveOrderIntent, context: ExecutionPermissionContext) -> None:
        # AI never places an order.
        if context.ai_trade_authority:
            raise AiTradeAuthorityForbidden(
                "execution gateway refused: ai_trade_authority is forbidden. "
                "AI never places an order in AMA-RT."
            )
        # Only OrderSource.LIVE may reach the live path (blind/sim/replay/
        # paper-shadow are isolated). Raises LivePathIsolationViolation.
        side = Direction.LONG if intent.side.value == "BUY" else Direction.SHORT
        iso_intent = IsolationIntent(
            source=intent.source,
            source_module="live.execution_gateway",
            symbol=intent.symbol,
            side=side,
            quantity=float(intent.quantity),
            notional_usdt=float(intent.notional_usdt),
            client_order_id=intent.client_order_id,
            opportunity_id=intent.opportunity_id,
        )
        self._isolation.assert_live_path(iso_intent)

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------
    def submit_order(
        self,
        intent: LiveOrderIntent,
        risk_decision: Any | None,
        context: ExecutionPermissionContext,
        *,
        validation: OrderValidationResult | None = None,
        profile: CapitalProfile | None = None,
        balance_before: float | None = None,
        balance_after: float | None = None,
        funding_usdt: float = 0.0,
    ) -> LiveOrderResult:
        """Submit a real order through the full gate, or return a BLOCKED result."""
        # 1. Hard isolation + AI refusal (raises).
        self._assert_admissible(intent, context)

        # 2. Validation (run against exchangeInfo if not supplied).
        if validation is None and self._adapter.exchange_info is not None:
            validation = self._adapter.validate_order_against_exchange_info(intent)

        # 3. The 15-point gate.
        decision = evaluate_execution_permission(
            intent, risk_decision, context, validation=validation, profile=profile
        )
        self._emit_submit_requested(intent, decision)

        if not decision.allowed:
            return self._blocked(intent, risk_decision, decision, validation)

        # 4. Compose + send (the adapter is the last line of defence).
        request = self._adapter.build_order_request(
            intent,
            validation if validation is not None else _empty_validation(intent),
            real_order_allowed=True,
            dry_run=False,
        )
        result = self._adapter.submit_order(request, real_order_allowed=True)

        # 5. Ledger + Telegram.
        self._ledger.record_order(
            intent, result, request=request, risk_decision_id=intent.risk_decision_id
        )
        self._emit_result_payload(
            intent, risk_decision, result, balance_before, balance_after, funding_usdt
        )
        return result

    def _blocked(
        self,
        intent: LiveOrderIntent,
        risk_decision: Any | None,
        decision: ExecutionPermissionDecision,
        validation: OrderValidationResult | None,
    ) -> LiveOrderResult:
        result = LiveOrderResult(
            status=LiveExecutionStatus.BLOCKED,
            client_order_id=intent.client_order_id or "",
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            reduce_only=intent.reduce_only,
            error_code=decision.reject_reason,
            error_message_sanitized=";".join(decision.reject_reasons),
            is_real_order=False,
            audit_event=EventType.LIVE_EXECUTION_BLOCKED.value,
            created_at=self._clock(),
            updated_at=self._clock(),
        )
        # Record the blocked order row (auditable; is_real_order=False).
        self._ledger.record_order(
            intent, result, risk_decision_id=intent.risk_decision_id
        )
        # Emit the LIVE_EXECUTION_BLOCKED event + Telegram payload.
        self._emit(
            EventType.LIVE_EXECUTION_BLOCKED,
            {
                "client_order_id": intent.client_order_id,
                "symbol": intent.symbol,
                "reject_reason": decision.reject_reason,
                "reject_reasons": list(decision.reject_reasons),
                "sanitized_detail": decision.sanitized_detail,
            },
            symbol=intent.symbol,
        )
        payload = build_execution_telegram_payload(
            PAYLOAD_LIVE_EXECUTION_BLOCKED,
            intent=intent,
            result=result,
            risk_decision=risk_decision,
            reject_reason=decision.reject_reason,
            runtime_mode=intent.runtime_mode,
        )
        self._last_telegram_payload = payload
        return result

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------
    def cancel_order(
        self,
        intent: LiveOrderIntent,
        risk_decision: Any | None,
        context: ExecutionPermissionContext,
        *,
        order_id: str | None = None,
        reduce_or_emergency: bool = False,
    ) -> LiveOrderResult:
        """Cancel an order. Requires the same gates, OR a reduce/emergency exception.

        A reduce-only / emergency cancel may proceed even if some opening
        gates would block a new entry - but it STILL requires the runtime
        to be armed (LIVE_LIMITED + confirmed + exchange_live_orders +
        trade_authority + private trade) and the kill switch logic is
        respected. The exception only waives the opening-specific checks
        (stop/exit plan, notional/leverage sizing).
        """
        self._assert_admissible(intent, context)
        # Build a reduce-only intent view for permission purposes.
        cancel_intent = dataclasses.replace(
            intent, reduce_only=True, emergency_exception=reduce_or_emergency
        )
        decision = evaluate_execution_permission(
            cancel_intent, risk_decision, context
        )
        if not decision.allowed and not reduce_or_emergency:
            return self._blocked(cancel_intent, risk_decision, decision, None)
        # For an emergency/reduce cancel we still require the runtime to be
        # armed; only the opening-specific reasons are waived.
        if reduce_or_emergency and not context.fully_armed:
            return self._blocked(cancel_intent, risk_decision, decision, None)

        result = self._adapter.cancel_order(
            intent.symbol,
            client_order_id=intent.client_order_id,
            order_id=order_id,
            real_order_allowed=True,
        )
        self._ledger.record_cancel(result, intent=intent)
        return result

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _emit_submit_requested(
        self, intent: LiveOrderIntent, decision: ExecutionPermissionDecision
    ) -> None:
        self._emit(
            EventType.LIVE_ORDER_SUBMIT_REQUESTED,
            {
                "client_order_id": intent.client_order_id,
                "symbol": intent.symbol,
                "side": intent.side.value,
                "order_type": intent.order_type.value,
                "permission_allowed": decision.allowed,
                "reject_reasons": list(decision.reject_reasons),
            },
            symbol=intent.symbol,
        )

    def _emit_result_payload(
        self,
        intent: LiveOrderIntent,
        risk_decision: Any | None,
        result: LiveOrderResult,
        balance_before: float | None,
        balance_after: float | None,
        funding_usdt: float,
    ) -> None:
        if result.status is LiveExecutionStatus.FILLED:
            ptype = PAYLOAD_LIVE_ORDER_FILLED
            etype = EventType.LIVE_ORDER_FILLED
        elif result.status is LiveExecutionStatus.PARTIALLY_FILLED:
            ptype = PAYLOAD_LIVE_ORDER_PARTIALLY_FILLED
            etype = EventType.LIVE_ORDER_PARTIALLY_FILLED
        elif result.status is LiveExecutionStatus.REJECTED:
            ptype = PAYLOAD_LIVE_ORDER_REJECTED
            etype = EventType.LIVE_ORDER_REJECTED
        else:
            ptype = PAYLOAD_LIVE_ORDER_SUBMITTED
            etype = EventType.LIVE_ORDER_SUBMITTED
        payload = build_execution_telegram_payload(
            ptype,
            intent=intent,
            result=result,
            risk_decision=risk_decision,
            runtime_mode=intent.runtime_mode,
            balance_before=balance_before,
            balance_after=balance_after,
            funding_usdt=funding_usdt,
        )
        self._last_telegram_payload = payload
        self._emit(
            etype,
            {
                "client_order_id": result.client_order_id,
                "exchange_order_id": result.exchange_order_id,
                "symbol": result.symbol,
                "status": result.status.value,
                "is_real_order": result.is_real_order,
            },
            symbol=result.symbol,
        )

    def _emit(self, event_type: EventType, payload: dict[str, Any], *, symbol: str | None = None) -> None:
        if self._event_repo is None:
            return
        try:
            self._event_repo.append(
                Event(
                    event_type=event_type,
                    source_module=LIVE_EXECUTION_GATEWAY_MODULE,
                    symbol=symbol,
                    payload={
                        **payload,
                        # PR113 safety markers (always pinned on audit).
                        "ai_trade_authority": False,
                        "trade_authority_default": False,
                        "phase_12_forbidden": True,
                    },
                )
            )
        except Exception:  # pragma: no cover - audit must never crash a submit
            pass


def _empty_validation(intent: LiveOrderIntent) -> OrderValidationResult:
    """A permissive validation used only when the gate already allowed but
    no exchangeInfo was available (kept consistent with the intent)."""
    return OrderValidationResult(
        ok=True,
        reasons=(),
        normalized_symbol=intent.symbol,
        normalized_quantity=float(intent.quantity),
        normalized_price=intent.price,
        normalized_stop_price=intent.stop_price,
        effective_notional_usdt=float(intent.notional_usdt),
        symbol_tradable=True,
    )


__all__ = [
    "LIVE_EXECUTION_GATEWAY_MODULE",
    "DEFAULT_ALLOWED_REAL_ORDER_PROFILES",
    "ExecutionRejectReason",
    "ExecutionPermissionContext",
    "ExecutionPermissionDecision",
    "authorize_real_order",
    "evaluate_execution_permission",
    "LiveExecutionGateway",
]
