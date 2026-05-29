"""Simulation package for AMA-RT V1.4.

This package contains the strict forward-only historical sim-live
time substrate.

  * Phase 11C.1D-D-A / PR94 - SimulationClock + Time-Wall Guard:

      - :class:`SimulationClock` - strict forward-only simulated UTC
        clock (the ONLY source of market-state decision time inside
        a blind walk-forward run),
      - :class:`HistoricalRecordTime` - the four-timestamp record-time
        helper (``event_time`` / ``available_at`` / ``ingested_at`` /
        ``source``),
      - :class:`TimeWallGuard` - the ``available_at <= simulated_time``
        enforcement layer,
      - :class:`NoLookaheadViolation` - audit-only descriptive
        violation object,
      - :class:`CandleVisibilityGuard` - closed-candle visibility
        enforcement (final OHLCV invisible before close),
      - :func:`assert_no_forbidden_fields` - recursive guard against
        trade-action / runtime-config-patch fields in any output
        payload.

  * Phase 11C.1D-D-B / PR95 - Historical Market Store v0:

      - :class:`HistoricalMarketRecordType` - closed taxonomy of
        historical record types (1m / 5m kline, funding rate, open
        interest, 24h ticker, exchangeInfo, symbol / listing /
        delisting status),
      - :class:`DataQualityFlag` - closed taxonomy of record-level
        data-quality flags,
      - :class:`SymbolStatus` - closed taxonomy of symbol statuses
        (with the ``TRADABLE_OR_MONITORABLE`` subset used by the
        as-of universe),
      - :class:`DataCompletenessState` - closed taxonomy of
        symbol-level data completeness states,
      - :class:`HistoricalMarketRecord` - generic historical record
        (non-kline shape),
      - :class:`HistoricalKlineRecord` - 1m / 5m kline record (final
        OHLCV invisible before candle close),
      - :class:`SymbolStatusRecord` - symbol metadata record for the
        as-of universe (no survivorship bias),
      - :class:`HistoricalMarketStore` - in-memory store with
        ``available_at <= simulated_time`` enforcement, closed-candle
        visibility, and as-of universe query.

  * Phase 11C.1D-D-C / PR96 - ReplayFeedProvider v0:

      - :class:`ReplayFeedProviderConfig` - frozen replay window /
        record-type filter / behaviour switches
        (``include_asof_universe``, ``allow_reemit``,
        ``strict_time_wall``, ``strict_candle_visibility``),
      - :class:`ReplayFeedCursor` - forward-only cursor (start /
        end / current / step_interval / emitted_record_ids /
        replay_complete),
      - :class:`ReplayFeedDiagnostics` - cumulative counters
        (``total_records_considered`` /
        ``emitted_record_count`` /
        ``future_records_rejected_count`` /
        ``missing_available_at_count`` /
        ``unclosed_candle_violation_count`` /
        ``duplicate_record_skipped_count`` /
        ``data_gap_flags`` / preserved
        :class:`NoLookaheadViolation` objects),
      - :class:`ReplayFeedBatch` - per-tick batch (``batch_id`` /
        ``simulated_time`` / ``records`` / ``klines_1m`` /
        ``klines_5m`` / ``funding_rates`` / ``open_interest`` /
        ``ticker_24h`` / ``symbol_status`` / ``asof_universe`` /
        ``diagnostics`` / ``violations`` / hard-pinned
        ``phase_12_forbidden=True``,
        ``auto_tuning_allowed=False``,
        ``trade_authority=False``),
      - :class:`ReplayFeedProvider` - the deterministic, forward-only
        feed substrate that consumes a
        :class:`HistoricalMarketStore` and a
        :class:`SimulationClock` and emits
        :class:`ReplayFeedBatch` batches obeying every
        ``available_at <= simulated_time`` / closed-candle
        visibility / as-of universe rule.

Hard safety boundaries (Phase 11C.1D-D-A / PR94 + Phase 11C.1D-D-B /
PR95 + Phase 11C.1D-D-C / PR96):

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

PR96 acceptance authorises ONLY PR97 (*MockExchange + Pessimistic
Fill Model v0*) to begin its own gate. PR96 does NOT implement, and
does NOT authorise:

  - the MockExchange + Pessimistic Fill Model (PR97),
  - the Simulated Capital Flow + Trade Ledger (PR98),
  - the Telegram Sandbox Outbox (PR99),
  - the Blind Walk-forward Runner (PR100),
  - Phase 12.

The Risk Engine remains the single trade-decision gate.
"""

from app.sim.historical_market_store import (
    PHASE_NAME as HISTORICAL_MARKET_STORE_PHASE_NAME,
)
from app.sim.historical_market_store import (
    DataCompletenessState,
    DataQualityFlag,
    HistoricalKlineRecord,
    HistoricalMarketRecord,
    HistoricalMarketRecordType,
    HistoricalMarketStore,
    SymbolStatus,
    SymbolStatusRecord,
)
from app.sim.replay_feed_provider import (
    PHASE_NAME as REPLAY_FEED_PROVIDER_PHASE_NAME,
)
from app.sim.replay_feed_provider import (
    ReplayFeedBatch,
    ReplayFeedCursor,
    ReplayFeedDiagnostics,
    ReplayFeedProvider,
    ReplayFeedProviderConfig,
)
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
    "HISTORICAL_MARKET_STORE_PHASE_NAME",
    "REPLAY_FEED_PROVIDER_PHASE_NAME",
    "FORBIDDEN_OUTPUT_FIELDS",
    "CandleVisibilityGuard",
    "DataCompletenessState",
    "DataQualityFlag",
    "HistoricalKlineRecord",
    "HistoricalMarketRecord",
    "HistoricalMarketRecordType",
    "HistoricalMarketStore",
    "HistoricalRecordTime",
    "NoLookaheadViolation",
    "NoLookaheadViolationReason",
    "NoLookaheadViolationSeverity",
    "ReplayFeedBatch",
    "ReplayFeedCursor",
    "ReplayFeedDiagnostics",
    "ReplayFeedProvider",
    "ReplayFeedProviderConfig",
    "SimulationClock",
    "SymbolStatus",
    "SymbolStatusRecord",
    "TimeWallGuard",
    "assert_no_forbidden_fields",
    "ensure_utc_aware",
    "parse_interval_seconds",
]
