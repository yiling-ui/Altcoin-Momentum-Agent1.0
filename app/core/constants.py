"""System-wide constants for AMA-RT.

Phase 1 only ships the bare minimum. Numerical thresholds live in YAML.
"""

from __future__ import annotations

PROJECT_NAME = "AMA-RT"
PROJECT_CODE_NAME = "Altcoin Momentum Agent - Right Tail Edition"

# Database file names per Spec §33.1
DB_EVENTS = "events.db"
DB_TRADES = "trades.db"
DB_POSITIONS = "positions.db"
DB_CAPITAL = "capital.db"
DB_INCIDENTS = "incidents.db"
DB_MARKET = "market.db"
DB_ORDERS = "orders.db"
DB_REFLECTION = "reflection.db"
DB_LLM_CACHE = "llm_cache.db"

ALL_DATABASES = (
    DB_EVENTS,
    DB_TRADES,
    DB_POSITIONS,
    DB_CAPITAL,
    DB_INCIDENTS,
    DB_MARKET,
    DB_ORDERS,
    DB_REFLECTION,
    DB_LLM_CACHE,
)
