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

Phase 11C.1C-A extension
------------------------

The chain now also emits the six Phase 11C.1C-A typed events
alongside the existing chain (``MARKET_REGIME_ASSESSED`` /
``CANDIDATE_STAGE_CLASSIFIED`` / ``OPPORTUNITY_SCORED`` /
``STRATEGY_MODE_SELECTED`` / ``CLUSTER_CONTEXT_ATTACHED`` /
``LABEL_QUEUE_ENQUEUED``) and attaches the resulting
:class:`AdaptiveCandidateContext` to the existing
:class:`LearningReadyContext` (under ``learning_ready.adaptive_candidate``).

The adaptive context is **descriptive only** - the strategy_mode is
a paper / virtual field; the Risk Engine remains the single trade-
decision gate; ``stop_unconfirmed=True`` continues to lock every
decision into the typed-reject path. None of the adaptive events
flips a Phase 1 safety flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.adaptive import (
    AdaptiveCandidateContext,
    OpportunityScoreInputs,
    build_adaptive_candidate_context,
    compute_runtime_calibration,
)
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
    # Phase 11C.1C-A - adaptive context surface. ``None`` when the
    # adaptive context could not be built (extremely defensive); on
    # the happy path every field is populated.
    adaptive_context: AdaptiveCandidateContext | None = None


