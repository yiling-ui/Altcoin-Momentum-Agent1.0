"""Phase 11C.1C-B - Adaptive Candidate Runtime Calibration & Early
Tail Discovery v0 tests.

Pins every behaviour the brief calls out:

  - test_early_tail_score_detects_volume_rank_jump
  - test_freshness_penalizes_late_chase
  - test_late_blowoff_never_follow
  - test_top_early_tail_candidates_reported
  - test_candidate_first_seen_price_preserved
  - test_volume_rank_jump_calculated
  - test_adaptive_runtime_fields_exportable
  - test_no_live_trading_flags_unchanged
  - test_runtime_calibration_payload_round_trips
  - test_pool_protects_high_early_tail_candidate_from_eviction
  - test_eden_alt_near_examples_surfaced

Every test runs in-process. No real socket is opened; the
deterministic in-process pump stands in for the public WebSocket
transport when needed.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.adaptive import (
    AdaptiveCandidateContext,
    CandidateStageAssessment,
    DEFAULT_EARLY_TAIL_PROTECT_THRESHOLD,
    MarketRegimeAssessment,
    OpportunityScore,
    RuntimeCalibrationMetrics,
    build_adaptive_candidate_context,
    compute_early_tail_score,
    compute_freshness_score,
    compute_late_chase_risk_score,
    compute_runtime_calibration,
    select_strategy_mode,
)
from app.config.settings import get_settings, load_settings
from app.core.events import EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.exports.service import TestDataExportService
from app.learning import OpportunityIdentity, payload_to_virtual_trade_plan
from app.market_data_public.candidate_pool import (
    CANDIDATE_STATE_ACTIVE,
    Candidate,
    CandidatePool,
    CandidatePoolConfig,
)
from app.market_data_public.radar import (
    AllMarketRadarSnapshot,
    pre_anomaly_score_light,
)
from app.market_data_public.ws_radar_chain import WSRadarChainDriver
from app.paper_run.daily_report import DailyReportBuilder
from app.replay.engine import ReplayEngine
from app.risk.engine import RiskEngine


# ---------------------------------------------------------------------------
# Helpers (mirror Phase 11C.1C-A test fixtures so the surface is consistent)
# ---------------------------------------------------------------------------


def _settings():
    get_settings.cache_clear()
    return load_settings()


def _make_event_repo(tmp_path: Path) -> tuple[EventRepository, DatabaseSet]:
    dbs = DatabaseSet.open(
        tmp_path / "sqlite",
        wal=False,
        databases=PHASE2_DATABASES,
    )
    migrate_database_set(dbs)
    return EventRepository(dbs.events, capital_conn=dbs.capital), dbs


def _make_radar_snapshot(
    *,
    symbol: str = "EDENUSDT",
    last_price: float = 1.05,
    timestamp: int = 1_700_000_060_000,
    price_change_pct_24h: float = 0.05,
    price_acceleration_60s: float = 0.012,
    quote_volume: float = 50_000_000.0,
    quote_volume_delta_60s: float = 1_000_000.0,
    volume_rank: int = 5,
    volume_rank_jump: int = 4,
    bid: float | None = 1.049,
    ask: float | None = 1.051,
    spread_pct: float = 0.002,
    mark_price: float = 1.05,
    funding_rate: float = 0.0001,
) -> AllMarketRadarSnapshot:
    return AllMarketRadarSnapshot(
        symbol=symbol,
        timestamp=timestamp,
        last_price=last_price,
        price_change_pct_24h=price_change_pct_24h,
        price_acceleration_60s=price_acceleration_60s,
        quote_volume=quote_volume,
        quote_volume_delta_60s=quote_volume_delta_60s,
        volume_rank=volume_rank,
        volume_rank_jump=volume_rank_jump,
        bid=bid,
        ask=ask,
        spread_pct=spread_pct,
        mark_price=mark_price,
        funding_rate=funding_rate,
    )


def _make_candidate(
    *,
    symbol: str = "EDENUSDT",
    snap: AllMarketRadarSnapshot | None = None,
    first_seen_ts: int = 1_700_000_000_000,
    first_seen_price: float = 1.00,
    radar_score: float | None = None,
) -> Candidate:
    snap = snap or _make_radar_snapshot(symbol=symbol)
    score = pre_anomaly_score_light(snap)
    radar_score = (
        float(radar_score) if radar_score is not None else float(score.radar_score)
    )
    identity = OpportunityIdentity.create(
        symbol=symbol,
        source_phase="phase_11c_1b_ws_first_radar",
        first_seen_ts=first_seen_ts,
    )
    cand = Candidate(
        symbol=symbol,
        state=CANDIDATE_STATE_ACTIVE,
        radar_score=radar_score,
        reason_tags=tuple(score.reason_tags),
        source_streams=tuple(score.source_streams),
        snapshot=snap,
        identity=identity,
        first_seen_ms=first_seen_ts,
        last_seen_ms=int(snap.timestamp),
        first_seen_price=first_seen_price,
        quote_volume_first_seen=float(snap.quote_volume or 0.0),
        volume_rank_first_seen=int(snap.volume_rank or 0),
    )
    # Build a small history so 1m / 5m accelerations are non-trivial.
    cand.price_history = [
        (first_seen_ts, first_seen_price),
        (first_seen_ts + 60_000, first_seen_price * 1.02),
        (int(snap.timestamp), float(snap.last_price)),
    ]
    cand.quote_volume_history = [
        (first_seen_ts, float(snap.quote_volume or 0.0) * 0.5),
        (first_seen_ts + 60_000, float(snap.quote_volume or 0.0) * 0.7),
        (int(snap.timestamp), float(snap.quote_volume or 0.0)),
    ]
    cand.volume_rank_history = [
        (first_seen_ts, max(1, int(snap.volume_rank or 0) + 5)),
        (int(snap.timestamp), int(snap.volume_rank or 0)),
    ]
    return cand


# ---------------------------------------------------------------------------
# 1. Brief-mandated tests
# ---------------------------------------------------------------------------


def test_early_tail_score_detects_volume_rank_jump():
    """An EDEN-style demon-coin start: jumping +10 ranks in 5 min,
    fresh, with positive accelerations, must produce an
    ``early_tail_score`` well above the protect threshold."""
    metrics = compute_runtime_calibration(
        first_seen_ts_ms=1_700_000_000_000,
        first_seen_price=1.0,
        current_ts_ms=1_700_000_120_000,  # 2 min elapsed
        current_price=1.10,
        price_history=[
            (1_700_000_000_000, 1.0),
            (1_700_000_060_000, 1.04),
            (1_700_000_120_000, 1.10),
        ],
        quote_volume_history=[
            (1_700_000_000_000, 5_000_000.0),
            (1_700_000_060_000, 12_000_000.0),
            (1_700_000_120_000, 25_000_000.0),
        ],
        volume_rank=3,
        volume_rank_5m_ago=15,
        candidate_stage="early",
    )
    assert metrics.volume_rank_jump_5m == 12
    assert metrics.early_tail_score >= DEFAULT_EARLY_TAIL_PROTECT_THRESHOLD
    # Late-chase risk should be modest because price barely moved
    # vs. typical late-stage thresholds.
    assert metrics.late_chase_risk < 50.0


def test_freshness_penalizes_late_chase():
    """A stale (low-freshness) candidate that ran up 40% off
    first-seen must produce HIGH late_chase_risk and LOW
    early_tail_score (freshness multiplier brings tail score down)."""
    fresh = compute_freshness_score(
        first_seen_ts_ms=1_700_000_000_000,
        current_ts_ms=1_700_001_200_000,  # 20 min elapsed
    )
    assert fresh < 0.25, f"freshness expected <0.25 at 20 min elapsed; got {fresh}"

    metrics = compute_runtime_calibration(
        first_seen_ts_ms=1_700_000_000_000,
        first_seen_price=1.0,
        current_ts_ms=1_700_001_200_000,
        current_price=1.40,
        price_history=[
            (1_700_000_000_000, 1.0),
            (1_700_000_300_000, 1.20),
            (1_700_001_200_000, 1.40),
        ],
        quote_volume_history=[
            (1_700_000_000_000, 5_000_000.0),
            (1_700_000_300_000, 8_000_000.0),
            (1_700_001_200_000, 8_500_000.0),
        ],
        volume_rank=10,
        volume_rank_5m_ago=10,
        candidate_stage="late",
    )
    assert metrics.freshness_score < 0.25
    assert metrics.late_chase_risk >= 70.0
    assert metrics.early_tail_score <= 30.0


def test_late_blowoff_never_follow():
    """The selector MUST NEVER pick ``follow`` (or ``pullback``) for a
    candidate whose stage is ``late`` / ``blowoff`` / ``dumped`` -
    even when the opportunity score happens to be high."""
    high_score = OpportunityScore(
        momentum_strength=90.0,
        volume_expansion=80.0,
        liquidity_quality=70.0,
        regime_fit=80.0,
        freshness=50.0,
        manipulation_risk=10.0,
        late_chase_risk=80.0,
        score=70.0,
        grade="A",
    )
    risk_on = MarketRegimeAssessment(
        regime_name="MEME_RISK_ON",
        confidence=0.7,
        risk_multiplier=1.0,
        allowed_strategy_modes=("follow", "pullback", "observe"),
    )
    for stage in ("late", "blowoff", "dumped"):
        stage_obj = CandidateStageAssessment(
            stage=stage,
            freshness=0.3,
            late_chase_risk=0.9 if stage != "dumped" else 0.0,
            blowoff_risk=0.8 if stage == "blowoff" else 0.2,
            first_seen_ts=1,
            first_seen_price=1.0,
            current_price=1.4 if stage != "dumped" else 0.85,
            distance_from_first_seen=0.4 if stage != "dumped" else -0.15,
            distance_to_24h_high=0.0,
        )
        decision = select_strategy_mode(
            market_regime=risk_on,
            candidate_stage=stage_obj,
            opportunity_score=high_score,
        )
        assert decision.mode != "follow", (
            f"selector returned follow for stage={stage}: {decision}"
        )
        assert decision.mode != "pullback", (
            f"selector returned pullback for stage={stage}: {decision}"
        )
        assert decision.follow_allowed is False
        assert decision.pullback_allowed is False


def test_top_early_tail_candidates_reported(tmp_path: Path):
    """The WS-radar chain driver populates
    ``adaptive_metrics_payload['top_early_tail_candidates']`` and the
    daily report carries it through verbatim."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        risk = RiskEngine(event_repo=repo)
        chain = WSRadarChainDriver(risk_engine=risk, event_repo=repo)
        # Drive two candidates with rising volume + price so they
        # accumulate a non-zero early_tail_score.
        chain.drive(
            _make_candidate(
                symbol="EDENUSDT",
                snap=_make_radar_snapshot(
                    symbol="EDENUSDT",
                    last_price=1.10,
                    volume_rank=3,
                    volume_rank_jump=12,
                    price_acceleration_60s=0.10,
                    quote_volume_delta_60s=20_000_000.0,
                ),
                first_seen_price=1.0,
            )
        )
        chain.drive(
            _make_candidate(
                symbol="ALTUSDT",
                snap=_make_radar_snapshot(
                    symbol="ALTUSDT",
                    last_price=2.10,
                    volume_rank=4,
                    volume_rank_jump=8,
                    price_acceleration_60s=0.07,
                ),
                first_seen_price=2.0,
            )
        )
        payload = chain.adaptive_metrics_payload()
        assert "top_early_tail_candidates" in payload
        assert "top_late_chase_risk_candidates" in payload
        assert "early_tail_score_top_symbols" in payload
        # At least one of the two candidates must surface above zero.
        scores = [
            row["early_tail_score"]
            for row in payload["top_early_tail_candidates"]
        ]
        assert scores, "no top_early_tail_candidates produced"
        assert any(s > 0.0 for s in scores)

        # Daily report carries it through.
        out_dir = tmp_path / "reports"
        out_dir.mkdir()
        builder = DailyReportBuilder(event_repo=repo, output_dir=out_dir)
        snap = builder.build(
            started_at_ms=1_700_000_000_000,
            finished_at_ms=1_700_000_120_000,
            adaptive_metrics=payload,
            write_to_disk=True,
        )
        assert snap.top_early_tail_candidates
        assert snap.top_late_chase_risk_candidates is not None
        assert "Phase 11C.1C-B Adaptive Candidate Runtime" in snap.markdown
        assert "Top early-tail candidates" in snap.markdown
        assert "Top late-chase-risk candidates" in snap.markdown
        assert "Opportunity score distribution" in snap.markdown
        assert "EDEN / ALT / NEAR-style examples" in snap.markdown
        assert "paper / virtual" in snap.markdown
        # JSON-safe.
        json.dumps(snap.to_payload(), sort_keys=True, default=str)
    finally:
        dbs.close()


