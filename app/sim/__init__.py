"""Simulation package for AMA-RT V1.4.

This package contains the strict forward-only historical sim-live
time substrate. Its first PR (Phase 11C.1D-D-A / PR94) introduces:

  - :class:`SimulationClock` - strict forward-only simulated UTC
    clock (the ONLY source of market-state decision time inside a
    blind walk-forward run),
  - :class:`HistoricalRecordTime` - the four-timestamp record-time
    helper (``event_time`` / ``available_at`` / ``ingested_at`` /
    ``source``),
  - :class:`TimeWallGuard` - the ``available_at <= simulated_time``
    enforcement layer,
  - :class:`NoLookaheadViolation` - audit-only descriptive violation
    object,
  - :class:`CandleVisibilityGuard` - closed-candle visibility
    enforcement (final OHLCV invisible before close),
  - :func:`assert_no_forbidden_fields` - recursive guard against
    trade-action / runtime-config-patch fields in any output payload.

Hard safety boundaries (Phase 11C.1D-D-A / PR94):

  - mode = paper
  - sandbox_only = True
  - live_trading = False
  - exchange_live_orders = False
  - binance_private_api_enabled = False
  - signed_endpoint_reachable = False
  - private_websocket_reachable = False
  - account_endpoint_reachable = False
  - order_endpoint_reachable = False
  - position_endpoint_reachable = False
  - leverage_endpoint_reachable = False
  - margin_endpoint_reachable = False
  - real_exchange_order_path = False
  - real_capital = False
  - telegram_outbound_enabled = False
  - telegram_live_command_authority = False
  - ai_trade_authority = False
  - trade_authority = False
  - auto_tuning_allowed = False
  - phase_12_forbidden = True

This package MUST NOT:

  - import app.risk / app.execution / app.exchanges / app.telegram /
    app.config
  - call DeepSeek / LLM / Telegram / Binance private API / any
    network
  - place an order
  - emit buy / sell / long / short / direction / entry / exit /
    position_size / leverage / stop / stop_loss / target /
    take_profit / risk_budget / order / execution_command
  - emit any runtime_config_patch / threshold_patch /
    symbol_limit_patch / candidate_pool_patch / regime_weight_patch /
    strategy_parameter_patch / signal_to_trade / should_buy /
    should_short / apply_change / deploy_change / enable_live /
    live_ready / trading_approved
  - authorize live trading or auto-tuning
  - enter Phase 12

PR94 acceptance authorises ONLY PR95 (*Historical Market Store v0*)
to begin. PR94 does NOT implement, and does NOT authorise:

  - the Blind Walk-forward Runner (PR100),
  - the Historical Market Store v0 (PR95),
  - the ReplayFeedProvider (PR96),
  - the MockExchange + Pessimistic Fill Model (PR97),
  - the Simulated Capital Flow + Trade Ledger (PR98),
  - the Telegram Sandbox Outbox (PR99),
  - Phase 12.

The Risk Engine remains the single trade-decision gate.
"""

from app.sim.simulation_clock import (
    PHASE_NAME,
    HistoricalRecordTime,
    SimulationClock,
    ensure_utc_aware,
    parse_interval_seconds,
)
from app.sim.time_wall_guard import (
    FORBIDDEN_OUTPUT_FIELDS,
    CandleVisibilityGuard,
    NoLookaheadViolation,
    NoLookaheadViolationReason,
    NoLookaheadViolationSeverity,
    TimeWallGuard,
    assert_no_forbidden_fields,
)

__all__ = [
    "PHASE_NAME",
    "FORBIDDEN_OUTPUT_FIELDS",
    "CandleVisibilityGuard",
    "HistoricalRecordTime",
    "NoLookaheadViolation",
    "NoLookaheadViolationReason",
    "NoLookaheadViolationSeverity",
    "SimulationClock",
    "TimeWallGuard",
    "assert_no_forbidden_fields",
    "ensure_utc_aware",
    "parse_interval_seconds",
]
