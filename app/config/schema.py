"""Pydantic schemas describing the structure of YAML config files.

Used by `app.config.settings.load_settings` to validate `defaults.yaml`,
`risk.yaml` and `strategy.yaml`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ModeConfig(BaseModel):
    trading_mode: str = "paper"
    live_trading_enabled: bool = False
    right_tail_enabled: bool = False
    llm_enabled: bool = False
    exchange_live_order_enabled: bool = False


class LoggingConfig(BaseModel):
    level: str = "INFO"


class DatabaseConfig(BaseModel):
    data_dir: str = "./data"
    sqlite_subdir: str = "sqlite"
    wal_mode: bool = True


class ExchangeConfig(BaseModel):
    name: str = "binance"
    market_type: str = "usdt_perpetual"
    symbols_limit: int = 200
    isolated_margin_only: bool = True
    cross_margin_allowed: bool = False


class TelegramConfirmConfig(BaseModel):
    resume: bool = True
    change_config: bool = True
    kill_all: bool = False


class TelegramConfig(BaseModel):
    """Phase 1 in-process command-bus + Phase 10D outbound transport.

    Phase 11C separates two concepts that previously rode on a single
    ``enabled`` flag:

      - ``enabled`` controls whether the in-process Telegram command
        bus / FakeTelegramClient is wired into the boot drill. It can
        flip True without ever opening a real socket.
      - ``outbound_enabled`` is the **real Telegram HTTP outbound**
        gate. Phase 11C requires it to remain False *independently* of
        ``enabled`` so that even if a future operator flips
        ``telegram.enabled=True`` to use the in-process command bus,
        no real outbound HTTP can ever land. The schema validator
        below refuses any deployment that loads
        ``outbound_enabled=True``.
    """

    enabled: bool = False
    outbound_enabled: bool = False
    command_confirm_required: TelegramConfirmConfig = Field(
        default_factory=TelegramConfirmConfig
    )

    @field_validator("outbound_enabled")
    @classmethod
    def _outbound_must_remain_false(cls, value: bool) -> bool:
        # Phase 11C hard rule: real Telegram outbound is forbidden
        # regardless of ``enabled``. Flipping this requires a Spec
        # §41 Go/No-Go landing in a separate PR that also lifts the
        # Phase 1 safety lock; until then the field is locked False
        # at the schema layer.
        if value:
            raise ValueError(
                "telegram.outbound_enabled must remain False; real "
                "Telegram outbound is forbidden by Phase 11C and "
                "every prior phase. The Phase 1 safety lock + Spec "
                "§41 Go/No-Go must land in a separate PR before this "
                "field can flip True."
            )
        return value


class LLMConfig(BaseModel):
    provider: str = "deepseek"
    enabled: bool = False
    max_calls_per_hour: int = 100
    allow_trade_decision: bool = False


class CapitalConfig(BaseModel):
    """Schema for capital section in defaults.yaml (Phase 8)."""

    initial_capital: float = 100.0
    currency: str = "USDT"
    harvest_suggest_at_2x: bool = True
    harvest_suggest_at_5x: bool = True
    harvest_suggest_at_10x: bool = True


class RestGovernorSection(BaseModel):
    """Phase 11C.1A - Binance public REST rate-limit governor knobs.

    All defaults are conservative. The whole section is consumed by
    :class:`app.exchanges.binance_rate_limit.BinancePublicRestGovernor`
    via :meth:`from_market_data_config`. The schema validators below
    refuse pathological values at boot rather than at the first 429.

    Phase 11C.1A boundary - the field defaults match the brief:

      - ``weight_budget_per_minute = 300``  (half of Binance's 1200/min
        public-data budget; leaves headroom for shared-IP deploys)
      - ``soft_weight_ratio = 0.50``        (warn at 150 weight)
      - ``hard_weight_ratio = 0.75``        (refuse at 225 weight)
      - ``retry_after_default_seconds = 300``
      - ``on_429 = backoff``                (PR-A: only supported value)
      - ``on_418 = shutdown``               (PR-A: only supported value)
      - ``candidate_detail_limit = 3``      (max candidates that may
                                             receive per-loop detail
                                             REST calls)
      - ``rest_layering_enabled = True``    (bootstrap-only public REST;
                                             detail endpoints gated on
                                             candidate ranking)
    """

    enabled: bool = True
    weight_budget_per_minute: int = 300
    soft_weight_ratio: float = 0.50
    hard_weight_ratio: float = 0.75
    retry_after_default_seconds: int = 300
    on_429: str = "backoff"
    on_418: str = "shutdown"
    candidate_detail_limit: int = 3
    rest_layering_enabled: bool = True

    @field_validator("weight_budget_per_minute")
    @classmethod
    def _budget_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(
                "rest_governor.weight_budget_per_minute must be > 0"
            )
        return value

    @field_validator("soft_weight_ratio")
    @classmethod
    def _soft_in_range(cls, value: float) -> float:
        if not (0.0 < value <= 1.0):
            raise ValueError(
                "rest_governor.soft_weight_ratio must be in (0, 1]"
            )
        return value

    @field_validator("hard_weight_ratio")
    @classmethod
    def _hard_in_range(cls, value: float) -> float:
        if not (0.0 < value <= 1.0):
            raise ValueError(
                "rest_governor.hard_weight_ratio must be in (0, 1]"
            )
        return value

    @field_validator("retry_after_default_seconds")
    @classmethod
    def _retry_after_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(
                "rest_governor.retry_after_default_seconds must be > 0"
            )
        return value

    @field_validator("on_429")
    @classmethod
    def _on_429_supported(cls, value: str) -> str:
        if value not in {"backoff"}:
            raise ValueError(
                "rest_governor.on_429 must be 'backoff' in Phase 11C.1A"
            )
        return value

    @field_validator("on_418")
    @classmethod
    def _on_418_supported(cls, value: str) -> str:
        if value not in {"shutdown"}:
            raise ValueError(
                "rest_governor.on_418 must be 'shutdown' in Phase 11C.1A"
            )
        return value

    @field_validator("candidate_detail_limit")
    @classmethod
    def _candidate_detail_in_range(cls, value: int) -> int:
        if value < 0 or value > 20:
            raise ValueError(
                "rest_governor.candidate_detail_limit must be in [0, 20]"
            )
        return value


class MarketDataConfig(BaseModel):
    """Phase 11C - public market data ingestion configuration.

    All defaults are conservative so a 2C/4G VPS can run a 24h paper
    session without saturating CPU / network. Phase 11C.1A lowers
    ``symbol_limit`` from 20 to 5 and ``rest_poll_interval_seconds``
    from 5.0 to 60.0 so the gateway never approaches the Binance
    sliding-window weight budget while the new rate-limit governor
    is the only line of defence. ``provider`` is fixed to
    ``binance_public`` and the runner refuses to start with any
    other value.

    Phase 11C boundary - encoded as defaults that the runner pins:

      - ``read_only=True``  - never flipped to write mode
      - ``provider="binance_public"`` - the only Phase 11C provider
      - ``websocket_enabled=true`` is accepted but only the REST poller
        is wired in this PR; the WS adapter is a future enhancement
        (Phase 11C.1B PR-B WebSocket-first radar)

    Phase 11C.1A additions:

      - ``rest_governor`` - rate-limit / 429 / 418 protection knobs
        consumed by :class:`BinancePublicRestGovernor`.
    """

    provider: str = "binance_public"
    enabled: bool = True
    read_only: bool = True
    symbol_limit: int = 5
    symbols_mode: str = "top_usdt_perpetual"
    rest_base_url: str = "https://fapi.binance.com"
    websocket_enabled: bool = True
    rest_enabled: bool = True
    depth_enabled: bool = True
    trades_enabled: bool = True
    klines_enabled: bool = True
    funding_enabled: bool = True
    open_interest_enabled: bool = True
    mark_price_enabled: bool = True
    book_ticker_enabled: bool = True
    max_ws_staleness_ms: int = 3000
    max_rest_latency_ms: int = 2000
    reconnect_backoff_seconds: int = 5
    rest_poll_interval_seconds: float = 60.0
    snapshot_interval_seconds: float = 5.0
    request_timeout_seconds: float = 5.0
    explicit_symbols: list[str] = Field(default_factory=list)
    rest_governor: RestGovernorSection = Field(
        default_factory=RestGovernorSection
    )

    @field_validator("read_only")
    @classmethod
    def _read_only_must_remain_true(cls, value: bool) -> bool:
        # Phase 11C hard rule: market data is read-only by construction.
        # The schema refuses any deployment that flips this; flipping
        # is a Phase 12+ concern and would require lifting the Phase 1
        # safety lock too.
        if not value:
            raise ValueError(
                "market_data.read_only must remain True in Phase 11C; "
                "Phase 11C is public-market read-only paper."
            )
        return value

    @field_validator("provider")
    @classmethod
    def _provider_must_be_public(cls, value: str) -> str:
        if value != "binance_public":
            raise ValueError(
                f"market_data.provider must be 'binance_public' in "
                f"Phase 11C; got {value!r}."
            )
        return value

    @field_validator("symbol_limit")
    @classmethod
    def _symbol_limit_in_range(cls, value: int) -> int:
        if value <= 0 or value > 200:
            raise ValueError(
                "market_data.symbol_limit must be in (0, 200]; default "
                "is 20 to stay within 2C/4G VPS budget."
            )
        return value


class LabelQueueRuntimeSection(BaseModel):
    """Phase 11C.1C-C-A - MFE / MAE Label Queue Runtime configuration.

    Every threshold the runtime consumes lives here so the brief's
    "thresholds must be configurable, not hard-coded" rule holds at
    the YAML / boot layer too. Defaults match
    :class:`app.adaptive.label_runtime.LabelQueueRuntimeConfig`.

    Phase 11C.1C-C-A boundary - this section is paper / virtual only.
    Nothing under it can flip a Phase 1 safety flag, open a socket,
    or read a private API. The runner builds the runtime from this
    section, but the runtime itself is read-only on settings.
    """

    enabled: bool = True
    max_pending_records: int = 500
    grace_period_seconds: int = 5 * 60
    primary_window_for_tail_label: str = "5m"
    window_seconds_map: dict[str, int] = Field(
        default_factory=lambda: {
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
        }
    )
    strong_tail_min_r_multiple: float = 5.0
    strong_tail_max_mae_pct: float = -0.04
    moderate_tail_min_r_multiple: float = 3.0
    weak_tail_min_r_multiple: float = 2.0
    fake_breakout_min_mfe_pct: float = 0.03
    fake_breakout_min_drawdown_after_mfe_pct: float = -0.02
    fake_breakout_max_final_pct: float = 0.005
    late_chase_failure_min_late_chase_risk: float = 60.0
    late_chase_failure_max_mfe_pct: float = 0.005
    dumped_min_mae_drop_pct: float = -0.05
    dumped_max_mfe_pct: float = 0.01
    stopped_before_tail_pct: float = -0.04
    missed_tail_min_mfe_pct: float = 0.05

    @field_validator("max_pending_records")
    @classmethod
    def _max_pending_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(
                "label_queue_runtime.max_pending_records must be > 0"
            )
        return value

    @field_validator("grace_period_seconds")
    @classmethod
    def _grace_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError(
                "label_queue_runtime.grace_period_seconds must be >= 0"
            )
        return value

    @field_validator("primary_window_for_tail_label")
    @classmethod
    def _primary_must_be_in_map(cls, value: str, info) -> str:
        # Defer cross-field validation: the model_validator below runs
        # AFTER both fields are populated.
        return str(value)

    @field_validator("window_seconds_map")
    @classmethod
    def _windows_positive(cls, value: dict[str, int]) -> dict[str, int]:
        if not value:
            raise ValueError(
                "label_queue_runtime.window_seconds_map must not be empty"
            )
        for k, v in value.items():
            if int(v) <= 0:
                raise ValueError(
                    f"label_queue_runtime.window_seconds_map[{k}] must be > 0"
                )
        return {str(k): int(v) for k, v in value.items()}


class StrategyValidationSection(BaseModel):
    """Phase 11C.1C-C-B-A - Strategy Validation Lab v0 configuration.

    Every threshold the runtime consumes lives here so the brief's
    "thresholds must be configurable, not hard-coded" rule holds at
    the YAML / boot layer too. Defaults match
    :class:`app.adaptive.strategy_validation_runtime.StrategyValidationRuntimeConfig`.

    Phase 11C.1C-C-B-A boundary - this section is paper / report
    only. Nothing under it can flip a Phase 1 safety flag, open a
    private API socket, or call an LLM / Telegram outbound. The
    ``suggested_cluster_action`` produced by the runtime is
    descriptive; the Risk Engine remains the single trade-decision
    gate.
    """

    enabled: bool = True
    max_samples: int = 2_000
    primary_window: str = "5m"
    overexposure_warning_threshold: int = 3
    top_symbol_limit: int = 10

    @field_validator("max_samples")
    @classmethod
    def _max_samples_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(
                "strategy_validation.max_samples must be > 0"
            )
        return value

    @field_validator("overexposure_warning_threshold")
    @classmethod
    def _overexposure_threshold_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(
                "strategy_validation.overexposure_warning_threshold "
                "must be > 0"
            )
        return value

    @field_validator("top_symbol_limit")
    @classmethod
    def _top_symbol_limit_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(
                "strategy_validation.top_symbol_limit must be > 0"
            )
        return value


class SafetyConfig(BaseModel):
    """Phase 11C - public-market safety guard rails.

    These flags are *assertions*, not opt-ins. A deployment that flips
    any of them to ``False`` is refused by :func:`SafetyConfig.validate`
    so an operator who tries to weaken Phase 11C sees the failure
    before the runner boots.
    """

    forbid_private_credentials: bool = True
    forbid_signed_endpoints: bool = True
    forbid_trade_endpoints: bool = True
    forbid_account_endpoints: bool = True
    forbid_position_endpoints: bool = True
    forbid_leverage_endpoints: bool = True
    forbid_margin_endpoints: bool = True
    forbid_live_trading: bool = True
    forbid_right_tail: bool = True
    forbid_llm_trade_decisions: bool = True
    forbid_telegram_outbound: bool = True

    @field_validator(
        "forbid_private_credentials",
        "forbid_signed_endpoints",
        "forbid_trade_endpoints",
        "forbid_account_endpoints",
        "forbid_position_endpoints",
        "forbid_leverage_endpoints",
        "forbid_margin_endpoints",
        "forbid_live_trading",
        "forbid_right_tail",
        "forbid_llm_trade_decisions",
        "forbid_telegram_outbound",
    )
    @classmethod
    def _flag_must_be_true(cls, value: bool, info) -> bool:
        if not value:
            raise ValueError(
                f"safety.{info.field_name} must remain True in Phase 11C; "
                "Phase 11C cannot loosen any Phase 1 / Phase 11B safety flag."
            )
        return value


class DefaultsConfig(BaseModel):
    """Schema for `app/config/defaults.yaml`."""

    mode: ModeConfig = Field(default_factory=ModeConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    capital: CapitalConfig = Field(default_factory=CapitalConfig)
    market_data: MarketDataConfig = Field(default_factory=MarketDataConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    label_queue_runtime: LabelQueueRuntimeSection = Field(
        default_factory=LabelQueueRuntimeSection
    )
    strategy_validation: StrategyValidationSection = Field(
        default_factory=StrategyValidationSection
    )


class RiskThresholds(BaseModel):
    max_daily_loss_pct: float = 0.05
    max_consecutive_losses: int = 5
    max_single_trade_loss_pct: dict[str, float] = Field(
        default_factory=lambda: {"scout": 0.005, "attack": 0.015}
    )
    stop_required: bool = True
    stop_confirmation_required: bool = True


class LiquidityThresholds(BaseModel):
    max_spread_pct: float = 0.003
    max_slippage_pct: float = 0.005
    min_depth_multiplier: int = 5


class RiskFile(BaseModel):
    """Schema for `app/config/risk.yaml`."""

    risk: RiskThresholds = Field(default_factory=RiskThresholds)
    liquidity: LiquidityThresholds = Field(default_factory=LiquidityThresholds)


class StrategyFile(BaseModel):
    """Schema for `app/config/strategy.yaml`."""

    strategies: dict = Field(default_factory=lambda: {"enabled": []})