def test_candidate_first_seen_price_preserved():
    """``Candidate.first_seen_price`` must be recorded ONCE at
    admission and NEVER overwritten on subsequent ``offer()`` updates,
    even if the candidate's current price moves dramatically."""
    pool = CandidatePool(
        config=CandidatePoolConfig(
            candidate_pool_size=5,
            active_detail_limit=3,
            candidate_ttl_seconds=900,
            radar_score_threshold=0.0,  # admit anything
        )
    )
    pool.begin_scan_batch()

    snap1 = _make_radar_snapshot(
        symbol="EDENUSDT",
        last_price=1.00,
        timestamp=1_700_000_000_000,
        volume_rank=10,
        quote_volume=5_000_000.0,
    )
    score1 = pre_anomaly_score_light(snap1)
    cand = pool.offer(snap1, score1)
    assert cand is not None
    assert cand.first_seen_price == pytest.approx(1.00)
    assert cand.quote_volume_first_seen == pytest.approx(5_000_000.0)
    assert cand.volume_rank_first_seen == 10

    # Refresh with a much higher price + lower rank.
    snap2 = _make_radar_snapshot(
        symbol="EDENUSDT",
        last_price=2.00,  # +100%
        timestamp=1_700_000_120_000,
        volume_rank=2,
        quote_volume=20_000_000.0,
    )
    score2 = pre_anomaly_score_light(snap2)
    cand2 = pool.offer(snap2, score2)
    assert cand2 is cand  # same candidate
    # Stable baselines must be preserved.
    assert cand2.first_seen_price == pytest.approx(1.00)
    assert cand2.quote_volume_first_seen == pytest.approx(5_000_000.0)
    assert cand2.volume_rank_first_seen == 10
    # But the current snapshot must reflect the latest data.
    assert cand2.snapshot.last_price == pytest.approx(2.00)
    assert cand2.snapshot.volume_rank == 2


