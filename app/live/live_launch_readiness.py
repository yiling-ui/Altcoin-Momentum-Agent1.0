"""Live launch readiness checker (PR116 - 10U LIVE_LIMITED Launch Pack v0).

A SINGLE end-to-end readiness check that validates everything the brief
lists before a 10U (or any funded-profile) LIVE_LIMITED launch:

  * Binance public / private-read / private-trade configuration,
  * Telegram outbound + allowed chat id,
  * DeepSeek status (OK or explicitly optional),
  * the active capital profile + usable-capital cap,
  * exchangeInfo / order precision + a DRY tiny-order validation,
  * the kill switch, live-path + blind/sim isolation,
  * funding / commission accounting availability,
  * the operator / system flags (exchange_live_orders / trade_authority /
    ai_trade_authority / live_limited_confirmed).

The check NEVER sends a real order. ``no_real_order_sent`` is always True;
the dry-order step only normalises + validates against exchangeInfo and
runs the deterministic execution-permission gate (which it never lets
submit).

It produces a :class:`app.live.live_launch_models.LaunchReadinessReport`
with an overall ``PASS`` / ``WARN`` / ``FAIL`` and the two GO decisions
(``go_for_live_shadow`` / ``go_for_live_limited``).

IO: the pure :meth:`LiveLaunchReadinessChecker.check` consumes injected
evidence (a Binance client / adapter / account snapshot / exchangeInfo)
so every unit test runs with fakes and no network. :meth:`run` is the IO
orchestrator the CLI uses; it degrades gracefully (a network failure is a
``FAIL`` item, never a crash, and never a real order).
"""

from __future__ import annotations

from typing import Any, Callable

from app.core.clock import now_ms
from app.core.enums import Direction, LiveRuntimeMode, OrderSource
from app.live.api_config import LiveApiConfig
from app.live.binance_execution_adapter import BinanceExecutionAdapter
from app.live.binance_models import (
    BinanceAccountSnapshot,
    BinanceExchangeInfoSnapshot,
    BinanceIncomeEvent,
)
from app.live.capital_profile import CapitalProfileId, get_profile
from app.live.capital_state import LiveCapitalState
from app.live.execution_gateway import (
    ExecutionPermissionContext,
    evaluate_execution_permission,
)
from app.live.execution_models import (
    LiveOrderIntent,
    OrderSide,
    OrderType,
    generate_client_order_id,
)
from app.live.health import run_unified_health_check
from app.live.live_launch_models import (
    LaunchCheckItem,
    LaunchReadinessReport,
)
from app.live.live_runtime import LiveRuntime
from app.live.path_isolation import (
    LiveOrderIntent as IsolationIntent,
    LivePathIsolationGuard,
    classify_source_module,
)
from app.live.pnl_accounting import build_live_pnl_summary
from app.live.status import HealthStatus, worst_of
from app.live.telegram_state import LiveOperatorStateStore

LIVE_LAUNCH_READINESS_MODULE = "live.live_launch_readiness"

# A conservative tiny notional used for the DRY order validation. It is
# never submitted; it only proves exchangeInfo precision + minNotional.
DRY_ORDER_NOTIONAL_USDT = 5.0


def _status(ok: bool, *, warn_if_false: bool = False) -> HealthStatus:
    if ok:
        return HealthStatus.PASS
    return HealthStatus.WARN if warn_if_false else HealthStatus.FAIL


