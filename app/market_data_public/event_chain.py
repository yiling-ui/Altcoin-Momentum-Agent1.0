"""Phase 11C - Paper event-chain driver from real public market data.

Given one :class:`PublicSymbolSnapshot` produced by
:class:`PublicMarketIngestor`, this driver emits the full Phase 11C
event chain:

    MARKET_SNAPSHOT       (already emitted by the ingestor)
    PRE_ANOMALY_DETECTED
    ANOMALY_DETECTED
    LIQUIDITY_CHECKED     (free-form summary, not a real Liquidity Filter pass)
    TRADE_CONFIRMED       (free-form summary, not the Phase 6 confirmation)
    MANIPULATION_DETECTED (free-form, M0 by default for Phase 11C)
    RISK_APPROVED  /  RISK_REJECTED
    STATE_TRANSITION

Phase 11C contract
------------------

  - Every ``RISK_REJECTED`` event MUST carry a Phase 8.5
    :class:`LearningReadyContext` with a real
    :class:`OpportunityIdentity` + :class:`SignalSnapshot` +
    :class:`VirtualTradePlan` + :class:`ConfigVersions`.
  - The Risk Engine is invoked with ``live_trading_required=False``,
    ``right_tail_amplify=False``, ``attack_intent=False``,
    ``stop_unconfirmed=True`` so EVERY decision falls into the
    typed-reject-reason path. This is the Phase 11C invariant: real
    market data drives the *decision pipeline* but never opens a real
    order.
  - The free-form ``LIQUIDITY_CHECKED`` / ``TRADE_CONFIRMED`` /
    ``MANIPULATION_DETECTED`` / ``STATE_TRANSITION`` events use the
    existing Phase 1-10 vocabulary. Phase 11C does NOT introduce any
    new EventType.
  - No write surface, no LLM, no Telegram outbound, no DeepSeek.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.core.clock import now_ms
from app.core.enums import (
    AnomalyReasonTag,
    ConfirmationReasonTag,
    LiquidityRejectReason,
    ManipulationLevel,
    ManipulationReasonTag,
    MarketRegime,
    OpportunityGrade,
    PreAnomalyReasonTag,
    RiskRejectReason,
    TradeConfirmationLevel,
    TradeState,
    TradeStateTrigger,
)
from app.core.events import Event, EventType
from app.core.models import SignalSnapshot
from app.database.repositories import EventRepository
from app.exchanges.binance_public import BinancePublicClient
from app.learning.context import LearningReadyContext, attach_learning_ready
from app.learning.identity import OpportunityIdentity
from app.learning.risk_payload import RiskRejectedLearningPayload
from app.learning.versions import ConfigVersions
from app.learning.virtual_trade import VirtualTradePlan
from app.market_data_public.ingest import PublicSymbolSnapshot
from app.risk.engine import RiskEngine, RiskRequest


@dataclass(frozen=True)
class PaperEventChainResult:
    """One pass of the Phase 11C paper event chain.

    Carries everything Reflection / the daily report wants to know
    about a single (symbol, snapshot) pair without re-querying the
    event log.
    """

    symbol: str
    timestamp: int
    opportunity_id: str
    scan_batch_id: str
    market_snapshot_emitted: bool
    pre_anomaly_score: float
    anomaly_score: float
    trade_confirmation_level: TradeConfirmationLevel
    manipulation_level: ManipulationLevel
    liquidity_passed: bool
    risk_approved: bool
    reject_reasons: tuple[str, ...]
    learning_ready_attached: bool
    notes: tuple[str, ...]


class PaperEventChainDriver:
    """Drive the Phase 11C event chain for a single :class:`PublicSymbolSnapshot`."""

    SOURCE_MODULE = "market_data_public.event_chain"
    SOURCE_PHASE = "phase_11c_public_market_paper"

    def __init__(
        self,
        *,
        risk_engine: RiskEngine,
        event_repo: EventRepository,
        public_client: BinancePublicClient | None = None,
        config_versions: ConfigVersions | None = None,
    ) -> None:
        self._risk = risk_engine
        self._event_repo = event_repo
        self._public_client = public_client
        self._config_versions = config_versions or ConfigVersions.defaults()
        self._scan_batch_id: str | None = None
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
    def begin_scan_batch(self, *, scan_batch_id: str | None = None) -> str:
        """Start a new scan batch. Returns the deterministic batch id.

        The id is reused for every chain emitted until the next call to
        :meth:`begin_scan_batch`. The runner calls this once per loop
        tick so every symbol's events share a batch.
        """
        from app.learning.identity import make_scan_batch_id

        self._scan_batch_id = make_scan_batch_id(scan_batch_id=scan_batch_id)
        return self._scan_batch_id

    # ------------------------------------------------------------------
    def drive(
        self,
        symbol_snapshot: PublicSymbolSnapshot,
        *,
        scan_batch_id: str | None = None,
    ) -> PaperEventChainResult:
        """Emit the Phase 11C event chain for one symbol snapshot."""
        if scan_batch_id is None:
            scan_batch_id = self._scan_batch_id or self.begin_scan_batch()

        self._chain_count += 1
        symbol = symbol_snapshot.symbol
        snap = symbol_snapshot.snapshot
        timestamp = int(snap.timestamp or now_ms())
        notes: list[str] = []

        # 1. Opportunity identity (deterministic per symbol+ts).
        opportunity = OpportunityIdentity.create(
            symbol=symbol,
            source_phase=self.SOURCE_PHASE,
            scan_batch_id=scan_batch_id,
            first_seen_ts=timestamp,
        )

        # 2. Pre-anomaly summary score (Phase 11C: cheap deterministic
        #    proxy off the snapshot, NOT a real Pre-Anomaly Scanner
        #    pass; the Phase 6 scanner needs aligned histories).
        pre_anomaly_score, pre_anomaly_tags = self._summarise_pre_anomaly(snap)
        self._emit(
            EventType.PRE_ANOMALY_DETECTED,
            symbol=symbol,
            timestamp=timestamp,
            payload={
                "opportunity_id": opportunity.opportunity_id,
                "scan_batch_id": opportunity.scan_batch_id,
                "source_phase": self.SOURCE_PHASE,
                "pre_anomaly_score": pre_anomaly_score,
                "reason_tags": [t.value for t in pre_anomaly_tags],
                "snapshot_summary": _snapshot_summary(snap),
                "is_degraded": symbol_snapshot.is_degraded,
                "degraded_reasons": list(symbol_snapshot.degraded_reasons),
            },
        )

        # 3. Anomaly summary score.
        anomaly_score, anomaly_tags = self._summarise_anomaly(snap)
        self._emit(
            EventType.ANOMALY_DETECTED,
            symbol=symbol,
            timestamp=timestamp,
            payload={
                "opportunity_id": opportunity.opportunity_id,
                "scan_batch_id": opportunity.scan_batch_id,
                "source_phase": self.SOURCE_PHASE,
                "anomaly_score": anomaly_score,
                "reason_tags": [t.value for t in anomaly_tags],
                "snapshot_summary": _snapshot_summary(snap),
            },
        )

        # 4. Liquidity summary. Phase 11C does NOT run the full
        #    LiquidityFilter (that would need fresh ExitPlan + slippage
        #    estimate); we record a summary so the event-chain shape
        #    matches every later phase.
        liquidity_passed = self._liquidity_summary(snap)
        liquidity_payload: dict[str, Any] = {
            "opportunity_id": opportunity.opportunity_id,
            "scan_batch_id": opportunity.scan_batch_id,
            "source_phase": self.SOURCE_PHASE,
            "passed": liquidity_passed,
            "spread_pct": snap.spread_pct,
            "orderbook_depth_usdt": snap.orderbook_depth_usdt,
            "volume_1m": snap.volume_1m,
            "volume_5m": snap.volume_5m,
            "reject_reasons": (
                []
                if liquidity_passed
                else [LiquidityRejectReason.SPREAD_TOO_WIDE.value]
            ),
        }
        self._emit(
            EventType.LIQUIDITY_CHECKED,
            symbol=symbol,
            timestamp=timestamp,
            payload=liquidity_payload,
        )

        # 5. Trade confirmation summary - Phase 11C records T0 by
        #    default; the dedicated Phase 6 confirmation engine runs
        #    later in the lifecycle.
        confirmation_level = TradeConfirmationLevel.T0
        confirmation_tags = (ConfirmationReasonTag.INSUFFICIENT_HISTORY,)
        self._emit(
            EventType.TRADE_CONFIRMED,
            symbol=symbol,
            timestamp=timestamp,
            payload={
                "opportunity_id": opportunity.opportunity_id,
                "scan_batch_id": opportunity.scan_batch_id,
                "source_phase": self.SOURCE_PHASE,
                "trade_confirmation_level": confirmation_level.value,
                "reason_tags": [t.value for t in confirmation_tags],
            },
        )

        # 6. Manipulation summary - Phase 11C records M0 by default.
        manipulation_level = ManipulationLevel.M0
        manipulation_tags = (ManipulationReasonTag.INSUFFICIENT_HISTORY,)
        self._emit(
            EventType.MANIPULATION_DETECTED,
            symbol=symbol,
            timestamp=timestamp,
            payload={
                "opportunity_id": opportunity.opportunity_id,
                "scan_batch_id": opportunity.scan_batch_id,
                "source_phase": self.SOURCE_PHASE,
                "manipulation_level": manipulation_level.value,
                "reason_tags": [t.value for t in manipulation_tags],
            },
        )

        # 7. Build the SignalSnapshot + VirtualTradePlan.
        signal = SignalSnapshot(
            symbol=symbol,
            timestamp=timestamp,
            regime=MarketRegime.SECTOR_ROTATION,
            pre_anomaly_score=pre_anomaly_score,
            anomaly_score=anomaly_score,
            liquidity_score=1.0 if liquidity_passed else 0.0,
            trade_confirmation_level=confirmation_level,
            manipulation_level=manipulation_level,
            right_tail_score=0.0,
            opportunity_grade=OpportunityGrade.D,
            no_trade_reason=[
                "phase_11c_paper_only",
                "stop_unconfirmed",
            ],
        )

        virtual_plan = self._build_virtual_trade_plan(snap)

        learning_context = LearningReadyContext(
            opportunity=opportunity,
            signal_snapshot=signal,
            virtual_trade_plan=virtual_plan,
            config_versions=self._config_versions,
            source_phase=self.SOURCE_PHASE,
        )

        # 8. Risk Engine adjudication. Phase 11C: stop_unconfirmed=True
        #    so the engine ALWAYS rejects the new-open path. This is
        #    the Phase 11C invariant: real market data drives the
        #    decision pipeline but never opens a real order.
        request = RiskRequest(
            source_module=self.SOURCE_MODULE,
            action="paper_observe",
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
                "phase": "11C",
                "provider": "binance_public",
                "scan_batch_id": opportunity.scan_batch_id,
                "is_degraded": symbol_snapshot.is_degraded,
            },
        )
        decision = self._risk.evaluate(request)
        if decision.approved:
            self._risk_approved_count += 1
        else:
            self._risk_rejected_count += 1
        # The Risk Engine itself emits RISK_APPROVED / RISK_REJECTED
        # with the learning_ready block; we do NOT re-emit.

        # 9. STATE_TRANSITION marker so Reflection can group every
        #    Phase 11C chain by opportunity_id.
        self._emit_state_transition(
            symbol=symbol,
            timestamp=timestamp,
            opportunity=opportunity,
            risk_approved=decision.approved,
            reject_reasons=tuple(decision.reasons),
            learning_context=learning_context,
        )

        learning_attached = bool(decision.reasons or decision.approved)
        if learning_attached:
            self._learning_ready_attached_count += 1

        return PaperEventChainResult(
            symbol=symbol,
            timestamp=timestamp,
            opportunity_id=opportunity.opportunity_id,
            scan_batch_id=opportunity.scan_batch_id,
            market_snapshot_emitted=True,
            pre_anomaly_score=pre_anomaly_score,
            anomaly_score=anomaly_score,
            trade_confirmation_level=confirmation_level,
            manipulation_level=manipulation_level,
            liquidity_passed=liquidity_passed,
            risk_approved=decision.approved,
            reject_reasons=tuple(decision.reasons),
            learning_ready_attached=learning_attached,
            notes=tuple(notes),
        )

    # ------------------------------------------------------------------
    # Pre-anomaly / anomaly summaries
    # ------------------------------------------------------------------
    @staticmethod
    def _summarise_pre_anomaly(snap) -> tuple[float, tuple[PreAnomalyReasonTag, ...]]:
        """Cheap deterministic Pre-Anomaly proxy.

        Phase 11C does NOT call the Phase 6 scanner directly because
        that requires a fully-warmed Phase 4 buffer (15m of history).
        We surface a low/medium score plus the relevant reason tags so
        the audit trail still records Phase 6's vocabulary.
        """
        tags: list[PreAnomalyReasonTag] = []
        score = 0.0
        if snap.volume_1m and snap.volume_5m and snap.volume_1m > snap.volume_5m / 5:
            tags.append(PreAnomalyReasonTag.VOLUME_BASE_EXPANSION)
            score += 15.0
        if snap.spread_pct is not None and snap.spread_pct < 0.0005:
            tags.append(PreAnomalyReasonTag.SPREAD_COMPRESSION)
            score += 15.0
        if snap.cvd_1m is not None and snap.cvd_1m > 0:
            tags.append(PreAnomalyReasonTag.BUY_PRESSURE_RISING)
            score += 15.0
        if not tags:
            tags.append(PreAnomalyReasonTag.INSUFFICIENT_HISTORY)
        return min(score, 100.0), tuple(tags)

    @staticmethod
    def _summarise_anomaly(snap) -> tuple[float, tuple[AnomalyReasonTag, ...]]:
        tags: list[AnomalyReasonTag] = []
        score = 0.0
        if snap.atr_1m is not None and snap.atr_5m is not None and snap.atr_5m > 0:
            if snap.atr_1m / snap.atr_5m >= 1.5:
                tags.append(AnomalyReasonTag.ATR_EXPANSION)
                score += 25.0
        if snap.volume_1m and snap.volume_5m and snap.volume_5m > 0:
            if snap.volume_1m / snap.volume_5m >= 0.5:
                # Mild signal; we don't claim a full "spike" without
                # baseline ratio.
                pass
        if not tags:
            tags.append(AnomalyReasonTag.INSUFFICIENT_HISTORY)
        return min(score, 100.0), tuple(tags)

    @staticmethod
    def _liquidity_summary(snap) -> bool:
        if snap.spread_pct is None or snap.bid <= 0 or snap.ask <= 0:
            return False
        if snap.spread_pct > 0.005:
            return False
        return True

    # ------------------------------------------------------------------
    # VirtualTradePlan helper
    # ------------------------------------------------------------------
    @staticmethod
    def _build_virtual_trade_plan(snap) -> VirtualTradePlan:
        from app.core.enums import Direction

        # Phase 11C: paper-only descriptive plan. NOT an authorisation
        # to trade. Long bias by convention; the entry is the current
        # mid (or last_price), stop -2%, TP1 +2%, TP2 +5%.
        ref_price = snap.last_price or (
            (snap.bid + snap.ask) / 2.0 if snap.bid > 0 and snap.ask > 0 else 0.0
        )
        if ref_price <= 0:
            ref_price = max(snap.mark_price or 0.0, 1.0)
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
            setup_type="phase_11c_observation",
            notes=("phase_11c_paper_observation",),
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
        self._event_repo.append(
            Event(
                event_type=event_type,
                source_module=self.SOURCE_MODULE,
                symbol=symbol,
                timestamp=timestamp,
                payload=payload,
            )
        )

    def _emit_state_transition(
        self,
        *,
        symbol: str,
        timestamp: int,
        opportunity: OpportunityIdentity,
        risk_approved: bool,
        reject_reasons: tuple[str, ...],
        learning_context: LearningReadyContext,
    ) -> None:
        # Phase 11C never approves a new open (stop_unconfirmed=True)
        # so the canonical transition is OBSERVE -> NO_TRADE with the
        # reject_reasons attached as the trigger context.
        target_state = (
            TradeState.OBSERVE if risk_approved else TradeState.NO_TRADE
        )
        trigger = (
            TradeStateTrigger.SIGNAL if risk_approved else TradeStateTrigger.DOWNGRADE
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
                "phase": "11C",
            },
            learning_context,
        )
        self._event_repo.append(
            Event(
                event_type=EventType.STATE_TRANSITION,
                source_module=self.SOURCE_MODULE,
                symbol=symbol,
                timestamp=timestamp,
                payload=payload,
            )
        )


def _snapshot_summary(snap) -> dict[str, Any]:
    """Return a JSON-safe slice of a :class:`MarketSnapshot`."""
    return {
        "last_price": snap.last_price,
        "mark_price": snap.mark_price,
        "bid": snap.bid,
        "ask": snap.ask,
        "spread_pct": snap.spread_pct,
        "volume_1m": snap.volume_1m,
        "volume_5m": snap.volume_5m,
        "oi": snap.oi,
        "funding_rate": snap.funding_rate,
        "cvd_1m": snap.cvd_1m,
        "cvd_5m": snap.cvd_5m,
        "atr_1m": snap.atr_1m,
        "atr_5m": snap.atr_5m,
        "orderbook_depth_usdt": snap.orderbook_depth_usdt,
    }


__all__ = [
    "PaperEventChainDriver",
    "PaperEventChainResult",
]