def test_volume_rank_jump_calculated():
    """``compute_runtime_calibration`` must return ``rank_5m_ago - rank_now``
    when both are supplied; ``0`` when ``rank_5m_ago`` is unknown.
    """
    # Up 8 ranks (smaller rank = better leaderboard position).
    metrics_up = compute_runtime_calibration(
        first_seen_ts_ms=0,
        first_seen_price=1.0,
        current_ts_ms=300_000,
        current_price=1.05,
        volume_rank=4,
        volume_rank_5m_ago=12,
        candidate_stage="early",
    )
    assert metrics_up.volume_rank_jump_5m == 8
    # Down 5 ranks - the value is negative (informational; the early
    # tail score does NOT credit downward jumps).
    metrics_down = compute_runtime_calibration(
        first_seen_ts_ms=0,
        first_seen_price=1.0,
        current_ts_ms=300_000,
        current_price=1.0,
        volume_rank=20,
        volume_rank_5m_ago=15,
        candidate_stage="early",
    )
    assert metrics_down.volume_rank_jump_5m == -5
    # Missing rank baseline -> zero.
    metrics_none = compute_runtime_calibration(
        first_seen_ts_ms=0,
        first_seen_price=1.0,
        current_ts_ms=300_000,
        current_price=1.0,
        volume_rank=4,
        volume_rank_5m_ago=None,
        candidate_stage="early",
    )
    assert metrics_none.volume_rank_jump_5m == 0