class LiveLaunchReadinessChecker:
    """Builds the end-to-end :class:`LaunchReadinessReport` (PR116)."""

    def __init__(
        self,
        config: LiveApiConfig,
        *,
        runtime: LiveRuntime | None = None,
        state_store: LiveOperatorStateStore | None = None,
        event_repo: Any | None = None,
        clock: Callable[[], int] = now_ms,
    ) -> None:
        self._config = config
        self._store = state_store or LiveOperatorStateStore()
        self._runtime = runtime or LiveRuntime(
            config, state_store=self._store, event_repo=event_repo
        )
        self._event_repo = event_repo
        self._clock = clock

    # ------------------------------------------------------------------
    # Pure core (consumes injected evidence; no network)
    # ------------------------------------------------------------------
    def check(
        self,
        *,
        pre_live_limited: bool = False,
        require_real_keys: bool = False,
        check_binance: bool = True,
        check_telegram: bool = True,
        check_deepseek: bool = False,
        binance_client: Any | None = None,
        adapter: BinanceExecutionAdapter | None = None,
        account_snapshot: BinanceAccountSnapshot | None = None,
        exchange_info: BinanceExchangeInfoSnapshot | None = None,
        income_events: list[BinanceIncomeEvent] | None = None,
        execution_flags: ExecutionPermissionContext | None = None,
        kill_switch_ready: bool | None = None,
        kill_switch_active: bool | None = None,
        kill_switch_armed: bool | None = None,
        live_limited_confirmed: bool | None = None,
        dry_order_symbol: str | None = None,
        environ: dict[str, str] | None = None,
    ) -> LaunchReadinessReport:
        cfg = self._config
        items: list[LaunchCheckItem] = []

        # -- Operator / system flags (env-driven) ------------------------
        flags = execution_flags or ExecutionPermissionContext.from_config(
            cfg, environ=environ
        )
        exchange_live_orders = bool(flags.exchange_live_orders)
        trade_authority = bool(flags.trade_authority)
        ai_trade_authority = bool(flags.ai_trade_authority)

        runtime_mode = self._runtime.runtime_mode()
        active_profile_id = self._runtime.active_capital_profile_id()
        active_profile = get_profile(active_profile_id)

        if kill_switch_active is None:
            # Backward-compat: the deprecated ``kill_switch_armed`` arg maps
            # onto the ACTIVE (emergency-halt) state.
            kill_switch_active = (
                bool(kill_switch_armed)
                if kill_switch_armed is not None
                else self._runtime.kill_switch_active()
            )
        if kill_switch_ready is None:
            kill_switch_ready = self._runtime.kill_switch_ready()
        if live_limited_confirmed is None:
            live_limited_confirmed = self._runtime.live_limited_confirmed()

        # -- Health check (Binance / Telegram / DeepSeek) ----------------
        report = run_unified_health_check(
            cfg,
            check_binance=check_binance,
            check_telegram=check_telegram,
            check_deepseek=check_deepseek,
            binance_client=binance_client,
            event_repo=self._event_repo,
        )

        binance_public_ok = (
            check_binance
            and report.binance is not None
            and bool(report.binance.public_market_ok)
        )
        binance_private_read_ok = (
            report.binance_private_read_status is HealthStatus.PASS
        )
        binance_private_trade_configured = cfg.binance.has_credentials
        binance_private_trade_enabled = bool(cfg.binance.enable_private_trade)

        # -- Secrets / placeholder detection -----------------------------
        placeholder_secret = (
            cfg.binance.api_key.is_placeholder
            or cfg.binance.api_secret.is_placeholder
            or (cfg.telegram.bot_token.is_present and cfg.telegram.bot_token.is_placeholder)
            or (cfg.deepseek.api_key.is_present and cfg.deepseek.api_key.is_placeholder)
        )
        missing_real_keys = not cfg.binance.has_credentials

        # -- Telegram (config-derived; the live getMe send-test is a
        #    separate operator step, so the readiness check stays
        #    network-free + deterministic) ----------------------------
        telegram_outbound_ok = bool(
            cfg.telegram.outbound_enabled
            and cfg.telegram.has_token
            and not cfg.telegram.bot_token.is_placeholder
        )
        telegram_allowed_chat_ok = len(cfg.telegram.allowed_chat_ids) > 0

        # -- DeepSeek (intelligence only; never a hard blocker) ----------
        deepseek_ok_or_optional = (not cfg.deepseek.enabled) or (
            report.deepseek_status is not HealthStatus.FAIL
        )

        # -- Capital state / usable-capital cap --------------------------
        account_equity: float | None = None
        usable_capital: float | None = None
        capital_cap_enforced = False
        capital_profile_mismatch = False
        if account_snapshot is not None:
            capital_state = LiveCapitalState.from_account_snapshot(
                account_snapshot,
                runtime_mode=runtime_mode,
                capital_profile_id=active_profile_id,
            )
            profile_state = self._runtime.evaluate_capital_profile(capital_state)
            account_equity = profile_state.account_equity_usdt
            usable_capital = profile_state.usable_capital_usdt
            cap = active_profile.max_account_capital_usdt
            capital_cap_enforced = cap > 0 and usable_capital <= cap + 1e-9
            capital_profile_mismatch = profile_state.mismatch.mismatch

        l1_10u_cap_enforced = (
            active_profile_id is CapitalProfileId.L1_10U_PROBE
            and usable_capital is not None
            and usable_capital <= 10.0 + 1e-9
        ) or (active_profile_id is CapitalProfileId.L1_10U_PROBE and account_equity is None)

        # -- exchangeInfo / order precision + DRY order validation -------
        exinfo = exchange_info
        if exinfo is None and adapter is not None:
            exinfo = adapter.exchange_info
        order_precision_ok = exinfo is not None and exinfo.symbol_count > 0
        dry_order_validation_ok = False
        execution_gateway_dry_run_ok = False
        if exinfo is not None and exinfo.symbol_count > 0:
            dry_adapter = adapter or BinanceExecutionAdapter(
                cfg.binance, runtime_mode=runtime_mode, exchange_info=exinfo
            )
            if dry_adapter.exchange_info is None:
                dry_adapter.set_exchange_info(exinfo)
            symbol = dry_order_symbol or _first_tradable_symbol(exinfo)
            if symbol is not None:
                intent = _build_dry_order_intent(
                    symbol, exinfo, runtime_mode, active_profile_id
                )
                validation = dry_adapter.validate_order_against_exchange_info(intent)
                dry_order_validation_ok = bool(validation.ok)
                # Run the deterministic gate (never submits). The dry-run
                # is "ok" when the gate ran + the order is exchange-valid.
                decision = evaluate_execution_permission(
                    intent, None, flags, validation=validation, profile=active_profile
                )
                execution_gateway_dry_run_ok = bool(validation.ok) and (
                    decision is not None
                )

        # -- Isolation ---------------------------------------------------
        live_path_isolation_ok = _check_live_path_isolation()
        blind_sim_isolation_ok = _check_blind_sim_isolation()

        # -- Funding / commission accounting -----------------------------
        funding_accounting_ok = True
        try:
            build_live_pnl_summary(
                income_events or [],
                account_equity_usdt=(account_equity or 0.0),
            )
        except Exception:  # pragma: no cover - accounting is deterministic
            funding_accounting_ok = False

        # ----------------------------------------------------------------
        # Build the per-check items.
        #
        # Every gate REQUIRED for a LIVE_LIMITED GO is a blocker
        # (``is_blocker=True``) regardless of the ``pre_live_limited``
        # flag, so ``go_for_live_limited`` always evaluates the full gate
        # set. The flag only controls SEVERITY: a failing live-limited
        # gate is a WARN in a plain check (Phase A returns WARN, not
        # FAIL) and a FAIL in a ``--pre-live-limited`` check.
        # ----------------------------------------------------------------
        def _ll(
            check_id: str,
            ok: bool,
            detail: str,
            value: Any,
            *,
            blocks_shadow: bool = False,
            hard_fail: bool = False,
        ) -> LaunchCheckItem:
            if ok:
                status = HealthStatus.PASS
            elif hard_fail:
                status = HealthStatus.FAIL
            else:
                status = HealthStatus.FAIL if pre_live_limited else HealthStatus.WARN
            return LaunchCheckItem(
                check_id, status, detail=detail, value=value,
                is_blocker=True, blocks_shadow=blocks_shadow,
            )

        # Binance public is required for BOTH shadow and live_limited.
        items.append(
            LaunchCheckItem(
                "binance_public_ok",
                _status(binance_public_ok) if check_binance else HealthStatus.SKIPPED,
                detail="Binance public market API reachable.",
                value=binance_public_ok,
                is_blocker=True,
                blocks_shadow=True,
            )
        )
        items.append(
            _ll(
                "binance_private_read_ok",
                binance_private_read_ok,
                "Binance private read (account/positions/income).",
                binance_private_read_ok,
                hard_fail=require_real_keys,
            )
        )
        items.append(
            _ll(
                "binance_private_trade_configured",
                binance_private_trade_configured,
                "Binance API credentials present.",
                binance_private_trade_configured,
                hard_fail=require_real_keys,
            )
        )
        items.append(
            _ll(
                "binance_private_trade_enabled",
                binance_private_trade_enabled,
                "enable_private_trade (operator intent).",
                binance_private_trade_enabled,
            )
        )
        items.append(
            _ll(
                "telegram_outbound_ok",
                telegram_outbound_ok,
                "Telegram outbound enabled + token present.",
                telegram_outbound_ok,
            )
        )
        items.append(
            _ll(
                "telegram_allowed_chat_ok",
                telegram_allowed_chat_ok,
                "Telegram allowed chat id configured.",
                telegram_allowed_chat_ok,
            )
        )
        # DeepSeek is intelligence-only: optional, never a blocker.
        items.append(
            LaunchCheckItem(
                "deepseek_ok_or_optional",
                HealthStatus.PASS if deepseek_ok_or_optional else HealthStatus.WARN,
                detail="DeepSeek OK or explicitly optional (intelligence-only).",
                value=deepseek_ok_or_optional,
                is_blocker=False,
            )
        )
        profile_ok = (
            active_profile.real_orders_allowed
            and active_profile_id is not CapitalProfileId.L0_SHADOW
        )
        items.append(
            _ll(
                "capital_profile_funded",
                profile_ok,
                f"Active profile {active_profile_id.value} allows real orders.",
                active_profile_id.value,
            )
        )
        items.append(
            _ll(
                "account_equity_available",
                account_equity is not None,
                "Account equity available (private read).",
                account_equity,
            )
        )
        items.append(
            _ll(
                "usable_capital_capped",
                capital_cap_enforced or account_equity is None,
                "Usable capital capped at the active profile cap.",
                usable_capital,
            )
        )
        items.append(
            _ll(
                "capital_profile_no_unack_mismatch",
                not capital_profile_mismatch,
                "No unacknowledged capital-profile/equity mismatch.",
                not capital_profile_mismatch,
            )
        )
        # Kill switch is split into two distinct GO gates (PR116 hotfix):
        #   * kill_switch_ready      - subsystem available (REQUIRED true).
        #   * kill_switch_not_active - no emergency halt engaged (REQUIRED
        #                              true; an ACTIVE kill switch blocks
        #                              every new entry, so it can never be a
        #                              GO requirement).
        items.append(
            _ll(
                "kill_switch_ready",
                bool(kill_switch_ready),
                "Kill switch subsystem ready/available (state readable, "
                "operator can trigger it).",
                bool(kill_switch_ready),
            )
        )
        items.append(
            _ll(
                "kill_switch_not_active",
                not bool(kill_switch_active),
                "Kill switch is NOT active (no emergency halt blocking new "
                "entries).",
                not bool(kill_switch_active),
            )
        )
        items.append(
            _ll(
                "order_precision_ok",
                order_precision_ok,
                "exchangeInfo filters / order precision loaded.",
                order_precision_ok,
            )
        )
        items.append(
            _ll(
                "dry_order_validation_ok",
                dry_order_validation_ok,
                "Tiny DRY order validates against exchangeInfo (never sent).",
                dry_order_validation_ok,
            )
        )
        items.append(
            LaunchCheckItem(
                "live_path_isolation_ok",
                _status(live_path_isolation_ok),
                detail="Live path isolation active (only LIVE source admissible).",
                value=live_path_isolation_ok,
                is_blocker=True,
                blocks_shadow=True,
            )
        )
        items.append(
            LaunchCheckItem(
                "blind_sim_isolation_ok",
                _status(blind_sim_isolation_ok),
                detail="Blind/replay/sim source isolation active.",
                value=blind_sim_isolation_ok,
                is_blocker=True,
                blocks_shadow=True,
            )
        )
        items.append(
            _ll(
                "funding_accounting_ok",
                funding_accounting_ok,
                "Funding/commission accounting available.",
                funding_accounting_ok,
                hard_fail=not funding_accounting_ok,
            )
        )
        # AI trade authority MUST be False (hard, both modes).
        items.append(
            LaunchCheckItem(
                "ai_trade_authority_disabled",
                HealthStatus.FAIL if ai_trade_authority else HealthStatus.PASS,
                detail="AI has NO trade authority.",
                value=not ai_trade_authority,
                is_blocker=True,
                blocks_shadow=True,
            )
        )
        items.append(
            _ll(
                "exchange_live_orders_enabled",
                exchange_live_orders,
                "exchange_live_orders explicitly enabled by operator.",
                exchange_live_orders,
            )
        )
        items.append(
            _ll(
                "trade_authority_enabled",
                trade_authority,
                "trade_authority explicitly enabled by operator.",
                trade_authority,
            )
        )
        items.append(
            _ll(
                "live_limited_confirmed",
                bool(live_limited_confirmed),
                "LIVE_LIMITED operator confirmation complete.",
                bool(live_limited_confirmed),
            )
        )
        # Placeholder secret is a hard config error (fails clearly).
        items.append(
            LaunchCheckItem(
                "no_placeholder_secret",
                HealthStatus.FAIL if placeholder_secret else HealthStatus.PASS,
                detail="No placeholder/dummy secret configured.",
                value=not placeholder_secret,
                is_blocker=True,
            )
        )
        # Missing real keys: WARN by default (Phase A), FAIL if required.
        if missing_real_keys:
            items.append(
                LaunchCheckItem(
                    "real_keys_present",
                    HealthStatus.FAIL if require_real_keys else HealthStatus.WARN,
                    detail="Real Binance API keys present.",
                    value=False,
                    is_blocker=require_real_keys,
                )
            )

        # ----------------------------------------------------------------
        # Roll-ups.
        # ----------------------------------------------------------------
        overall_status = worst_of([i.status for i in items])

        blockers = tuple(
            i.check_id
            for i in items
            if i.is_blocker and i.status is not HealthStatus.PASS
        )
        warnings = tuple(
            i.check_id for i in items if i.status is HealthStatus.WARN
        )

        go_for_live_shadow = binance_public_ok and all(
            i.status is HealthStatus.PASS for i in items if i.blocks_shadow
        )
        go_for_live_limited = all(
            i.status is HealthStatus.PASS for i in items if i.is_blocker
        )

        return LaunchReadinessReport(
            overall_status=overall_status,
            go_for_live_shadow=go_for_live_shadow,
            go_for_live_limited=go_for_live_limited,
            blockers=blockers,
            warnings=warnings,
            items=tuple(items),
            runtime_mode=runtime_mode.value,
            capital_profile_id=active_profile_id.value,
            account_equity_usdt=account_equity,
            usable_live_capital_usdt=usable_capital,
            profile_max_account_capital_usdt=active_profile.max_account_capital_usdt,
            capital_cap_enforced=capital_cap_enforced,
            capital_profile_mismatch=capital_profile_mismatch,
            l1_10u_cap_enforced=bool(l1_10u_cap_enforced),
            binance_public_ok=binance_public_ok,
            binance_private_read_ok=binance_private_read_ok,
            binance_private_trade_configured=binance_private_trade_configured,
            binance_private_trade_enabled=binance_private_trade_enabled,
            telegram_outbound_ok=telegram_outbound_ok,
            telegram_allowed_chat_ok=telegram_allowed_chat_ok,
            deepseek_ok_or_optional=deepseek_ok_or_optional,
            kill_switch_ready=bool(kill_switch_ready),
            kill_switch_active=bool(kill_switch_active),
            kill_switch_armed=bool(kill_switch_active),
            live_limited_confirmed=bool(live_limited_confirmed),
            exchange_live_orders=exchange_live_orders,
            trade_authority=trade_authority,
            ai_trade_authority=ai_trade_authority,
            live_path_isolation_ok=live_path_isolation_ok,
            blind_sim_isolation_ok=blind_sim_isolation_ok,
            funding_accounting_ok=funding_accounting_ok,
            order_precision_ok=order_precision_ok,
            dry_order_validation_ok=dry_order_validation_ok,
            execution_gateway_dry_run_ok=execution_gateway_dry_run_ok,
            no_real_order_sent=True,
            requested_pre_live_limited=pre_live_limited,
            require_real_keys=require_real_keys,
        )

    # ------------------------------------------------------------------
    # IO orchestrator (used by the CLI). Degrades gracefully; no order.
    # ------------------------------------------------------------------
    def run(
        self,
        *,
        pre_live_limited: bool = False,
        require_real_keys: bool = False,
        check_binance: bool = True,
        check_telegram: bool = True,
        check_deepseek: bool = False,
        dry_order_symbol: str | None = None,
    ) -> LaunchReadinessReport:
        """Gather evidence (Binance read / exchangeInfo) then run :meth:`check`.

        Every network call is best-effort: a failure becomes a non-PASS
        item, never a crash, and never a real order.
        """
        from app.live.binance_client import BinanceLiveClient

        cfg = self._config
        binance_client: BinanceLiveClient | None = None
        adapter: BinanceExecutionAdapter | None = None
        account_snapshot: BinanceAccountSnapshot | None = None
        exchange_info: BinanceExchangeInfoSnapshot | None = None
        income_events: list[BinanceIncomeEvent] | None = None

        if check_binance:
            binance_client = BinanceLiveClient(
                cfg.binance,
                runtime_mode=self._runtime.runtime_mode(),
                event_repo=self._event_repo,
            )
            try:
                exchange_info = binance_client.get_exchange_info()
            except Exception:
                exchange_info = None
            if (
                cfg.binance.enable_private_read
                and cfg.binance.has_credentials
                and not (
                    cfg.binance.api_key.is_placeholder
                    or cfg.binance.api_secret.is_placeholder
                )
            ):
                try:
                    account_snapshot = binance_client.get_account()
                except Exception:
                    account_snapshot = None
                try:
                    income_events = binance_client.get_income_history(limit=50)
                except Exception:
                    income_events = None
            if exchange_info is not None:
                adapter = BinanceExecutionAdapter(
                    cfg.binance,
                    runtime_mode=self._runtime.runtime_mode(),
                    exchange_info=exchange_info,
                    event_repo=self._event_repo,
                )

        return self.check(
            pre_live_limited=pre_live_limited,
            require_real_keys=require_real_keys,
            check_binance=check_binance,
            check_telegram=check_telegram,
            check_deepseek=check_deepseek,
            binance_client=binance_client,
            adapter=adapter,
            account_snapshot=account_snapshot,
            exchange_info=exchange_info,
            income_events=income_events,
            dry_order_symbol=dry_order_symbol,
        )


