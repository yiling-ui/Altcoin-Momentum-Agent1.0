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

Phase 11C.1C-B extension (Adaptive Candidate Runtime Calibration &
Early Tail Discovery v0):

  - every :class:`Candidate` now preserves its
    ``first_seen_price`` + ``quote_volume_first_seen`` +
    ``volume_rank_first_seen`` from admission. They never get
    overwritten on subsequent ``offer()`` calls so the runtime
    calibration block can compute ``price_change_since_first_seen``
    / ``volume_rank_jump_5m`` against a stable baseline.
  - candidates carry rolling per-symbol price + quote-volume
    history (oldest -> newest, capped) so the runtime layer can
    compute 1m / 5m accelerations without re-querying the radar
    buffer.
  - candidates carry an ``early_tail_score`` and a
    ``late_chase_risk_score`` (both 0..100) that the WS-radar chain
    driver writes back via :meth:`CandidatePool.update_runtime_metrics`
    after each chain pass.
  - the pool's capacity-eviction logic (in
    :meth:`_enforce_capacity`) refuses to evict a candidate whose
    ``early_tail_score`` is at or above
    ``CandidatePoolConfig.early_tail_protect_threshold`` unless the
    pool is *full of* such candidates, in which case the lowest
    early-tail score among them is evicted last. This is the
    "do not lose the demon coin to capacity pressure" invariant.

The pool is single-threaded by construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from loguru import logger

