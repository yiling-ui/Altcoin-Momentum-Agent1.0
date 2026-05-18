"""Pydantic schemas describing the structure of YAML config files.

Used by `app.config.settings.load_settings` to validate `defaults.yaml`,
`risk.yaml` and `strategy.yaml`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


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
    enabled: bool = False
    command_confirm_required: TelegramConfirmConfig = Field(default_factory=TelegramConfirmConfig)


class LLMConfig(BaseModel):
    provider: str = "deepseek"
    enabled: bool = False
    max_calls_per_hour: int = 100
    allow_trade_decision: bool = False


class DefaultsConfig(BaseModel):
    """Schema for `app/config/defaults.yaml`."""

    mode: ModeConfig = Field(default_factory=ModeConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)


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