# ---------------------------------------------------------------------------
# Isolation self-checks (deterministic; no IO)
# ---------------------------------------------------------------------------
def _check_live_path_isolation() -> bool:
    """A LIVE intent is admissible; every non-LIVE source is blocked."""
    guard = LivePathIsolationGuard()
    live = IsolationIntent(
        source=OrderSource.LIVE,
        source_module="live.live_launch_readiness",
        symbol="BTCUSDT",
        side=Direction.LONG,
    )
    if not guard.authorize(live).authorised:
        return False
    for src in (
        OrderSource.SIM,
        OrderSource.BLIND,
        OrderSource.REPLAY,
        OrderSource.PAPER_SHADOW,
        OrderSource.BACKTEST,
        OrderSource.OFFLINE_AI,
        OrderSource.TELEGRAM_SANDBOX,
    ):
        intent = IsolationIntent(
            source=src,
            source_module="sim",
            symbol="BTCUSDT",
            side=Direction.LONG,
        )
        if guard.authorize(intent).authorised:
            return False
    return True


def _check_blind_sim_isolation() -> bool:
    """Blind / replay / sim / paper-shadow modules never classify as LIVE."""
    for module in (
        "MockExchangeClient",
        "MockExchange",
        "HistoricalMarketStore",
        "SimulatedCapitalFlowEngine",
        "BlindWalkForwardRunner",
        "ReplayFeedProvider",
        "PaperShadowStrategyBridge",
    ):
        if classify_source_module(module) is OrderSource.LIVE:
            return False
    # An unknown module must fail-safe to a non-LIVE source.
    return classify_source_module("SomethingUnknown") is not OrderSource.LIVE