def test_adaptive_runtime_fields_exportable(tmp_path: Path):
    """Phase 8.5 export must carry the runtime calibration block on
    every adaptive event without choking; the Phase 10A replay
    engine must accept the events without raising."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        risk = RiskEngine(event_repo=repo)
        chain = WSRadarChainDriver(risk_engine=risk, event_repo=repo)
        chain.drive(_make_candidate())
        out_dir = tmp_path / "exports"
        out_dir.mkdir()
        service = TestDataExportService(
            event_repo=repo, trading_mode="paper", output_dir=out_dir
        )
        result = service.export(
            range_label="range",
            start_ms=1_699_000_000_000,
            end_ms=2_000_000_000_000,
            type_filter="all",
        )
        with zipfile.ZipFile(result.zip_path) as zf:
            seen_runtime = False
            for line in zf.read("events.jsonl").decode("utf-8").splitlines():
                row = json.loads(line)
                payload = row.get("payload") or {}
                lr = payload.get("learning_ready") or {}
                adaptive = lr.get("adaptive_candidate") or {}
                runtime = adaptive.get("runtime_calibration")
                if runtime:
                    # Validate every brief-mandated field is present.
                    for key in (
                        "candidate_first_seen_ts",
                        "candidate_first_seen_price",
                        "current_price",
                        "price_change_since_first_seen",
                        "quote_volume_acceleration_1m",
                        "quote_volume_acceleration_5m",
                        "price_acceleration_1m",
                        "price_acceleration_5m",
                        "volume_rank",
                        "volume_rank_jump_5m",
                        "distance_to_24h_high",
                        "distance_from_first_seen",
                        "freshness_score",
                        "late_chase_risk",
                        "early_tail_score",
                    ):
                        assert key in runtime, (
                            f"runtime calibration missing field {key}"
                        )
                    seen_runtime = True
            assert seen_runtime, (
                "no exported event carried a runtime_calibration block"
            )
        # Replay engine must accept the new event types without error.
        eng = ReplayEngine(event_repo=repo)
        rejects = eng.replay_risk_rejections()
        assert rejects, "replay returned no RISK_REJECTED rows"
    finally:
        dbs.close()


def test_no_live_trading_flags_unchanged():
    """The five Phase 1 safety flags + telegram_outbound +
    binance_private_api + every safety.forbid_* flag remain at their
    locked values."""
    s = _settings()
    assert s.trading_mode == "paper"
    assert s.live_trading_enabled is False
    assert s.right_tail_enabled is False
    assert s.llm_enabled is False
    assert s.exchange_live_order_enabled is False
    assert s.telegram_outbound_enabled is False
    safety = s.safety
    for flag in (
        "forbid_private_credentials",
        "forbid_signed_endpoints",
        "forbid_trade_endpoints",
        "forbid_account_endpoints",
        "forbid_position_endpoints",
        "forbid_leverage_endpoints",
        "forbid_margin_endpoints",
        "forbid_live_trading",
        "forbid_right_tail",
        "forbid_llm_trade_decisions",
        "forbid_telegram_outbound",
    ):
        assert getattr(safety, flag) is True


# ---------------------------------------------------------------------------
# 2. Supporting tests
# ---------------------------------------------------------------------------


def test_runtime_calibration_payload_round_trips():
    """``RuntimeCalibrationMetrics`` is JSON-stable: payload round-trip
    preserves every field without surprise."""
    m = compute_runtime_calibration(
        first_seen_ts_ms=1_700_000_000_000,
        first_seen_price=1.00,
        current_ts_ms=1_700_000_300_000,
        current_price=1.20,
        price_24h_high=1.30,
        price_history=[
            (1_700_000_000_000, 1.00),
            (1_700_000_120_000, 1.10),
            (1_700_000_300_000, 1.20),
        ],
        quote_volume_history=[
            (1_700_000_000_000, 1_000_000.0),
            (1_700_000_120_000, 1_500_000.0),
            (1_700_000_300_000, 2_500_000.0),
        ],
        volume_rank=5,
        volume_rank_5m_ago=12,
        candidate_stage="early",
    )
    payload = m.to_payload()
    assert payload["candidate_first_seen_ts"] == 1_700_000_000_000
    assert payload["candidate_first_seen_price"] == pytest.approx(1.00)
    assert payload["current_price"] == pytest.approx(1.20)
    assert payload["price_change_since_first_seen"] == pytest.approx(0.20)
    assert payload["volume_rank_jump_5m"] == 7
    assert payload["volume_rank"] == 5
    # Every payload value is JSON-safe.
    json.dumps(payload, sort_keys=True)
    # Reconstruction.
    m2 = RuntimeCalibrationMetrics(**payload)
    assert m2.to_payload() == payload


def test_pool_protects_high_early_tail_candidate_from_eviction():
    """Phase 11C.1C-B brief: high ``early_tail_score`` candidates MUST
    NOT be silently evicted to make room for slow majors."""
    pool = CandidatePool(
        config=CandidatePoolConfig(
            candidate_pool_size=2,  # tiny, so eviction triggers fast
            active_detail_limit=2,
            candidate_ttl_seconds=900,
            radar_score_threshold=0.0,
        )
    )
    pool.begin_scan_batch()

    # 1) Slow major - low early-tail-score, slightly-higher radar.
    slow = _make_radar_snapshot(
        symbol="BTCUSDT",
        last_price=70_000.0,
        timestamp=1_700_000_000_000,
        price_acceleration_60s=0.0001,
        volume_rank=1,
    )
    pool.offer(slow, pre_anomaly_score_light(slow))
    pool.update_runtime_metrics("BTCUSDT", early_tail_score=10.0)

    # 2) Demon coin - HIGH early-tail score, lower radar.
    eden = _make_radar_snapshot(
        symbol="EDENUSDT",
        last_price=1.10,
        timestamp=1_700_000_001_000,
        price_acceleration_60s=0.10,
        volume_rank=4,
    )
    pool.offer(eden, pre_anomaly_score_light(eden))
    pool.update_runtime_metrics("EDENUSDT", early_tail_score=85.0)

    # 3) Slow ETH - low early-tail-score. Should be evicted to make
    # room when the next admission lands; the demon coin must survive.
    eth = _make_radar_snapshot(
        symbol="ETHUSDT",
        last_price=3_500.0,
        timestamp=1_700_000_002_000,
        price_acceleration_60s=0.0001,
        volume_rank=2,
    )
    pool.offer(eth, pre_anomaly_score_light(eth))
    pool.update_runtime_metrics("ETHUSDT", early_tail_score=5.0)

    # Pool size is 2; one offer must have been evicted. The
    # protected demon coin must still be present.
    surviving_symbols = {c.symbol for c in pool.all_candidates()}
    assert "EDENUSDT" in surviving_symbols, (
        f"high early-tail-score candidate was evicted: "
        f"{surviving_symbols}"
    )
    assert pool.candidates_evicted == 1


def test_eden_alt_near_examples_surfaced(tmp_path: Path):
    """When the chain drives an EDEN / ALT / NEAR-style candidate
    with a non-zero ``early_tail_score``, the daily-report
    ``eden_alt_near_examples`` must surface it."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        risk = RiskEngine(event_repo=repo)
        chain = WSRadarChainDriver(risk_engine=risk, event_repo=repo)
        chain.drive(
            _make_candidate(
                symbol="NEARUSDT",
                snap=_make_radar_snapshot(
                    symbol="NEARUSDT",
                    last_price=6.0,
                    volume_rank=3,
                    volume_rank_jump=10,
                    price_acceleration_60s=0.06,
                    quote_volume_delta_60s=10_000_000.0,
                ),
                first_seen_price=5.0,
            )
        )
        payload = chain.adaptive_metrics_payload()
        examples = payload.get("eden_alt_near_examples", [])
        assert any(
            row.get("symbol", "").upper().startswith("NEAR")
            for row in examples
        ), f"NEAR-style example missing from eden_alt_near_examples: {examples}"
    finally:
        dbs.close()


