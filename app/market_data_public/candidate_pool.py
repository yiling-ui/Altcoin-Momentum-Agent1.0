"""Phase 11C.1B - Candidate Pool for the WebSocket-first radar (PR-B).

The candidate pool is the bridge between the all-market WebSocket
radar and the existing Phase 11C event-chain driver:

  - the radar (all-market, every symbol) feeds
    :class:`AllMarketRadarSnapshot` + :class:`RadarScoreResult` into
    the pool;
  - the pool maintains a small, time-bounded set of candidates
    (default size 20, default TTL 900 s);
  - the runner drains the pool's "active" head (default 3) on every
    loop tick and runs the existing Phase 11C event chain
    (PRE_ANOMALY_DETECTED / ANOMALY_DETECTED / RISK_REJECTED /
    STATE_TRANSITION + Phase 8.5 LearningReadyContext) for those
    symbols only.

Phase 11C.1B contract:

  - the pool NEVER opens a socket;
  - the pool NEVER calls REST itself - the runner does that, gated
    on the ``active_detail_limit`` head;
  - every candidate carries a Phase 8.5 ``opportunity_id`` /
    ``scan_batch_id`` so the audit trail matches every other
    Phase 8.5 candidate;
  - upgrade / downgrade / expire transitions are recorded as state
    changes on the pool but DO NOT bypass the Risk Engine.

The pool is single-threaded by construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from loguru import logger

from app.core.clock import now_ms
from app.learning.identity import OpportunityIdentity
from app.market_data_public.radar import (
    AllMarketRadarSnapshot,
    RadarScoreResult,
)


# Phase 11C.1B source-phase tag for OpportunityIdentity. Distinct
# from the parent Phase 11C tag so Reflection / Replay can split
# WS-radar candidates from REST-bootstrap candidates.
CANDIDATE_SOURCE_PHASE: str = "phase_11c_1b_ws_first_radar"


@dataclass(frozen=True)
class CandidatePoolConfig:
    """Configuration knobs for the candidate pool.

    Defaults match the Phase 11C.1B brief.
    """

    candidate_pool_size: int = 20
    active_detail_limit: int = 3
    candidate_ttl_seconds: int = 900
    radar_score_threshold: float = 30.0
    volume_rank_jump_threshold: int = 3
    price_acceleration_threshold: float = 0.005
    liquidation_promotes: bool = True

    def __post_init__(self) -> None:
        if self.candidate_pool_size <= 0:
            raise ValueError(
                "CandidatePoolConfig.candidate_pool_size must be > 0"
            )
        if self.active_detail_limit < 0:
            raise ValueError(
                "CandidatePoolConfig.active_detail_limit must be >= 0"
            )
        if self.active_detail_limit > self.candidate_pool_size:
            raise ValueError(
                "CandidatePoolConfig.active_detail_limit must be "
                "<= candidate_pool_size"
            )
        if self.candidate_ttl_seconds <= 0:
            raise ValueError(
                "CandidatePoolConfig.candidate_ttl_seconds must be > 0"
            )
        if self.radar_score_threshold < 0.0:
            raise ValueError(
                "CandidatePoolConfig.radar_score_threshold must be >= 0"
            )


# Internal candidate state machine. ``ACTIVE`` candidates are picked
# up by the runner for per-loop REST detail enrichment + the existing
# Phase 11C event chain. ``WATCHING`` candidates are kept in the pool
# but not promoted; they may be upgraded to ACTIVE on the next tick.
# ``EXPIRED`` candidates are removed from the pool.
CANDIDATE_STATE_WATCHING: str = "watching"
CANDIDATE_STATE_ACTIVE: str = "active"
CANDIDATE_STATE_EXPIRED: str = "expired"


@dataclass
class Candidate:
    """One candidate inside the pool.

    Carries the full Phase 8.5 identity (``opportunity_id`` /
    ``scan_batch_id``) so the audit trail can match this candidate
    against later RISK_REJECTED / STATE_TRANSITION events.
    """

    symbol: str
    state: str
    radar_score: float
    reason_tags: tuple[str, ...]
    source_streams: tuple[str, ...]
    snapshot: AllMarketRadarSnapshot
    identity: OpportunityIdentity
    first_seen_ms: int
    last_seen_ms: int
    upgrade_count: int = 0
    downgrade_count: int = 0
    extra: dict[str, object] = field(default_factory=dict)

    @property
    def opportunity_id(self) -> str:
        return self.identity.opportunity_id

    @property
    def scan_batch_id(self) -> str:
        return self.identity.scan_batch_id

    def to_payload(self) -> dict[str, object]:
        """Return a JSON-safe payload for event emission / daily report."""
        return {
            "symbol": self.symbol,
            "state": self.state,
            "radar_score": float(self.radar_score),
            "reason_tags": list(self.reason_tags),
            "source_streams": list(self.source_streams),
            "opportunity_id": self.opportunity_id,
            "scan_batch_id": self.scan_batch_id,
            "first_seen_ms": int(self.first_seen_ms),
            "last_seen_ms": int(self.last_seen_ms),
            "upgrade_count": int(self.upgrade_count),
            "downgrade_count": int(self.downgrade_count),
            "snapshot": self.snapshot.to_payload(),
        }


class CandidatePool:
    """Bounded, TTL-aware candidate pool fed from the all-market radar.

    Lifecycle:

      1. The runner pumps fresh WS messages into
         :class:`AllMarketRadarBuffer` and pulls a list of
         ``(symbol, snapshot, score)`` for every symbol with new data.
      2. The runner calls :meth:`offer` per symbol. The pool either
         creates a new :class:`Candidate` (with fresh
         ``OpportunityIdentity``), upgrades an existing one to ACTIVE,
         or downgrades it to WATCHING. Items beyond
         ``candidate_pool_size`` evict the lowest-scoring candidate.
      3. On every loop tick the runner calls :meth:`expire` to roll
         off TTL-expired candidates and :meth:`active_head` to read
         the top-N candidates for per-loop REST detail enrichment.
    """

    def __init__(
        self,
        *,
        config: CandidatePoolConfig | None = None,
        clock_fn=now_ms,
    ) -> None:
        self._config = config or CandidatePoolConfig()
        self._clock_fn = clock_fn
        self._candidates: dict[str, Candidate] = {}
        # Counters for the daily report / runner banner.
        self._candidates_seen: int = 0
        self._candidates_admitted: int = 0
        self._candidates_promoted: int = 0
        self._candidates_demoted: int = 0
        self._candidates_expired: int = 0
        self._candidates_evicted: int = 0
        self._max_size_observed: int = 0
        self._scan_batch_id: str | None = None

    # ------------------------------------------------------------------
    @property
    def config(self) -> CandidatePoolConfig:
        return self._config

    @property
    def size(self) -> int:
        return len(self._candidates)

    @property
    def candidates_seen(self) -> int:
        return self._candidates_seen

    @property
    def candidates_admitted(self) -> int:
        return self._candidates_admitted

    @property
    def candidates_promoted(self) -> int:
        return self._candidates_promoted

    @property
    def candidates_demoted(self) -> int:
        return self._candidates_demoted

    @property
    def candidates_expired(self) -> int:
        return self._candidates_expired

    @property
    def candidates_evicted(self) -> int:
        return self._candidates_evicted

    @property
    def max_size_observed(self) -> int:
        return self._max_size_observed

    @property
    def scan_batch_id(self) -> str | None:
        return self._scan_batch_id

    # ------------------------------------------------------------------
    # Scan-batch wiring
    # ------------------------------------------------------------------
    def begin_scan_batch(self, *, scan_batch_id: str | None = None) -> str:
        """Start a new Phase 8.5 scan batch.

        The runner calls this once per loop tick; every candidate
        admitted / re-scored within that tick shares the same
        ``scan_batch_id``. The id is propagated into every
        :class:`Candidate.identity` so Reflection / Replay can group on
        it later.
        """
        from app.learning.identity import make_scan_batch_id

        self._scan_batch_id = make_scan_batch_id(scan_batch_id=scan_batch_id)
        return self._scan_batch_id

    # ------------------------------------------------------------------
    # Offer / promote / demote
    # ------------------------------------------------------------------
    def offer(
        self,
        snapshot: AllMarketRadarSnapshot,
        score: RadarScoreResult,
    ) -> Candidate | None:
        """Offer one (snapshot, score) pair to the pool.

        Returns the resulting :class:`Candidate` if the symbol is
        admitted (or already in the pool), or ``None`` if the offer
        was refused (score below threshold and not already tracked).

        Admission rules (in priority order):

          1. ``radar_score >= radar_score_threshold``
          2. ``volume_rank_jump >= volume_rank_jump_threshold``
          3. ``price_acceleration_60s`` magnitude exceeds threshold
          4. ``liquidation_event=True`` (only when
             ``liquidation_promotes`` is True)
        """
        symbol = (snapshot.symbol or "").upper().strip()
        if not symbol:
            return None
        self._candidates_seen += 1
        admit_reasons = self._admission_reasons(snapshot=snapshot, score=score)
        existing = self._candidates.get(symbol)
        if not admit_reasons and existing is None:
            return None
        # Make sure we have a scan-batch id so the OpportunityIdentity
        # is well-formed.
        scan_batch_id = self._scan_batch_id or self.begin_scan_batch()
        ts = int(self._clock_fn())
        if existing is None:
            identity = OpportunityIdentity.create(
                symbol=symbol,
                source_phase=CANDIDATE_SOURCE_PHASE,
                scan_batch_id=scan_batch_id,
                first_seen_ts=ts,
            )
            new_state = (
                CANDIDATE_STATE_ACTIVE
                if score.radar_score >= self._config.radar_score_threshold
                else CANDIDATE_STATE_WATCHING
            )
            candidate = Candidate(
                symbol=symbol,
                state=new_state,
                radar_score=float(score.radar_score),
                reason_tags=tuple(score.reason_tags),
                source_streams=tuple(score.source_streams),
                snapshot=snapshot,
                identity=identity,
                first_seen_ms=ts,
                last_seen_ms=ts,
            )
            self._candidates[symbol] = candidate
            self._candidates_admitted += 1
            if new_state == CANDIDATE_STATE_ACTIVE:
                self._candidates_promoted += 1
            self._enforce_capacity()
            self._max_size_observed = max(
                self._max_size_observed, len(self._candidates)
            )
            return candidate
        # Existing candidate: refresh + maybe upgrade / downgrade.
        previous_state = existing.state
        existing.snapshot = snapshot
        existing.radar_score = float(score.radar_score)
        existing.reason_tags = tuple(score.reason_tags)
        existing.source_streams = tuple(score.source_streams)
        existing.last_seen_ms = ts
        if score.radar_score >= self._config.radar_score_threshold:
            new_state = CANDIDATE_STATE_ACTIVE
        else:
            new_state = CANDIDATE_STATE_WATCHING
        if new_state != previous_state:
            existing.state = new_state
            if new_state == CANDIDATE_STATE_ACTIVE:
                existing.upgrade_count += 1
                self._candidates_promoted += 1
            else:
                existing.downgrade_count += 1
                self._candidates_demoted += 1
        self._max_size_observed = max(
            self._max_size_observed, len(self._candidates)
        )
        return existing

    def _admission_reasons(
        self,
        *,
        snapshot: AllMarketRadarSnapshot,
        score: RadarScoreResult,
    ) -> list[str]:
        reasons: list[str] = []
        if score.radar_score >= self._config.radar_score_threshold:
            reasons.append("radar_score")
        rank_jump = snapshot.volume_rank_jump
        if (
            rank_jump is not None
            and rank_jump >= self._config.volume_rank_jump_threshold
        ):
            reasons.append("volume_rank_jump")
        accel_60 = snapshot.price_acceleration_60s
        if (
            accel_60 is not None
            and abs(accel_60) >= self._config.price_acceleration_threshold
        ):
            reasons.append("price_acceleration")
        if (
            self._config.liquidation_promotes
            and snapshot.liquidation_event
        ):
            reasons.append("liquidation_event")
        return reasons

    # ------------------------------------------------------------------
    # Capacity enforcement
    # ------------------------------------------------------------------
    def _enforce_capacity(self) -> None:
        excess = len(self._candidates) - self._config.candidate_pool_size
        if excess <= 0:
            return
        # Evict the lowest-score (and oldest) candidates first.
        ordered = sorted(
            self._candidates.values(),
            key=lambda c: (c.radar_score, c.last_seen_ms),
        )
        to_evict = ordered[:excess]
        for cand in to_evict:
            self._candidates.pop(cand.symbol, None)
            self._candidates_evicted += 1
            logger.debug(
                "[phase11c.1b] candidate evicted (capacity) symbol={} "
                "score={:.2f}",
                cand.symbol,
                cand.radar_score,
            )

    # ------------------------------------------------------------------
    # Expiry
    # ------------------------------------------------------------------
    def expire(self) -> list[Candidate]:
        """Drop every candidate older than ``candidate_ttl_seconds``.

        Returns the list of expired candidates so the runner can
        record an audit trail (e.g. emit a STATE_TRANSITION-style
        downgrade event in a future PR). Phase 11C.1B does NOT emit a
        new EventType for expiry; the daily-report counter is the
        load-bearing record for now.
        """
        ts = int(self._clock_fn())
        ttl_ms = int(self._config.candidate_ttl_seconds) * 1000
        expired: list[Candidate] = []
        for symbol, cand in list(self._candidates.items()):
            if ts - int(cand.last_seen_ms) >= ttl_ms:
                cand.state = CANDIDATE_STATE_EXPIRED
                expired.append(cand)
                self._candidates.pop(symbol, None)
                self._candidates_expired += 1
        return expired

    # ------------------------------------------------------------------
    # Read views
    # ------------------------------------------------------------------
    def all_candidates(self) -> list[Candidate]:
        """Return every candidate sorted by score (desc, ties by recency)."""
        return sorted(
            self._candidates.values(),
            key=lambda c: (-c.radar_score, -c.last_seen_ms),
        )

    def active_head(self, limit: int | None = None) -> list[Candidate]:
        """Return the top-N ACTIVE candidates ordered by score.

        Limit defaults to ``active_detail_limit``. The runner uses
        this list to decide which symbols receive a per-loop REST
        detail call (and therefore which symbols drive the existing
        Phase 11C event chain).
        """
        top = limit if limit is not None else self._config.active_detail_limit
        if top is None or top <= 0:
            return []
        actives = [
            c
            for c in self.all_candidates()
            if c.state == CANDIDATE_STATE_ACTIVE
        ]
        return actives[: int(top)]

    def get(self, symbol: str) -> Candidate | None:
        return self._candidates.get((symbol or "").upper().strip())

    def remove(self, symbol: str) -> Candidate | None:
        """Remove one candidate (e.g. after the runner finishes its
        per-loop detail call). Returns the removed candidate if any.
        """
        return self._candidates.pop((symbol or "").upper().strip(), None)

    def clear(self) -> None:
        self._candidates.clear()

    # ------------------------------------------------------------------
    # Daily-report payload
    # ------------------------------------------------------------------
    def metrics_payload(self) -> dict[str, object]:
        """Return the JSON-safe metrics block.

        Field names match the Phase 11C.1B daily-report spec verbatim.
        """
        active_top = self.active_head(self._config.active_detail_limit)
        return {
            "radar_candidates_seen": int(self._candidates_seen),
            "candidate_pool_size": int(self.size),
            "candidate_pool_size_max": int(self._max_size_observed),
            "candidate_pool_admitted": int(self._candidates_admitted),
            "candidate_pool_promoted": int(self._candidates_promoted),
            "candidate_pool_demoted": int(self._candidates_demoted),
            "candidate_pool_expired": int(self._candidates_expired),
            "candidate_pool_evicted": int(self._candidates_evicted),
            "candidate_pool_active_head": [
                c.to_payload() for c in active_top
            ],
            "candidate_pool_top_symbols": [
                {
                    "symbol": c.symbol,
                    "radar_score": float(c.radar_score),
                    "state": c.state,
                }
                for c in self.all_candidates()[: self._config.candidate_pool_size]
            ],
            "candidate_pool_size_limit": int(
                self._config.candidate_pool_size
            ),
            "active_detail_limit": int(self._config.active_detail_limit),
            "candidate_ttl_seconds": int(self._config.candidate_ttl_seconds),
            "radar_score_threshold": float(
                self._config.radar_score_threshold
            ),
        }


# ---------------------------------------------------------------------------
# Convenience batch offer
# ---------------------------------------------------------------------------
def offer_snapshots(
    pool: CandidatePool,
    snapshots: Iterable[AllMarketRadarSnapshot],
    *,
    score_fn,
) -> list[Candidate]:
    """Offer every snapshot in ``snapshots`` to ``pool`` after scoring.

    ``score_fn(snapshot) -> RadarScoreResult`` is invoked once per
    snapshot. Returns the list of candidates that were admitted /
    refreshed (skipping snapshots the pool refused).
    """
    out: list[Candidate] = []
    for snap in snapshots:
        score = score_fn(snap)
        cand = pool.offer(snap, score)
        if cand is not None:
            out.append(cand)
    return out


__all__ = [
    "CANDIDATE_SOURCE_PHASE",
    "CANDIDATE_STATE_ACTIVE",
    "CANDIDATE_STATE_EXPIRED",
    "CANDIDATE_STATE_WATCHING",
    "Candidate",
    "CandidatePool",
    "CandidatePoolConfig",
    "offer_snapshots",
]