# ---------------------------------------------------------------------------
# DRY order helpers
# ---------------------------------------------------------------------------
def _first_tradable_symbol(exinfo: BinanceExchangeInfoSnapshot) -> str | None:
    for sym in sorted(exinfo.filters.keys()):
        f = exinfo.filters[sym]
        if f.is_tradable:
            return sym
    return None


def _build_dry_order_intent(
    symbol: str,
    exinfo: BinanceExchangeInfoSnapshot,
    runtime_mode: LiveRuntimeMode,
    profile_id: CapitalProfileId,
) -> LiveOrderIntent:
    """Build a tiny, exchange-valid DRY order intent (never submitted).

    Quantity / price are derived from the symbol filters so the order
    clears minQty + minNotional deterministically. It carries a full
    stop+exit plan so the gate's plan check is satisfied.
    """
    f = exinfo.get(symbol)
    min_qty = f.min_qty if (f and f.min_qty > 0) else (f.step_size if (f and f.step_size > 0) else 1.0)
    qty = min_qty
    min_notional = f.min_notional if (f and f.min_notional > 0) else DRY_ORDER_NOTIONAL_USDT
    # Choose a price so notional comfortably clears minNotional.
    price = (min_notional / qty) * 2.0 if qty > 0 else 1.0
    return LiveOrderIntent(
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=qty,
        notional_usdt=qty * price,
        planned_entry_price=price,
        planned_stop_price=price * 0.9,
        planned_take_profit_price=price * 1.2,
        planned_leverage=1.0,
        exit_plan_present=True,
        stop_plan_present=True,
        client_order_id=generate_client_order_id("readiness"),
        source=OrderSource.LIVE,
        runtime_mode=runtime_mode,
        capital_profile_id=profile_id,
        opportunity_id="readiness_dry_order",
    )


__all__ = [
    "LIVE_LAUNCH_READINESS_MODULE",
    "DRY_ORDER_NOTIONAL_USDT",
    "LiveLaunchReadinessChecker",
]