def test_strategy_mode_does_not_authorise_real_trade(tmp_path: Path):
    """Even when a chain drives an early-tail-protected candidate, the
    Risk Engine still has stop_unconfirmed=True so every new-open
    path is refused. ``early_tail_score`` is paper / virtual only."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        risk = RiskEngine(event_repo=repo)
        chain = WSRadarChainDriver(risk_engine=risk, event_repo=repo)
        result = chain.drive(_make_candidate())
        assert result.risk_approved is False
        assert "stop_unconfirmed" in result.reject_reasons
        # Adaptive context carries the runtime calibration block.
        assert result.adaptive_context is not None
        assert result.adaptive_context.runtime_calibration is not None
        runtime = result.adaptive_context.runtime_calibration
        # Even with a high tail score, the safety flags must still
        # hold: settings remain paper-mode.
        s = _settings()
        assert s.live_trading_enabled is False
        assert s.exchange_live_order_enabled is False
        assert s.telegram_outbound_enabled is False
        # Sanity: runtime metrics include the brief-mandated keys.
        payload = runtime.to_payload()
        for k in (
            "candidate_first_seen_ts",
            "candidate_first_seen_price",
            "early_tail_score",
            "late_chase_risk",
        ):
            assert k in payload
    finally:
        dbs.close()
