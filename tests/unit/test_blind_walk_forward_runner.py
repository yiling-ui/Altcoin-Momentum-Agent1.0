"""Unit tests for the Blind Walk-forward Runner v0
(Phase 11C.1D-D-G / PR100).

These tests are the safety contract for this PR. If any of them
fails the module is not safe to merge.

Hard safety boundary covered by these tests:

  - mode = historical_blind_sim_live
  - sandbox_only = True
  - simulated_only = True
  - no_live_order = True
  - live_trading = False
  - exchange_live_orders = False
  - binance_private_api_enabled = False
  - signed_endpoint_reachable = False
  - private_websocket_reachable = False
  - account_endpoint_reachable = False
  - order_endpoint_reachable = False
  - position_endpoint_reachable = False
  - leverage_endpoint_reachable = False
  - margin_endpoint_reachable = False
  - real_exchange_order_path = False
  - real_capital = False
  - telegram_outbound_enabled = False
  - telegram_live_command_authority = False
  - telegram_production_channel_enabled = False
  - ai_trade_authority = False
  - trade_authority = False
  - auto_tuning_inside_blind_window = False
  - auto_tuning_allowed = False
  - phase_12_forbidden = True

The tests also assert that the new module:

  - does NOT import app.risk / app.execution / app.exchanges /
    app.telegram / app.config
  - does NOT pull any DeepSeek / LLM / Telegram / Binance / network
    transport
  - emits no forbidden trade / runtime-config / live-ready field
  - emits no real_exchange_order_id / exchange_order_id /
    real_account_id / api_key / api_secret / signed-endpoint
    reference
  - is deterministic
"""

from __future__ import annotations

import ast
import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import pytest