from app.adaptive.runtime import DEFAULT_EARLY_TAIL_PROTECT_THRESHOLD
from app.core.clock import now_ms
from app.learning.identity import OpportunityIdentity
from app.market_data_public.radar import (
    AllMarketRadarSnapshot,
    RadarScoreResult,
)
from app.market_data_public.symbol_universe import (
    REASON_NOT_IN_EXCHANGE_INFO,
    SymbolUniverse,
    emit_symbol_rejected,
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
    # Phase 11C.1C-B - early-tail-discovery knobs.
    #
    # ``early_tail_protect_threshold`` is the early-tail-score at or
    # above which a candidate is *protected* from capacity eviction.
    # The default mirrors :data:`DEFAULT_EARLY_TAIL_PROTECT_THRESHOLD`.
    #
    # ``per_symbol_history_max_samples`` caps the per-candidate
    # price + quote-volume rolling history used for 1m / 5m
    # acceleration computations. Holds ~5 minutes at 5 s cadence
    # plus headroom; bounded so long-running deployments do not
    # grow the pool unbounded.
    early_tail_protect_threshold: float = DEFAULT_EARLY_TAIL_PROTECT_THRESHOLD
    per_symbol_history_max_samples: int = 200

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
        if not (0.0 <= float(self.early_tail_protect_threshold) <= 100.0):
            raise ValueError(
                "CandidatePoolConfig.early_tail_protect_threshold must "
                "be in [0.0, 100.0]"
            )
        if int(self.per_symbol_history_max_samples) <= 0:
            raise ValueError(
                "CandidatePoolConfig.per_symbol_history_max_samples "
                "must be > 0"
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

    Phase 11C.1C-B additions:

      - ``first_seen_price`` / ``quote_volume_first_seen`` /
        ``volume_rank_first_seen`` are recorded ONCE at admission
        and never overwritten on subsequent ``offer()`` updates.
        They are the stable baseline the runtime calibration block
        diffs the current snapshot against.
      - ``price_history`` / ``quote_volume_history`` /
        ``volume_rank_history`` are rolling per-symbol histories
        (oldest -> newest, capped at
        ``CandidatePoolConfig.per_symbol_history_max_samples``)
        used for 1m / 5m accelerations and the 5-min volume-rank
        jump.
      - ``early_tail_score`` / ``late_chase_risk_score`` /
        ``freshness_score`` are paper / virtual signals updated by
        :meth:`CandidatePool.update_runtime_metrics` after the
        WS-radar chain has built the runtime calibration block.
        They are read by :meth:`_enforce_capacity` so a candidate
        with high ``early_tail_score`` is protected from eviction.
      - ``promoted_before_24h_top_move`` is True iff the candidate
        was admitted before its 24h top printed (i.e. the radar
        caught the move early). This mirrors the brief's
        ``symbols_promoted_before_24h_top_move`` daily-report
        metric.
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
    # Phase 11C.1C-B: stable baselines (set once at admission).
    first_seen_price: float = 0.0
    quote_volume_first_seen: float = 0.0
    volume_rank_first_seen: int = 0
    # Phase 11C.1C-B: rolling per-candidate histories (oldest ->
    # newest). Stored as tuples of (ts_ms, value); the pool trims
    # them on every offer.
    price_history: list[tuple[int, float]] = field(default_factory=list)
    quote_volume_history: list[tuple[int, float]] = field(default_factory=list)
    volume_rank_history: list[tuple[int, int]] = field(default_factory=list)
    # Phase 11C.1C-B: runtime-layer scores written back by the
    # WS-radar chain driver after each pass. 0.0 until the chain
    # has run at least once for this candidate.
    early_tail_score: float = 0.0
    late_chase_risk_score: float = 0.0
    freshness_score: float = 1.0
    # Phase 11C.1C-B: True when admission preceded the 24h top
    # print (positive evidence that the radar caught the move
    # early). Updated by the WS-radar chain.
    promoted_before_24h_top_move: bool = False

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
            # Phase 11C.1C-B runtime calibration baselines + scores.
            "first_seen_price": float(self.first_seen_price),
            "quote_volume_first_seen": float(self.quote_volume_first_seen),
            "volume_rank_first_seen": int(self.volume_rank_first_seen),
            "early_tail_score": float(self.early_tail_score),
            "late_chase_risk_score": float(self.late_chase_risk_score),
            "freshness_score": float(self.freshness_score),
            "promoted_before_24h_top_move": bool(
                self.promoted_before_24h_top_move
            ),
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
        symbol_universe: SymbolUniverse | None = None,
        event_repo: Any = None,
    ) -> None:
        self._config = config or CandidatePoolConfig()
        self._clock_fn = clock_fn
        self._candidates: dict[str, Candidate] = {}
        # Phase 11C.1B SymbolUniverse gate: when ``symbol_universe`` is
        # bootstrapped (built from /fapi/v1/exchangeInfo at runner
        # startup), :meth:`offer` rejects any symbol that is NOT in
        # the set and emits a typed WS_SYMBOL_REJECTED event via
        # ``event_repo``. Symbol identity is exact-match on the
        # canonical Binance string - non-ASCII contracts (e.g. the
        # documented Chinese-named USDT contracts ``我踏马来了USDT`` /
        # ``币安人生USDT``) flow through unchanged when they ARE in
        # the bootstrap snapshot. The empty universe (default) is
        # the back-compat "admit everything" fallback used by
        # in-process / dry-run / fixture tests.
        self._symbol_universe: SymbolUniverse = (
            symbol_universe
            if symbol_universe is not None
            else SymbolUniverse.empty()
        )
        self._event_repo = event_repo
        # Counters for the daily report / runner banner.
        self._candidates_seen: int = 0
        self._candidates_admitted: int = 0
        self._candidates_promoted: int = 0
        self._candidates_demoted: int = 0
        self._candidates_expired: int = 0
        self._candidates_evicted: int = 0
        self._candidates_rejected_by_universe: int = 0
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
    def candidates_rejected_by_universe(self) -> int:
        """Phase 11C.1B - count of WS-radar offers refused because the
        symbol was missing from the bootstrapped exchangeInfo set.

        Always 0 when the universe is the empty fallback (default for
        dry-run / fixtures); load-bearing only when the runner has
        bootstrapped a real exchangeInfo snapshot.
        """
        return self._candidates_rejected_by_universe

    @property
    def symbol_universe(self) -> SymbolUniverse:
        return self._symbol_universe

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
        # Phase 11C.1B (PR #34) SymbolUniverse contract: preserve the
        # exact Binance exchangeInfo canonical symbol string. Membership
        # is exact-match on the canonical string (no .upper() / .lower(),
        # no ASCII-only filter); only surrounding whitespace may be
        # stripped. Case-folding here would silently break the
        # exact-match invariant for any non-uppercase canonical string
        # exchangeInfo returns.
        symbol = str(snapshot.symbol or "").strip()
        if not symbol:
            return None
        # Phase 11C.1B SymbolUniverse gate (exchangeInfo-as-truth).
        # Binance lists non-ASCII contract symbols (e.g. ``我踏马来了USDT``,
        # ``币安人生USDT``); we explicitly REFUSE to filter symbols by
        # ASCII-only regex - the only authoritative set is the
        # /fapi/v1/exchangeInfo snapshot the runner bootstrapped at
        # startup. The empty universe (default for dry-run / fixtures)
        # admits every non-empty symbol so existing tests keep working;
        # a bootstrapped universe rejects any symbol missing from the
        # set and emits WS_SYMBOL_REJECTED. The check runs BEFORE the
        # ``candidates_seen`` counter to mirror the brief: a rejected
        # symbol never enters the candidate pool's accounting.
        if not self._symbol_universe.is_valid(symbol):
            self._candidates_rejected_by_universe += 1
            emit_symbol_rejected(
                self._event_repo,
                symbol=symbol,
                reason=REASON_NOT_IN_EXCHANGE_INFO,
                extra_payload={
                    "radar_score": float(score.radar_score),
                    "reason_tags": list(score.reason_tags),
                    "source_streams": list(score.source_streams),
                    "universe_size": int(len(self._symbol_universe)),
                    "universe_source": str(self._symbol_universe.source),
                },
                clock_fn=self._clock_fn,
            )
            logger.debug(
                "[phase11c.1b] candidate refused by SymbolUniverse "
                "(not in exchangeInfo) symbol={}",
                symbol,
            )
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
        # Phase 11C.1C-B - capture the snapshot's pricing / volume /
        # rank baselines once at admission. These never get
        # overwritten on subsequent ``offer()`` updates.
        snap_last_price = float(snapshot.last_price or 0.0)
        if snap_last_price <= 0.0 and snapshot.mark_price is not None:
            snap_last_price = float(snapshot.mark_price)
        snap_quote_volume = float(snapshot.quote_volume or 0.0)
        snap_volume_rank = (
            int(snapshot.volume_rank)
            if snapshot.volume_rank is not None
            else 0
        )
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
                # Phase 11C.1C-B: stable admission baselines.
                first_seen_price=snap_last_price,
                quote_volume_first_seen=snap_quote_volume,
                volume_rank_first_seen=snap_volume_rank,
            )
            self._append_history(candidate, snapshot=snapshot, ts=ts)
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
        # Phase 11C.1C-B: never overwrite the stable admission
        # baselines; only top them up if they were missing on
        # admission (e.g. dry-run fixtures with last_price=0).
        if existing.first_seen_price <= 0.0 and snap_last_price > 0.0:
            existing.first_seen_price = snap_last_price
        if existing.quote_volume_first_seen <= 0.0 and snap_quote_volume > 0.0:
            existing.quote_volume_first_seen = snap_quote_volume
        if existing.volume_rank_first_seen <= 0 and snap_volume_rank > 0:
            existing.volume_rank_first_seen = snap_volume_rank
        self._append_history(existing, snapshot=snapshot, ts=ts)
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
        # Phase 11C.1C-B Early Tail Discovery v0:
        #
        # Eviction order is now a tiered sort:
        #
        #   1. UNPROTECTED candidates (early_tail_score below
        #      ``early_tail_protect_threshold``) get evicted first,
        #      ranked by lowest radar_score / oldest last_seen.
        #   2. PROTECTED candidates (early_tail_score >=
        #      ``early_tail_protect_threshold``) get evicted only if
        #      every unprotected candidate has already been removed,
        #      and even then the lowest early-tail-score / lowest
        #      radar_score / oldest last_seen go first.
        #
        # The brief calls this out: "不因为候选池 capacity evict 而
        # 丢失高 early_tail_score 候选". A demon-coin candidate with a
        # high early-tail score must NOT be silently dropped to make
        # room for a slow USDT major.
        threshold = float(self._config.early_tail_protect_threshold)

        def evict_key(c: Candidate) -> tuple[int, float, float, int]:
            protected = 1 if float(c.early_tail_score) >= threshold else 0
            return (
                protected,
                float(c.early_tail_score),
                float(c.radar_score),
                int(c.last_seen_ms),
            )

        ordered = sorted(self._candidates.values(), key=evict_key)
        to_evict = ordered[:excess]
        for cand in to_evict:
            self._candidates.pop(cand.symbol, None)
            self._candidates_evicted += 1
            logger.debug(
                "[phase11c.1c-b] candidate evicted (capacity) symbol={} "
                "score={:.2f} early_tail={:.2f}",
                cand.symbol,
                cand.radar_score,
                float(cand.early_tail_score),
            )

    # ------------------------------------------------------------------
    # Phase 11C.1C-B - per-candidate rolling history + runtime metrics
    # ------------------------------------------------------------------
    def _append_history(
        self,
        candidate: Candidate,
        *,
        snapshot: AllMarketRadarSnapshot,
        ts: int,
    ) -> None:
        """Append the latest snapshot to the candidate's rolling state.

        ``price_history`` and ``quote_volume_history`` are
        ``(ts_ms, value)`` tuples ordered oldest -> newest;
        ``volume_rank_history`` is ``(ts_ms, rank_int)``. Each list is
        capped at
        :attr:`CandidatePoolConfig.per_symbol_history_max_samples`.
        Stale samples (older than 10 minutes) are also dropped so the
        accelerator helpers stay close to the documented windows.
        """
        max_samples = int(self._config.per_symbol_history_max_samples)
        history_window_ms = 10 * 60_000  # 10 minutes
        cutoff = int(ts) - history_window_ms

        last_price = float(snapshot.last_price or 0.0)
        if last_price <= 0.0 and snapshot.mark_price is not None:
            last_price = float(snapshot.mark_price)
        if last_price > 0.0:
            candidate.price_history.append((int(ts), float(last_price)))
        qv = snapshot.quote_volume
        if qv is not None and float(qv) > 0:
            candidate.quote_volume_history.append((int(ts), float(qv)))
        rk = snapshot.volume_rank
        if rk is not None and int(rk) > 0:
            candidate.volume_rank_history.append((int(ts), int(rk)))

        # Trim by age then by length.
        candidate.price_history = [
            row for row in candidate.price_history if row[0] >= cutoff
        ][-max_samples:]
        candidate.quote_volume_history = [
            row for row in candidate.quote_volume_history if row[0] >= cutoff
        ][-max_samples:]
        candidate.volume_rank_history = [
            row for row in candidate.volume_rank_history if row[0] >= cutoff
        ][-max_samples:]

    def volume_rank_5m_ago(self, candidate: Candidate, *, now_ms_value: int) -> int | None:
        """Return the candidate's volume rank ~5 min before ``now_ms_value``.

        Returns the most recent rank at-or-before ``now_ms_value - 5min``
        if any, else the oldest sample's rank if it is at least 2.5
        min old (so a short-burst run still produces a usable
        baseline), else ``None``.
        """
        history = candidate.volume_rank_history
        if not history:
            return None
        target_ts = int(now_ms_value) - 5 * 60_000
        baseline: int | None = None
        for sample_ts, rank in history:
            if int(sample_ts) <= target_ts:
                baseline = int(rank)
            else:
                break
        if baseline is None:
            oldest_ts, oldest_rank = history[0]
            if int(now_ms_value) - int(oldest_ts) >= 2 * 60_000 + 30_000:
                baseline = int(oldest_rank)
        return baseline

    def update_runtime_metrics(
        self,
        symbol: str,
        *,
        early_tail_score: float | None = None,
        late_chase_risk_score: float | None = None,
        freshness_score: float | None = None,
        promoted_before_24h_top_move: bool | None = None,
    ) -> Candidate | None:
        """Write back runtime calibration scores onto the candidate.

        Called by :class:`WSRadarChainDriver` after each chain pass
        so the next ``offer()`` can consult the up-to-date
        ``early_tail_score`` for capacity protection.

        Returns the updated candidate if found, else ``None``.
        """
        cand = self._candidates.get(str(symbol or "").strip())
        if cand is None:
            return None
        if early_tail_score is not None:
            cand.early_tail_score = max(
                0.0, min(100.0, float(early_tail_score))
            )
        if late_chase_risk_score is not None:
            cand.late_chase_risk_score = max(
                0.0, min(100.0, float(late_chase_risk_score))
            )
        if freshness_score is not None:
            cand.freshness_score = max(
                0.0, min(1.0, float(freshness_score))
            )
        if promoted_before_24h_top_move is not None:
            cand.promoted_before_24h_top_move = bool(
                promoted_before_24h_top_move
            )
        return cand

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
        # Phase 11C.1B (PR #34) SymbolUniverse contract: look up by the
        # exact canonical symbol string; only strip surrounding
        # whitespace. Case-folding here would miss any non-uppercase
        # canonical key admitted via offer().
        return self._candidates.get(str(symbol or "").strip())

    def remove(self, symbol: str) -> Candidate | None:
        """Remove one candidate (e.g. after the runner finishes its
        per-loop detail call). Returns the removed candidate if any.
        """
        # Phase 11C.1B (PR #34) SymbolUniverse contract: pop by the
        # exact canonical symbol string; only strip surrounding
        # whitespace.
        return self._candidates.pop(str(symbol or "").strip(), None)

    def clear(self) -> None:
        self._candidates.clear()

    # ------------------------------------------------------------------
    # Daily-report payload
    # ------------------------------------------------------------------
    def metrics_payload(self) -> dict[str, object]:
        """Return the JSON-safe metrics block.

        Field names match the Phase 11C.1B daily-report spec verbatim.

        Phase 11C.1C-B additions:

          - ``candidate_pool_top_early_tail`` - top candidates by
            ``early_tail_score`` (desc, capped at 10).
          - ``candidate_pool_top_late_chase_risk`` - top candidates by
            ``late_chase_risk_score`` (desc, capped at 10).
          - ``candidate_pool_promoted_before_24h_top_move`` - count
            of admitted candidates whose admission preceded the 24h
            top move marker (set by the WS-radar chain driver).
          - ``early_tail_protect_threshold`` - the early-tail
            protection threshold in effect.
        """
        active_top = self.active_head(self._config.active_detail_limit)
        all_cands = self.all_candidates()
        # Phase 11C.1C-B - early-tail / late-chase aggregates.
        top_early_tail = sorted(
            all_cands,
            key=lambda c: (
                -float(c.early_tail_score),
                -int(c.last_seen_ms),
            ),
        )[:10]
        top_late_chase = sorted(
            all_cands,
            key=lambda c: (
                -float(c.late_chase_risk_score),
                -int(c.last_seen_ms),
            ),
        )[:10]
        promoted_before_top = sum(
            1 for c in all_cands if c.promoted_before_24h_top_move
        )
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
                    "early_tail_score": float(c.early_tail_score),
                    "late_chase_risk_score": float(c.late_chase_risk_score),
                }
                for c in all_cands[: self._config.candidate_pool_size]
            ],
            "candidate_pool_size_limit": int(
                self._config.candidate_pool_size
            ),
            "active_detail_limit": int(self._config.active_detail_limit),
            "candidate_ttl_seconds": int(self._config.candidate_ttl_seconds),
            "radar_score_threshold": float(
                self._config.radar_score_threshold
            ),
            # Phase 11C.1C-B - early-tail / late-chase aggregates.
            "candidate_pool_top_early_tail": [
                {
                    "symbol": c.symbol,
                    "early_tail_score": float(c.early_tail_score),
                    "radar_score": float(c.radar_score),
                    "state": c.state,
                }
                for c in top_early_tail
                if float(c.early_tail_score) > 0.0
            ],
            "candidate_pool_top_late_chase_risk": [
                {
                    "symbol": c.symbol,
                    "late_chase_risk_score": float(c.late_chase_risk_score),
                    "radar_score": float(c.radar_score),
                    "state": c.state,
                }
                for c in top_late_chase
                if float(c.late_chase_risk_score) > 0.0
            ],
            "candidate_pool_promoted_before_24h_top_move": int(
                promoted_before_top
            ),
            "early_tail_protect_threshold": float(
                self._config.early_tail_protect_threshold
            ),
            # Phase 11C.1B SymbolUniverse gate metrics. ``rejected_by_universe``
            # is non-zero only when the runner bootstrapped a real
            # exchangeInfo snapshot AND a WS push delivered a symbol
            # outside that snapshot - typical causes are: a brand-new
            # listing that came online mid-run, or a contract delisting
            # whose WS pushes arrived between the bootstrap REST call
            # and the WS subscribe.
            "candidate_pool_rejected_by_universe": int(
                self._candidates_rejected_by_universe
            ),
            **self._symbol_universe.metrics_payload(),
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
