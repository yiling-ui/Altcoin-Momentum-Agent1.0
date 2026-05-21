"""Phase 11C.1B - WS-radar event-chain driver (PR-B).

The :class:`WSRadarChainDriver` is the Phase 11C.1B equivalent of the
existing :class:`PaperEventChainDriver` but driven by an
:class:`AllMarketRadarSnapshot` instead of a
:class:`PublicSymbolSnapshot`. It exists for two reasons:

  1. The radar surface produces snapshots for *every* symbol Binance
     publishes on ``!ticker@arr`` - we never want every one of those
     to land in the Phase 8.5 learning-ready stream. The candidate
     pool is the gate, and the radar chain emits ONE chain per
     candidate per scan batch.
  2. The candidate pool already carries a Phase 8.5
     :class:`OpportunityIdentity` (assigned at admission). Reusing
     the existing ``PaperEventChainDriver`` would cause it to
     allocate a NEW identity on every drive and break the
     opportunity-id continuity. The Phase 11C.1B chain reuses the
     candidate's identity verbatim.

Phase 11C.1B contract:

  - the chain attaches a Phase 8.5 :class:`LearningReadyContext` to
    every ``PRE_ANOMALY_DETECTED`` / ``ANOMALY_DETECTED`` /
    ``STATE_TRANSITION`` it emits;
  - the chain calls the live :class:`RiskEngine` with
    ``stop_unconfirmed=True`` so EVERY decision falls into the
    typed-reject-reason path. Real market data drives the *decision
    pipeline* but never opens a real order;
  - the chain does NOT emit a ``MARKET_SNAPSHOT`` event - that surface
    belongs to :class:`PublicMarketIngestor` and lands only when the
    runner makes a per-loop REST detail call for the candidate;
  - the chain does NOT call any LLM / Telegram outbound / private
    endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.core.clock import now_ms
from app.core.enums import (
    AnomalyReasonTag,
    ConfirmationReasonTag,
    Direction,
    LiquidityRejectReason,
    ManipulationLevel,
    ManipulationReasonTag,
    MarketRegime,
    OpportunityGrade,
    PreAnomalyReasonTag,
    TradeConfirmationLevel,
    TradeState,
    TradeStateTrigger,
)
from app.core.events import Event, EventType
from app.core.models import SignalSnapshot
from app.database.repositories import EventRepository
from app.learning.context import LearningReadyContext, attach_learning_ready
from app.learning.versions import ConfigVersions
from app.learning.virtual_trade import VirtualTradePlan
from app.market_data_public.candidate_pool import Candidate
from app.market_data_public.radar import (
    RADAR_REASON_FUNDING_NOT_OVERHEATED,
    RADAR_REASON_LIQUIDATION_EVENT,
    RADAR_REASON_MARK_PRICE_ALIGNMENT,
    RADAR_REASON_PRICE_ACCEL_15S,
    RADAR_REASON_PRICE_ACCEL_60S,
    RADAR_REASON_QUOTE_VOLUME_DELTA_60S,
    RADAR_REASON_SPREAD_COMPRESSION,
    RADAR_REASON_VOLUME_RANK_JUMP,
)
from app.risk.engine import RiskEngine, RiskRequest


@dataclass(frozen=True)
class WSRadarChainResult:
    """Result of one Phase 11C.1B WS-radar chain pass."""

    symbol: str
    timestamp: int
    opportunity_id: str
    scan_batch_id: str
    radar_score: float
    risk_approved: bool
    reject_reasons: tuple[str, ...]
    learning_ready_attached: bool
    notes: tuple[str, ...]


class WSRadarChainDriver:
    """Drive the Phase 11C.1B WS-radar chain for one :class:`Candidate`."""

    SOURCE_MODULE = "market_data_public.ws_radar_chain"
    SOURCE_PHASE = "phase_11c_1b_ws_first_radar"

    def __init__(
        self,
        *,
        risk_engine: RiskEngine,
        event_repo: EventRepository,
        config_versions: ConfigVersions | None = None,
    ) -> None:
        self._risk = risk_engine
        self._event_repo = event_repo
        self._config_versions = config_versions or ConfigVersions.defaults()
        self._chain_count = 0
        self._risk_approved_count = 0
        self._risk_rejected_count = 0
        self._learning_ready_attached_count = 0

    # ------------------------------------------------------------------
    @property
    def chain_count(self) -> int:
        return self._chain_count

    @property
    def risk_approved_count(self) -> int:
        return self._risk_approved_count

    @property
    def risk_rejected_count(self) -> int:
        return self._risk_rejected_count

    @property
    def learning_ready_attached_count(self) -> int:
        return self._learning_ready_attached_count

    # ------------------------------------------------------------------
    def drive(self, candidate: Candidate) -> WSRadarChainResult:
        """Emit the Phase 11C.1B WS-radar chain for one candidate."""
        self._chain_count += 1
        snap = candidate.snapshot
        symbol = candidate.symbol
        timestamp = int(snap.timestamp or now_ms())
        notes: list[str] = []

        # The candidate already carries a Phase 8.5 identity; reuse it
        # so opportunity_id / scan_batch_id continuity is preserved.
        opportunity = candidate.identity

        # 1. PRE_ANOMALY_DETECTED with the radar reasons mapped onto
        #    the existing Phase 6 reason vocabulary.
        pre_anomaly_score = float(candidate.radar_score)
        pre_anomaly_tags = self._map_radar_reasons_to_pre_anomaly(
            candidate.reason_tags
        )
        pre_payload: dict[str, Any] = {
            "opportunity_id": opportunity.opportunity_id,
            "scan_batch_id": opportunity.scan_batch_id,
            "source_phase": self.SOURCE_PHASE,
            "pre_anomaly_score": pre_anomaly_score,
            "reason_tags": [t.value for t in pre_anomaly_tags],
            "radar_reason_tags": list(candidate.reason_tags),
            "radar_source_streams": list(candidate.source_streams),
            "candidate_state": candidate.state,
            "snapshot_summary": _radar_summary(snap),
        }
        # Drop a learning_ready block on the PRE_ANOMALY_DETECTED event
        # so Phase 8.5 export can pick it up directly without waiting
        # for the Risk Engine.
        signal = self._build_signal_snapshot(
            symbol=symbol, timestamp=timestamp,
            pre_anomaly_score=pre_anomaly_score,
            anomaly_score=pre_anomaly_score,  # radar score doubles as proxy
        )
        virtual_plan = self._build_virtual_trade_plan(snap=snap)
        learning_context = LearningReadyContext(
            opportunity=opportunity,
            signal_snapshot=signal,
            virtual_trade_plan=virtual_plan,
            config_versions=self._config_versions,
            source_phase=self.SOURCE_PHASE,
            extra={
                "radar_score": float(candidate.radar_score),
                "radar_reason_tags": list(candidate.reason_tags),
                "radar_source_streams": list(candidate.source_streams),
            },
        )
        self._emit(
            EventType.PRE_ANOMALY_DETECTED,
            symbol=symbol,
            timestamp=timestamp,
            payload=attach_learning_ready(pre_payload, learning_context),
        )

        # 2. ANOMALY_DETECTED. Use the same score; reason tags map to
        #    Phase 6 anomaly vocabulary (kept light because the buffer
        #    has no aligned histories).
        anomaly_tags = self._map_radar_reasons_to_anomaly(
            candidate.reason_tags
        )
        anomaly_payload: dict[str, Any] = {
            "opportunity_id": opportunity.opportunity_id,
            "scan_batch_id": opportunity.scan_batch_id,
            "source_phase": self.SOURCE_PHASE,
            "anomaly_score": pre_anomaly_score,
            "reason_tags": [t.value for t in anomaly_tags],
            "radar_reason_tags": list(candidate.reason_tags),
            "radar_source_streams": list(candidate.source_streams),
            "snapshot_summary": _radar_summary(snap),
        }
        self._emit(
            EventType.ANOMALY_DETECTED,
            symbol=symbol,
            timestamp=timestamp,
            payload=attach_learning_ready(anomaly_payload, learning_context),
        )

        # 3. Risk Engine. stop_unconfirmed=True locks every Phase 11C.1B
        #    decision into RISK_REJECTED.
        request = RiskRequest(
            source_module=self.SOURCE_MODULE,
            action="paper_observe_ws_radar",
            symbol=symbol,
            live_trading_required=False,
            right_tail_amplify=False,
            stop_unconfirmed=True,
            unknown_position=False,
            attack_intent=False,
            is_new_open=True,
            opportunity=opportunity,
            opportunity_id=opportunity.opportunity_id,
            virtual_trade_plan=virtual_plan,
            config_versions=self._config_versions,
            learning_context=learning_context,
            extra={
                "phase": "11C.1B",
                "provider": "binance_public_ws",
                "scan_batch_id": opportunity.scan_batch_id,
                "radar_score": float(candidate.radar_score),
            },
        )
        decision = self._risk.evaluate(request)
        if decision.approved:
            self._risk_approved_count += 1
        else:
            self._risk_rejected_count += 1

        # 4. STATE_TRANSITION marker so Reflection can group every
        #    radar chain by opportunity_id.
        self._emit_state_transition(
            symbol=symbol,
            timestamp=timestamp,
            opportunity=opportunity,
            risk_approved=decision.approved,
            reject_reasons=tuple(decision.reasons),
            learning_context=learning_context,
            radar_score=float(candidate.radar_score),
            candidate_state=candidate.state,
        )

        learning_attached = bool(decision.reasons or decision.approved)
        if learning_attached:
            self._learning_ready_attached_count += 1

        return WSRadarChainResult(
            symbol=symbol,
            timestamp=timestamp,
            opportunity_id=opportunity.opportunity_id,
            scan_batch_id=opportunity.scan_batch_id,
            radar_score=float(candidate.radar_score),
            risk_approved=decision.approved,
            reject_reasons=tuple(decision.reasons),
            learning_ready_attached=learning_attached,
            notes=tuple(notes),
        )

    # ------------------------------------------------------------------
    # Reason-tag mapping
    # ------------------------------------------------------------------
    @staticmethod
    def _map_radar_reasons_to_pre_anomaly(
        radar_tags: tuple[str, ...],
    ) -> tuple[PreAnomalyReasonTag, ...]:
        out: list[PreAnomalyReasonTag] = []
        if RADAR_REASON_QUOTE_VOLUME_DELTA_60S in radar_tags:
            out.append(PreAnomalyReasonTag.VOLUME_BASE_EXPANSION)
        if RADAR_REASON_SPREAD_COMPRESSION in radar_tags:
            out.append(PreAnomalyReasonTag.SPREAD_COMPRESSION)
        if RADAR_REASON_PRICE_ACCEL_15S in radar_tags:
            out.append(PreAnomalyReasonTag.MINOR_UPTREND)
        if RADAR_REASON_FUNDING_NOT_OVERHEATED in radar_tags:
            out.append(PreAnomalyReasonTag.FUNDING_NOT_OVERHEATED)
        if not out:
            out.append(PreAnomalyReasonTag.INSUFFICIENT_HISTORY)
        return tuple(out)

    @staticmethod
    def _map_radar_reasons_to_anomaly(
        radar_tags: tuple[str, ...],
    ) -> tuple[AnomalyReasonTag, ...]:
        out: list[AnomalyReasonTag] = []
        if (
            RADAR_REASON_PRICE_ACCEL_60S in radar_tags
            or RADAR_REASON_PRICE_ACCEL_15S in radar_tags
        ):
            out.append(AnomalyReasonTag.MULTI_TIMEFRAME_BREAKOUT)
        if RADAR_REASON_QUOTE_VOLUME_DELTA_60S in radar_tags:
            out.append(AnomalyReasonTag.VOLUME_SPIKE)
        if RADAR_REASON_LIQUIDATION_EVENT in radar_tags:
            out.append(AnomalyReasonTag.LIQUIDATION_SPIKE)
        if RADAR_REASON_VOLUME_RANK_JUMP in radar_tags:
            out.append(AnomalyReasonTag.VOLUME_SPIKE)
        if not out:
            out.append(AnomalyReasonTag.INSUFFICIENT_HISTORY)
        # Deduplicate while preserving order.
        seen: set[AnomalyReasonTag] = set()
        deduped: list[AnomalyReasonTag] = []
        for t in out:
            if t not in seen:
                seen.add(t)
                deduped.append(t)
        return tuple(deduped)

    # ------------------------------------------------------------------
    # SignalSnapshot + VirtualTradePlan helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_signal_snapshot(
        *,
        symbol: str,
        timestamp: int,
        pre_anomaly_score: float,
        anomaly_score: float,
    ) -> SignalSnapshot:
        return SignalSnapshot(
            symbol=symbol,
            timestamp=timestamp,
            regime=MarketRegime.SECTOR_ROTATION,
            pre_anomaly_score=float(pre_anomaly_score),
            anomaly_score=float(anomaly_score),
            liquidity_score=0.0,
            trade_confirmation_level=TradeConfirmationLevel.T0,
            manipulation_level=ManipulationLevel.M0,
            right_tail_score=0.0,
            opportunity_grade=OpportunityGrade.D,
            no_trade_reason=[
                "phase_11c_1b_ws_radar_paper_only",
                "stop_unconfirmed",
            ],
        )

    @staticmethod
    def _build_virtual_trade_plan(*, snap) -> VirtualTradePlan:
        ref_price = float(snap.last_price or 0.0)
        if ref_price <= 0 and snap.bid is not None and snap.ask is not None:
            if snap.bid > 0 and snap.ask > 0:
                ref_price = (float(snap.bid) + float(snap.ask)) / 2.0
        if ref_price <= 0:
            ref_price = max(float(snap.mark_price or 0.0), 1.0)
        stop = ref_price * 0.98
        tp1 = ref_price * 1.02
        tp2 = ref_price * 1.05
        invalid = ref_price * 0.97
        return VirtualTradePlan(
            virtual_entry=float(ref_price),
            virtual_stop=float(stop),
            virtual_tp1=float(tp1),
            virtual_tp2=float(tp2),
            invalid_price=float(invalid),
            suggested_leverage=1.0,
            risk_budget_pct=0.0,
            direction=Direction.LONG,
            setup_type="phase_11c_1b_ws_radar_observation",
            notes=("phase_11c_1b_ws_radar_paper_observation",),
        )

    # ------------------------------------------------------------------
    # Event emission helpers
    # ------------------------------------------------------------------
    def _emit(
        self,
        event_type: EventType,
        *,
        symbol: str,
        timestamp: int,
        payload: dict[str, Any],
    ) -> None:
        try:
            self._event_repo.append(
                Event(
                    event_type=event_type,
                    source_module=self.SOURCE_MODULE,
                    symbol=symbol,
                    timestamp=timestamp,
                    payload=payload,
                )
            )
        except Exception as exc:  # pragma: no cover - protective
            logger.error(
                "[phase11c.1b] failed to emit {} for {}: {}",
                event_type.value,
                symbol,
                exc,
            )

    def _emit_state_transition(
        self,
        *,
        symbol: str,
        timestamp: int,
        opportunity,
        risk_approved: bool,
        reject_reasons: tuple[str, ...],
        learning_context: LearningReadyContext,
        radar_score: float,
        candidate_state: str,
    ) -> None:
        target_state = (
            TradeState.OBSERVE if risk_approved else TradeState.NO_TRADE
        )
        trigger = (
            TradeStateTrigger.SIGNAL
            if risk_approved
            else TradeStateTrigger.DOWNGRADE
        )
        payload = attach_learning_ready(
            {
                "opportunity_id": opportunity.opportunity_id,
                "scan_batch_id": opportunity.scan_batch_id,
                "source_phase": self.SOURCE_PHASE,
                "from_state": TradeState.NO_TRADE.value,
                "to_state": target_state.value,
                "trigger": trigger.value,
                "reject_reasons": list(reject_reasons),
                "phase": "11C.1B",
                "radar_score": float(radar_score),
                "candidate_state": candidate_state,
            },
            learning_context,
        )
        self._emit(
            EventType.STATE_TRANSITION,
            symbol=symbol,
            timestamp=timestamp,
            payload=payload,
        )


def _radar_summary(snap) -> dict[str, Any]:
    return {
        "last_price": float(snap.last_price or 0.0),
        "price_change_pct_24h": (
            float(snap.price_change_pct_24h)
            if snap.price_change_pct_24h is not None
            else None
        ),
        "price_acceleration_15s": (
            float(snap.price_acceleration_15s)
            if snap.price_acceleration_15s is not None
            else None
        ),
        "price_acceleration_60s": (
            float(snap.price_acceleration_60s)
            if snap.price_acceleration_60s is not None
            else None
        ),
        "quote_volume": (
            float(snap.quote_volume) if snap.quote_volume is not None else None
        ),
        "quote_volume_delta_60s": (
            float(snap.quote_volume_delta_60s)
            if snap.quote_volume_delta_60s is not None
            else None
        ),
        "volume_rank": (
            int(snap.volume_rank) if snap.volume_rank is not None else None
        ),
        "volume_rank_jump": (
            int(snap.volume_rank_jump)
            if snap.volume_rank_jump is not None
            else None
        ),
        "spread_pct": (
            float(snap.spread_pct) if snap.spread_pct is not None else None
        ),
        "mark_price": (
            float(snap.mark_price) if snap.mark_price is not None else None
        ),
        "funding_rate": (
            float(snap.funding_rate) if snap.funding_rate is not None else None
        ),
        "liquidation_event": bool(snap.liquidation_event),
        "liquidation_notional": float(snap.liquidation_notional),
        "ws_source_flags": list(snap.ws_source_flags),
    }


__all__ = [
    "WSRadarChainDriver",
    "WSRadarChainResult",
]
