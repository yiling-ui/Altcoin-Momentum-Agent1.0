"""Universe Filter (Phase 5 - Issue #5).

Spec §16. Decides eligibility per symbol against:

  - spread (must be <= ``max_spread_pct``)
  - depth (orderbook notional must be >= ``min_orderbook_depth_usdt``)
  - trade continuity (>= ``min_trade_count_5m`` trades in the last 5m)
  - contract status (must be in ``allowed_contract_statuses``)
  - data reliability (must be >= ``min_reliability``)
  - minimum volume (5m base volume >= ``min_volume_5m``)
  - abnormal data flag (any external system can set this; we reject)

Phase 5 also enforces:

  - data_degraded (from :class:`MarketDataBuffer.is_degraded`) is a
    hard reject. The Phase 5 boundary forbids feeding new openings
    while data is untrustworthy.
  - regime risk_permission in
    :attr:`UniverseConfig.blocking_risk_permissions` is a hard reject.
    SYSTEMIC_RISK is always in this set.

Every decision is recorded as one ``UNIVERSE_FILTERED`` event so
Reflection and Replay (Issue #10) can rebuild Phase 5 behaviour from
events.db alone.
"""

from __future__ import annotations

from typing import Iterable

from app.core.clock import now_ms
from app.core.enums import (
    DataReliability,
    MarketRegime,
    RiskPermission,
    UniverseRejectReason,
)
from app.core.events import Event, EventType
from app.core.models import MarketSnapshot
from app.database.repositories import EventRepository
from app.exchanges.models import ExchangeSymbol
from app.regime.models import RegimeSnapshot
from app.universe.models import UniverseConfig, UniverseDecision, UniverseInput


