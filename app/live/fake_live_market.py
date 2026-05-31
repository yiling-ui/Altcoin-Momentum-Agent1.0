"""Fake live market generator (PR117 - Full-System Single-Altcoin Live
Sandbox Audit v0).

A deterministic, IO-free generator of fake *live* market frames for a
single sandbox altcoin (``RAVEUSDT_SANDBOX``). It feeds the full-system
sandbox audit so the real PR110-PR116 live chain can run end-to-end
without ever touching a real exchange.

Hard boundaries (PR117):
  * This is a fake LIVE-equivalent market source. It is NOT a historical
    store / replay feed / sim market: those remain blocked from the live
    path by PR110/PR114 isolation. The class name is deliberately NOT in
    :data:`app.live.live_runtime.FORBIDDEN_LIVE_SOURCE_CLASSES`.
  * It produces market measurements only. It never builds an order, never
    decides direction / size / leverage, and never carries a future label
    (no MFE / MAE / completed_tail_label leakage).

Scenarios (the brief's 8 market shapes):
  1. ``quiet_market``             - sideways, no signal.
  2. ``weak_pump``                - small pump, insufficient evidence.
  3. ``right_tail_breakout``      - RAVE-like right-tail breakout.
  4. ``fake_breakout_reversal``   - fake breakout then sharp reversal.
  5. ``funding_negative_hold``    - a hold during negative funding (fee paid).
  6. ``funding_positive_hold``    - a hold during positive funding (income).
  7. ``spread_liquidity_bad``     - liquidity / slippage fails the floor.
  8. ``exchange_failure_mid_trade`` - order submitted then query fails /
     partial / timeout (the market frame itself is a clean breakout; the
     failure is injected at the fake exchange).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.enums import MarketRegime

FAKE_LIVE_MARKET_MODULE = "live.fake_live_market"

# This is a fake LIVE-equivalent market; PR117 never sends a real order.
FAKE_LIVE_MARKET_SOURCE = "FAKE_LIVE_SANDBOX"

DEFAULT_SANDBOX_SYMBOL = "RAVEUSDT_SANDBOX"


# The eight required market scenarios.
class MarketScenario:
    QUIET_MARKET = "quiet_market"
    WEAK_PUMP = "weak_pump"
    RIGHT_TAIL_BREAKOUT = "right_tail_breakout"
    FAKE_BREAKOUT_REVERSAL = "fake_breakout_reversal"
    FUNDING_NEGATIVE_HOLD = "funding_negative_hold"
    FUNDING_POSITIVE_HOLD = "funding_positive_hold"
    SPREAD_LIQUIDITY_BAD = "spread_liquidity_bad"
    EXCHANGE_FAILURE_MID_TRADE = "exchange_failure_mid_trade"


ALL_MARKET_SCENARIOS: tuple[str, ...] = (
    MarketScenario.QUIET_MARKET,
    MarketScenario.WEAK_PUMP,
    MarketScenario.RIGHT_TAIL_BREAKOUT,
    MarketScenario.FAKE_BREAKOUT_REVERSAL,
    MarketScenario.FUNDING_NEGATIVE_HOLD,
    MarketScenario.FUNDING_POSITIVE_HOLD,
    MarketScenario.SPREAD_LIQUIDITY_BAD,
    MarketScenario.EXCHANGE_FAILURE_MID_TRADE,
)


@dataclass(frozen=True)
class MarketFrame:
    """A single fake live market frame (deterministic; no future labels)."""

    timestamp: int
    symbol: str
    price: float
    volume: float
    spread_bps: float
    estimated_slippage_bps: float
    liquidity_score: float
    volatility_score: float
    volume_expansion_score: float
    oi_expansion_score: float
    breakout_structure_score: float
    funding_rate: float
    market_regime: MarketRegime
    systemic_risk_state: bool
    # Provenance markers (audit visibility): this is a LIVE-equivalent
    # fake frame, NOT a blind / replay / sim frame and NOT a future label.
    source: str = FAKE_LIVE_MARKET_SOURCE
    is_future_label: bool = False
    completed_tail_label: Any = None
    mfe_pct: Any = None
    mae_pct: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "price": self.price,
            "volume": self.volume,
            "spread_bps": self.spread_bps,
            "estimated_slippage_bps": self.estimated_slippage_bps,
            "liquidity_score": self.liquidity_score,
            "volatility_score": self.volatility_score,
            "volume_expansion_score": self.volume_expansion_score,
            "oi_expansion_score": self.oi_expansion_score,
            "breakout_structure_score": self.breakout_structure_score,
            "funding_rate": self.funding_rate,
            "market_regime": self.market_regime.value,
            "systemic_risk_state": self.systemic_risk_state,
            "source": self.source,
            "is_future_label": self.is_future_label,
        }


# Per-scenario shape: a tuple of multiplicative / additive deltas applied
# over the frame sequence to make the trajectory legible (sideways vs.
# breakout vs. reversal). All deterministic.
@dataclass(frozen=True)
class _ScenarioShape:
    base_price: float
    price_path: tuple[float, ...]  # multiplicative factor per frame
    volume: float
    spread_bps: float
    estimated_slippage_bps: float
    liquidity_score: float
    volatility_score: float
    volume_expansion_score: float
    oi_expansion_score: float
    breakout_structure_score: float
    funding_rate: float
    market_regime: MarketRegime
    systemic_risk_state: bool = False


_SHAPES: dict[str, _ScenarioShape] = {
    MarketScenario.QUIET_MARKET: _ScenarioShape(
        base_price=1.0,
        price_path=(1.0, 1.001, 0.999, 1.0, 1.0005),
        volume=10_000.0,
        spread_bps=4.0,
        estimated_slippage_bps=5.0,
        liquidity_score=0.7,
        volatility_score=0.1,
        volume_expansion_score=0.05,
        oi_expansion_score=0.05,
        breakout_structure_score=0.05,
        funding_rate=0.0001,
        market_regime=MarketRegime.BTC_ABSORPTION,
    ),
    MarketScenario.WEAK_PUMP: _ScenarioShape(
        base_price=1.0,
        price_path=(1.0, 1.01, 1.015, 1.012, 1.014),
        volume=22_000.0,
        spread_bps=6.0,
        estimated_slippage_bps=7.0,
        liquidity_score=0.55,
        volatility_score=0.3,
        volume_expansion_score=0.3,
        oi_expansion_score=0.25,
        breakout_structure_score=0.3,
        funding_rate=0.0002,
        market_regime=MarketRegime.SECTOR_ROTATION,
    ),
    MarketScenario.RIGHT_TAIL_BREAKOUT: _ScenarioShape(
        base_price=1.0,
        price_path=(1.0, 1.05, 1.14, 1.28, 1.42),
        volume=180_000.0,
        spread_bps=5.0,
        estimated_slippage_bps=6.0,
        liquidity_score=0.82,
        volatility_score=0.85,
        volume_expansion_score=0.92,
        oi_expansion_score=0.88,
        breakout_structure_score=0.9,
        funding_rate=0.0003,
        market_regime=MarketRegime.MEME_RISK_ON,
    ),
    MarketScenario.FAKE_BREAKOUT_REVERSAL: _ScenarioShape(
        base_price=1.0,
        # Pops up then collapses BELOW the entry zone (triggers stop / exit).
        price_path=(1.0, 1.12, 1.18, 0.96, 0.88),
        volume=150_000.0,
        spread_bps=7.0,
        estimated_slippage_bps=9.0,
        liquidity_score=0.78,
        volatility_score=0.9,
        volume_expansion_score=0.85,
        oi_expansion_score=0.8,
        breakout_structure_score=0.82,
        funding_rate=0.0004,
        market_regime=MarketRegime.MEME_RISK_ON,
    ),
    MarketScenario.FUNDING_NEGATIVE_HOLD: _ScenarioShape(
        base_price=1.0,
        price_path=(1.0, 1.06, 1.16, 1.30, 1.33),
        volume=170_000.0,
        spread_bps=5.0,
        estimated_slippage_bps=6.0,
        liquidity_score=0.8,
        volatility_score=0.8,
        volume_expansion_score=0.9,
        oi_expansion_score=0.85,
        breakout_structure_score=0.88,
        funding_rate=-0.0006,  # negative funding -> longs PAY funding fee
        market_regime=MarketRegime.MEME_RISK_ON,
    ),
    MarketScenario.FUNDING_POSITIVE_HOLD: _ScenarioShape(
        base_price=1.0,
        price_path=(1.0, 1.06, 1.16, 1.30, 1.33),
        volume=170_000.0,
        spread_bps=5.0,
        estimated_slippage_bps=6.0,
        liquidity_score=0.8,
        volatility_score=0.8,
        volume_expansion_score=0.9,
        oi_expansion_score=0.85,
        breakout_structure_score=0.88,
        funding_rate=0.0006,  # positive funding -> longs RECEIVE funding income
        market_regime=MarketRegime.MEME_RISK_ON,
    ),
    MarketScenario.SPREAD_LIQUIDITY_BAD: _ScenarioShape(
        base_price=1.0,
        price_path=(1.0, 1.08, 1.2, 1.32, 1.4),
        volume=4_000.0,
        spread_bps=140.0,  # far above any profile slippage floor
        estimated_slippage_bps=180.0,
        liquidity_score=0.05,  # below every profile's min_exit_liquidity_score
        volatility_score=0.9,
        volume_expansion_score=0.9,
        oi_expansion_score=0.85,
        breakout_structure_score=0.88,
        funding_rate=0.0003,
        market_regime=MarketRegime.MEME_RISK_ON,
    ),
    MarketScenario.EXCHANGE_FAILURE_MID_TRADE: _ScenarioShape(
        base_price=1.0,
        price_path=(1.0, 1.05, 1.14, 1.28, 1.42),
        volume=180_000.0,
        spread_bps=5.0,
        estimated_slippage_bps=6.0,
        liquidity_score=0.82,
        volatility_score=0.85,
        volume_expansion_score=0.92,
        oi_expansion_score=0.88,
        breakout_structure_score=0.9,
        funding_rate=0.0003,
        market_regime=MarketRegime.MEME_RISK_ON,
    ),
}

# Base timestamp (deterministic; no wall-clock dependency).
_BASE_TS = 1_700_000_000_000


@dataclass(frozen=True)
class FakeMarketSeries:
    """A deterministic series of frames for one scenario + helpers."""

    scenario: str
    symbol: str
    frames: tuple[MarketFrame, ...]

    @property
    def first(self) -> MarketFrame:
        return self.frames[0]

    @property
    def last(self) -> MarketFrame:
        return self.frames[-1]

    @property
    def entry_frame(self) -> MarketFrame:
        """The frame at which a right-tail entry would be planned.

        The breakout is confirmed by the second frame in every shape.
        """
        return self.frames[min(1, len(self.frames) - 1)]

    @property
    def peak_price(self) -> float:
        return max(f.price for f in self.frames)

    @property
    def trough_price(self) -> float:
        return min(f.price for f in self.frames)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "symbol": self.symbol,
            "frame_count": len(self.frames),
            "frames": [f.to_dict() for f in self.frames],
        }


class FakeLiveMarketAdapter:
    """A deterministic fake live market source for the sandbox audit.

    NOT a blind / replay / sim source: it represents a LIVE-equivalent
    market so the real live chain can run. It never emits a future label.
    """

    name = "FakeLiveMarketAdapter"

    def __init__(self, symbol: str = DEFAULT_SANDBOX_SYMBOL) -> None:
        self.symbol = symbol

    def scenarios(self) -> tuple[str, ...]:
        return ALL_MARKET_SCENARIOS

    def series(self, scenario: str, *, frame_count: int = 5) -> FakeMarketSeries:
        """Build a deterministic :class:`FakeMarketSeries` for ``scenario``."""
        if scenario not in _SHAPES:
            raise ValueError(f"unknown market scenario: {scenario!r}")
        shape = _SHAPES[scenario]
        path = shape.price_path
        frames: list[MarketFrame] = []
        n = max(frame_count, len(path))
        for i in range(n):
            factor = path[i] if i < len(path) else path[-1]
            price = round(shape.base_price * factor, 8)
            frames.append(
                MarketFrame(
                    timestamp=_BASE_TS + i * 60_000,
                    symbol=self.symbol,
                    price=price,
                    volume=shape.volume,
                    spread_bps=shape.spread_bps,
                    estimated_slippage_bps=shape.estimated_slippage_bps,
                    liquidity_score=shape.liquidity_score,
                    volatility_score=shape.volatility_score,
                    volume_expansion_score=shape.volume_expansion_score,
                    oi_expansion_score=shape.oi_expansion_score,
                    breakout_structure_score=shape.breakout_structure_score,
                    funding_rate=shape.funding_rate,
                    market_regime=shape.market_regime,
                    systemic_risk_state=shape.systemic_risk_state,
                )
            )
        return FakeMarketSeries(scenario=scenario, symbol=self.symbol, frames=tuple(frames))


__all__ = [
    "FAKE_LIVE_MARKET_MODULE",
    "FAKE_LIVE_MARKET_SOURCE",
    "DEFAULT_SANDBOX_SYMBOL",
    "MarketScenario",
    "ALL_MARKET_SCENARIOS",
    "MarketFrame",
    "FakeMarketSeries",
    "FakeLiveMarketAdapter",
]
