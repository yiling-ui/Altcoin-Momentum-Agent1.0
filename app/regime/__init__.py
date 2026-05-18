"""Regime Engine package (Phase 5 - Issue #5).

Spec references:
    §15  Regime Engine 市场周期闸门
    §15.1 Output schema (market_regime, btc_trend, btc_volatility,
          alt_liquidity, risk_permission)
    §15.2 Five regimes: MEME_RISK_ON, SECTOR_ROTATION, BTC_ABSORPTION,
          ALT_RISK_OFF, SYSTEMIC_RISK
    §15.3 Action mapping (regime -> risk_permission)

Phase 5 hard boundary
---------------------

The Regime Engine is a *pure classifier*. It reads MarketSnapshot
data through the Phase 4 :class:`MarketDataBuffer` (or accepts a
:class:`RegimeInput` directly so tests can drive it deterministically),
emits a single :class:`RegimeSnapshot` value object, and writes one
``REGIME_UPDATED`` event through the existing
:class:`EventRepository`. It MUST NOT:

  - place an order, cancel an order, or change leverage;
  - call any LLM;
  - amplify a position via the right tail;
  - import an exchange SDK or open an outbound socket;
  - read or accept an API key;
  - mutate the Phase 1 safety lock.

The five Phase 1 safety flags (`trading_mode=paper`,
`live_trading_enabled=False`, `right_tail_enabled=False`,
`llm_enabled=False`, `exchange_live_order_enabled=False`) are
unchanged. The four ``SafeModeViolation`` write-surface refusals on
``ExchangeClientBase`` are unchanged.
"""

from app.regime.engine import RegimeEngine
from app.regime.models import (
    REGIME_TO_RISK_PERMISSION,
    RegimeConfig,
    RegimeInput,
    RegimeSnapshot,
)

__all__ = [
    "REGIME_TO_RISK_PERMISSION",
    "RegimeConfig",
    "RegimeEngine",
    "RegimeInput",
    "RegimeSnapshot",
]