class WSRadarChainDriver:
    """Drive the Phase 11C.1B WS-radar chain for one :class:`Candidate`."""

    SOURCE_MODULE = "market_data_public.ws_radar_chain"
    SOURCE_PHASE = "phase_11c_1b_ws_first_radar"
    # Phase 11C.1C-A - source-phase tag for the adaptive sub-block.
    # Distinct from :attr:`SOURCE_PHASE` so Reflection can split the
    # adaptive vs. non-adaptive parts of the chain.
    ADAPTIVE_SOURCE_PHASE = "phase_11c_1c_a_adaptive_candidate"
    # Phase 11C.1C-B - source-phase tag for the runtime calibration
    # sub-block. Distinct from :attr:`ADAPTIVE_SOURCE_PHASE` so
    # Reflection can group runtime calibration / early-tail-discovery
    # decisions independently of the underlying adaptive contract.
    RUNTIME_CALIBRATION_SOURCE_PHASE = "phase_11c_1c_b_runtime_calibration"

    def __init__(
        self,
        *,
        risk_engine: RiskEngine,
        event_repo: EventRepository,
        config_versions: ConfigVersions | None = None,
        candidate_pool=None,
    ) -> None:
        self._risk = risk_engine
        self._event_repo = event_repo
        self._config_versions = config_versions or ConfigVersions.defaults()
        # Phase 11C.1C-B - optional candidate pool handle so the
        # driver can write the runtime metrics
        # (early_tail_score / late_chase_risk_score / freshness)
        # back onto the candidate after each pass. Falling back to
        # ``None`` keeps the existing 11C.1C-A unit tests working
        # without a pool.
        self._candidate_pool = candidate_pool
        self._chain_count = 0
        self._risk_approved_count = 0
        self._risk_rejected_count = 0
        self._learning_ready_attached_count = 0
        # Phase 11C.1C-A - adaptive event counters.
        self._market_regime_assessed_count = 0
        self._candidate_stage_classified_count = 0
        self._opportunity_scored_count = 0
        self._strategy_mode_selected_count = 0
        self._cluster_context_attached_count = 0
        self._label_queue_enqueued_count = 0
        # Per-grade / per-mode / per-stage histograms for the daily
        # report. Keys are the canonical labels in
        # :data:`OPPORTUNITY_GRADES` / :data:`STRATEGY_MODES` /
        # :data:`CANDIDATE_STAGES`.
        self._opportunity_grade_counts: dict[str, int] = {}
        self._strategy_mode_counts: dict[str, int] = {}
        self._candidate_stage_counts: dict[str, int] = {}
        self._market_regime_counts: dict[str, int] = {}
        self._top_opportunity_scores: list[
            tuple[str, str, float, str]
        ] = []  # (symbol, opp_id, score, grade)
        self._observe_count = 0
        self._reject_count = 0
        self._follow_count = 0
        self._pullback_count = 0
        self._late_chase_rejected_count = 0
        self._blowoff_observed_count = 0
        # Phase 11C.1C-B runtime-calibration counters + per-symbol
        # rolling top lists. Capped at 50 entries each so a long
        # run does not grow the in-process state unbounded.
        self._top_early_tail_scores: list[
            tuple[str, str, float, float]
        ] = []  # (symbol, opp_id, early_tail_score, freshness)
        self._top_late_chase_risk_scores: list[
            tuple[str, str, float, str]
        ] = []  # (symbol, opp_id, late_chase_risk_score, stage)
        self._opportunity_score_distribution: dict[str, int] = {}
        self._symbols_promoted_before_24h_top_move: list[
            tuple[str, str, int]
        ] = []  # (symbol, opp_id, ts_ms)

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

    # ---- Phase 11C.1C-A counters --------------------------------------
    @property
    def market_regime_assessed_count(self) -> int:
        return self._market_regime_assessed_count

    @property
    def candidate_stage_classified_count(self) -> int:
        return self._candidate_stage_classified_count

    @property
    def opportunity_scored_count(self) -> int:
        return self._opportunity_scored_count

    @property
    def strategy_mode_selected_count(self) -> int:
        return self._strategy_mode_selected_count

    @property
    def cluster_context_attached_count(self) -> int:
        return self._cluster_context_attached_count

    @property
    def label_queue_enqueued_count(self) -> int:
        return self._label_queue_enqueued_count

    def adaptive_metrics_payload(self) -> dict[str, Any]:
        """Return a JSON-safe dict of Phase 11C.1C-A adaptive metrics.

        Used by the runner / daily-report builder to surface the
        adaptive counters without re-querying events.db.

        Phase 11C.1C-B additions:

          - ``top_early_tail_candidates`` - top symbols by
            ``early_tail_score`` (desc, capped at 10).
          - ``top_late_chase_risk_candidates`` - top symbols by
            ``late_chase_risk`` (desc, capped at 10).
          - ``early_tail_score_top_symbols`` - alias kept for the
            brief-mandated daily-report field name.
          - ``opportunity_score_distribution`` - bucketed
            distribution of opportunity scores (10-point bins).
          - ``symbols_promoted_before_24h_top_move`` - candidates
            whose admission preceded the 24h top print.
          - ``eden_alt_near_examples`` - canonical EDEN / ALT /
            NEAR-style demon-coin examples observed in the run
            (so the brief's "EDEN/ALT/NEAR style candidate examples
            if present" surfaces in the daily report).
        """
        # Top opportunity scores ordered desc by score, capped at 10.
        top = sorted(
            self._top_opportunity_scores,
            key=lambda r: -r[2],
        )[:10]
        # Phase 11C.1C-B - early-tail / late-chase aggregates.
        top_early_tail = sorted(
            (row for row in self._top_early_tail_scores if row[2] > 0.0),
            key=lambda r: -r[2],
        )[:10]
        top_late_chase = sorted(
            (
                row
                for row in self._top_late_chase_risk_scores
                if row[2] > 0.0
            ),
            key=lambda r: -r[2],
        )[:10]
        eden_alt_near = self._eden_alt_near_examples()
        return {
            "market_regime_assessed_count": int(
                self._market_regime_assessed_count
            ),
            "candidate_stage_classified_count": int(
                self._candidate_stage_classified_count
            ),
            "opportunity_scored_count": int(self._opportunity_scored_count),
            "strategy_mode_selected_count": int(
                self._strategy_mode_selected_count
            ),
            "cluster_context_attached_count": int(
                self._cluster_context_attached_count
            ),
            "label_queue_enqueued_count": int(
                self._label_queue_enqueued_count
            ),
            "market_regime_counts": dict(self._market_regime_counts),
            "candidate_stage_counts": dict(self._candidate_stage_counts),
            "strategy_mode_counts": dict(self._strategy_mode_counts),
            "opportunity_grade_counts": dict(self._opportunity_grade_counts),
            "follow_count": int(self._follow_count),
            "pullback_count": int(self._pullback_count),
            "observe_count": int(self._observe_count),
            "reject_count": int(self._reject_count),
            "late_chase_rejected_count": int(self._late_chase_rejected_count),
            "blowoff_observed_count": int(self._blowoff_observed_count),
            "top_opportunity_scores": [
                {
                    "symbol": sym,
                    "opportunity_id": opp_id,
                    "score": float(score),
                    "grade": grade,
                }
                for sym, opp_id, score, grade in top
            ],
            "label_queue_enqueued": int(self._label_queue_enqueued_count),
            # Phase 11C.1C-B - runtime calibration aggregates.
            "top_early_tail_candidates": [
                {
                    "symbol": sym,
                    "opportunity_id": opp_id,
                    "early_tail_score": float(score),
                    "freshness_score": float(fresh),
                }
                for sym, opp_id, score, fresh in top_early_tail
            ],
            "top_late_chase_risk_candidates": [
                {
                    "symbol": sym,
                    "opportunity_id": opp_id,
                    "late_chase_risk": float(score),
                    "candidate_stage": stage,
                }
                for sym, opp_id, score, stage in top_late_chase
            ],
            "early_tail_score_top_symbols": [
                {"symbol": sym, "early_tail_score": float(score)}
                for sym, _opp_id, score, _fresh in top_early_tail
            ],
            "opportunity_score_distribution": dict(
                self._opportunity_score_distribution
            ),
            "symbols_promoted_before_24h_top_move": [
                {
                    "symbol": sym,
                    "opportunity_id": opp_id,
                    "timestamp_ms": int(ts),
                }
                for sym, opp_id, ts in self._symbols_promoted_before_24h_top_move
            ],
            "eden_alt_near_examples": eden_alt_near,
        }

    # ------------------------------------------------------------------
    # Phase 11C.1C-B - EDEN / ALT / NEAR-style canonical examples
    # ------------------------------------------------------------------
    # Static-ish allowlist of canonical demon-coin symbol stems used
    # to surface "EDEN / ALT / NEAR style candidate examples" in the
    # daily report. The matcher is exact-prefix on the upper-cased
    # symbol so non-ASCII contracts and unrelated symbols do not
    # accidentally match.
    _EDEN_ALT_NEAR_STEMS: tuple[str, ...] = (
        "EDEN",
        "ALT",
        "NEAR",
    )

    def _eden_alt_near_examples(self) -> list[dict[str, Any]]:
        """Return up to five EDEN / ALT / NEAR-style examples observed.

        The list is built from the in-process top-early-tail tracker
        so a candidate that was admitted but never received a
        meaningful early-tail score is excluded.
        """
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for sym, opp_id, score, fresh in sorted(
            self._top_early_tail_scores, key=lambda r: -r[2]
        ):
            symbol_upper = str(sym).upper()
            for stem in self._EDEN_ALT_NEAR_STEMS:
                if (
                    symbol_upper.startswith(stem)
                    and symbol_upper not in seen
                ):
                    seen.add(symbol_upper)
                    out.append(
                        {
                            "symbol": sym,
                            "opportunity_id": opp_id,
                            "early_tail_score": float(score),
                            "freshness_score": float(fresh),
                        }
                    )
                    break
            if len(out) >= 5:
                break
        return out

    # ------------------------------------------------------------------
    def drive(self, candidate: Candidate) -> WSRadarChainResult:
        """Emit the Phase 11C.1B WS-radar chain for one candidate.

        Phase 11C.1C-A: also builds and emits the adaptive context
        events (``MARKET_REGIME_ASSESSED`` /
        ``CANDIDATE_STAGE_CLASSIFIED`` / ``OPPORTUNITY_SCORED`` /
        ``STRATEGY_MODE_SELECTED`` / ``CLUSTER_CONTEXT_ATTACHED`` /
        ``LABEL_QUEUE_ENQUEUED``) and attaches the adaptive context
        to the existing :class:`LearningReadyContext`.
        """
        self._chain_count += 1
        snap = candidate.snapshot
        symbol = candidate.symbol
        timestamp = int(snap.timestamp or now_ms())
        notes: list[str] = []

        # The candidate already carries a Phase 8.5 identity; reuse it
        # so opportunity_id / scan_batch_id continuity is preserved.
        opportunity = candidate.identity

        # 0. Phase 11C.1C-A - build the adaptive candidate context
        #    BEFORE the rest of the chain so every event the chain
        #    emits can carry the adaptive sub-block.
        adaptive = self._build_adaptive_context_for_candidate(
            candidate=candidate, timestamp=timestamp
        )

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
        virtual_plan = self._build_virtual_trade_plan(
            snap=snap, adaptive=adaptive
        )
        learning_context = LearningReadyContext(
            opportunity=opportunity,
            signal_snapshot=signal,
            virtual_trade_plan=virtual_plan,
            config_versions=self._config_versions,
            adaptive_candidate=adaptive,
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

        # 2b. Phase 11C.1C-A - emit the six adaptive events
        #     alongside the existing chain.
        self._emit_adaptive_events(
            adaptive=adaptive,
            symbol=symbol,
            timestamp=timestamp,
            learning_context=learning_context,
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
                "adaptive_strategy_mode": (
                    adaptive.strategy_mode.mode if adaptive else None
                ),
                "adaptive_opportunity_grade": (
                    adaptive.opportunity_score.grade if adaptive else None
                ),
                "adaptive_candidate_stage": (
                    adaptive.candidate_stage.stage if adaptive else None
                ),
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

        # 5. Phase 11C.1C-B - write the runtime calibration scores
        #    back onto the candidate so the next CandidatePool
        #    capacity-eviction pass can consult an up-to-date
        #    ``early_tail_score``. Also accumulate the top
        #    early-tail / late-chase aggregates the daily report
        #    consumes.
        self._write_runtime_metrics_to_candidate(
            candidate=candidate, adaptive=adaptive
        )

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
            adaptive_context=adaptive,
        )

    # ------------------------------------------------------------------
    # Phase 11C.1C-B - runtime metric write-back + aggregates
    # ------------------------------------------------------------------
    def _write_runtime_metrics_to_candidate(
        self,
        *,
        candidate: Candidate,
        adaptive: AdaptiveCandidateContext,
    ) -> None:
        """Push the runtime calibration scores back onto the
        candidate + accumulate top-N aggregates for the daily report.

        Pure I/O on in-process state; no external calls.
        """
        runtime = adaptive.runtime_calibration
        if runtime is None:
            return
        # Update mutable candidate fields directly (the candidate
        # dataclass is mutable).
        candidate.early_tail_score = float(runtime.early_tail_score)
        candidate.late_chase_risk_score = float(runtime.late_chase_risk)
        candidate.freshness_score = float(runtime.freshness_score)
        # ``promoted_before_24h_top_move``: we mark the candidate as
        # caught-before-top when its admission timestamp is at least
        # 5 minutes BEFORE the latest snapshot AND the snapshot's
        # 24h price-change percentage is positive (the high happened
        # after admission). The check is conservative; a candidate
        # only flips True once and never flips back.
        if not candidate.promoted_before_24h_top_move:
            elapsed_ms = int(adaptive.timestamp_ms) - int(
                candidate.first_seen_ms
            )
            change_pct_24h = (
                float(candidate.snapshot.price_change_pct_24h)
                if candidate.snapshot.price_change_pct_24h is not None
                else 0.0
            )
            if elapsed_ms >= 5 * 60 * 1000 and change_pct_24h > 0.0:
                candidate.promoted_before_24h_top_move = True
                self._symbols_promoted_before_24h_top_move.append(
                    (
                        candidate.symbol,
                        candidate.identity.opportunity_id,
                        int(adaptive.timestamp_ms),
                    )
                )
        # Mirror onto the optional candidate pool so an early-tail
        # candidate is protected from capacity eviction.
        if self._candidate_pool is not None:
            try:
                self._candidate_pool.update_runtime_metrics(
                    candidate.symbol,
                    early_tail_score=float(runtime.early_tail_score),
                    late_chase_risk_score=float(runtime.late_chase_risk),
                    freshness_score=float(runtime.freshness_score),
                    promoted_before_24h_top_move=bool(
                        candidate.promoted_before_24h_top_move
                    ),
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "[phase11c.1c-b] update_runtime_metrics failed "
                    "symbol={} exc={}",
                    candidate.symbol,
                    exc,
                )

        # Accumulate aggregates.
        self._top_early_tail_scores.append(
            (
                candidate.symbol,
                candidate.identity.opportunity_id,
                float(runtime.early_tail_score),
                float(runtime.freshness_score),
            )
        )
        if len(self._top_early_tail_scores) > 50:
            self._top_early_tail_scores.sort(key=lambda r: -r[2])
            self._top_early_tail_scores = self._top_early_tail_scores[:50]
        self._top_late_chase_risk_scores.append(
            (
                candidate.symbol,
                candidate.identity.opportunity_id,
                float(runtime.late_chase_risk),
                str(adaptive.candidate_stage.stage),
            )
        )
        if len(self._top_late_chase_risk_scores) > 50:
            self._top_late_chase_risk_scores.sort(key=lambda r: -r[2])
            self._top_late_chase_risk_scores = (
                self._top_late_chase_risk_scores[:50]
            )

        # Phase 11C.1C-B - opportunity-score distribution buckets.
        # Buckets are 10-point wide: 0..10, 10..20, ..., 90..100.
        score_value = float(adaptive.opportunity_score.score)
        bucket_lo = int(min(90, max(0, int(score_value // 10) * 10)))
        bucket = f"{bucket_lo}-{bucket_lo + 10}"
        self._opportunity_score_distribution[bucket] = (
            self._opportunity_score_distribution.get(bucket, 0) + 1
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
    def _build_virtual_trade_plan(
        *, snap, adaptive: AdaptiveCandidateContext | None = None
    ) -> VirtualTradePlan:
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

        # Phase 11C.1C-A - propagate the adaptive sub-block onto the
        # paper VirtualTradePlan. Every adaptive field is descriptive
        # only; nothing here authorises a real trade. The Risk Engine
        # remains the single trade-decision gate; ``stop_unconfirmed``
        # is True downstream so the engine refuses the new-open path
        # regardless of the paper plan content.
        if adaptive is not None:
            adaptive_kwargs: dict[str, Any] = {
                "opportunity_score": float(
                    adaptive.opportunity_score.score
                ),
                "opportunity_grade": str(adaptive.opportunity_score.grade),
                "candidate_stage": str(adaptive.candidate_stage.stage),
                "strategy_mode": str(adaptive.strategy_mode.mode),
                "cluster_id": str(adaptive.cluster.cluster_id),
                "cluster_leader": (
                    str(adaptive.cluster.cluster_leader)
                    if adaptive.cluster.cluster_leader is not None
                    else None
                ),
                "label_queue_pending": bool(
                    adaptive.label_queue.mfe_mae_label_pending
                    or adaptive.label_queue.future_tail_label_pending
                ),
                "follow_allowed": bool(adaptive.strategy_mode.follow_allowed),
                "pullback_allowed": bool(
                    adaptive.strategy_mode.pullback_allowed
                ),
                "observe_only": bool(adaptive.strategy_mode.observe_only),
                "reject_reason": adaptive.strategy_mode.reject_reason,
            }
        else:
            adaptive_kwargs = {}

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
            **adaptive_kwargs,
        )

    # ------------------------------------------------------------------
    # Phase 11C.1C-A - Adaptive candidate context builder + emitter.
    # ------------------------------------------------------------------
    def _build_adaptive_context_for_candidate(
        self,
        *,
        candidate: Candidate,
        timestamp: int,
    ) -> AdaptiveCandidateContext:
        """Build the Phase 11C.1C-A adaptive context for one candidate.

        Phase 11C.1C-B refinement: the function now reads the
        candidate's stable ``first_seen_price`` baseline (recorded
        once at admission) and threads the candidate's rolling
        ``price_history`` / ``quote_volume_history`` /
        ``volume_rank_history`` through ``compute_runtime_calibration``
        so the runtime-calibration block on the
        :class:`AdaptiveCandidateContext` carries real 1m / 5m
        accelerations + a meaningful 5-min volume-rank jump.

        The function reads ONLY information already on the candidate /
        snapshot (no REST call, no LLM, no Telegram outbound).
        """
        snap = candidate.snapshot
        symbol = candidate.symbol
        identity = candidate.identity
        # Phase 11C.1C-B: prefer the stable admission baseline when
        # we have one. Falls back to the latest snapshot's
        # last_price / mark_price only if the baseline is missing
        # (very unusual; happens on dry-run fixtures with
        # last_price=0).
        first_seen_price = float(candidate.first_seen_price or 0.0)
        if first_seen_price <= 0.0:
            first_seen_price = (
                float(snap.last_price)
                if snap.last_price
                else float(getattr(snap, "mark_price", 0.0) or 0.0)
            )
        first_seen_ts_ms = int(candidate.first_seen_ms or timestamp)
        current_price = float(snap.last_price or 0.0)
        if current_price <= 0.0:
            current_price = float(getattr(snap, "mark_price", 0.0) or 0.0)
        # Approximate price_24h_high using the 24h price-change
        # percentage. ``price_change_pct_24h`` is signed; when it is
        # positive, the 24h high is at least as large as the current
        # price, so we approximate the high as
        # ``current_price / (1 - high_offset)`` with a small floor
        # so the ``distance_to_24h_high`` numeric stays informative
        # even for momentum candidates that have just printed a new
        # high.
        price_24h_high = self._approximate_24h_high(snap, current_price)
        accel_60 = (
            float(snap.price_acceleration_60s)
            if snap.price_acceleration_60s is not None
            else None
        )
        # Per-snapshot regime aggregates: a future PR threads
        # cross-batch values through; for Phase 11C.1C-A we use the
        # candidate's own acceleration so the classifier always has
        # a non-None input. ``positive_acceleration_ratio`` is 1.0
        # when the candidate's accel is positive, else 0.0; this is
        # conservative - the classifier defaults to NEUTRAL unless
        # the score is large enough.
        if accel_60 is None:
            avg_accel = 0.0
            pos_ratio = 0.0
        else:
            avg_accel = float(accel_60)
            pos_ratio = 1.0 if accel_60 > 0.0 else 0.0
        liq_rate = 1.0 if bool(snap.liquidation_event) else 0.0
        radar_score = float(candidate.radar_score)

        # Phase 11C.1C-B: thread the candidate's rolling history
        # into the runtime calibration block.
        price_history = tuple(candidate.price_history)
        qv_history = tuple(candidate.quote_volume_history)
        volume_rank_now = (
            int(snap.volume_rank) if snap.volume_rank is not None else 0
        )
        rank_5m_ago = None
        if self._candidate_pool is not None:
            try:
                rank_5m_ago = self._candidate_pool.volume_rank_5m_ago(
                    candidate, now_ms_value=int(timestamp)
                )
            except Exception:  # pragma: no cover - defensive
                rank_5m_ago = None

        return build_adaptive_candidate_context(
            opportunity_id=identity.opportunity_id,
            scan_batch_id=identity.scan_batch_id,
            symbol=symbol,
            timestamp_ms=int(timestamp),
            first_seen_ts_ms=first_seen_ts_ms,
            first_seen_price=first_seen_price,
            current_price=current_price,
            price_24h_high=price_24h_high,
            price_acceleration_60s=accel_60,
            avg_price_acceleration_60s=avg_accel,
            positive_acceleration_ratio=pos_ratio,
            liquidation_event_rate=liq_rate,
            data_quality="ok",
            snapshot_count=1,
            radar_score=radar_score,
            cluster_reason=("ws_radar_chain",),
            label_queue_notes=(self.SOURCE_PHASE,),
            # Phase 11C.1C-B - runtime calibration inputs.
            price_history=price_history,
            quote_volume_history=qv_history,
            volume_rank=volume_rank_now,
            volume_rank_5m_ago=rank_5m_ago,
        )

    @staticmethod
    def _approximate_24h_high(snap, current_price: float) -> float:
        """Approximate the 24h high from the snapshot.

        Phase 11C.1C-A only has the 24h price-change percentage on
        the snapshot. We derive a conservative 24h high so the
        ``distance_to_24h_high`` numeric is non-zero and informative.
        """
        if current_price <= 0.0:
            return 0.0
        pct = snap.price_change_pct_24h
        if pct is None or pct <= 0.0:
            # If 24h change is non-positive, the 24h high is at least
            # current_price; bias the high slightly above current.
            return float(current_price * 1.001)
        # Naive: assume the 24h high is at most 1% above the current
        # price + 0.5 * pct of additional headroom. The exact formula
        # is not load-bearing; the field is informational.
        try:
            headroom = max(0.0, float(pct) * 0.5)
        except (TypeError, ValueError):
            headroom = 0.0
        return float(current_price * (1.0 + headroom + 0.001))

    def _emit_adaptive_events(
        self,
        *,
        adaptive: AdaptiveCandidateContext,
        symbol: str,
        timestamp: int,
        learning_context: LearningReadyContext,
    ) -> None:
        """Emit the six Phase 11C.1C-A adaptive events.

        Every payload carries the Phase 8.5 identity tuple plus the
        Phase 11C.1C-A version labels so Reflection / Replay can
        group on them without parsing free-form audit dicts.
        """
        identity_block = {
            "opportunity_id": adaptive.opportunity_id,
            "scan_batch_id": adaptive.scan_batch_id,
            "symbol": symbol,
            "timestamp": int(timestamp),
            "strategy_version": adaptive.strategy_version,
            "scoring_version": adaptive.scoring_version,
            "risk_config_version": adaptive.risk_config_version,
            "state_machine_version": adaptive.state_machine_version,
            "source_phase": self.ADAPTIVE_SOURCE_PHASE,
        }

        # 1. MARKET_REGIME_ASSESSED
        regime_payload = {
            **identity_block,
            "market_regime": adaptive.market_regime.to_payload(),
        }
        self._emit(
            EventType.MARKET_REGIME_ASSESSED,
            symbol=symbol,
            timestamp=timestamp,
            payload=attach_learning_ready(regime_payload, learning_context),
        )
        self._market_regime_assessed_count += 1
        regime_name = str(adaptive.market_regime.regime_name)
        self._market_regime_counts[regime_name] = (
            self._market_regime_counts.get(regime_name, 0) + 1
        )

        # 2. CANDIDATE_STAGE_CLASSIFIED
        stage_payload = {
            **identity_block,
            "candidate_stage": adaptive.candidate_stage.to_payload(),
        }
        self._emit(
            EventType.CANDIDATE_STAGE_CLASSIFIED,
            symbol=symbol,
            timestamp=timestamp,
            payload=attach_learning_ready(stage_payload, learning_context),
        )
        self._candidate_stage_classified_count += 1
        stage_label = str(adaptive.candidate_stage.stage)
        self._candidate_stage_counts[stage_label] = (
            self._candidate_stage_counts.get(stage_label, 0) + 1
        )

        # 3. OPPORTUNITY_SCORED
        score_payload = {
            **identity_block,
            "opportunity_score": adaptive.opportunity_score.to_payload(),
        }
        self._emit(
            EventType.OPPORTUNITY_SCORED,
            symbol=symbol,
            timestamp=timestamp,
            payload=attach_learning_ready(score_payload, learning_context),
        )
        self._opportunity_scored_count += 1
        grade = str(adaptive.opportunity_score.grade)
        self._opportunity_grade_counts[grade] = (
            self._opportunity_grade_counts.get(grade, 0) + 1
        )
        self._top_opportunity_scores.append(
            (
                symbol,
                str(adaptive.opportunity_id),
                float(adaptive.opportunity_score.score),
                grade,
            )
        )
        # Cap the top list to 50 entries so long runs do not grow
        # the in-process counter unbounded.
        if len(self._top_opportunity_scores) > 50:
            self._top_opportunity_scores.sort(key=lambda r: -r[2])
            self._top_opportunity_scores = self._top_opportunity_scores[:50]

        # 4. STRATEGY_MODE_SELECTED
        mode_payload = {
            **identity_block,
            "strategy_mode": adaptive.strategy_mode.to_payload(),
        }
        self._emit(
            EventType.STRATEGY_MODE_SELECTED,
            symbol=symbol,
            timestamp=timestamp,
            payload=attach_learning_ready(mode_payload, learning_context),
        )
        self._strategy_mode_selected_count += 1
        mode = str(adaptive.strategy_mode.mode)
        self._strategy_mode_counts[mode] = (
            self._strategy_mode_counts.get(mode, 0) + 1
        )
        if mode == "follow":
            self._follow_count += 1
        elif mode == "pullback":
            self._pullback_count += 1
        elif mode == "observe":
            self._observe_count += 1
        elif mode == "reject":
            self._reject_count += 1
        # late_chase / blowoff bookkeeping: a candidate counted as
        # observe AND classified as late or blowoff is the
        # late_chase_rejected / blowoff_observed cohort.
        if mode == "observe" and stage_label == "late":
            self._late_chase_rejected_count += 1
        if mode == "observe" and stage_label == "blowoff":
            self._blowoff_observed_count += 1

        # 5. CLUSTER_CONTEXT_ATTACHED
        cluster_payload = {
            **identity_block,
            "cluster": adaptive.cluster.to_payload(),
        }
        self._emit(
            EventType.CLUSTER_CONTEXT_ATTACHED,
            symbol=symbol,
            timestamp=timestamp,
            payload=attach_learning_ready(cluster_payload, learning_context),
        )
        self._cluster_context_attached_count += 1

        # 6. LABEL_QUEUE_ENQUEUED
        label_payload = {
            **identity_block,
            "label_queue": adaptive.label_queue.to_payload(),
        }
        self._emit(
            EventType.LABEL_QUEUE_ENQUEUED,
            symbol=symbol,
            timestamp=timestamp,
            payload=attach_learning_ready(label_payload, learning_context),
        )
        self._label_queue_enqueued_count += 1

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