class UniverseFilter:
    """Stateless symbol-eligibility gate.

    Phase 5 keeps the filter stateless: each call to :meth:`evaluate`
    is independent. The filter:

      1. Reads :class:`UniverseInput` (or assembles one from a
         :class:`MarketSnapshot` + :class:`ExchangeSymbol` +
         optional :class:`RegimeSnapshot` for the higher-level
         :meth:`evaluate_with_buffer` helper).
      2. Walks every reject condition in order, collecting reasons.
      3. Emits one ``UNIVERSE_FILTERED`` event with the full reason
         list (empty when accepted) so events.db is the source of
         truth.

    Phase 5 hard rules enforced here (per Issue #5):

      - 1: SYSTEMIC_RISK -> reject every symbol.
      - 4: data degraded -> reject.
      - 5: every reject must carry a reject_reason.
      - 6: every reject must be persisted.
    """

    SOURCE_MODULE = "universe.filter"

    def __init__(
        self,
        *,
        config: UniverseConfig | None = None,
        event_repo: EventRepository | None = None,
    ) -> None:
        self._config = config or UniverseConfig()
        self._event_repo = event_repo
        self._evaluations: int = 0
        self._accepted: int = 0
        self._rejected: int = 0
        self._universe_filtered_emitted: int = 0
        self._universe_filtered_skipped: int = 0

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------
    @property
    def config(self) -> UniverseConfig:
        return self._config

    @property
    def evaluations(self) -> int:
        return self._evaluations

    @property
    def accepted(self) -> int:
        return self._accepted

    @property
    def rejected(self) -> int:
        return self._rejected

    @property
    def universe_filtered_events_emitted(self) -> int:
        return self._universe_filtered_emitted

    @property
    def universe_filtered_events_skipped(self) -> int:
        """Number of decisions that were NOT persisted because the
        per-call override or the :attr:`UniverseConfig.event_emit_enabled`
        config flag suppressed them. Phase 4 PR #15 review fix shape:
        observability for the throttle itself.
        """
        return self._universe_filtered_skipped

    # ------------------------------------------------------------------
    # Evaluate
    # ------------------------------------------------------------------
    def evaluate(
        self, request: UniverseInput, *, emit_event: bool | None = None
    ) -> UniverseDecision:
        cfg = self._config
        reasons: list[UniverseRejectReason] = []
        notes: list[str] = []

        # 1. Regime gate (Phase 5 hard rule 1).
        if (
            request.risk_permission is not None
            and request.risk_permission in cfg.blocking_risk_permissions
        ):
            reasons.append(UniverseRejectReason.REGIME_BLOCKED)
            notes.append(
                f"risk_permission={request.risk_permission.value}"
                + (
                    f" market_regime={request.market_regime.value}"
                    if request.market_regime is not None
                    else ""
                )
            )

        # 2. Data degraded (Phase 5 hard rule 4).
        if request.is_data_degraded:
            reasons.append(UniverseRejectReason.DATA_DEGRADED)
            notes.append("market_data_buffer reports degraded view")

        # 3. Abnormal data flag.
        if request.abnormal_data_flag:
            reasons.append(UniverseRejectReason.ABNORMAL_DATA_FLAG)
            notes.append("upstream abnormal_data_flag=true")

        # 4. Data reliability.
        if request.reliability is None or not request.reliability.is_at_least(
            cfg.min_reliability
        ):
            reasons.append(UniverseRejectReason.DATA_RELIABILITY_TOO_LOW)
            notes.append(
                "reliability="
                + (request.reliability.value if request.reliability else "None")
                + f" required>={cfg.min_reliability.value}"
            )

        # 5. Contract status (Spec §16.2).
        if request.contract_status not in cfg.allowed_contract_statuses:
            reasons.append(UniverseRejectReason.CONTRACT_NOT_TRADING)
            notes.append(f"contract_status={request.contract_status}")

        # 6. Spread.
        if request.spread_pct is None:
            reasons.append(UniverseRejectReason.SPREAD_TOO_WIDE)
            notes.append("spread_pct missing")
        elif request.spread_pct > cfg.max_spread_pct:
            reasons.append(UniverseRejectReason.SPREAD_TOO_WIDE)
            notes.append(
                f"spread_pct={request.spread_pct:.6f}"
                f" > max={cfg.max_spread_pct:.6f}"
            )

        # 7. Depth.
        if request.orderbook_depth_usdt is None:
            reasons.append(UniverseRejectReason.DEPTH_INSUFFICIENT)
            notes.append("orderbook_depth_usdt missing")
        elif request.orderbook_depth_usdt < cfg.min_orderbook_depth_usdt:
            reasons.append(UniverseRejectReason.DEPTH_INSUFFICIENT)
            notes.append(
                f"depth_usdt={request.orderbook_depth_usdt:.2f}"
                f" < min={cfg.min_orderbook_depth_usdt:.2f}"
            )

        # 8. Trade continuity.
        if request.trade_count_5m < cfg.min_trade_count_5m:
            reasons.append(UniverseRejectReason.TRADE_DISCONTINUOUS)
            notes.append(
                f"trade_count_5m={request.trade_count_5m}"
                f" < min={cfg.min_trade_count_5m}"
            )

        # 9. Minimum volume.
        if request.volume_5m < cfg.min_volume_5m:
            reasons.append(UniverseRejectReason.VOLUME_BELOW_MINIMUM)
            notes.append(
                f"volume_5m={request.volume_5m:.6f}"
                f" < min={cfg.min_volume_5m:.6f}"
            )

        eligible = not reasons
        # Deduplicate while preserving insertion order.
        seen: set[UniverseRejectReason] = set()
        ordered_reasons: list[UniverseRejectReason] = []
        for r in reasons:
            if r not in seen:
                seen.add(r)
                ordered_reasons.append(r)

        decision = UniverseDecision(
            symbol=request.symbol,
            eligible=eligible,
            reject_reasons=tuple(ordered_reasons),
            notes=tuple(notes),
            timestamp=request.timestamp if request.timestamp is not None else now_ms(),
        )
        self._evaluations += 1
        if eligible:
            self._accepted += 1
        else:
            self._rejected += 1
        # Resolve event-emission policy:
        #   emit_event=True  -> always emit (per-call override)
        #   emit_event=False -> always skip (per-call override)
        #   emit_event=None  -> follow self._config.event_emit_enabled
        should_emit = emit_event if emit_event is not None else self._config.event_emit_enabled
        if should_emit:
            self._record(decision, request)
        else:
            self._universe_filtered_skipped += 1
        return decision

    # ------------------------------------------------------------------
    # Convenience: build the input from a MarketSnapshot + ExchangeSymbol
    # ------------------------------------------------------------------
    def evaluate_snapshot(
        self,
        snapshot: MarketSnapshot,
        *,
        symbol_meta: ExchangeSymbol,
        regime: RegimeSnapshot | None = None,
        is_data_degraded: bool = False,
        abnormal_data_flag: bool = False,
        reliability: DataReliability = DataReliability.A,
        trade_count_5m: int | None = None,
        emit_event: bool | None = None,
    ) -> UniverseDecision:
        """Build a :class:`UniverseInput` from Phase 4 outputs and call
        :meth:`evaluate`. Tests also use this to keep call sites tidy.

        ``trade_count_5m`` is optional. If not supplied we approximate
        it from ``volume_5m > 0`` (>= 1 trade) so the gate degrades
        gracefully when the caller has not wired the metric in.
        """
        if trade_count_5m is None:
            trade_count_5m = 1 if (snapshot.volume_5m or 0.0) > 0 else 0
        request = UniverseInput(
            symbol=snapshot.symbol,
            contract_status=symbol_meta.status,
            spread_pct=snapshot.spread_pct,
            orderbook_depth_usdt=snapshot.orderbook_depth_usdt,
            trade_count_5m=trade_count_5m,
            volume_5m=snapshot.volume_5m,
            reliability=reliability,
            is_data_degraded=is_data_degraded,
            abnormal_data_flag=abnormal_data_flag,
            market_regime=regime.market_regime if regime is not None else None,
            risk_permission=regime.risk_permission if regime is not None else None,
            timestamp=snapshot.timestamp,
        )
        return self.evaluate(request, emit_event=emit_event)

    def evaluate_many(
        self, requests: Iterable[UniverseInput], *, emit_event: bool | None = None
    ) -> list[UniverseDecision]:
        return [self.evaluate(r, emit_event=emit_event) for r in requests]

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------
    def _record(self, decision: UniverseDecision, request: UniverseInput) -> None:
        if self._event_repo is None:
            return
        payload: dict[str, object] = {
            "symbol": decision.symbol,
            "eligible": decision.eligible,
            "reject_reasons": [r.value for r in decision.reject_reasons],
            "notes": list(decision.notes),
            "spread_pct": request.spread_pct,
            "orderbook_depth_usdt": request.orderbook_depth_usdt,
            "trade_count_5m": request.trade_count_5m,
            "volume_5m": request.volume_5m,
            "reliability": request.reliability.value if request.reliability else None,
            "is_data_degraded": request.is_data_degraded,
            "abnormal_data_flag": request.abnormal_data_flag,
            "contract_status": request.contract_status,
            "market_regime": (
                request.market_regime.value if request.market_regime else None
            ),
            "risk_permission": (
                request.risk_permission.value if request.risk_permission else None
            ),
        }
        self._event_repo.append_event(
            Event(
                event_type=EventType.UNIVERSE_FILTERED,
                source_module=self.SOURCE_MODULE,
                symbol=decision.symbol,
                timestamp=decision.timestamp or now_ms(),
                payload=payload,
            )
        )
        self._universe_filtered_emitted += 1
