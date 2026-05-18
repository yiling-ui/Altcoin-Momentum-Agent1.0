"""Settings loader for AMA-RT.

Loads `defaults.yaml`, `risk.yaml`, `strategy.yaml`, then validates them via
the Pydantic schemas in `app.config.schema`. Environment variables prefixed
with `AMA_` may override mode/logging fields.

Phase 1 SAFETY GUARANTEE
------------------------
Regardless of what the YAML files or environment variables say, this module
hard-coerces the following four flags to safe values before returning the
Settings object:

    trading_mode = "paper"
    live_trading_enabled = False
    right_tail_enabled = False
    llm_enabled = False
    exchange_live_order_enabled = False

This is enforced by `_apply_phase1_safety_lock()` and unit-tested. To loosen
these flags a future PR must (a) raise the project phase, (b) update tests,
and (c) explicitly remove or modify the lock.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config.schema import DefaultsConfig, RiskFile, StrategyFile

CONFIG_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CONFIG_DIR.parent.parent

PHASE1_SAFETY_FLAGS: dict[str, Any] = {
    "trading_mode": "paper",
    "live_trading_enabled": False,
    "right_tail_enabled": False,
    "llm_enabled": False,
    "exchange_live_order_enabled": False,
}


@dataclass(frozen=True)
class Settings:
    """Top-level merged settings container."""

    defaults: DefaultsConfig
    risk: RiskFile
    strategy: StrategyFile
    project_root: Path

    @property
    def trading_mode(self) -> str:
        return self.defaults.mode.trading_mode

    @property
    def live_trading_enabled(self) -> bool:
        return self.defaults.mode.live_trading_enabled

    @property
    def right_tail_enabled(self) -> bool:
        return self.defaults.mode.right_tail_enabled

    @property
    def llm_enabled(self) -> bool:
        return self.defaults.mode.llm_enabled

    @property
    def exchange_live_order_enabled(self) -> bool:
        return self.defaults.mode.exchange_live_order_enabled

    @property
    def data_dir(self) -> Path:
        d = Path(self.defaults.database.data_dir)
        if not d.is_absolute():
            d = (self.project_root / d).resolve()
        return d

    @property
    def sqlite_dir(self) -> Path:
        return self.data_dir / self.defaults.database.sqlite_subdir


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file {path} must be a YAML mapping at top level.")
    return data


def _apply_env_overrides(defaults_raw: dict[str, Any]) -> dict[str, Any]:
    """Apply AMA_* env-var overrides on top of YAML defaults."""

    mode = defaults_raw.setdefault("mode", {})
    logging_cfg = defaults_raw.setdefault("logging", {})
    db_cfg = defaults_raw.setdefault("database", {})

    env_map = {
        "AMA_TRADING_MODE": ("mode", "trading_mode", str),
        "AMA_LIVE_TRADING_ENABLED": ("mode", "live_trading_enabled", _to_bool),
        "AMA_RIGHT_TAIL_ENABLED": ("mode", "right_tail_enabled", _to_bool),
        "AMA_LLM_ENABLED": ("mode", "llm_enabled", _to_bool),
        "AMA_EXCHANGE_LIVE_ORDER_ENABLED": ("mode", "exchange_live_order_enabled", _to_bool),
        "AMA_LOG_LEVEL": ("logging", "level", str),
        "AMA_DATA_DIR": ("database", "data_dir", str),
    }
    sections = {"mode": mode, "logging": logging_cfg, "database": db_cfg}

    for env_name, (section, key, caster) in env_map.items():
        raw = os.environ.get(env_name)
        if raw is None or raw == "":
            continue
        try:
            sections[section][key] = caster(raw)
        except (TypeError, ValueError):
            # Ignore malformed env override; YAML default wins.
            continue
    return defaults_raw


def _to_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _apply_phase1_safety_lock(defaults: DefaultsConfig) -> DefaultsConfig:
    """Force every Phase 1 safety flag to its safe value.

    Even if a malicious or accidental config sets `live_trading_enabled: true`
    we override it here. This is the single point of truth for Phase 1.
    """

    locked_mode = defaults.mode.model_copy(update=PHASE1_SAFETY_FLAGS)
    return defaults.model_copy(update={"mode": locked_mode})


def load_settings(config_dir: Path | None = None) -> Settings:
    """Load and validate AMA-RT settings."""

    cdir = config_dir or CONFIG_DIR
    defaults_raw = _read_yaml(cdir / "defaults.yaml")
    risk_raw = _read_yaml(cdir / "risk.yaml")
    strategy_raw = _read_yaml(cdir / "strategy.yaml")

    defaults_raw = _apply_env_overrides(defaults_raw)

    defaults_cfg = DefaultsConfig.model_validate(defaults_raw)
    defaults_cfg = _apply_phase1_safety_lock(defaults_cfg)

    risk_cfg = RiskFile.model_validate(risk_raw)
    strategy_cfg = StrategyFile.model_validate(strategy_raw)

    return Settings(
        defaults=defaults_cfg,
        risk=risk_cfg,
        strategy=strategy_cfg,
        project_root=PROJECT_ROOT,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
