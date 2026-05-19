"""Risk Engine (Spec §27, Issue #7).

Phase 1 contract (preserved verbatim)
-------------------------------------
The Risk Engine has *final authority*. No module may bypass it.

Phase 7 contract (Issue #7)
---------------------------
Phase 7 turns the Phase 1 / Phase 6 skeleton into a real Risk Engine
by composing:

  - The Phase 1 hard flags (live trading off, right-tail off,
    stop_unconfirmed, unknown_position) - **unchanged**.
  - The Phase 6 manipulation / confirmation hard rules - **unchanged**.
  - The new Phase 7 :func:`no_trade_gate.evaluate_no_trade_gate`
    composer that consumes the Phase 5 (Regime / Universe / Liquidity)
    + Phase 6 (Manipulation / Confirmation) decisions plus the
    exchange-link health, the data-degraded view, and the Account
    Life Tier policy + Circuit Breaker state.

The engine is **additive**. Every Phase 1 + Phase 6 caller that does
not pass the new fields keeps working unchanged - the Phase 7 gate
simply does not fire when the relevant input is missing. Tests pin
this in :file:`tests/unit/test_risk_engine.py` and
:file:`tests/unit/test_risk_engine_phase6.py`.

Phase 7 boundary
----------------
The Risk Engine does NOT trade. It does NOT call any exchange. It
does NOT call any LLM. It does NOT amplify a position. It only
adjudicates a :class:`RiskRequest` and writes one
``RISK_APPROVED`` or ``RISK_REJECTED`` audit event. Phase 7 ALSO
does not implement Issue #8 (Capital Flow), Issue #9 (Execution FSM
+ Reconciliation) or Issue #10 (LLM / Telegram outbound / Replay /
Reflection).

Manipulation M3 protective-exit caveat
--------------------------------------

The M3 branch below blocks **NEW openings** only. Phase 7 **adds**
the explicit ``is_new_open`` flag on :class:`RiskRequest` (default
``True`` for backwards compat) so the M3 / M2 / regime / liquidity
gates can be turned off when the caller is closing / reducing / running
a protective exit. Phase 9 (Execution FSM + Reconciliation) MUST set
``is_new_open=False`` on every kill_all / LOCK_PROFIT / FORCED_EXIT /
DISTRIBUTION_ALERT / stop-loss re-attachment path:

  * Refusing those exits under M3 would trap a live position when
    manipulation is detected and is a P0 incident, not a safety win.
  * Reduce-only closing orders shrink exposure, they never grow it.
  * Reconciliation must be allowed to re-attach stop-loss state under
    M3.

Phase 7 keeps the contract narrow: ``is_new_open=True`` exercises
every defensive gate; ``is_new_open=False`` only exercises the
non-position-opening rejections (live_trading_required, kill_all is
explicitly enabled by Phase 1 anyway).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config.settings import Settings, get_settings
from app.core.enums import (
    AccountLifeTier,
    CircuitBreakerState,
    ExchangeConnectionState,
    ManipulationLevel,
    RiskRejectReason,
    TradeConfirmationLevel,
    TradingMode,
)
from app.core.events import Event, EventType
from app.database.repositories import EventRepository
from app.learning.context import (
    LearningReadyContext,
    attach_learning_ready,
)
from app.learning.identity import OpportunityIdentity
from app.learning.risk_payload import (
    RiskRejectedLearningPayload,
    reject_reasons_as_strings,
)
from app.learning.versions import ConfigVersions
from app.learning.virtual_trade import VirtualTradePlan
from app.liquidity.models import ExitPlan, LiquidityDecision
from app.regime.models import RegimeSnapshot
from app.risk.account_tier import (
    classify_account_tier,
    policy_for,
)
from app.risk.circuit_breaker import (
    ConsecutiveLossCircuitBreaker,
    DailyLossCircuitBreaker,
)
from app.risk.no_trade_gate import (
    NoTradeGateDecision,
    NoTradeGateInput,
    evaluate_no_trade_gate,
)
from app.universe.models import UniverseDecision


@dataclass(frozen=True)
class RiskRequest:
    """Request submitted to the Risk Engine for adjudication.

    Phase 1 hard flags
    ------------------
    - live_trading_required: caller wants a real exchange order. Always
      rejected in Phase 1+.
    - right_tail_amplify: caller wants right-tail amplification. Always
      rejected in Phase 1+.
    - stop_unconfirmed: stop-loss not confirmed.
    - unknown_position: local/exchange position state unknown.

    Phase 6 hooks (Issue #6)
    ------------------------
    - manipulation_level: from the Phase 6 ManipulationDetector.
    - trade_confirmation_level: from the Phase 6 RealTradeConfirmation.
    - attack_intent: caller intends an ATTACK / RIGHT_TAIL_AMPLIFY
      transition. ``right_tail_amplify=True`` always implies attack
      intent.

    Phase 7 hooks (Issue #7)
    ------------------------
    - is_new_open: caller is opening a *new* position. Defaults to
      ``True`` so existing callers retain Phase 1/6 behaviour. Phase 9
      will set this to ``False`` on reduce-only / kill_all /
      protective-exit paths so the M3 / regime / liquidity gates do
      not block a forced exit.
    - regime_snapshot: latest :class:`RegimeSnapshot`.
    - universe_decision: per-symbol :class:`UniverseDecision`.
    - liquidity_decision: latest :class:`LiquidityDecision`.
    - exit_plan: latest :class:`ExitPlan` from
      :meth:`LiquidityFilter.can_exit_position`.
    - is_data_degraded: ``MarketDataBuffer.is_degraded(symbol)``.
    - exchange_connection_state: latest exchange-link state.
    - current_equity / initial_capital: Account Life Tier inputs.
      Phase 7 ships the classifier; Issue #8 will populate these from
      ``capital.db.capital_snapshots``.
    - account_tier_override: optional explicit tier override (tests
      pass this without populating equity numbers).
    - throughput_safety_factor: per-request override of the
      conservative-discount factor applied on top of the Phase 5
      ``can_exit_position`` throughput estimate. ``None`` (default)
      defers to ``RiskEngine.throughput_safety_factor`` (default 0.5).
      A value of 0.5 doubles the exit-time estimate before comparing
      it to ``max_exit_seconds``. Issue #7 hard rule: the engine MUST
      treat ``volume_5m / 300s`` as an UPPER BOUND.
    - max_exit_seconds: ceiling for the discounted re-check. When
      ``None`` the engine derives it from the supplied
      ``LiquidityDecision`` / ``ExitPlan``.
    """

    source_module: str
    action: str
    symbol: str | None = None
    live_trading_required: bool = False
    right_tail_amplify: bool = False
    stop_unconfirmed: bool = False
    unknown_position: bool = False
    # Phase 6 hooks (Issue #6).
    manipulation_level: ManipulationLevel | None = None
    trade_confirmation_level: TradeConfirmationLevel | None = None
    attack_intent: bool = False
    # Phase 7 hooks (Issue #7).
    is_new_open: bool = True
    regime_snapshot: RegimeSnapshot | None = None
    universe_decision: UniverseDecision | None = None
    liquidity_decision: LiquidityDecision | None = None
    exit_plan: ExitPlan | None = None
    is_data_degraded: bool = False
    exchange_connection_state: ExchangeConnectionState | None = None
    current_equity: float | None = None
    initial_capital: float | None = None
    account_tier_override: AccountLifeTier | None = None
    # Phase 7 Issue #7 fix: conservative throughput discount applied
    # on top of LiquidityFilter.can_exit_position. Default mirrors
    # ``RiskEngine.throughput_safety_factor`` (0.5). Per-request
    # override lets tests exercise edge cases without re-instantiating
    # the engine. ``max_exit_seconds`` overrides the ceiling used by
    # the discounted re-check; when ``None`` the engine derives it
    # from the supplied ``LiquidityDecision`` / ``ExitPlan``.
    throughput_safety_factor: float | None = None
    max_exit_seconds: float | None = None
    # Phase 8.5 hooks (Issue #8.5).
    # Optional learning-ready enrichment - all attach to the
    # ``RISK_APPROVED`` / ``RISK_REJECTED`` audit payload under a
    # new ``learning_ready`` sub-block. The legacy audit fields are
    # preserved unchanged.
    opportunity: OpportunityIdentity | None = None
    opportunity_id: str | None = None
    virtual_trade_plan: VirtualTradePlan | None = None
    config_versions: ConfigVersions | None = None
    learning_context: LearningReadyContext | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_attack_intent(self) -> bool:
        """``right_tail_amplify=True`` always implies attack intent."""
        return bool(self.attack_intent or self.right_tail_amplify)


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reasons: list[str]
    request: RiskRequest
    account_tier: AccountLifeTier | None = None
    no_trade_gate_decision: NoTradeGateDecision | None = None

    @property
    def rejected(self) -> bool:
        return not self.approved


class RiskEngine:
    """Phase 7 Risk Engine.

    Composes Phase 1 hard flags + Phase 6 hard rules + the Phase 7
    No-Trade Gate + the Account Life Tier policy + the Circuit
    Breakers. Every reject path returns a typed
    :class:`RiskRejectReason` value (rendered into the audit event as
    its string value, byte-compatible with Phase 1 / Phase 6).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        event_repo: EventRepository | None = None,
        *,
        consecutive_loss_breaker: ConsecutiveLossCircuitBreaker | None = None,
        daily_loss_breaker: DailyLossCircuitBreaker | None = None,
        throughput_safety_factor: float = 0.5,
        capital_flow_engine: object | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._event_repo = event_repo
        # Phase 8: optional reference to the CapitalFlowEngine so the
        # Risk Engine can check ``is_rebase_in_progress`` and auto-populate
        # equity/initial_capital on requests that omit them.
        self._capital_flow_engine = capital_flow_engine
        # Phase 7: circuit breakers are part of the engine instance so
        # tests / Issue #8 can record realised PnL onto the same engine
        # that adjudicates new requests. Defaults match the YAML.
        risk_cfg = self._settings.risk.risk
        self._consecutive_loss_breaker = (
            consecutive_loss_breaker
            or ConsecutiveLossCircuitBreaker(
                threshold=risk_cfg.max_consecutive_losses
            )
        )
        self._daily_loss_breaker = (
            daily_loss_breaker
            or DailyLossCircuitBreaker(
                max_daily_loss_pct=risk_cfg.max_daily_loss_pct,
            )
        )
        # Phase 7 Issue #7 fix: conservative throughput discount.
        # Spec §27 requires Phase 7 to apply this discount on top of
        # the Phase 5 ``can_exit_position`` upper-bound estimate
        # before allowing ATTACK / RIGHT_TAIL_AMPLIFY. Default 0.5.
        if not (0.0 < throughput_safety_factor <= 1.0):
            raise ValueError(
                "throughput_safety_factor must be in (0.0, 1.0]; "
                f"got {throughput_safety_factor}"
            )
        self._throughput_safety_factor = throughput_safety_factor

    # ------------------------------------------------------------------
    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def consecutive_loss_breaker(self) -> ConsecutiveLossCircuitBreaker:
        return self._consecutive_loss_breaker

    @property
    def daily_loss_breaker(self) -> DailyLossCircuitBreaker:
        return self._daily_loss_breaker

    @property
    def throughput_safety_factor(self) -> float:
        """Conservative discount applied on top of Phase 5's
        ``can_exit_position`` throughput estimate before allowing
        ATTACK / RIGHT_TAIL_AMPLIFY (Issue #7 hard rule). Default
        0.5; per-request overrides honoured."""
        return self._throughput_safety_factor

    # ------------------------------------------------------------------
    # Public hooks for Issue #8 (Capital Flow): record realised PnL so
    # the breakers stay current. Phase 7 keeps these simple; Issue #8
    # will replace the in-memory counters with capital.db lookups.
    def record_loss(self, *, loss_amount: float) -> None:
        self._consecutive_loss_breaker.record_loss()
        self._daily_loss_breaker.record_loss(loss_amount=loss_amount)

    def record_win(self, *, profit_amount: float = 0.0) -> None:
        self._consecutive_loss_breaker.record_win()
        self._daily_loss_breaker.record_win(profit_amount=profit_amount)

    def configure_initial_capital(self, *, initial_capital: float) -> None:
        """Set the daily-loss breaker's initial capital so the
        threshold can be applied. Phase 7 keeps this explicit; Issue #8
        will populate it from ``capital.db``."""
        self._daily_loss_breaker.initial_capital = initial_capital

    def set_capital_flow_engine(self, engine: object) -> None:
        """Attach a CapitalFlowEngine instance (Phase 8).

        Once attached, the Risk Engine will:
          - Check ``engine.is_rebase_in_progress`` and reject new opens.
          - Auto-populate current_equity / initial_capital on requests
            that omit them (using the engine's state).
        """
        self._capital_flow_engine = engine

    @property
    def capital_flow_engine(self) -> object | None:
        """The attached CapitalFlowEngine, or None."""
        return self._capital_flow_engine

    # ------------------------------------------------------------------
    def evaluate(self, request: RiskRequest) -> RiskDecision:
        reasons: list[str] = []
        attack_intent = request.effective_attack_intent

        # ----------------------------------------------------------
        # 1. Phase 1 hard rejections - byte-compatible with Phase 1.
        # ----------------------------------------------------------
        if request.live_trading_required and not self._settings.live_trading_enabled:
            reasons.append(RiskRejectReason.LIVE_TRADING_DISABLED.value)
        if request.right_tail_amplify and not self._settings.right_tail_enabled:
            reasons.append(RiskRejectReason.RIGHT_TAIL_DISABLED.value)
        if request.stop_unconfirmed and request.is_new_open:
            reasons.append(RiskRejectReason.STOP_UNCONFIRMED.value)
        if request.unknown_position and request.is_new_open:
            reasons.append(RiskRejectReason.UNKNOWN_POSITION.value)
        if self._settings.trading_mode != TradingMode.PAPER.value and not (
            self._settings.live_trading_enabled
        ):
            reasons.append(RiskRejectReason.TRADING_MODE_INCONSISTENT.value)

        # ----------------------------------------------------------
        # 1b. Phase 8 - Capital Rebase in progress blocks new opens.
        #     Spec §28.4 hard rule: "Rebase 前禁止新开仓".
        # ----------------------------------------------------------
        if request.is_new_open and self._capital_flow_engine is not None:
            if getattr(self._capital_flow_engine, "is_rebase_in_progress", False):
                reasons.append(RiskRejectReason.REBASE_IN_PROGRESS.value)

        # ----------------------------------------------------------
        # 2. Phase 6 hard rules - byte-compatible with Phase 6.
        #    The M3 branch here protects NEW OPENINGS only. Phase 9
        #    must call evaluate(...) with is_new_open=False on every
        #    protective-exit / reduce-only / kill_all path.
        # ----------------------------------------------------------
        if (
            request.manipulation_level is ManipulationLevel.M3
            and request.is_new_open
        ):
            reasons.append(RiskRejectReason.MANIPULATION_M3.value)
        elif (
            request.manipulation_level is ManipulationLevel.M2
            and attack_intent
        ):
            reasons.append(RiskRejectReason.MANIPULATION_M2_ATTACK.value)
        if attack_intent and request.trade_confirmation_level in (
            TradeConfirmationLevel.T0,
            TradeConfirmationLevel.T1,
        ):
            reasons.append(
                RiskRejectReason.TRADE_CONFIRMATION_TOO_LOW_FOR_ATTACK.value
            )

        # ----------------------------------------------------------
        # 3. Phase 7 No-Trade Gate (composes Phase 5 + Phase 6 +
        #    exchange / data / breakers).
        # ----------------------------------------------------------
        gate_input = NoTradeGateInput(
            symbol=request.symbol,
            attack_intent=request.attack_intent,
            right_tail_amplify_intent=request.right_tail_amplify,
            is_new_open=request.is_new_open,
            stop_unconfirmed=request.stop_unconfirmed,
            unknown_position=request.unknown_position,
            is_data_degraded=request.is_data_degraded,
            exchange_connection_state=request.exchange_connection_state,
            regime_snapshot=request.regime_snapshot,
            universe_decision=request.universe_decision,
            liquidity_decision=request.liquidity_decision,
            exit_plan=request.exit_plan,
            manipulation_level=request.manipulation_level,
            trade_confirmation_level=request.trade_confirmation_level,
            daily_loss_breaker_state=self._daily_loss_breaker.state,
            consecutive_loss_breaker_state=self._consecutive_loss_breaker.state,
            throughput_safety_factor=(
                request.throughput_safety_factor
                if request.throughput_safety_factor is not None
                else self._throughput_safety_factor
            ),
            max_exit_seconds=request.max_exit_seconds,
        )
        gate_decision = evaluate_no_trade_gate(gate_input)
        for reason in gate_decision.reasons:
            if reason.value not in reasons:
                reasons.append(reason.value)

        # ----------------------------------------------------------
        # 4. Account Life Tier policy.
        # ----------------------------------------------------------
        tier = self._resolve_tier(request)
        if tier is not None and request.is_new_open:
            policy = policy_for(tier)
            if policy.halt_only:
                reasons.append(RiskRejectReason.ACCOUNT_TIER_HALT.value)
            if not policy.allow_new_open:
                reasons.append(RiskRejectReason.ACCOUNT_TIER_NO_NEW_OPEN.value)
            if policy.paper_only and self._settings.trading_mode != TradingMode.PAPER.value:
                reasons.append(RiskRejectReason.ACCOUNT_TIER_PAPER_ONLY.value)
            if attack_intent and request.right_tail_amplify and not policy.allow_right_tail_amplify:
                reasons.append(RiskRejectReason.ACCOUNT_TIER_NO_RIGHT_TAIL.value)

        # ----------------------------------------------------------
        # 5. Right-tail amplification must come from floating profit.
        #    Phase 7 ships this as a defensive check on the engine
        #    surface even though Phase 1 already locks
        #    right_tail_enabled to False. The check fires only when
        #    the caller has supplied an unrealized_pnl <= 0.
        # ----------------------------------------------------------
        if request.right_tail_amplify and request.extra.get(
            "unrealized_pnl", None
        ) is not None and request.extra.get("unrealized_pnl", 0.0) <= 0:
            reasons.append(
                RiskRejectReason.RIGHT_TAIL_FROM_PRINCIPAL_FORBIDDEN.value
            )

        # Deduplicate while preserving order.
        seen: set[str] = set()
        ordered: list[str] = []
        for r in reasons:
            if r not in seen:
                seen.add(r)
                ordered.append(r)

        approved = not ordered
        if approved:
            ordered = ["paper_only_skeleton_approval"]

        decision = RiskDecision(
            approved=approved,
            reasons=ordered,
            request=request,
            account_tier=tier,
            no_trade_gate_decision=gate_decision,
        )
        self._record(decision)
        return decision

    # ------------------------------------------------------------------
    def _resolve_tier(self, request: RiskRequest) -> AccountLifeTier | None:
        if request.account_tier_override is not None:
            return request.account_tier_override
        # Phase 8: auto-populate from CapitalFlowEngine if available.
        current_equity = request.current_equity
        initial_capital = request.initial_capital
        if self._capital_flow_engine is not None:
            if current_equity is None:
                current_equity = getattr(
                    self._capital_flow_engine, "trading_capital", None
                )
            if initial_capital is None:
                initial_capital = getattr(
                    self._capital_flow_engine, "initial_capital", None
                )
        if current_equity is None or initial_capital is None:
            return None
        return classify_account_tier(
            current_equity=current_equity,
            initial_capital=initial_capital,
        )

    # ------------------------------------------------------------------
    def _record(self, decision: RiskDecision) -> None:
        if self._event_repo is None:
            return
        ev_type = (
            EventType.RISK_APPROVED if decision.approved else EventType.RISK_REJECTED
        )
        gate = decision.no_trade_gate_decision
        base_payload: dict[str, Any] = {
                    "action": decision.request.action,
                    "source_module": decision.request.source_module,
                    "reasons": list(decision.reasons),
                    "live_trading_required": decision.request.live_trading_required,
                    "right_tail_amplify": decision.request.right_tail_amplify,
                    "stop_unconfirmed": decision.request.stop_unconfirmed,
                    "unknown_position": decision.request.unknown_position,
                    "attack_intent": decision.request.effective_attack_intent,
                    "is_new_open": decision.request.is_new_open,
                    "manipulation_level": (
                        decision.request.manipulation_level.value
                        if decision.request.manipulation_level is not None
                        else None
                    ),
                    "trade_confirmation_level": (
                        decision.request.trade_confirmation_level.value
                        if decision.request.trade_confirmation_level is not None
                        else None
                    ),
                    # Phase 7 audit additions.
                    "account_tier": (
                        decision.account_tier.value
                        if decision.account_tier is not None
                        else None
                    ),
                    "no_trade_gate_reasons": (
                        [r.value for r in gate.reasons] if gate is not None else []
                    ),
                    "no_trade_gate_notes": (
                        list(gate.notes) if gate is not None else []
                    ),
                    "daily_loss_breaker_state": self._daily_loss_breaker.state.value,
                    "consecutive_loss_breaker_state": self._consecutive_loss_breaker.state.value,
                    "regime": (
                        decision.request.regime_snapshot.market_regime.value
                        if decision.request.regime_snapshot is not None
                        else None
                    ),
                    "risk_permission": (
                        decision.request.regime_snapshot.risk_permission.value
                        if decision.request.regime_snapshot is not None
                        else None
                    ),
                    "is_data_degraded": decision.request.is_data_degraded,
                    "exchange_connection_state": (
                        decision.request.exchange_connection_state.value
                        if decision.request.exchange_connection_state is not None
                        else None
                    ),
                    "throughput_safety_factor": (
                        decision.request.throughput_safety_factor
                        if decision.request.throughput_safety_factor is not None
                        else self._throughput_safety_factor
                    ),
                    "max_exit_seconds": decision.request.max_exit_seconds,
        }

        # Phase 8.5 - attach the learning-ready block when the caller
        # supplied one. The merge is mutation-free: the existing keys
        # above are preserved verbatim, and a new ``learning_ready``
        # sub-key is appended. Issue contract: every RISK_REJECTED
        # event must be ABLE to carry opportunity_id, reject_reasons,
        # account_life_tier, regime, universe_eligible, liquidity_state,
        # trade_confirmation_level, manipulation_level,
        # capital_state_version, risk_config_version. We populate as
        # many fields as we can derive from the request, then merge
        # the caller-supplied ``learning_context`` on top so explicit
        # values always win.
        learning_ctx = self._build_learning_context(decision)
        full_payload = attach_learning_ready(base_payload, learning_ctx)

        self._event_repo.append(
            Event(
                event_type=ev_type,
                source_module="risk_engine",
                symbol=decision.request.symbol,
                payload=full_payload,
            )
        )

    # ------------------------------------------------------------------
    def _build_learning_context(
        self, decision: RiskDecision
    ) -> LearningReadyContext | None:
        """Compose the Phase 8.5 LearningReadyContext for an audit event.

        - If the request supplies an explicit ``learning_context``,
          we honour it (caller has already populated risk_decision /
          opportunity / virtual_trade_plan / config_versions).
        - Otherwise we synthesise a minimal context from the
          request: opportunity (if opportunity / opportunity_id is
          set), risk_decision, virtual_trade_plan, config_versions.
          A request that supplies none of these returns ``None`` so
          the legacy payload shape is preserved bit-for-bit.
        """
        request = decision.request
        ctx = request.learning_context

        # Build the typed RiskRejectedLearningPayload from the request +
        # the resolved decision.
        opp_id = request.opportunity_id
        if opp_id is None and request.opportunity is not None:
            opp_id = request.opportunity.opportunity_id

        risk_decision_payload = RiskRejectedLearningPayload(
            opportunity_id=opp_id,
            reject_reasons=reject_reasons_as_strings(decision.reasons),
            account_life_tier=decision.account_tier,
            regime=(
                request.regime_snapshot.market_regime
                if request.regime_snapshot is not None
                else None
            ),
            universe_eligible=(
                request.universe_decision.eligible
                if request.universe_decision is not None
                else None
            ),
            liquidity_state=_summarise_liquidity_state(request.liquidity_decision),
            trade_confirmation_level=request.trade_confirmation_level,
            manipulation_level=request.manipulation_level,
            capital_state_version=(
                request.config_versions.capital_state_version
                if request.config_versions is not None
                else (ctx.config_versions.capital_state_version
                      if ctx is not None and ctx.config_versions is not None
                      else None)
            ),
            risk_config_version=(
                request.config_versions.risk_config_version
                if request.config_versions is not None
                else (ctx.config_versions.risk_config_version
                      if ctx is not None and ctx.config_versions is not None
                      else None)
            ),
            daily_loss_breaker_state=self._daily_loss_breaker.state.value,
            consecutive_loss_breaker_state=self._consecutive_loss_breaker.state.value,
            is_new_open=request.is_new_open,
            attack_intent=request.effective_attack_intent,
        )

        if ctx is None:
            # No explicit context: emit one only when at least one of
            # the Phase 8.5 fields was set, so legacy callers keep
            # producing payloads without ``learning_ready``.
            has_phase_8_5_signal = (
                request.opportunity is not None
                or request.opportunity_id is not None
                or request.virtual_trade_plan is not None
                or request.config_versions is not None
            )
            if not has_phase_8_5_signal:
                return None
            return LearningReadyContext(
                opportunity=request.opportunity,
                virtual_trade_plan=request.virtual_trade_plan,
                config_versions=request.config_versions,
                risk_decision=risk_decision_payload,
                source_phase="risk_engine",
            )

        # Caller supplied an explicit context. Merge our derived
        # risk_decision in if the caller did not set one. We never
        # overwrite a caller-supplied risk_decision so the audit trail
        # honours the operator's intent.
        return LearningReadyContext(
            opportunity=ctx.opportunity or request.opportunity,
            signal_snapshot=ctx.signal_snapshot,
            virtual_trade_plan=(
                ctx.virtual_trade_plan or request.virtual_trade_plan
            ),
            config_versions=ctx.config_versions or request.config_versions,
            risk_decision=ctx.risk_decision or risk_decision_payload,
            source_phase=ctx.source_phase or "risk_engine",
            extra=dict(ctx.extra),
        )


# Re-export common breaker symbol so callers can keep the import
# narrow. ``RiskEngine`` plus the breakers are the public Phase 7
# surface from this module.
__all__ = [
    "RiskDecision",
    "RiskEngine",
    "RiskRequest",
    "ConsecutiveLossCircuitBreaker",
    "DailyLossCircuitBreaker",
    "CircuitBreakerState",
]


def _summarise_liquidity_state(decision: LiquidityDecision | None) -> str | None:
    """Render a short string label for the Phase 8.5 ``liquidity_state``
    field. Returns ``None`` when no LiquidityDecision was supplied so
    the audit payload distinguishes "passed" from "unknown".

    Phase 8.5 stays deliberately conservative: we do NOT expose the
    Phase 5 reject-reason enum values verbatim because Issue #10
    Reflection wants a single short label per decision; the full
    reason list already lives on the LIQUIDITY_CHECKED event payload.
    """
    if decision is None:
        return None
    if decision.passed:
        return "passed"
    if decision.reject_reasons:
        # Use the FIRST reject reason as the canonical label so the
        # field stays short and stable for grouping queries.
        first = decision.reject_reasons[0]
        return getattr(first, "value", str(first))
    return "rejected"
