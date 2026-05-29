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

  * Phase 11C.1D-D-D / PR97 - MockExchange + Pessimistic Fill Model v0:

      - :class:`MockOrderType` - closed taxonomy of mock order types
        (``MARKET`` / ``LIMIT`` / ``STOP_MARKET`` /
        ``TAKE_PROFIT_MARKET`` / ``FORCED_EXIT``),
      - :class:`MockOrderSide` - closed taxonomy of mock order sides
        (``BUY`` / ``SELL``); paper-only field, NEVER an AI /
        strategy recommendation,
      - :class:`MockOrderStatus` - closed taxonomy of mock order
        statuses (``CREATED`` / ``ACCEPTED`` / ``PARTIALLY_FILLED``
        / ``FILLED`` / ``REJECTED`` / ``CANCELED`` / ``EXPIRED`` /
        ``STALE`` / ``AMBIGUOUS_INTRABAR_PATH``),
      - :class:`MockOrder` - mutable mock order with hard-pinned
        ``simulated_only=True`` / ``no_live_order=True`` /
        ``phase_12_forbidden=True`` / ``trade_authority=False``,
      - :class:`MockFill` - frozen mock fill with conservative-
        assumption markers (``TAKER_FEE_APPLIED`` /
        ``SLIPPAGE_APPLIED`` / ``LATENCY_PENALTY_APPLIED`` /
        ``LIMIT_PENETRATION_REQUIRED`` / ``STOP_ADVERSE_FILL`` /
        ``TAKE_PROFIT_CONSERVATIVE_FILL`` /
        ``FORCED_EXIT_CONSERVATIVE_FILL`` /
        ``AMBIGUOUS_INTRABAR_WORST_CASE`` / ``PARTIAL_FILL`` /
        ``NO_OPTIMISTIC_FILL_ON_INSUFFICIENT_DATA``),
      - :class:`MockExchangeConfig` - frozen taker / maker fee bps,
        slippage / latency bps, ``reject_if_no_visible_price`` (default
        ``True``), ``limit_touch_fill_policy`` (default
        ``NO_FILL_ON_TOUCH``), ``ambiguous_intrabar_policy`` (default
        ``WORST_CASE``), ``partial_fill_enabled`` /
        ``max_fill_fraction_per_batch``, hard-pinned
        ``sandbox_only=True`` / ``live_order_enabled=False``,
      - :class:`PessimisticFillModel` - pure / deterministic /
        pessimistic fill model: market / forced-exit pay taker fee +
        slippage + latency adverse to side; limit refuses fill on
        touch and requires penetration; stop fills at the adverse
        stop price plus taker fee + slippage; take-profit fills
        conservatively; same-candle stop + take-profit triggers fall
        back to ``WORST_CASE`` (stop fires, TP canceled) or
        ``AMBIGUOUS_INTRABAR_PATH`` per
        :class:`AmbiguousIntrabarPolicy`; insufficient visible price
        data NEVER produces an optimistic fill,
      - :class:`OrderRequest` - frozen request shape used by
        :meth:`MockExchange.submit_order`,
      - :class:`MockExchangeDiagnostics` - cumulative counters,
      - :class:`MockExchange` - paper-only simulated exchange with
        ``submit_order`` / ``cancel_order`` / ``expire_order`` /
        ``process_batch`` / ``get_order`` / ``list_open_orders`` /
        ``list_all_orders`` / ``list_fills`` / ``reset`` /
        ``safety_payload`` / ``to_dict``. NEVER calls a real
        exchange, NEVER advertises a real exchange order id, NEVER
        opens a private websocket, NEVER touches the Binance private
        API.

