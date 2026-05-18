"""Regime Engine (Phase 5 - Issue #5).

The engine takes a :class:`RegimeInput` (or a Phase 4 buffer plus a
BTC reference symbol) and produces one :class:`RegimeSnapshot`. The
output is determined by:

  1. A SYSTEMIC_RISK override (explicit flag, big BTC drop, or extreme
     realised vol) - if any fires, regime is :attr:`MarketRegime.SYSTEMIC_RISK`
     and risk_permission is :attr:`RiskPermission.BLOCK_ALL`.
  2. A degraded-data override - if the input is flagged
     ``data_degraded=True`` we fall back to ``ALT_RISK_OFF`` /
     ``OBSERVE_ONLY`` and tag the reason. The Phase 5 hard rule
     "数据 degraded 时必须降级" lives here.
  3. A trend / vol / liquidity classifier producing one of the four
     non-systemic regimes. Spec §15.2 maps:

        MEME_RISK_ON     - BTC up + EXPANDING liquidity (or stable
                           liquidity with normal vol)
        SECTOR_ROTATION  - BTC sideways + STABLE liquidity
        BTC_ABSORPTION   - BTC up + alt liquidity contracting (alts
                           bleed into BTC)
        ALT_RISK_OFF     - BTC down + DRY/CONTRACTING liquidity, or
                           BTC down for >= configured streak

The engine emits one ``REGIME_UPDATED`` event through the supplied
:class:`EventRepository` whenever evaluate is called. The event
payload mirrors Spec §15.1.

Phase 5 boundary
----------------

The engine does NOT trade. It does NOT call any LLM. It does NOT
import an exchange SDK or open any socket. It does NOT amplify a
position. It does NOT modify the Phase 1 safety lock. It does NOT
add a write surface. The Risk Engine (Issue #7) is the only module
that ever turns a :class:`RegimeSnapshot` into a trading action.
"""

from __future__ import annotations

from typing import Iterable

from loguru import logger

from app.core.clock import now_ms
from app.core.enums import (
    AltLiquidity,
    BtcTrend,
    BtcVolatility,
    MarketRegime,
    RiskPermission,
)
from app.core.events import Event, EventType
from app.database.repositories import EventRepository
from app.regime.models import (
    REGIME_TO_RISK_PERMISSION,
    RegimeConfig,
    RegimeInput,
    RegimeSnapshot,
)


