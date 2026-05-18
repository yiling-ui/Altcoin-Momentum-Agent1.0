"""AMA-RT configuration system.

Provides type-checked settings and YAML config loading. Phase 1 hard-codes
safety defaults: paper mode, live trading disabled, right-tail disabled,
LLM disabled, exchange live orders disabled.
"""

from app.config.settings import Settings, get_settings, load_settings

__all__ = ["Settings", "get_settings", "load_settings"]