Hard safety boundaries (Phase 11C.1D-D-A / PR94 + Phase 11C.1D-D-B /
PR95 + Phase 11C.1D-D-C / PR96 + Phase 11C.1D-D-D / PR97):

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
Fill Model v0*) to begin its own gate. PR97 acceptance authorises
ONLY PR98 (*Simulated Capital Flow + Trade Ledger v0*) to begin its
own gate. Neither PR96 nor PR97 implements, and neither PR96 nor
PR97 authorises:

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
from app.sim.historical_data_manifest import (
    PHASE_NAME as HISTORICAL_DATA_INGESTION_PHASE_NAME,
)
from app.sim.historical_data_manifest import (
    DataIngestionStatus,
    HistoricalDataManifest,
    HistoricalDataSourceType,
    UniverseManifest,
)
from app.sim.historical_data_ingestion import (
    SUPPORTED_KLINE_INTERVALS as HISTORICAL_DATA_SUPPORTED_KLINE_INTERVALS,
)
from app.sim.historical_data_ingestion import (
    HistoricalDataIngestion,
    HistoricalDataIngestionConfig,
    HistoricalDataIngestionResult,
    IngestionSchemaError,
    IngestionTimeFieldError,
    parse_funding_row,
    parse_kline_row,
    parse_open_interest_row,
    parse_symbol_status_row,
    parse_ticker_24h_row,
)
from app.sim.historical_data_manifest import (
    compute_artefact_hash as historical_data_compute_artefact_hash,
)
from app.sim.historical_data_manifest import (
    safety_payload as historical_data_safety_payload,
)
from app.sim.mock_exchange import (
    PHASE_NAME as MOCK_EXCHANGE_PHASE_NAME,
)
from app.sim.mock_exchange import (
    MockExchange,
    MockExchangeDiagnostics,
    OrderRequest,
)
from app.sim.pessimistic_fill_model import (
    PHASE_NAME as PESSIMISTIC_FILL_MODEL_PHASE_NAME,
)
from app.sim.pessimistic_fill_model import (
    AmbiguousIntrabarPolicy,
    ConservativeAssumption,
    FillModelDecision,
    FillReason,
    LimitTouchFillPolicy,
    MockExchangeConfig,
    MockFill,
    MockOrder,
    MockOrderSide,
    MockOrderStatus,
    MockOrderType,
    PessimisticFillModel,
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
from app.sim.simulated_capital_flow import (
    PHASE_NAME as SIMULATED_CAPITAL_FLOW_PHASE_NAME,
)
from app.sim.simulated_capital_flow import (
    CapitalFrozenError,
    PositionSide,
    PositionStatus,
    RiskFreezeReason,
    SimulatedCapitalConfig,
    SimulatedCapitalFlowEngine,
    SimulatedCapitalState,
    SimulatedPosition,
)
from app.sim.simulation_clock import (
    PHASE_NAME,
    HistoricalRecordTime,
    SimulationClock,
    ensure_utc_aware,
    parse_interval_seconds,
)
from app.sim.telegram_sandbox_outbox import (
    PHASE_NAME as TELEGRAM_SANDBOX_OUTBOX_PHASE_NAME,
)
from app.sim.telegram_sandbox_outbox import (
    DEFAULT_OUTPUT_JSONL_PATH as TELEGRAM_SANDBOX_DEFAULT_OUTPUT_JSONL_PATH,
)
from app.sim.telegram_sandbox_outbox import (
    DEFAULT_OUTPUT_MARKDOWN_PATH as TELEGRAM_SANDBOX_DEFAULT_OUTPUT_MARKDOWN_PATH,
)
from app.sim.telegram_sandbox_outbox import (
    MANDATORY_LABELS as TELEGRAM_SANDBOX_MANDATORY_LABELS,
)
from app.sim.telegram_sandbox_outbox import (
    NO_LIVE_ORDER_LABEL,
    NO_REAL_CAPITAL_LABEL,
    NO_TELEGRAM_COMMAND_AUTHORITY_LABEL,
    SIMULATED_HISTORICAL_BLIND_TEST_LABEL,
    TelegramSandboxMessage,
    TelegramSandboxMessageType,
    TelegramSandboxOutbox,
    TelegramSandboxOutboxConfig,
    TelegramSandboxSeverity,
)
from app.sim.trade_ledger import (
    PHASE_NAME as TRADE_LEDGER_PHASE_NAME,
)
from app.sim.trade_ledger import (
    EquityTimeseriesPoint,
    TradeFailureFlag,
    TradeLedger,
    TradeLedgerEntry,
    TradeLedgerSummary,
    TradeOutcome,
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
from app.sim.blind_walk_forward_manifest import (
    PHASE_NAME as BLIND_WALK_FORWARD_RUNNER_PHASE_NAME,
)
from app.sim.blind_walk_forward_manifest import (
    ALLOWED_TIMEFRAMES as BLIND_WALK_FORWARD_ALLOWED_TIMEFRAMES,
)
from app.sim.blind_walk_forward_manifest import (
    DEFAULT_BASE_CLOCK_STEP as BLIND_WALK_FORWARD_DEFAULT_BASE_CLOCK_STEP,
)
from app.sim.blind_walk_forward_manifest import (
    BlindRunManifest,
    BlindWalkForwardWindow,
    compute_artefact_hash,
)
from app.sim.blind_walk_forward_manifest import (
    safety_payload as blind_walk_forward_safety_payload,
)
from app.sim.blind_walk_forward_scoring import (
    BlindRunInvalidationReason,
    BlindRunScore,
    BlindRunStatus,
    score_blind_run,
)
from app.sim.blind_walk_forward_runner import (
    DEFAULT_REPORT_ROOT as BLIND_WALK_FORWARD_DEFAULT_REPORT_ROOT,
)
from app.sim.blind_walk_forward_runner import (
    AsOfFeatureCache,
    BlindWalkForwardRunner,
    BlindWalkForwardRunnerConfig,
    DecisionCallback,
    MultiTimeframeAsOfGuard,
)

__all__ = [
    "PHASE_NAME",
    "HISTORICAL_MARKET_STORE_PHASE_NAME",
    "HISTORICAL_DATA_INGESTION_PHASE_NAME",
    "HISTORICAL_DATA_SUPPORTED_KLINE_INTERVALS",
    "REPLAY_FEED_PROVIDER_PHASE_NAME",
    "MOCK_EXCHANGE_PHASE_NAME",
    "PESSIMISTIC_FILL_MODEL_PHASE_NAME",
    "SIMULATED_CAPITAL_FLOW_PHASE_NAME",
    "TRADE_LEDGER_PHASE_NAME",
    "TELEGRAM_SANDBOX_OUTBOX_PHASE_NAME",
    "TELEGRAM_SANDBOX_DEFAULT_OUTPUT_JSONL_PATH",
    "TELEGRAM_SANDBOX_DEFAULT_OUTPUT_MARKDOWN_PATH",
    "TELEGRAM_SANDBOX_MANDATORY_LABELS",
    "BLIND_WALK_FORWARD_RUNNER_PHASE_NAME",
    "BLIND_WALK_FORWARD_ALLOWED_TIMEFRAMES",
    "BLIND_WALK_FORWARD_DEFAULT_BASE_CLOCK_STEP",
    "BLIND_WALK_FORWARD_DEFAULT_REPORT_ROOT",
    "AsOfFeatureCache",
    "BlindRunInvalidationReason",
    "BlindRunManifest",
    "BlindRunScore",
    "BlindRunStatus",
    "BlindWalkForwardRunner",
    "BlindWalkForwardRunnerConfig",
    "BlindWalkForwardWindow",
    "DecisionCallback",
    "MultiTimeframeAsOfGuard",
    "blind_walk_forward_safety_payload",
    "compute_artefact_hash",
    "score_blind_run",
    "NO_LIVE_ORDER_LABEL",
    "NO_REAL_CAPITAL_LABEL",
    "NO_TELEGRAM_COMMAND_AUTHORITY_LABEL",
    "SIMULATED_HISTORICAL_BLIND_TEST_LABEL",
    "TelegramSandboxMessage",
    "TelegramSandboxMessageType",
    "TelegramSandboxOutbox",
    "TelegramSandboxOutboxConfig",
    "TelegramSandboxSeverity",
    "FORBIDDEN_OUTPUT_FIELDS",
    "AmbiguousIntrabarPolicy",
    "CandleVisibilityGuard",
    "CapitalFrozenError",
    "ConservativeAssumption",
    "DataCompletenessState",
    "DataQualityFlag",
    "DataIngestionStatus",
    "HistoricalDataIngestion",
    "HistoricalDataIngestionConfig",
    "HistoricalDataIngestionResult",
    "HistoricalDataManifest",
    "HistoricalDataSourceType",
    "UniverseManifest",
    "IngestionSchemaError",
    "IngestionTimeFieldError",
    "parse_kline_row",
    "parse_funding_row",
    "parse_open_interest_row",
    "parse_ticker_24h_row",
    "parse_symbol_status_row",
    "historical_data_compute_artefact_hash",
    "historical_data_safety_payload",
    "EquityTimeseriesPoint",
    "FillModelDecision",
    "FillReason",
    "HistoricalKlineRecord",
    "HistoricalMarketRecord",
    "HistoricalMarketRecordType",
    "HistoricalMarketStore",
    "HistoricalRecordTime",
    "LimitTouchFillPolicy",
    "MockExchange",
    "MockExchangeConfig",
    "MockExchangeDiagnostics",
    "MockFill",
    "MockOrder",
    "MockOrderSide",
    "MockOrderStatus",
    "MockOrderType",
    "NoLookaheadViolation",
    "NoLookaheadViolationReason",
    "NoLookaheadViolationSeverity",
    "OrderRequest",
    "PessimisticFillModel",
    "PositionSide",
    "PositionStatus",
    "ReplayFeedBatch",
    "ReplayFeedCursor",
    "ReplayFeedDiagnostics",
    "ReplayFeedProvider",
    "ReplayFeedProviderConfig",
    "RiskFreezeReason",
    "SimulatedCapitalConfig",
    "SimulatedCapitalFlowEngine",
    "SimulatedCapitalState",
    "SimulatedPosition",
    "SimulationClock",
    "SymbolStatus",
    "SymbolStatusRecord",
    "TimeWallGuard",
    "TradeFailureFlag",
    "TradeLedger",
    "TradeLedgerEntry",
    "TradeLedgerSummary",
    "TradeOutcome",
    "assert_no_forbidden_fields",
    "ensure_utc_aware",
    "parse_interval_seconds",
]