class RegimeEngine:
    """Pure classifier mapping (BTC trend, BTC vol, alt liquidity,
    overrides) to a :class:`RegimeSnapshot`.

    Phase 5 keeps the engine stateless: every call to
    :meth:`evaluate_input` is independent. Issue #6 / #7 may add a
    small history buffer (e.g. EMA smoothing of the regime label) but
    that is out of scope here.
    """

    SOURCE_MODULE = "regime.engine"

    def __init__(
        self,
        *,
        config: RegimeConfig | None = None,
        event_repo: EventRepository | None = None,
    ) -> None:
        self._config = config or RegimeConfig()
        self._event_repo = event_repo
        self._evaluations: int = 0
        self._regime_updated_emitted: int = 0

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------
    @property
    def config(self) -> RegimeConfig:
        return self._config

    @property
    def evaluations(self) -> int:
        return self._evaluations

    @property
    def regime_updated_events_emitted(self) -> int:
        return self._regime_updated_emitted

    # ------------------------------------------------------------------
    # Evaluate from a pre-built RegimeInput (preferred for tests + Issue
    # #7 wiring).
    # ------------------------------------------------------------------
    def evaluate_input(
        self, request: RegimeInput, *, emit_event: bool = True
    ) -> RegimeSnapshot:
        cfg = self._config
        reasons: list[str] = []

        # ---- Tier 1: SYSTEMIC_RISK override --------------------------
        if request.systemic_risk_override:
            reasons.append("systemic_risk_override")
            return self._finalise(
                request,
                regime=MarketRegime.SYSTEMIC_RISK,
                btc_trend=self._classify_trend(request),
                btc_vol=self._classify_volatility(request),
                alt_liquidity=self._classify_alt_liquidity(request),
                reasons=tuple(reasons),
                emit_event=emit_event,
            )

        if (
            request.btc_return_pct_window is not None
            and request.btc_return_pct_window <= cfg.systemic_risk_btc_drop_pct
        ):
            reasons.append("btc_drop_systemic")
            return self._finalise(
                request,
                regime=MarketRegime.SYSTEMIC_RISK,
                btc_trend=BtcTrend.DOWN,
                btc_vol=self._classify_volatility(request),
                alt_liquidity=self._classify_alt_liquidity(request),
                reasons=tuple(reasons),
                emit_event=emit_event,
            )

        if (
            request.btc_atr_pct is not None
            and request.btc_atr_pct >= cfg.systemic_risk_btc_extreme_vol_pct
        ):
            reasons.append("btc_extreme_volatility")
            return self._finalise(
                request,
                regime=MarketRegime.SYSTEMIC_RISK,
                btc_trend=self._classify_trend(request),
                btc_vol=BtcVolatility.EXTREME,
                alt_liquidity=self._classify_alt_liquidity(request),
                reasons=tuple(reasons),
                emit_event=emit_event,
            )

        # ---- Tier 2: Data degraded fallback --------------------------
        if request.data_degraded:
            reasons.append("data_degraded")
            return self._finalise(
                request,
                regime=MarketRegime.ALT_RISK_OFF,
                btc_trend=self._classify_trend(request),
                btc_vol=self._classify_volatility(request),
                alt_liquidity=AltLiquidity.UNKNOWN,
                reasons=tuple(reasons),
                emit_event=emit_event,
            )

        # ---- Tier 3: Normal classifier -------------------------------
        btc_trend = self._classify_trend(request)
        btc_vol = self._classify_volatility(request)
        alt_liq = self._classify_alt_liquidity(request)

        regime, reason = self._classify_regime(
            btc_trend=btc_trend,
            btc_vol=btc_vol,
            alt_liquidity=alt_liq,
            request=request,
        )
        reasons.append(reason)

        return self._finalise(
            request,
            regime=regime,
            btc_trend=btc_trend,
            btc_vol=btc_vol,
            alt_liquidity=alt_liq,
            reasons=tuple(reasons),
            emit_event=emit_event,
        )

    # ------------------------------------------------------------------
    # Convenience: build the input from a Phase 4 buffer
    # ------------------------------------------------------------------
    def evaluate_from_buffer(
        self,
        buffer,
        *,
        btc_symbol: str = "BTCUSDT",
        alt_symbols: Iterable[str] | None = None,
        emit_event: bool = True,
    ) -> RegimeSnapshot:
        """Build a :class:`RegimeInput` from a :class:`MarketDataBuffer`
        and evaluate it.

        Phase 5 keeps this helper conservative: the heavy lifting (return
        windows, multi-bar slope detection) belongs to Issue #6 / #7;
        here we use the existing buffer surface (snapshot, is_degraded)
        to populate the inputs.

        ``buffer`` is typed as the Phase 4 :class:`MarketDataBuffer`
        but kept as a duck-type so tests can substitute lightweight
        stubs without instantiating a full buffer.
        """
        cfg = self._config

        # Use the buffer's snapshot helper to read the BTC reference.
        # We pass emit_event=False so this convenience method does not
        # spam events.db with a MARKET_SNAPSHOT every time the regime
        # is evaluated; the regime engine emits its own REGIME_UPDATED.
        try:
            btc_snap = buffer.snapshot(btc_symbol, emit_event=False)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "[regime] BTC snapshot failed for {}: {}", btc_symbol, exc
            )
            btc_snap = None

        btc_last_price = btc_snap.last_price if btc_snap else None
        btc_atr_1m = btc_snap.atr_1m if btc_snap else None
        btc_atr_pct: float | None = None
        if btc_atr_1m is not None and btc_last_price is not None and btc_last_price > 0:
            btc_atr_pct = btc_atr_1m / btc_last_price

        # Phase 5 uses the simplest possible window-return estimate:
        # `cvd_5m` agreement is too noisy to feed the regime gate, but
        # `volume_5m` is. We fall back to UNKNOWN trend if we cannot
        # compute a return.
        btc_return_pct_window: float | None = None
        if btc_snap is not None and btc_snap.last_price > 0:
            try:
                # Use the difference of the most recent two closed 1m
                # bars to derive a window return. The buffer exposes
                # this through its private candle builder; we go through
                # `snapshot()` only and let the snapshot's last_price
                # vs the previous bar's close drive the trend label.
                # Issue #6 / #7 will replace this with a real slope
                # estimator over an N-bar window.
                bars = list(
                    getattr(
                        buffer._state_for(btc_symbol).candle_1m, "closed_bars", []
                    )
                )
                if len(bars) >= 2:
                    prev_close = bars[-2].close
                    if prev_close > 0:
                        btc_return_pct_window = (
                            (btc_snap.last_price - prev_close) / prev_close
                        )
            except Exception:  # pragma: no cover - best-effort only
                btc_return_pct_window = None

        # Aggregate alt liquidity ratio: short window vs long window
        # of total altcoin volume. We compute volume_5m vs (volume_5m
        # observed across the alt set + 1) to avoid div-by-zero. The
        # Phase 4 buffer doesn't yet retain a deeper history; we
        # therefore default to the "stable" zone if we cannot compute.
        alt_liquidity_ratio: float | None = None
        alt_syms = (
            list(alt_symbols)
            if alt_symbols is not None
            else [s for s in getattr(buffer, "symbols", ()) if s != btc_symbol]
        )
        if alt_syms:
            short_total = 0.0
            long_total = 0.0
            for sym in alt_syms:
                try:
                    snap = buffer.snapshot(sym, emit_event=False)
                except Exception:  # pragma: no cover - defensive
                    continue
                short_total += snap.volume_1m or 0.0
                long_total += snap.volume_5m or 0.0
            if long_total > 0.0:
                # short_total scaled to the same window so the ratio is
                # interpretable: 5x of 1m equals one 5m. We use 5x to
                # match the engine's threshold semantics.
                alt_liquidity_ratio = (short_total * 5.0) / long_total

        data_degraded = bool(getattr(buffer, "is_degraded", lambda _s: False)(btc_symbol))

        # BTC down streak: we look at the last few closed 1m bars and
        # count how many had a non-positive close-vs-open delta. This
        # is conservative on purpose; Issue #6 will replace it with a
        # proper structural test.
        down_streak = 0
        try:
            bars = list(
                getattr(
                    buffer._state_for(btc_symbol).candle_1m, "closed_bars", []
                )
            )
            for bar in reversed(bars[-cfg.alt_risk_off_min_btc_down_streak * 2 :]):
                if bar.close <= bar.open:
                    down_streak += 1
                else:
                    break
        except Exception:  # pragma: no cover - best-effort only
            down_streak = 0

        request = RegimeInput(
            btc_symbol=btc_symbol,
            btc_last_price=btc_last_price,
            btc_return_pct_window=btc_return_pct_window,
            btc_atr_pct=btc_atr_pct,
            btc_down_streak=down_streak,
            alt_liquidity_ratio=alt_liquidity_ratio,
            systemic_risk_override=False,
            data_degraded=data_degraded,
            timestamp=now_ms(),
        )
        return self.evaluate_input(request, emit_event=emit_event)

    # Public alias matching Issue #5 wording.
    def evaluate(
        self,
        request: RegimeInput | None = None,
        *,
        buffer=None,
        btc_symbol: str = "BTCUSDT",
        alt_symbols: Iterable[str] | None = None,
        emit_event: bool = True,
    ) -> RegimeSnapshot:
        if request is not None and buffer is not None:
            raise ValueError(
                "RegimeEngine.evaluate accepts either request= OR buffer=, "
                "not both."
            )
        if request is not None:
            return self.evaluate_input(request, emit_event=emit_event)
        if buffer is not None:
            return self.evaluate_from_buffer(
                buffer,
                btc_symbol=btc_symbol,
                alt_symbols=alt_symbols,
                emit_event=emit_event,
            )
        raise ValueError(
            "RegimeEngine.evaluate requires request= or buffer= to be set."
        )

    # ------------------------------------------------------------------
    # Internal classifiers
    # ------------------------------------------------------------------
    def _classify_trend(self, request: RegimeInput) -> BtcTrend:
        cfg = self._config
        ret = request.btc_return_pct_window
        if ret is None:
            return BtcTrend.UNKNOWN
        if ret >= cfg.btc_trend_up_pct:
            return BtcTrend.UP
        if ret <= cfg.btc_trend_down_pct:
            return BtcTrend.DOWN
        return BtcTrend.SIDEWAYS

    def _classify_volatility(self, request: RegimeInput) -> BtcVolatility:
        cfg = self._config
        atr_pct = request.btc_atr_pct
        if atr_pct is None:
            return BtcVolatility.UNKNOWN
        if atr_pct >= cfg.btc_vol_extreme_pct:
            return BtcVolatility.EXTREME
        if atr_pct >= cfg.btc_vol_high_pct:
            return BtcVolatility.HIGH
        if atr_pct < cfg.btc_vol_low_pct:
            return BtcVolatility.LOW
        return BtcVolatility.NORMAL

    def _classify_alt_liquidity(self, request: RegimeInput) -> AltLiquidity:
        cfg = self._config
        ratio = request.alt_liquidity_ratio
        if ratio is None:
            return AltLiquidity.UNKNOWN
        if ratio >= cfg.alt_liquidity_expanding_ratio:
            return AltLiquidity.EXPANDING
        if ratio >= cfg.alt_liquidity_stable_low:
            return AltLiquidity.STABLE
        if ratio >= cfg.alt_liquidity_contracting_low:
            return AltLiquidity.CONTRACTING
        return AltLiquidity.DRY

    def _classify_regime(
        self,
        *,
        btc_trend: BtcTrend,
        btc_vol: BtcVolatility,
        alt_liquidity: AltLiquidity,
        request: RegimeInput,
    ) -> tuple[MarketRegime, str]:
        """Map (trend, vol, liquidity) -> one of the four non-systemic
        regimes. Returns (regime, reason_tag).
        """
        cfg = self._config

        # 1. ALT_RISK_OFF: explicit DOWN trend that has persisted, or
        #    DOWN + dry liquidity.
        if btc_trend is BtcTrend.DOWN:
            if request.btc_down_streak >= cfg.alt_risk_off_min_btc_down_streak:
                return MarketRegime.ALT_RISK_OFF, "btc_down_streak"
            if alt_liquidity in (AltLiquidity.DRY, AltLiquidity.CONTRACTING):
                return MarketRegime.ALT_RISK_OFF, "btc_down_alt_dry"
            return MarketRegime.ALT_RISK_OFF, "btc_down_default"

        # 2. BTC_ABSORPTION: BTC up but altcoin liquidity is contracting
        #    or drying up.
        if btc_trend is BtcTrend.UP and alt_liquidity in (
            AltLiquidity.CONTRACTING,
            AltLiquidity.DRY,
        ):
            return MarketRegime.BTC_ABSORPTION, "btc_up_alt_contracting"

        # 3. MEME_RISK_ON: BTC up with expanding liquidity, OR BTC
        #    sideways with expanding liquidity AND non-low volatility.
        if btc_trend is BtcTrend.UP and alt_liquidity is AltLiquidity.EXPANDING:
            return MarketRegime.MEME_RISK_ON, "btc_up_alt_expanding"
        if (
            btc_trend is BtcTrend.SIDEWAYS
            and alt_liquidity is AltLiquidity.EXPANDING
            and btc_vol is not BtcVolatility.LOW
        ):
            return MarketRegime.MEME_RISK_ON, "btc_sideways_alt_expanding"

        # 4. SECTOR_ROTATION: BTC sideways with stable liquidity, or BTC
        #    up with stable liquidity (rotation between alt sectors).
        if btc_trend is BtcTrend.SIDEWAYS and alt_liquidity in (
            AltLiquidity.STABLE,
            AltLiquidity.EXPANDING,
        ):
            return MarketRegime.SECTOR_ROTATION, "btc_sideways_stable"
        if btc_trend is BtcTrend.UP and alt_liquidity is AltLiquidity.STABLE:
            return MarketRegime.SECTOR_ROTATION, "btc_up_stable"

        # 5. UNKNOWN inputs -> conservative ALT_RISK_OFF (Issue #5
        #    rule: when the gate cannot prove ALLOW, default to a
        #    risk-off label so downstream filters degrade safely).
        return MarketRegime.ALT_RISK_OFF, "regime_unknown_inputs"

    # ------------------------------------------------------------------
    # Snapshot construction + event emission
    # ------------------------------------------------------------------
    def _finalise(
        self,
        request: RegimeInput,
        *,
        regime: MarketRegime,
        btc_trend: BtcTrend,
        btc_vol: BtcVolatility,
        alt_liquidity: AltLiquidity,
        reasons: tuple[str, ...],
        emit_event: bool,
    ) -> RegimeSnapshot:
        risk_permission = REGIME_TO_RISK_PERMISSION[regime]
        snapshot = RegimeSnapshot(
            market_regime=regime,
            btc_trend=btc_trend,
            btc_volatility=btc_vol,
            alt_liquidity=alt_liquidity,
            risk_permission=risk_permission,
            reason_tags=reasons,
            btc_return_pct_window=request.btc_return_pct_window,
            btc_atr_pct=request.btc_atr_pct,
            alt_liquidity_ratio=request.alt_liquidity_ratio,
            timestamp=request.timestamp if request.timestamp is not None else now_ms(),
        )
        self._evaluations += 1
        if emit_event and self._event_repo is not None:
            self._event_repo.append_event(
                Event(
                    event_type=EventType.REGIME_UPDATED,
                    source_module=self.SOURCE_MODULE,
                    timestamp=snapshot.timestamp or now_ms(),
                    payload={
                        "market_regime": snapshot.market_regime.value,
                        "btc_trend": snapshot.btc_trend.value,
                        "btc_volatility": snapshot.btc_volatility.value,
                        "alt_liquidity": snapshot.alt_liquidity.value,
                        "risk_permission": snapshot.risk_permission.value,
                        "reason_tags": list(snapshot.reason_tags),
                        "btc_return_pct_window": snapshot.btc_return_pct_window,
                        "btc_atr_pct": snapshot.btc_atr_pct,
                        "alt_liquidity_ratio": snapshot.alt_liquidity_ratio,
                        "btc_symbol": request.btc_symbol,
                    },
                )
            )
            self._regime_updated_emitted += 1
        return snapshot