from app.sim import (
    AsOfFeatureCache,
    BlindRunInvalidationReason,
    BlindRunManifest,
    BlindRunScore,
    BlindRunStatus,
    BlindWalkForwardRunner,
    BlindWalkForwardRunnerConfig,
    BlindWalkForwardWindow,
    FORBIDDEN_OUTPUT_FIELDS,
    HistoricalKlineRecord,
    HistoricalMarketStore,
    MockExchange,
    MockExchangeConfig,
    MockOrderSide,
    MockOrderType,
    MultiTimeframeAsOfGuard,
    NO_LIVE_ORDER_LABEL,
    NO_REAL_CAPITAL_LABEL,
    NO_TELEGRAM_COMMAND_AUTHORITY_LABEL,
    NoLookaheadViolation,
    NoLookaheadViolationReason,
    OrderRequest,
    PessimisticFillModel,
    ReplayFeedProvider,
    ReplayFeedProviderConfig,
    SimulatedCapitalConfig,
    SimulatedCapitalFlowEngine,
    SimulationClock,
    SymbolStatus,
    SymbolStatusRecord,
    TelegramSandboxOutbox,
    TelegramSandboxOutboxConfig,
    assert_no_forbidden_fields,
    score_blind_run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _walk_keys(payload: Any):
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(payload, (list, tuple)):
        for v in payload:
            yield from _walk_keys(v)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _runner_module_files() -> List[Path]:
    root = _project_root()
    return [
        root / "app" / "sim" / "blind_walk_forward_manifest.py",
        root / "app" / "sim" / "blind_walk_forward_scoring.py",
        root / "app" / "sim" / "blind_walk_forward_runner.py",
    ]


def _collect_imports(text: str) -> set:
    tree = ast.parse(text)
    mods: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    return mods


def _make_kline(
    *,
    symbol: str,
    open_time: datetime,
    interval: str = "1m",
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
    volume: float = 12.34,
    available_at: datetime = None,
    record_id: str = None,
) -> HistoricalKlineRecord:
    seconds = (
        60 if interval == "1m" else (300 if interval == "5m" else 60)
    )
    if available_at is None:
        available_at = open_time + timedelta(seconds=seconds)
    return HistoricalKlineRecord(
        symbol=symbol,
        interval=interval,
        open_time=open_time,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        available_at=available_at,
        source="binance_public",
        record_id=record_id,
    )


def _make_symbol_status(
    *,
    symbol: str = "BTCUSDT",
    listed_at: datetime = None,
) -> SymbolStatusRecord:
    if listed_at is None:
        listed_at = _T0 - timedelta(days=30)
    return SymbolStatusRecord(
        symbol=symbol,
        market_type="PERP",
        listed_at=listed_at,
        status=SymbolStatus.TRADING,
        available_at=listed_at,
        min_notional=10.0,
        tick_size=0.01,
        step_size=0.001,
        contract_type="USDT_PERP",
        source="binance_public",
    )


def _make_window(
    *,
    train_minutes: int = 5,
    blind_minutes: int = 5,
) -> BlindWalkForwardWindow:
    return BlindWalkForwardWindow(
        train_start=_T0 - timedelta(minutes=train_minutes),
        train_end=_T0,
        blind_start=_T0,
        blind_end=_T0 + timedelta(minutes=blind_minutes),
        reference_window="60d",
    )


def _make_store_with_klines(
    *,
    symbol: str = "BTCUSDT",
    blind_minutes: int = 5,
    include_5m: bool = False,
) -> HistoricalMarketStore:
    """Build a store whose 1m klines cover the blind window.

    The kline at open_time = _T0 + i*1m has available_at = open_time +
    1m, so it becomes visible at simulated_time = _T0 + (i+1)*1m,
    which is exactly the next replay tick. This means tick (i+1)
    sees kline i (the closed candle covering the previous minute).
    """
    store = HistoricalMarketStore()
    store.add_record(_make_symbol_status(symbol=symbol))
    base = 100.0
    klines = []
    for i in range(-1, blind_minutes):
        open_time = _T0 + timedelta(minutes=i)
        close_price = base + i * 0.5
        klines.append(
            _make_kline(
                symbol=symbol,
                open_time=open_time,
                interval="1m",
                open_=close_price - 0.1,
                high=close_price + 0.2,
                low=close_price - 0.3,
                close=close_price,
                record_id=f"k1m_{symbol}_{i + 5}",
            )
        )
    if include_5m:
        klines.append(
            _make_kline(
                symbol=symbol,
                open_time=_T0 - timedelta(minutes=5),
                interval="5m",
                open_=base,
                high=base + 1.0,
                low=base - 1.0,
                close=base + 0.5,
                record_id=f"k5m_{symbol}_0",
            )
        )
    for k in klines:
        store.add_record(k)
    return store


def _make_provider(
    *,
    store: HistoricalMarketStore,
    blind_minutes: int = 5,
) -> ReplayFeedProvider:
    clock = SimulationClock(
        start_time_utc=_T0,
        end_time_utc=_T0 + timedelta(minutes=blind_minutes),
        monotonic_forward_only=True,
    )
    config = ReplayFeedProviderConfig(
        start_time=_T0,
        end_time=_T0 + timedelta(minutes=blind_minutes),
        step_interval=timedelta(minutes=1),
        allow_reemit=False,
        include_asof_universe=True,
    )
    return ReplayFeedProvider(store=store, clock=clock, config=config)


def _make_capital_flow(
    initial_capital: float = 10_000.0,
) -> SimulatedCapitalFlowEngine:
    return SimulatedCapitalFlowEngine(
        config=SimulatedCapitalConfig(initial_capital=initial_capital)
    )


def _make_mock_exchange() -> MockExchange:
    return MockExchange()


def _make_telegram(tmpdir: Path) -> TelegramSandboxOutbox:
    cfg = TelegramSandboxOutboxConfig(
        output_jsonl_path=str(tmpdir / "telegram_sandbox.jsonl"),
        output_markdown_path=str(tmpdir / "telegram_sandbox.md"),
    )
    return TelegramSandboxOutbox(config=cfg)


def _make_runner(
    *,
    tmpdir: Path,
    blind_minutes: int = 5,
    decision_callback=None,
    include_5m: bool = False,
    ai_post_window_summary_enabled: bool = True,
) -> BlindWalkForwardRunner:
    store = _make_store_with_klines(
        blind_minutes=blind_minutes, include_5m=include_5m
    )
    provider = _make_provider(store=store, blind_minutes=blind_minutes)
    capital = _make_capital_flow()
    exchange = _make_mock_exchange()
    telegram = _make_telegram(tmpdir)
    cfg = BlindWalkForwardRunnerConfig(
        window=_make_window(blind_minutes=blind_minutes),
        config_artefact={"ver": 1, "label": "test"},
        rule_artefact={"rules": ["a", "b"]},
        feature_schema_artefact={"schema": ["close", "high"]},
        data_manifest_artefact={"data": "v0"},
        universe_manifest_artefact={"universe": ["BTCUSDT"]},
        fee_model_artefact={"taker_bps": 4.0},
        slippage_model_artefact={"bps": 5.0},
        latency_model_artefact={"bps": 1.0},
        outage_model_artefact={"min_gap_seconds": 0},
        fill_model_artefact={"policy": "WORST_CASE"},
        code_commit="testcommit12345678",
        run_id="bwf_test_run_001",
        report_root=str(tmpdir / "reports"),
        ai_post_window_summary_enabled=ai_post_window_summary_enabled,
    )
    return BlindWalkForwardRunner(
        config=cfg,
        replay_provider=provider,
        capital_flow=capital,
        mock_exchange=exchange,
        telegram_sandbox=telegram,
        decision_callback=decision_callback,
    )


def _buy_then_sell_callback(
    symbol: str = "BTCUSDT", qty: float = 0.1
):
    """Build a deterministic decision callback that submits a BUY on
    the first step and a SELL on the second step.
    """
    state = {"calls": 0}

    def cb(simulated_time, batch, runner):
        state["calls"] += 1
        if state["calls"] == 1:
            return [
                OrderRequest(
                    symbol=symbol,
                    side=MockOrderSide.BUY,
                    order_type=MockOrderType.MARKET,
                    requested_qty=qty,
                )
            ]
        if state["calls"] == 2:
            return [
                OrderRequest(
                    symbol=symbol,
                    side=MockOrderSide.SELL,
                    order_type=MockOrderType.MARKET,
                    requested_qty=qty,
                )
            ]
        return []

    return cb


# ---------------------------------------------------------------------------
# 1. Manifest creation with frozen hashes
# ---------------------------------------------------------------------------


def test_runner_creates_manifest_with_frozen_hashes(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    manifest = runner.prepare_manifest()
    assert isinstance(manifest, BlindRunManifest)
    for fname in (
        "config_hash",
        "rule_hash",
        "feature_schema_hash",
        "data_manifest_hash",
        "universe_manifest_hash",
        "fee_model_hash",
        "slippage_model_hash",
        "latency_model_hash",
        "outage_model_hash",
        "fill_model_hash",
    ):
        h = getattr(manifest, fname)
        assert isinstance(h, str)
        assert h.startswith("sha256:")
        assert h != "sha256:unknown"
        assert len(h) == len("sha256:") + 64
    assert manifest.window.blind_start == _T0
    assert manifest.window.blind_end == _T0 + timedelta(minutes=5)
    assert_no_forbidden_fields(manifest.to_dict())


# ---------------------------------------------------------------------------
# 2. Default base_clock_step is 1m
# ---------------------------------------------------------------------------


def test_runner_uses_base_clock_step_1m_by_default(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    assert runner.config.base_clock_step == "1m"
    manifest = runner.prepare_manifest()
    assert manifest.base_clock_step == "1m"
    md = manifest.to_dict()
    assert md["base_clock_step"] == "1m"
    assert "1m" in md["allowed_timeframes"]


# ---------------------------------------------------------------------------
# 3. SimulationClock advances forward only
# ---------------------------------------------------------------------------


def test_runner_advances_simulation_clock_forward_only(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    runner.run()
    times = [p.timestamp for p in runner.equity_timeseries]
    assert times, "equity timeseries must contain at least one point"
    for prev, nxt in zip(times, times[1:]):
        assert nxt >= prev


# ---------------------------------------------------------------------------
# 4. Runner consumes ReplayFeedProvider batches only
# ---------------------------------------------------------------------------


def test_runner_consumes_replay_feed_provider_batches_only(tmp_path):
    cb = _buy_then_sell_callback()
    runner = _make_runner(tmpdir=tmp_path, decision_callback=cb)
    runner.run()
    assert runner.batches_consumed > 0
    assert runner.batches_consumed == runner.steps_run


# ---------------------------------------------------------------------------
# 5. Future records are rejected and recorded as a no-lookahead violation
# ---------------------------------------------------------------------------


def test_runner_rejects_future_records_and_records_violation(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    runner.prepare_manifest()
    runner.freeze_artifacts()
    fake_violation = NoLookaheadViolation(
        violation_id="v_test_0001",
        reason=NoLookaheadViolationReason.FUTURE_AVAILABLE_AT,
        simulated_time=_T0,
        record_id="r_future",
        symbol="BTCUSDT",
        event_time=_T0 + timedelta(hours=1),
        available_at=_T0 + timedelta(hours=1),
        source="test",
    )
    runner._violations.append(fake_violation)
    runner._record_invalidation(
        BlindRunInvalidationReason.FUTURE_RECORD_ACCESS,
        detail="injected for unit test",
    )
    runner._record_failure(
        kind="no_lookahead_violation",
        detail="injected",
        simulated_time=_T0,
    )
    runner.run_blind_window()
    score = runner.score_after_window_close()
    assert score.status == BlindRunStatus.INVALIDATED_LOOKAHEAD_OR_DRIFT
    assert (
        BlindRunInvalidationReason.FUTURE_RECORD_ACCESS
        in score.invalidation_reasons
    )


# ---------------------------------------------------------------------------
# 6. Runner does not compute outcome labels during the blind window
# ---------------------------------------------------------------------------


def test_runner_does_not_compute_outcome_labels_during_blind_window(
    tmp_path,
):
    runner = _make_runner(tmpdir=tmp_path)
    runner.prepare_manifest()
    runner.freeze_artifacts()
    for _ in range(3):
        b = runner.step_once()
        if b is None:
            break
        assert runner.score is None
        for entry in runner.generate_discovery_quality_ledger():
            for key in entry:
                assert "outcome" not in key.lower()
                assert "tail_label" not in key
                assert "training_label" not in key


# ---------------------------------------------------------------------------
# 7. score_after_window_close computes scoring only after blind_end
# ---------------------------------------------------------------------------


def test_score_after_window_close_only_after_blind_end(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    runner.prepare_manifest()
    runner.freeze_artifacts()
    with pytest.raises(RuntimeError):
        runner.score_after_window_close()
    runner.run_blind_window()
    score = runner.score_after_window_close()
    assert isinstance(score, BlindRunScore)
    assert score.scored_at >= runner.config.window.blind_end


# ---------------------------------------------------------------------------
# 8. auto_tuning_inside_blind_window is False
# ---------------------------------------------------------------------------


def test_auto_tuning_inside_blind_window_is_false(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    assert runner.config.auto_tuning_inside_blind_window is False
    manifest = runner.prepare_manifest()
    md = manifest.to_dict()
    assert md["auto_tuning_inside_blind_window"] is False
    assert md["auto_tuning_allowed"] is False
    with pytest.raises(ValueError):
        BlindWalkForwardRunnerConfig(
            window=_make_window(),
            auto_tuning_inside_blind_window=True,
        )


# ---------------------------------------------------------------------------
# 9. Multi-timeframe feature as-of guard rejects unclosed higher timeframe
# ---------------------------------------------------------------------------


def test_multi_timeframe_asof_guard_rejects_unclosed_higher_timeframe():
    guard = MultiTimeframeAsOfGuard(
        base_clock_step="1m",
        allowed_timeframes=("1m", "5m", "15m", "1h", "4h", "1d"),
    )
    open_time = _T0
    sim_time = _T0 + timedelta(minutes=30)
    available_at = open_time + timedelta(hours=1)
    visible, reason = guard.is_kline_visible(
        timeframe="1h",
        open_time=open_time,
        available_at=available_at,
        simulated_time=sim_time,
    )
    assert visible is False
    assert reason == "unclosed_higher_timeframe_candle"
    sim_time2 = _T0 + timedelta(hours=1)
    visible2, reason2 = guard.is_kline_visible(
        timeframe="1h",
        open_time=open_time,
        available_at=available_at,
        simulated_time=sim_time2,
    )
    assert visible2 is True
    assert reason2 is None


# ---------------------------------------------------------------------------
# 10. Feature cache keyed by as_of_time
# ---------------------------------------------------------------------------


def test_feature_cache_keyed_by_as_of_time():
    cache = AsOfFeatureCache()
    feat_time_a = _T0
    feat_time_b = _T0 + timedelta(minutes=1)
    cache.put(as_of_time=feat_time_a, feature_id="momo_5m", value=1.23)
    cache.put(as_of_time=feat_time_b, feature_id="momo_5m", value=4.56)
    v1 = cache.get(
        as_of_time=feat_time_a,
        feature_id="momo_5m",
        simulated_time=feat_time_a,
    )
    assert v1 == 1.23
    v2 = cache.get(
        as_of_time=feat_time_b,
        feature_id="momo_5m",
        simulated_time=feat_time_a,
    )
    assert v2 is None
    assert cache.future_access_count == 1


# ---------------------------------------------------------------------------
# 11. Blind-window AI bundle cannot include future outcome
# ---------------------------------------------------------------------------


def test_blind_window_ai_bundle_cannot_include_future_outcome(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    runner.prepare_manifest()
    runner.freeze_artifacts()
    with pytest.raises(ValueError):
        runner.assert_blind_window_ai_evidence_bundle(
            bundle={"tail_label": "PEAK"},
            simulated_time=_T0,
        )
    with pytest.raises(ValueError):
        runner.assert_blind_window_ai_evidence_bundle(
            bundle={
                "evidence_refs": [
                    {
                        "ref_id": "r1",
                        "available_at": (
                            _T0 + timedelta(hours=1)
                        ).isoformat(),
                    }
                ]
            },
            simulated_time=_T0,
        )
    runner.assert_blind_window_ai_evidence_bundle(
        bundle={
            "evidence_refs": [
                {
                    "ref_id": "r0",
                    "available_at": (
                        _T0 - timedelta(minutes=1)
                    ).isoformat(),
                }
            ]
        },
        simulated_time=_T0,
    )


# ---------------------------------------------------------------------------
# 12. Post-window AI summary unavailable inside the blind window
# ---------------------------------------------------------------------------


def test_post_window_ai_summary_unavailable_inside_blind_window(
    tmp_path,
):
    runner = _make_runner(tmpdir=tmp_path)
    runner.prepare_manifest()
    runner.freeze_artifacts()
    with pytest.raises(RuntimeError):
        runner.build_post_window_ai_summary(commentary="should refuse")
    runner.run_blind_window()
    summary = runner.build_post_window_ai_summary(commentary="ok")
    assert summary["ai_role"] == "OFFLINE_POST_WINDOW_COMMENTARY_ONLY"
    assert summary["ai_authority"] == "NONE"
    assert summary["is_truth_layer_fact"] is False
    assert summary["is_training_label"] is False
    assert summary["is_tail_label"] is False
    assert summary["is_strategy_validation_sample"] is False
    assert summary["is_runtime_patch"] is False
    assert summary["is_ai_in_decision_chain"] is False


# ---------------------------------------------------------------------------
# 13. AI output cannot become truth / training label / tail_label /
#     strategy sample
# ---------------------------------------------------------------------------


def test_ai_output_cannot_become_truth_training_tail_or_strategy_sample(
    tmp_path,
):
    runner = _make_runner(tmpdir=tmp_path)
    runner.run()
    summary = runner.build_post_window_ai_summary(commentary="x")
    flags = (
        "is_truth_layer_fact",
        "is_training_label",
        "is_tail_label",
        "is_strategy_validation_sample",
        "is_runtime_patch",
        "is_ai_in_decision_chain",
    )
    for flag in flags:
        assert summary[flag] is False
    assert summary["ai_authority"] == "NONE"
    assert summary["trade_authority"] is False


# ---------------------------------------------------------------------------
# 14. MockExchange fills remain simulated_only / no_live_order
# ---------------------------------------------------------------------------


def test_mock_exchange_fills_remain_simulated_only_and_no_live_order(
    tmp_path,
):
    cb = _buy_then_sell_callback()
    runner = _make_runner(tmpdir=tmp_path, decision_callback=cb)
    runner.run()
    ledger_dict = runner.trade_ledger.to_dict()
    payload = json.dumps(ledger_dict, sort_keys=True, default=str)
    assert '"simulated_only": true' in payload
    assert '"no_live_order": true' in payload
    assert '"live_capital_enabled": false' in payload
    assert '"phase_12_forbidden": true' in payload
    assert '"trade_authority": false' in payload


# ---------------------------------------------------------------------------
# 15. Capital flow updates equity timeseries
# ---------------------------------------------------------------------------


def test_capital_flow_updates_equity_timeseries(tmp_path):
    cb = _buy_then_sell_callback()
    runner = _make_runner(tmpdir=tmp_path, decision_callback=cb)
    runner.run()
    pts = runner.equity_timeseries
    assert len(pts) >= 1
    for pt in pts:
        assert pt.simulated_only is True
        assert pt.no_live_order is True
        assert pt.live_capital_enabled is False
        assert pt.phase_12_forbidden is True


# ---------------------------------------------------------------------------
# 16. Trade ledger generated
# ---------------------------------------------------------------------------


def test_trade_ledger_generated(tmp_path):
    cb = _buy_then_sell_callback()
    runner = _make_runner(tmpdir=tmp_path, decision_callback=cb)
    runner.run()
    ledger = runner.trade_ledger
    assert ledger is not None
    summary = ledger.summary().to_dict()
    assert "trade_count" in summary
    assert summary["simulated_only"] is True
    assert summary["no_live_order"] is True
    assert summary["live_capital_enabled"] is False


# ---------------------------------------------------------------------------
# 17. Failure ledger generated
# ---------------------------------------------------------------------------


def test_failure_ledger_generated(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    runner.run()
    fl = runner.generate_failure_ledger()
    assert isinstance(fl, list)
    score = runner.score
    assert score is not None
    assert score.failure_ledger_entry_count == len(fl)


# ---------------------------------------------------------------------------
# 18. Telegram sandbox transcript generated and contains required labels
# ---------------------------------------------------------------------------


def test_telegram_sandbox_transcript_generated_with_required_labels(
    tmp_path,
):
    runner = _make_runner(tmpdir=tmp_path)
    out = runner.run()
    assert "telegram_sandbox_transcript.md" in out["paths"]
    transcript_path = Path(
        out["paths"]["telegram_sandbox_transcript.md"]
    )
    assert transcript_path.exists()
    text = transcript_path.read_text(encoding="utf-8")
    for label in (
        NO_LIVE_ORDER_LABEL,
        NO_REAL_CAPITAL_LABEL,
        NO_TELEGRAM_COMMAND_AUTHORITY_LABEL,
    ):
        assert label in text
    assert "telegram_outbound_enabled=false" in text


# ---------------------------------------------------------------------------
# 19. INVALIDATED_LOOKAHEAD_OR_DRIFT when future access occurs
# ---------------------------------------------------------------------------


def test_invalidated_lookahead_or_drift_when_future_access_occurs(
    tmp_path,
):
    runner = _make_runner(tmpdir=tmp_path)
    runner.prepare_manifest()
    runner.freeze_artifacts()
    runner._record_invalidation(
        BlindRunInvalidationReason.CONFIG_DRIFT,
        detail="injected drift for unit test",
    )
    runner.run_blind_window()
    score = runner.score_after_window_close()
    assert score.status == BlindRunStatus.INVALIDATED_LOOKAHEAD_OR_DRIFT
    assert (
        BlindRunInvalidationReason.CONFIG_DRIFT
        in score.invalidation_reasons
    )


# ---------------------------------------------------------------------------
# 20. phase_12_forbidden = True
# ---------------------------------------------------------------------------


def test_phase_12_forbidden_in_every_payload(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    out = runner.run()
    for fname in (
        "blind_run_manifest.json",
        "blind_walk_forward_report.json",
    ):
        p = Path(out["paths"][fname])
        payload = json.loads(p.read_text(encoding="utf-8"))
        assert payload["phase_12_forbidden"] is True


# ---------------------------------------------------------------------------
# 21. live_trading = False
# ---------------------------------------------------------------------------


def test_live_trading_false_in_every_payload(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    out = runner.run()
    for fname in (
        "blind_run_manifest.json",
        "blind_walk_forward_report.json",
        "trade_ledger.json",
        "equity_timeseries.json",
        "discovery_quality_ledger.json",
        "failure_ledger.json",
        "no_lookahead_violations.json",
    ):
        p = Path(out["paths"][fname])
        payload = json.loads(p.read_text(encoding="utf-8"))
        assert payload["live_trading"] is False


# ---------------------------------------------------------------------------
# 22. exchange_live_orders = False
# ---------------------------------------------------------------------------


def test_exchange_live_orders_false_in_every_payload(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    out = runner.run()
    for fname in (
        "blind_run_manifest.json",
        "blind_walk_forward_report.json",
        "trade_ledger.json",
        "equity_timeseries.json",
        "discovery_quality_ledger.json",
        "failure_ledger.json",
        "no_lookahead_violations.json",
    ):
        p = Path(out["paths"][fname])
        payload = json.loads(p.read_text(encoding="utf-8"))
        assert payload["exchange_live_orders"] is False


# ---------------------------------------------------------------------------
# 23. binance_private_api_enabled = False
# ---------------------------------------------------------------------------


def test_binance_private_api_enabled_false_in_every_payload(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    out = runner.run()
    for fname in (
        "blind_run_manifest.json",
        "blind_walk_forward_report.json",
        "trade_ledger.json",
        "equity_timeseries.json",
        "discovery_quality_ledger.json",
        "failure_ledger.json",
        "no_lookahead_violations.json",
    ):
        p = Path(out["paths"][fname])
        payload = json.loads(p.read_text(encoding="utf-8"))
        assert payload["binance_private_api_enabled"] is False


# ---------------------------------------------------------------------------
# 24. auto_tuning_allowed = False
# ---------------------------------------------------------------------------


def test_auto_tuning_allowed_false_in_every_payload(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    out = runner.run()
    for fname in (
        "blind_run_manifest.json",
        "blind_walk_forward_report.json",
        "trade_ledger.json",
        "equity_timeseries.json",
        "discovery_quality_ledger.json",
        "failure_ledger.json",
        "no_lookahead_violations.json",
    ):
        p = Path(out["paths"][fname])
        payload = json.loads(p.read_text(encoding="utf-8"))
        assert payload["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# 25. trade_authority = False
# ---------------------------------------------------------------------------


def test_trade_authority_false_in_every_payload(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    out = runner.run()
    for fname in (
        "blind_run_manifest.json",
        "blind_walk_forward_report.json",
        "trade_ledger.json",
        "equity_timeseries.json",
        "discovery_quality_ledger.json",
        "failure_ledger.json",
        "no_lookahead_violations.json",
    ):
        p = Path(out["paths"][fname])
        payload = json.loads(p.read_text(encoding="utf-8"))
        assert payload["trade_authority"] is False


# ---------------------------------------------------------------------------
# 26. Forbidden fields absent from serialized outputs
# ---------------------------------------------------------------------------


def test_forbidden_fields_absent_from_serialised_outputs(tmp_path):
    cb = _buy_then_sell_callback()
    runner = _make_runner(tmpdir=tmp_path, decision_callback=cb)
    out = runner.run()
    for fname in (
        "blind_run_manifest.json",
        "blind_walk_forward_report.json",
        "trade_ledger.json",
        "equity_timeseries.json",
        "discovery_quality_ledger.json",
        "failure_ledger.json",
        "no_lookahead_violations.json",
    ):
        p = Path(out["paths"][fname])
        payload = json.loads(p.read_text(encoding="utf-8"))
        keys = set(_walk_keys(payload))
        forbidden_seen = keys & FORBIDDEN_OUTPUT_FIELDS
        assert not forbidden_seen, (
            f"forbidden keys {forbidden_seen} found in {fname}"
        )


# ---------------------------------------------------------------------------
# 27. Module does not import app.exchanges / app.telegram / app.config /
#     app.risk / app.execution
# ---------------------------------------------------------------------------


def test_runner_does_not_import_forbidden_app_modules():
    forbidden_prefixes = (
        "app.risk",
        "app.execution",
        "app.exchanges",
        "app.telegram",
        "app.config",
    )
    for path in _runner_module_files():
        text = path.read_text(encoding="utf-8")
        mods = _collect_imports(text)
        for m in mods:
            for fp in forbidden_prefixes:
                assert not (m == fp or m.startswith(fp + ".")), (
                    f"{path.name} imports forbidden module {m!r}"
                )


# ---------------------------------------------------------------------------
# 28. No DeepSeek / LLM / network call path required
# ---------------------------------------------------------------------------


def test_no_deepseek_llm_or_network_call_path_required():
    forbidden_substrings = (
        "deepseek",
        "openai",
        "anthropic",
        "requests",
        "httpx",
        "urllib",
        "websocket",
        "telegram_bot",
        "ccxt",
    )
    for path in _runner_module_files():
        text = path.read_text(encoding="utf-8")
        mods = _collect_imports(text)
        for m in mods:
            lo = m.lower()
            for s in forbidden_substrings:
                assert s not in lo, (
                    f"{path.name} imports {m!r} which contains "
                    f"forbidden substring {s!r}"
                )


# ---------------------------------------------------------------------------
# 29. Deterministic output with fixed fixture
# ---------------------------------------------------------------------------


def test_deterministic_output_with_fixed_fixture(tmp_path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    out_a.mkdir()
    out_b.mkdir()

    def _run(target: Path) -> Dict[str, Any]:
        cb = _buy_then_sell_callback()
        store = _make_store_with_klines(blind_minutes=5)
        provider = _make_provider(store=store, blind_minutes=5)
        capital = _make_capital_flow()
        exchange = _make_mock_exchange()
        telegram = TelegramSandboxOutbox(
            config=TelegramSandboxOutboxConfig(
                output_jsonl_path=str(target / "tg.jsonl"),
                output_markdown_path=str(target / "tg.md"),
            )
        )
        cfg = BlindWalkForwardRunnerConfig(
            window=_make_window(blind_minutes=5),
            config_artefact={"ver": 1, "label": "test"},
            rule_artefact={"rules": ["a", "b"]},
            feature_schema_artefact={"schema": ["close", "high"]},
            data_manifest_artefact={"data": "v0"},
            universe_manifest_artefact={"universe": ["BTCUSDT"]},
            fee_model_artefact={"taker_bps": 4.0},
            slippage_model_artefact={"bps": 5.0},
            latency_model_artefact={"bps": 1.0},
            outage_model_artefact={"min_gap_seconds": 0},
            fill_model_artefact={"policy": "WORST_CASE"},
            code_commit="testcommit12345678",
            run_id="bwf_det_run",
            report_root=str(target / "reports"),
        )
        runner = BlindWalkForwardRunner(
            config=cfg,
            replay_provider=provider,
            capital_flow=capital,
            mock_exchange=exchange,
            telegram_sandbox=telegram,
            decision_callback=cb,
        )
        return runner.run()

    res_a = _run(out_a)
    res_b = _run(out_b)
    ma = res_a["manifest"]
    mb = res_b["manifest"]
    for k in (
        "config_hash",
        "rule_hash",
        "feature_schema_hash",
        "data_manifest_hash",
        "universe_manifest_hash",
        "fee_model_hash",
        "slippage_model_hash",
        "latency_model_hash",
        "outage_model_hash",
        "fill_model_hash",
        "base_clock_step",
    ):
        assert ma[k] == mb[k], f"manifest field {k} mismatch"
    sa = res_a["score"]
    sb = res_b["score"]
    for k in (
        "status",
        "sample_count",
        "closed_trade_count",
        "win_count",
        "loss_count",
        "breakeven_count",
        "no_lookahead_violation_count",
        "failure_ledger_entry_count",
    ):
        assert sa[k] == sb[k], f"score field {k} mismatch"


# ---------------------------------------------------------------------------
# 30. No Phase 12 / no live-ready wording in any output
# ---------------------------------------------------------------------------


def test_no_phase_12_or_live_ready_wording_in_outputs(tmp_path):
    runner = _make_runner(tmpdir=tmp_path)
    out = runner.run()
    forbidden_phrases = (
        "live_ready",
        "live ready",
        "trading_approved",
        "trading approved",
        "enable_live",
        "deploy_change",
        "apply_change",
    )
    forbidden_phase_phrases = (
        "phase 12 enabled",
        "phase_12_enabled",
        "phase 12 = allowed",
        "phase 12 = enabled",
    )
    for fname in (
        "blind_run_manifest.json",
        "blind_walk_forward_report.json",
        "blind_walk_forward_report.md",
        "trade_ledger.json",
        "equity_timeseries.json",
        "discovery_quality_ledger.json",
        "failure_ledger.json",
        "no_lookahead_violations.json",
    ):
        p = Path(out["paths"][fname])
        text = p.read_text(encoding="utf-8")
        lo = text.lower()
        for s in forbidden_phrases:
            assert s not in lo, (
                f"forbidden phrase {s!r} present in {fname}"
            )
        for s in forbidden_phase_phrases:
            assert s not in lo, (
                f"forbidden phrase {s!r} present in {fname}"
            )


# ---------------------------------------------------------------------------
# Bonus: scoring helper produces INSUFFICIENT_EVIDENCE on empty run
# ---------------------------------------------------------------------------


def test_score_insufficient_evidence_on_empty_run():
    score = score_blind_run(
        run_id="r",
        window_id="w",
        scored_at=_T0,
        sample_count=0,
        ledger_summary={"trade_count": 0},
        no_lookahead_violation_count=0,
        failure_ledger_entry_count=0,
    )
    assert score.status == BlindRunStatus.INSUFFICIENT_EVIDENCE



# ===========================================================================
# PR103 - Blind Runner Historical Store Input Glue
# (Phase 11C.1D-D-I)
#
# These tests cover wiring a PR101/PR102 Historical Data Store
# (records.jsonl + historical_data_manifest.json + universe_manifest.json)
# into the PR100 Blind Walk-forward Runner CLI. They never relax the
# PR94 TimeWallGuard / PR96 ReplayFeedProvider gates and never fabricate
# data.
# ===========================================================================

from scripts import run_blind_walk_forward as bwf_cli  # noqa: E402


_PR103_T0 = datetime(2026, 5, 2, 0, 0, 0, tzinfo=timezone.utc)


def _pr103_kline(
    open_time: datetime,
    close_price: float,
    record_id: str,
    *,
    symbol: str = "BTCUSDT",
    interval: str = "1m",
) -> HistoricalKlineRecord:
    seconds = 60 if interval == "1m" else 300
    return HistoricalKlineRecord(
        symbol=symbol,
        interval=interval,
        open_time=open_time,
        open=close_price - 0.1,
        high=close_price + 0.2,
        low=close_price - 0.3,
        close=close_price,
        volume=12.34,
        available_at=open_time + timedelta(seconds=seconds),
        source="binance_public",
        record_id=record_id,
    )


def _pr103_symbol_status(symbol: str = "BTCUSDT") -> SymbolStatusRecord:
    listed = _PR103_T0 - timedelta(days=30)
    return SymbolStatusRecord(
        symbol=symbol,
        market_type="PERP",
        listed_at=listed,
        status=SymbolStatus.TRADING,
        available_at=listed,
        min_notional=10.0,
        tick_size=0.01,
        step_size=0.001,
        contract_type="USDT_PERP",
        source="binance_public",
    )


def _pr103_valid_records(symbol: str = "BTCUSDT") -> List[Any]:
    """As-of fixture whose every record is available by the first
    replay tick (blind_start + 1m).

    Because no record is ever ``available_at > simulated_time`` at any
    tick, the strict forward-only replay raises **zero** no-lookahead
    violations - this is the canonical "valid as-of fixture".
    """
    recs: List[Any] = [_pr103_symbol_status(symbol)]
    base = 100.0
    # open_time T0-5m .. T0  =>  available_at (= close_time) <= T0+1m.
    for i in range(-5, 1):
        recs.append(
            _pr103_kline(
                _PR103_T0 + timedelta(minutes=i),
                base + i * 0.5,
                f"{symbol}_k_{i}",
                symbol=symbol,
            )
        )
    return recs


def _pr103_write_store_dir(
    base_dir: Path,
    records: List[Any],
    *,
    write_data_manifest: bool = True,
    write_universe_manifest: bool = True,
    data_manifest_hash: str = None,
    universe_manifest_hash: str = None,
    source_files: Tuple[str, ...] = ("BTCUSDT-1m.csv",),
    record_counts: Dict[str, int] = None,
) -> Path:
    """Write a PR101-style Historical Data Store directory."""
    store_dir = Path(base_dir)
    store_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r.to_dict(), sort_keys=True) for r in records]
    (store_dir / "records.jsonl").write_text(
        "\n".join(lines) + ("\n" if lines else ""),
        encoding="utf-8",
    )
    if write_data_manifest:
        dm = {
            "data_manifest_hash": (
                data_manifest_hash or ("sha256:" + "a" * 64)
            ),
            "source_files": list(source_files),
            "record_counts_by_type": dict(
                record_counts or {"KLINE_1M": 6, "SYMBOL_STATUS": 1}
            ),
            "is_historical_data_manifest": True,
        }
        (store_dir / "historical_data_manifest.json").write_text(
            json.dumps(dm, sort_keys=True), encoding="utf-8"
        )
    if write_universe_manifest:
        um = {
            "universe_manifest_hash": (
                universe_manifest_hash or ("sha256:" + "b" * 64)
            ),
            "is_universe_manifest": True,
        }
        (store_dir / "universe_manifest.json").write_text(
            json.dumps(um, sort_keys=True), encoding="utf-8"
        )
    return store_dir


def _pr103_cli_args(
    store_dir,
    report_root: Path,
    *,
    run_id: str = "pr103_run",
    blind_minutes: int = 3,
    extra: List[str] = None,
) -> List[str]:
    args = [
        "--train-start",
        (_PR103_T0 - timedelta(minutes=5)).isoformat(),
        "--train-end",
        _PR103_T0.isoformat(),
        "--blind-start",
        _PR103_T0.isoformat(),
        "--blind-end",
        (_PR103_T0 + timedelta(minutes=blind_minutes)).isoformat(),
        "--reference-window",
        "60d",
        "--report-root",
        str(report_root),
        "--run-id",
        run_id,
        "--base-clock-step",
        "1m",
        "--initial-capital",
        "10000",
        "--no-ai-post-window-summary",
    ]
    if store_dir is not None:
        args += ["--historical-store-dir", str(store_dir)]
    if extra:
        args += extra
    return args


# ---- 1. CLI accepts --historical-store-dir (+ the explicit overrides) ----


def test_pr103_cli_accepts_historical_store_dir():
    parser = bwf_cli._build_argparser()
    ns = parser.parse_args(
        _pr103_cli_args("data/historical_market_store/x", Path("/tmp/r"))
    )
    assert ns.historical_store_dir == "data/historical_market_store/x"
    # The explicit override flags are also accepted.
    ns2 = parser.parse_args(
        [
            "--train-start",
            _PR103_T0.isoformat(),
            "--train-end",
            _PR103_T0.isoformat(),
            "--blind-start",
            _PR103_T0.isoformat(),
            "--blind-end",
            (_PR103_T0 + timedelta(minutes=1)).isoformat(),
            "--records-path",
            "x/records.jsonl",
            "--historical-data-manifest-path",
            "x/historical_data_manifest.json",
            "--universe-manifest-path",
            "x/universe_manifest.json",
        ]
    )
    assert ns2.records_path == "x/records.jsonl"
    assert (
        ns2.historical_data_manifest_path
        == "x/historical_data_manifest.json"
    )
    assert ns2.universe_manifest_path == "x/universe_manifest.json"


# ---- 2. CLI loads records.jsonl from the historical store dir ----


def test_pr103_load_records_jsonl_restores_record_types(tmp_path):
    store_dir = _pr103_write_store_dir(
        tmp_path / "store", _pr103_valid_records()
    )
    records = bwf_cli.load_records_jsonl(store_dir / "records.jsonl")
    assert len(records) == 7  # 1 symbol status + 6 klines
    klines = [
        r for r in records if isinstance(r, HistoricalKlineRecord)
    ]
    statuses = [
        r for r in records if isinstance(r, SymbolStatusRecord)
    ]
    assert len(klines) == 6
    assert len(statuses) == 1
    # Round-trip fidelity: a restored kline serialises identically.
    src = _pr103_valid_records()
    by_id = {r.record_id: r for r in records}
    for orig in src:
        assert orig.to_dict() == by_id[orig.record_id].to_dict()


# ---- 3. HistoricalKlineRecord JSONL restores into HistoricalMarketStore --


def test_pr103_records_restore_into_historical_market_store(tmp_path):
    store_dir = _pr103_write_store_dir(
        tmp_path / "store", _pr103_valid_records()
    )
    records = bwf_cli.load_records_jsonl(store_dir / "records.jsonl")
    store = bwf_cli.build_historical_store_from_records(records)
    assert isinstance(store, HistoricalMarketStore)
    assert store.kline_count == 6
    assert store.symbol_status_count == 1
    assert store.record_count == 7


# ---- 4. Blind runner consumes real records through ReplayFeedProvider ----


def test_pr103_blind_runner_consumes_records_via_replay_provider(
    tmp_path,
):
    store_dir = _pr103_write_store_dir(
        tmp_path / "store", _pr103_valid_records()
    )
    loaded = bwf_cli.load_historical_store_dir(store_dir=str(store_dir))
    assert loaded.status is None
    blind_end = _PR103_T0 + timedelta(minutes=3)
    clock = SimulationClock(
        start_time_utc=_PR103_T0,
        end_time_utc=blind_end,
        monotonic_forward_only=True,
    )
    provider = ReplayFeedProvider(
        store=loaded.store,
        clock=clock,
        config=ReplayFeedProviderConfig(
            start_time=_PR103_T0,
            end_time=blind_end,
            step_interval=timedelta(minutes=1),
            allow_reemit=False,
            include_asof_universe=True,
        ),
    )
    total_klines = 0
    total_violations = 0
    while not provider.replay_complete:
        batch = provider.next_batch()
        if batch is None:
            break
        total_klines += len(batch.klines_1m)
        total_violations += len(batch.violations)
    assert total_klines == 6, "runner must see the real restored klines"
    assert total_violations == 0


# ---- 5. Missing records.jsonl returns INSUFFICIENT_EVIDENCE (no fake) ----


def test_pr103_missing_records_jsonl_insufficient_evidence(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    loaded = bwf_cli.load_historical_store_dir(store_dir=str(empty_dir))
    assert loaded.status == BlindRunStatus.INSUFFICIENT_EVIDENCE
    assert loaded.record_count == 0
    assert loaded.data_manifest_hash is None
    # End-to-end: main() reports INSUFFICIENT_EVIDENCE and exit code 3.
    rc = bwf_cli.main(
        _pr103_cli_args(empty_dir, tmp_path / "reports", run_id="miss")
    )
    assert rc == 3


# ---- 6. Empty records.jsonl returns INSUFFICIENT_EVIDENCE ----


def test_pr103_empty_records_jsonl_insufficient_evidence(tmp_path):
    store_dir = _pr103_write_store_dir(
        tmp_path / "store",
        [],
        write_data_manifest=False,
        write_universe_manifest=False,
    )
    assert (store_dir / "records.jsonl").read_text() == ""
    loaded = bwf_cli.load_historical_store_dir(store_dir=str(store_dir))
    assert loaded.status == BlindRunStatus.INSUFFICIENT_EVIDENCE
    rc = bwf_cli.main(
        _pr103_cli_args(store_dir, tmp_path / "reports", run_id="empty")
    )
    assert rc == 3


# ---- 7. data_manifest_hash from manifest appears in BlindRunManifest ----


def test_pr103_data_manifest_hash_in_blind_run_manifest(tmp_path):
    dm_hash = "sha256:" + "c" * 64
    store_dir = _pr103_write_store_dir(
        tmp_path / "store",
        _pr103_valid_records(),
        data_manifest_hash=dm_hash,
    )
    report_root = tmp_path / "reports"
    rc = bwf_cli.main(
        _pr103_cli_args(store_dir, report_root, run_id="dmhash")
    )
    assert rc == 0
    manifest = json.loads(
        (report_root / "dmhash" / "blind_run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["data_manifest_hash"] == dm_hash


# ---- 8. universe_manifest_hash appears when universe_manifest exists ----


def test_pr103_universe_manifest_hash_in_blind_run_manifest(tmp_path):
    um_hash = "sha256:" + "d" * 64
    store_dir = _pr103_write_store_dir(
        tmp_path / "store",
        _pr103_valid_records(),
        universe_manifest_hash=um_hash,
    )
    report_root = tmp_path / "reports"
    rc = bwf_cli.main(
        _pr103_cli_args(store_dir, report_root, run_id="umhash")
    )
    assert rc == 0
    manifest = json.loads(
        (report_root / "umhash" / "blind_run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["universe_manifest_hash"] == um_hash


# ---- 8b. Missing universe_manifest WARNs but does not block kline-only ----


def test_pr103_missing_universe_manifest_does_not_block(tmp_path):
    store_dir = _pr103_write_store_dir(
        tmp_path / "store",
        _pr103_valid_records(),
        write_universe_manifest=False,
    )
    loaded = bwf_cli.load_historical_store_dir(store_dir=str(store_dir))
    assert loaded.status is None
    assert loaded.universe_manifest_hash is None
    assert any("universe_manifest" in w for w in loaded.warnings)
    report_root = tmp_path / "reports"
    rc = bwf_cli.main(
        _pr103_cli_args(store_dir, report_root, run_id="nouvm")
    )
    assert rc == 0


# ---- 8c. Missing data_manifest WARNs but does not fabricate a hash ----


def test_pr103_missing_data_manifest_warns_no_fabricated_hash(tmp_path):
    store_dir = _pr103_write_store_dir(
        tmp_path / "store",
        _pr103_valid_records(),
        write_data_manifest=False,
    )
    loaded = bwf_cli.load_historical_store_dir(store_dir=str(store_dir))
    assert loaded.status is None
    assert loaded.data_manifest_hash is None
    assert any(
        "historical_data_manifest" in w for w in loaded.warnings
    )


# ---- 9. No-lookahead violations remain zero for valid as-of fixture ----


def test_pr103_no_lookahead_violations_zero_for_valid_fixture(tmp_path):
    store_dir = _pr103_write_store_dir(
        tmp_path / "store", _pr103_valid_records()
    )
    report_root = tmp_path / "reports"
    rc = bwf_cli.main(
        _pr103_cli_args(store_dir, report_root, run_id="zeroviol")
    )
    assert rc == 0
    run_dir = report_root / "zeroviol"
    viol = json.loads(
        (run_dir / "no_lookahead_violations.json").read_text(
            encoding="utf-8"
        )
    )
    assert viol["violations"] == []
    assert viol["invalidations"] == []
    score = json.loads(
        (run_dir / "blind_walk_forward_report.json").read_text(
            encoding="utf-8"
        )
    )
    # The report embeds the score; violation count must be zero.
    assert score.get("no_lookahead_violation_count", 0) == 0


# ---- 10-16. Safety boundary flags pinned in the BlindRunManifest ----


def test_pr103_safety_flags_pinned_in_manifest_and_summary(tmp_path):
    store_dir = _pr103_write_store_dir(
        tmp_path / "store", _pr103_valid_records()
    )
    report_root = tmp_path / "reports"
    rc = bwf_cli.main(
        _pr103_cli_args(store_dir, report_root, run_id="safety")
    )
    assert rc == 0
    manifest = json.loads(
        (report_root / "safety" / "blind_run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["phase_12_forbidden"] is True
    assert manifest["live_trading"] is False
    assert manifest["exchange_live_orders"] is False
    assert manifest["binance_private_api_enabled"] is False
    assert manifest["telegram_outbound_enabled"] is False
    assert manifest["auto_tuning_allowed"] is False
    assert manifest["trade_authority"] is False
    # The historical-store sidecar carries the same boundary.
    sidecar = json.loads(
        (
            report_root / "safety" / "historical_store_input.json"
        ).read_text(encoding="utf-8")
    )
    assert sidecar["phase_12_forbidden"] is True
    assert sidecar["live_trading"] is False
    assert sidecar["exchange_live_orders"] is False
    assert sidecar["binance_private_api_enabled"] is False
    assert sidecar["telegram_outbound_enabled"] is False
    assert sidecar["auto_tuning_allowed"] is False
    assert sidecar["trade_authority"] is False


# ---- 17. The CLI script imports no app.exchanges / app.telegram /
#          app.config (nor app.risk / app.execution / app.ai) ----


def _pr103_script_path() -> Path:
    return (
        _project_root()
        / "scripts"
        / "run_blind_walk_forward.py"
    )


def test_pr103_script_imports_no_forbidden_app_modules():
    forbidden_prefixes = (
        "app.risk",
        "app.execution",
        "app.exchanges",
        "app.telegram",
        "app.config",
        "app.ai",
    )
    mods = _collect_imports(
        _pr103_script_path().read_text(encoding="utf-8")
    )
    for m in mods:
        for fp in forbidden_prefixes:
            assert not (m == fp or m.startswith(fp + ".")), (
                f"run_blind_walk_forward.py imports forbidden "
                f"module {m!r}"
            )


# ---- 18. No network / private API / DeepSeek / LLM call path ----


def test_pr103_script_imports_no_network_or_llm_modules():
    forbidden_substrings = (
        "deepseek",
        "openai",
        "anthropic",
        "requests",
        "httpx",
        "urllib",
        "http.client",
        "socket",
        "websocket",
        "aiohttp",
        "ccxt",
        "binance",
        "telegram",
    )
    mods = _collect_imports(
        _pr103_script_path().read_text(encoding="utf-8")
    )
    for m in mods:
        lo = m.lower()
        for s in forbidden_substrings:
            assert s not in lo, (
                f"run_blind_walk_forward.py imports {m!r} which "
                f"contains forbidden substring {s!r}"
            )


# ---- 19. Forbidden fields absent from serialized PR103 outputs ----


def test_pr103_forbidden_fields_absent_from_outputs(tmp_path):
    store_dir = _pr103_write_store_dir(
        tmp_path / "store", _pr103_valid_records()
    )
    report_root = tmp_path / "reports"
    rc = bwf_cli.main(
        _pr103_cli_args(store_dir, report_root, run_id="nofbd")
    )
    assert rc == 0
    run_dir = report_root / "nofbd"
    for name in (
        "blind_run_manifest.json",
        "blind_walk_forward_report.json",
        "historical_store_input.json",
        "no_lookahead_violations.json",
    ):
        payload = json.loads(
            (run_dir / name).read_text(encoding="utf-8")
        )
        # Should not raise.
        assert_no_forbidden_fields(payload)
        keys = set(_walk_keys(payload))
        assert not (keys & FORBIDDEN_OUTPUT_FIELDS)
        # No real exchange / account / secret leakage either.
        for banned in (
            "api_key",
            "api_secret",
            "real_exchange_order_id",
            "exchange_order_id",
            "real_account_id",
            "listen_key",
        ):
            assert banned not in keys


# ---- 20. Deterministic output with a fixed fixture ----


def test_pr103_deterministic_output_with_fixed_fixture(tmp_path):
    store_dir = _pr103_write_store_dir(
        tmp_path / "store", _pr103_valid_records()
    )

    def _run(tag: str) -> Dict[str, Any]:
        report_root = tmp_path / f"reports_{tag}"
        rc = bwf_cli.main(
            _pr103_cli_args(
                store_dir, report_root, run_id="bwf_pr103_det"
            )
        )
        assert rc == 0
        return json.loads(
            (
                report_root
                / "bwf_pr103_det"
                / "blind_run_manifest.json"
            ).read_text(encoding="utf-8")
        )

    manifest_a = _run("a")
    manifest_b = _run("b")
    assert manifest_a == manifest_b
    assert manifest_a["data_manifest_hash"] == "sha256:" + "a" * 64
    assert manifest_a["universe_manifest_hash"] == "sha256:" + "b" * 64


# ---- Config-level: explicit hash overrides validated as sha256 ----


def test_pr103_runner_config_rejects_non_sha256_hash_override():
    with pytest.raises(ValueError):
        BlindWalkForwardRunnerConfig(
            window=_make_window(blind_minutes=3),
            data_manifest_hash="not-a-hash",
        )
    # A valid sha256 override is accepted and pinned onto the manifest.
    cfg = BlindWalkForwardRunnerConfig(
        window=_make_window(blind_minutes=3),
        data_manifest_hash="sha256:" + "e" * 64,
        universe_manifest_hash="sha256:" + "f" * 64,
    )
    assert cfg.data_manifest_hash == "sha256:" + "e" * 64
    assert cfg.universe_manifest_hash == "sha256:" + "f" * 64
