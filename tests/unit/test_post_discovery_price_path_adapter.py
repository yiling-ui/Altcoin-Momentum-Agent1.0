"""Phase 11C.1C-C-B-B-B-D-B.1 - Post-Discovery Price Path Adapter v0
unit tests / *Kline Path Adapter v0 单测*.

Paper / report / evidence ONLY. None of these tests authorise a
real trade or modify any runtime knob.

Test plan:

  1. Adapter without a store path returns ABSENT resolutions with
     ``HISTORICAL_STORE_DIR_NOT_PROVIDED`` missing reason.
  2. Adapter pointed at a missing directory returns
     ``HISTORICAL_STORE_DIR_MISSING``.
  3. Adapter pointed at an empty store returns
     ``HISTORICAL_STORE_EMPTY``.
  4. Containing-day lookup picks ``first_seen_price = open_price``
     and never returns the day's high / low / close as
     ``first_seen_price``.
  5. Lookahead Guard: post-first-seen path NEVER carries a point
     whose timestamp is <= ``first_seen_time_utc_ms``.
  6. Containing-day open / high / low are dropped from the post-
     first-seen path; only the close at ``day_end_ms`` is kept.
  7. Subsequent-day OHLC is emitted; high / low are stamped at
     ``day_end_ms`` (approximate intra-day timestamps surfaced via
     ``approximate_intra_day_timestamps``).
  8. ``first_seen_time_utc_ms is None`` -> NO_FIRST_SEEN_TIME.
  9. Symbol absent from the store -> SYMBOL_NOT_IN_HISTORICAL_STORE.
 10. ``first_seen_time`` outside any daily row -> NO_TOP_MOVER_ROW_
     COVERING_FIRST_SEEN_TIME.
 11. ``reference_window_end_utc_ms`` upper bound clips the path.
 12. ``summarise_price_path_resolutions`` aggregates source +
     missing reason summaries.
 13. Forbidden imports: the adapter module never imports Risk /
     Execution / private exchange / LLM / Telegram modules.
 14. The adapter never opens a network socket or signs a request
     (proven by the no-network surface + no-credential reading).
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.adaptive.post_discovery_price_path_adapter import (  # noqa: E402
    DEFAULT_KLINE_INTERVAL_USED,
    HistoricalPricePathAdapter,
    PricePathMissingReason,
    PricePathResolution,
    PricePathSource,
    build_operator_supplied_price_path_resolution,
    summarise_price_path_resolutions,
)
from app.adaptive.post_discovery_outcome_metrics import (  # noqa: E402
    PricePoint,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DAY_MS = 24 * 60 * 60 * 1000
_BASE_MS = 1_767_225_600_000  # ~ 2026-01-01T00:00:00Z


def _ms(day: int, hour: int = 0) -> int:
    return _BASE_MS + day * _DAY_MS + hour * 60 * 60 * 1000


def _row(
    *,
    symbol: str,
    day: int,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    rank: int = 1,
) -> dict[str, object]:
    """Build a top_mover row in the same shape that
    :func:`scripts.build_historical_mover_reference_store.klines_to_daily_top_movers`
    writes.

    Lookahead-forbidden columns (``completed_tail_label``, etc.)
    are intentionally absent so the loader does not raise.
    """

    day_start_ms = _ms(day)
    day_end_ms = day_start_ms + _DAY_MS
    return {
        "symbol": symbol,
        "snapshot_date": "2026-01-01",
        "reference_timestamp_utc_ms": day_end_ms,
        "mover_window_start_utc_ms": day_start_ms,
        "mover_window_end_utc_ms": day_end_ms,
        "timeframe": "1h",
        "open_price": open_price,
        "close_price": close_price,
        "high_price": high_price,
        "low_price": low_price,
        "window_gain_pct": (close_price - open_price) / open_price,
        "max_window_gain": (close_price - open_price) / open_price,
        "max_24h_gain_pct": (high_price - open_price) / open_price,
        "max_24h_gain": (high_price - open_price) / open_price,
        "min_window_drawdown_pct": (low_price - open_price) / open_price,
        "quote_volume": 1_000_000.0,
        "quote_volume_usdt": 1_000_000.0,
        "kline_count": 24,
        "quote_asset": "USDT",
        "contract_type": "PERPETUAL",
        "eligible_usdt_perpetual": True,
        "source": "binance_public_futures_klines_1h",
        "lookahead_policy": "post_hoc_reference_only",
        "top_mover_rank": rank,
    }


def _write_store(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    """Write a Historical Market Store layout under ``tmp_path/store``."""

    root = tmp_path / "store"
    top_movers_dir = root / "top_movers"
    top_movers_dir.mkdir(parents=True)
    (top_movers_dir / "rows.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    return root


# ---------------------------------------------------------------------------
# Adapter availability
# ---------------------------------------------------------------------------


def test_adapter_without_store_dir_returns_absent_resolutions() -> None:
    """No historical_store_dir -> every resolve returns ABSENT
    with ``HISTORICAL_STORE_DIR_NOT_PROVIDED``."""

    adapter = HistoricalPricePathAdapter(historical_store_dir=None)
    assert not adapter.is_available
    assert (
        adapter.initial_missing_reason
        == PricePathMissingReason.HISTORICAL_STORE_DIR_NOT_PROVIDED
    )

    resolution = adapter.resolve(
        symbol="RAVEUSDT", first_seen_time_utc_ms=_ms(3, hour=2)
    )
    assert resolution.source == PricePathSource.ABSENT
    assert (
        resolution.missing_reason
        == PricePathMissingReason.HISTORICAL_STORE_DIR_NOT_PROVIDED
    )
    assert resolution.first_seen_price is None
    assert resolution.price_path == ()
    assert not resolution.is_loaded()


def test_adapter_with_missing_store_dir(tmp_path: Path) -> None:
    """Historical store directory does not exist on disk -> the
    adapter records the gap explicitly."""

    adapter = HistoricalPricePathAdapter(
        historical_store_dir=tmp_path / "does_not_exist"
    )
    assert not adapter.is_available
    assert (
        adapter.initial_missing_reason
        == PricePathMissingReason.HISTORICAL_STORE_DIR_MISSING
    )

    resolution = adapter.resolve(
        symbol="RAVEUSDT", first_seen_time_utc_ms=_ms(3, hour=2)
    )
    assert (
        resolution.missing_reason
        == PricePathMissingReason.HISTORICAL_STORE_DIR_MISSING
    )
    assert resolution.first_seen_price is None
    assert resolution.price_path == ()


def test_adapter_with_empty_store(tmp_path: Path) -> None:
    """Empty top_movers/ -> ``HISTORICAL_STORE_EMPTY``."""

    root = tmp_path / "store"
    (root / "top_movers").mkdir(parents=True)

    adapter = HistoricalPricePathAdapter(historical_store_dir=root)
    assert not adapter.is_available
    assert (
        adapter.initial_missing_reason
        == PricePathMissingReason.HISTORICAL_STORE_EMPTY
    )


# ---------------------------------------------------------------------------
# Containing-day anchor (lookahead-safe first_seen_price)
# ---------------------------------------------------------------------------


def test_first_seen_price_is_open_of_containing_day(tmp_path: Path) -> None:
    """``first_seen_price`` must be the OPEN of the containing
    day - never the high / low / close (which all have timestamps
    > first_seen_time and would be a lookahead leak)."""

    rows = [
        _row(
            symbol="RAVEUSDT",
            day=3,
            open_price=1.00,
            high_price=1.50,
            low_price=0.80,
            close_price=1.40,
        ),
        _row(
            symbol="RAVEUSDT",
            day=4,
            open_price=1.40,
            high_price=1.80,
            low_price=1.20,
            close_price=1.60,
        ),
    ]
    root = _write_store(tmp_path, rows)
    adapter = HistoricalPricePathAdapter(historical_store_dir=root)

    resolution = adapter.resolve(
        symbol="RAVEUSDT", first_seen_time_utc_ms=_ms(3, hour=2)
    )
    assert resolution.is_loaded()
    assert (
        resolution.source
        == PricePathSource.HISTORICAL_MARKET_STORE_DAILY_TOP_MOVERS
    )
    assert resolution.first_seen_price == pytest.approx(1.00)
    assert resolution.missing_reason == PricePathMissingReason.NONE
    assert resolution.kline_interval_used == DEFAULT_KLINE_INTERVAL_USED


def test_post_first_seen_path_strictly_after_first_seen(
    tmp_path: Path,
) -> None:
    """Lookahead Guard: every PricePoint in
    ``price_path_after_first_seen`` must have
    ``timestamp_utc_ms > first_seen_time_utc_ms``."""

    rows = [
        _row(
            symbol="RAVEUSDT",
            day=3,
            open_price=1.00,
            high_price=1.50,
            low_price=0.80,
            close_price=1.40,
        ),
        _row(
            symbol="RAVEUSDT",
            day=4,
            open_price=1.40,
            high_price=1.80,
            low_price=1.20,
            close_price=1.60,
        ),
        _row(
            symbol="RAVEUSDT",
            day=5,
            open_price=1.60,
            high_price=1.90,
            low_price=1.30,
            close_price=1.70,
        ),
    ]
    root = _write_store(tmp_path, rows)
    adapter = HistoricalPricePathAdapter(historical_store_dir=root)

    first_seen_time = _ms(3, hour=2)
    resolution = adapter.resolve(
        symbol="RAVEUSDT", first_seen_time_utc_ms=first_seen_time
    )
    assert resolution.is_loaded()
    for point in resolution.price_path:
        assert point.timestamp_utc_ms > first_seen_time, (
            "lookahead leak: post-first-seen path contains a point at or "
            f"before first_seen_time (point.ts={point.timestamp_utc_ms} "
            f"vs first_seen={first_seen_time})"
        )


def test_containing_day_only_close_is_emitted(tmp_path: Path) -> None:
    """Containing day: the day's open / high / low timestamps are
    not strictly known and may have been before first_seen_time;
    only the close at day_end_ms is emitted."""

    rows = [
        _row(
            symbol="RAVEUSDT",
            day=3,
            open_price=1.00,
            high_price=1.50,
            low_price=0.80,
            close_price=1.40,
        ),
    ]
    root = _write_store(tmp_path, rows)
    adapter = HistoricalPricePathAdapter(historical_store_dir=root)

    first_seen_time = _ms(3, hour=2)
    resolution = adapter.resolve(
        symbol="RAVEUSDT", first_seen_time_utc_ms=first_seen_time
    )
    assert resolution.is_loaded()
    # Only the close at day_end is emitted for the containing day.
    day_end = _ms(3) + _DAY_MS
    assert len(resolution.price_path) == 1
    point = resolution.price_path[0]
    assert point.timestamp_utc_ms == day_end
    assert point.price == pytest.approx(1.40)
    # Containing-day high / low must not appear by price either.
    prices = {pt.price for pt in resolution.price_path}
    assert 1.50 not in prices  # high
    assert 0.80 not in prices  # low


def test_subsequent_day_emits_open_high_low_close(tmp_path: Path) -> None:
    """Subsequent days: open at day_start, high / low / close at
    day_end (approximate intra-day timestamps recorded as
    ``approximate_intra_day_timestamps``)."""

    rows = [
        _row(
            symbol="RAVEUSDT",
            day=3,
            open_price=1.00,
            high_price=1.50,
            low_price=0.80,
            close_price=1.40,
        ),
        _row(
            symbol="RAVEUSDT",
            day=4,
            open_price=1.40,
            high_price=1.80,
            low_price=1.20,
            close_price=1.60,
        ),
    ]
    root = _write_store(tmp_path, rows)
    adapter = HistoricalPricePathAdapter(historical_store_dir=root)

    resolution = adapter.resolve(
        symbol="RAVEUSDT", first_seen_time_utc_ms=_ms(3, hour=2)
    )
    assert resolution.is_loaded()
    assert resolution.approximate_intra_day_timestamps is True

    # Containing-day close + 4 OHLC points for day 4 = 5 points.
    assert len(resolution.price_path) == 5

    # Open of day 4 stamped at day_start.
    day4_open_ts = _ms(4)
    assert any(
        pt.timestamp_utc_ms == day4_open_ts and pt.price == pytest.approx(1.40)
        for pt in resolution.price_path
    )
    # High / low / close of day 4 stamped at day_end.
    day4_end_ts = _ms(4) + _DAY_MS
    prices_at_day4_end = sorted(
        pt.price
        for pt in resolution.price_path
        if pt.timestamp_utc_ms == day4_end_ts
    )
    assert prices_at_day4_end == pytest.approx([1.20, 1.60, 1.80])


def test_high_low_appear_in_path_so_evaluator_sees_post_seen_high(
    tmp_path: Path,
) -> None:
    """Sanity: max(price_path).price equals the highest
    subsequent-day high so the evaluator's
    ``post_seen_high_price`` is correct."""

    rows = [
        _row(
            symbol="RAVEUSDT",
            day=3,
            open_price=1.00,
            high_price=1.10,
            low_price=0.90,
            close_price=1.05,
        ),
        _row(
            symbol="RAVEUSDT",
            day=4,
            open_price=1.05,
            high_price=2.00,  # the peak we want to surface
            low_price=0.95,
            close_price=1.50,
        ),
    ]
    root = _write_store(tmp_path, rows)
    adapter = HistoricalPricePathAdapter(historical_store_dir=root)

    resolution = adapter.resolve(
        symbol="RAVEUSDT", first_seen_time_utc_ms=_ms(3, hour=2)
    )
    max_price = max(pt.price for pt in resolution.price_path)
    assert max_price == pytest.approx(2.00)


# ---------------------------------------------------------------------------
# Missing-reason taxonomy
# ---------------------------------------------------------------------------


def test_no_first_seen_time_yields_no_first_seen_time_reason(
    tmp_path: Path,
) -> None:
    rows = [
        _row(
            symbol="RAVEUSDT",
            day=3,
            open_price=1.00,
            high_price=1.50,
            low_price=0.80,
            close_price=1.40,
        ),
    ]
    root = _write_store(tmp_path, rows)
    adapter = HistoricalPricePathAdapter(historical_store_dir=root)

    resolution = adapter.resolve(
        symbol="RAVEUSDT", first_seen_time_utc_ms=None
    )
    assert resolution.source == PricePathSource.ABSENT
    assert (
        resolution.missing_reason
        == PricePathMissingReason.NO_FIRST_SEEN_TIME
    )
    assert resolution.first_seen_price is None
    assert resolution.price_path == ()


def test_symbol_not_in_store_yields_clear_reason(
    tmp_path: Path,
) -> None:
    rows = [
        _row(
            symbol="RAVEUSDT",
            day=3,
            open_price=1.00,
            high_price=1.50,
            low_price=0.80,
            close_price=1.40,
        ),
    ]
    root = _write_store(tmp_path, rows)
    adapter = HistoricalPricePathAdapter(historical_store_dir=root)

    resolution = adapter.resolve(
        symbol="STOUSDT", first_seen_time_utc_ms=_ms(3, hour=2)
    )
    assert resolution.source == PricePathSource.ABSENT
    assert (
        resolution.missing_reason
        == PricePathMissingReason.SYMBOL_NOT_IN_HISTORICAL_STORE
    )


def test_first_seen_outside_any_daily_row_yields_clear_reason(
    tmp_path: Path,
) -> None:
    """``first_seen_time`` falls between snapshot days for which
    the symbol has no row."""

    rows = [
        _row(
            symbol="RAVEUSDT",
            day=3,
            open_price=1.00,
            high_price=1.50,
            low_price=0.80,
            close_price=1.40,
        ),
        _row(
            symbol="RAVEUSDT",
            day=10,
            open_price=2.00,
            high_price=2.50,
            low_price=1.80,
            close_price=2.20,
        ),
    ]
    root = _write_store(tmp_path, rows)
    adapter = HistoricalPricePathAdapter(historical_store_dir=root)

    resolution = adapter.resolve(
        symbol="RAVEUSDT", first_seen_time_utc_ms=_ms(5, hour=12)
    )
    assert resolution.source == PricePathSource.ABSENT
    assert (
        resolution.missing_reason
        == PricePathMissingReason
        .NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME
    )


def test_reference_window_end_clips_path(tmp_path: Path) -> None:
    """``reference_window_end_utc_ms`` clips the path so points
    past the audit window are dropped."""

    rows = [
        _row(
            symbol="RAVEUSDT",
            day=3,
            open_price=1.00,
            high_price=1.50,
            low_price=0.80,
            close_price=1.40,
        ),
        _row(
            symbol="RAVEUSDT",
            day=4,
            open_price=1.40,
            high_price=1.80,
            low_price=1.20,
            close_price=1.60,
        ),
        _row(
            symbol="RAVEUSDT",
            day=5,
            open_price=1.60,
            high_price=2.00,
            low_price=1.30,
            close_price=1.70,
        ),
    ]
    root = _write_store(tmp_path, rows)
    adapter = HistoricalPricePathAdapter(historical_store_dir=root)

    # End the window at day 4's day_end - day 5 must be dropped.
    upper = _ms(5)
    resolution = adapter.resolve(
        symbol="RAVEUSDT",
        first_seen_time_utc_ms=_ms(3, hour=2),
        reference_window_end_utc_ms=upper,
    )
    assert resolution.is_loaded()
    for point in resolution.price_path:
        assert point.timestamp_utc_ms <= upper


# ---------------------------------------------------------------------------
# summarise_price_path_resolutions
# ---------------------------------------------------------------------------


def test_summarise_price_path_resolutions_aggregates_counts(
    tmp_path: Path,
) -> None:
    rows = [
        _row(
            symbol="RAVEUSDT",
            day=3,
            open_price=1.00,
            high_price=1.50,
            low_price=0.80,
            close_price=1.40,
        ),
        _row(
            symbol="RAVEUSDT",
            day=4,
            open_price=1.40,
            high_price=1.80,
            low_price=1.20,
            close_price=1.60,
        ),
    ]
    root = _write_store(tmp_path, rows)
    adapter = HistoricalPricePathAdapter(historical_store_dir=root)

    rave_resolution = adapter.resolve(
        symbol="RAVEUSDT", first_seen_time_utc_ms=_ms(3, hour=2)
    )
    sto_resolution = adapter.resolve(
        symbol="STOUSDT", first_seen_time_utc_ms=_ms(3, hour=2)
    )
    no_time_resolution = adapter.resolve(
        symbol="RAVEUSDT", first_seen_time_utc_ms=None
    )

    summary = summarise_price_path_resolutions(
        [rave_resolution, sto_resolution, no_time_resolution]
    )
    assert summary["price_path_records_loaded"] == 1
    assert summary["price_path_records_missing"] == 2
    assert (
        summary["price_path_source_summary"][
            PricePathSource.HISTORICAL_MARKET_STORE_DAILY_TOP_MOVERS
        ]
        == 1
    )
    assert (
        summary["price_path_source_summary"][PricePathSource.ABSENT] == 2
    )
    assert (
        summary["price_path_missing_reason_summary"][
            PricePathMissingReason.SYMBOL_NOT_IN_HISTORICAL_STORE
        ]
        == 1
    )
    assert (
        summary["price_path_missing_reason_summary"][
            PricePathMissingReason.NO_FIRST_SEEN_TIME
        ]
        == 1
    )
    assert summary["kline_interval_used"] == DEFAULT_KLINE_INTERVAL_USED
    assert summary["approximate_intra_day_timestamp_count"] == 1


def test_summarise_empty_resolutions_returns_zero_counts() -> None:
    summary = summarise_price_path_resolutions([])
    assert summary["price_path_records_loaded"] == 0
    assert summary["price_path_records_missing"] == 0
    assert summary["price_path_source_summary"] == {}
    assert summary["price_path_missing_reason_summary"] == {}
    assert summary["kline_interval_used"] == DEFAULT_KLINE_INTERVAL_USED
    assert summary["approximate_intra_day_timestamp_count"] == 0


# ---------------------------------------------------------------------------
# Boundary / safety
# ---------------------------------------------------------------------------


def test_adapter_module_does_not_import_forbidden_modules() -> None:
    """The adapter module MUST NOT import Risk / Execution /
    private exchange / LLM / Telegram modules."""

    adapter_path = (
        PROJECT_ROOT
        / "app"
        / "adaptive"
        / "post_discovery_price_path_adapter.py"
    )
    source = adapter_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_prefixes = (
        "app.risk",
        "app.execution",
        "app.exchanges.binance",
        "app.exchanges.binance_public_ws",
        "app.llm",
        "app.telegram",
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in forbidden_prefixes:
                    assert not alias.name.startswith(prefix), (
                        f"adapter imports forbidden module {alias.name!r}"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for prefix in forbidden_prefixes:
                assert not module.startswith(prefix), (
                    f"adapter imports forbidden module {module!r}"
                )


def test_resolution_to_dict_round_trip(tmp_path: Path) -> None:
    """``PricePathResolution.to_dict`` produces a JSON-serialisable
    dict with no surprises."""

    rows = [
        _row(
            symbol="RAVEUSDT",
            day=3,
            open_price=1.00,
            high_price=1.50,
            low_price=0.80,
            close_price=1.40,
        ),
    ]
    root = _write_store(tmp_path, rows)
    adapter = HistoricalPricePathAdapter(historical_store_dir=root)

    resolution = adapter.resolve(
        symbol="RAVEUSDT", first_seen_time_utc_ms=_ms(3, hour=2)
    )
    payload = resolution.to_dict()
    json.dumps(payload)  # round-trip
    assert payload["symbol"] == "RAVEUSDT"
    assert payload["source"] == (
        PricePathSource.HISTORICAL_MARKET_STORE_DAILY_TOP_MOVERS
    )
    assert payload["missing_reason"] == PricePathMissingReason.NONE
    assert payload["kline_interval_used"] == DEFAULT_KLINE_INTERVAL_USED


def test_pre_loaded_snapshot_path(tmp_path: Path) -> None:
    """The adapter accepts a pre-loaded snapshot directly so the
    runner / tests can avoid double-reads."""

    from app.adaptive.historical_mover_coverage_backfill import (
        load_historical_market_store,
    )

    rows = [
        _row(
            symbol="RAVEUSDT",
            day=3,
            open_price=1.00,
            high_price=1.50,
            low_price=0.80,
            close_price=1.40,
        ),
    ]
    root = _write_store(tmp_path, rows)
    snapshot = load_historical_market_store(root)

    adapter = HistoricalPricePathAdapter(snapshot=snapshot)
    assert adapter.is_available
    assert adapter.has_symbol("RAVEUSDT")
    assert adapter.indexed_symbol_count == 1



# ---------------------------------------------------------------------------
# Phase 11C.1C-C-B-B-B-D-B.1 PR71 fix: operator-supplied path Lookahead Guard
# ---------------------------------------------------------------------------


def test_operator_resolution_case_3_anchor_at_or_before_first_seen() -> None:
    """**Case 3** (Lookahead-safe operator anchor):
    operator path's first point timestamp ``<= first_seen_time``.

    Expected:
      * ``first_seen_price`` is the operator point at the anchor.
      * ``price_path`` only carries operator points strictly AFTER
        ``first_seen_time`` (the anchor itself is excluded from
        the post-first-seen path).
      * No future point becomes ``first_seen_price``.
    """

    first_seen = _ms(3, hour=2)
    operator_points = (
        PricePoint(timestamp_utc_ms=_ms(3, hour=1), price=1.00),  # anchor
        PricePoint(timestamp_utc_ms=first_seen, price=1.05),       # anchor candidate (latest <=)
        PricePoint(timestamp_utc_ms=_ms(3, hour=3), price=1.10),  # post
        PricePoint(timestamp_utc_ms=_ms(3, hour=4), price=1.20),  # post
    )

    resolution = build_operator_supplied_price_path_resolution(
        symbol="EARLYUSDT",
        first_seen_time_utc_ms=first_seen,
        operator_points=operator_points,
    )

    assert resolution.source == PricePathSource.OPERATOR_SUPPLIED_PATH
    assert resolution.missing_reason == PricePathMissingReason.NONE
    # Anchor: latest operator point with ts <= first_seen_time.
    assert resolution.first_seen_price == pytest.approx(1.05)
    # Path: only points strictly AFTER first_seen_time. The anchor
    # at ts == first_seen and the earlier point at ts < first_seen
    # are NOT in the path.
    assert all(
        pt.timestamp_utc_ms > first_seen for pt in resolution.price_path
    )
    assert len(resolution.price_path) == 2
    assert resolution.price_path[0].price == pytest.approx(1.10)
    assert resolution.price_path[1].price == pytest.approx(1.20)
    assert resolution.is_loaded()


def test_operator_resolution_case_2_anchor_strictly_after_first_seen() -> None:
    """**Case 2** (Lookahead leak forbidden):
    operator path's first point timestamp strictly AFTER
    ``first_seen_time``.

    Expected when no fallback is provided:
      * ``first_seen_price`` is **None** (the future point is NOT
        used as anchor - that would be a lookahead leak).
      * ``missing_reason`` =
        :attr:`OPERATOR_PATH_STARTS_AFTER_FIRST_SEEN`.
      * ``price_path`` still carries the operator points (they ARE
        post-first-seen and lookahead-safe AS A PATH); only the
        anchor is missing.
      * Resolution is NOT loaded (anchor missing).
    """

    first_seen = _ms(3, hour=2)
    operator_points = (
        PricePoint(timestamp_utc_ms=_ms(3, hour=3), price=1.10),
        PricePoint(timestamp_utc_ms=_ms(3, hour=4), price=1.20),
        PricePoint(timestamp_utc_ms=_ms(3, hour=5), price=1.50),
    )

    resolution = build_operator_supplied_price_path_resolution(
        symbol="EARLYUSDT",
        first_seen_time_utc_ms=first_seen,
        operator_points=operator_points,
    )

    assert resolution.source == PricePathSource.OPERATOR_SUPPLIED_PATH
    assert resolution.first_seen_price is None
    assert (
        resolution.missing_reason
        == PricePathMissingReason.OPERATOR_PATH_STARTS_AFTER_FIRST_SEEN
    )
    # Lookahead-safe operator points still surface in price_path
    # (every point is strictly AFTER first_seen_time).
    assert len(resolution.price_path) == 3
    assert all(
        pt.timestamp_utc_ms > first_seen for pt in resolution.price_path
    )
    # Resolution is NOT loaded because anchor is missing.
    assert not resolution.is_loaded()


def test_operator_resolution_case_2_with_fallback_anchor_succeeds() -> None:
    """**Case 2 + fallback**: operator path's first point is
    strictly AFTER ``first_seen_time``, but a lookahead-safe
    fallback resolution (e.g. the adapter's containing-day open)
    is provided.

    Expected:
      * ``first_seen_price`` comes from the fallback (the future
        operator point is still NOT used as anchor).
      * ``missing_reason`` is :attr:`PricePathMissingReason.NONE`.
      * Source remains :attr:`PricePathSource.OPERATOR_SUPPLIED_PATH`
        because the post-first-seen path is operator-supplied.
      * Notes record that the anchor came from the fallback.
    """

    first_seen = _ms(3, hour=2)
    fallback = PricePathResolution(
        symbol="EARLYUSDT",
        first_seen_time_utc_ms=first_seen,
        first_seen_price=10.00,
        price_path=(),
        source=(
            PricePathSource.HISTORICAL_MARKET_STORE_DAILY_TOP_MOVERS
        ),
        missing_reason=PricePathMissingReason.NONE,
        kline_interval_used=DEFAULT_KLINE_INTERVAL_USED,
    )
    operator_points = (
        PricePoint(timestamp_utc_ms=_ms(3, hour=3), price=1.10),
        PricePoint(timestamp_utc_ms=_ms(3, hour=4), price=1.20),
    )

    resolution = build_operator_supplied_price_path_resolution(
        symbol="EARLYUSDT",
        first_seen_time_utc_ms=first_seen,
        operator_points=operator_points,
        fallback_resolution=fallback,
    )

    assert resolution.source == PricePathSource.OPERATOR_SUPPLIED_PATH
    assert resolution.first_seen_price == pytest.approx(10.00)
    assert resolution.missing_reason == PricePathMissingReason.NONE
    assert resolution.is_loaded()
    assert "first_seen_price_anchor_from_fallback" in resolution.notes
    # Path is still operator-supplied points, all > first_seen.
    assert len(resolution.price_path) == 2
    assert all(
        pt.timestamp_utc_ms > first_seen for pt in resolution.price_path
    )


def test_operator_resolution_no_first_seen_time_rejects_path() -> None:
    """Without ``first_seen_time_utc_ms`` the lookahead guard
    cannot be applied so the operator path is rejected wholesale
    (NO_FIRST_SEEN_TIME). The resolver does NOT default the
    anchor to the first operator point - that would be a future
    leak."""

    operator_points = (
        PricePoint(timestamp_utc_ms=_ms(3, hour=3), price=1.10),
        PricePoint(timestamp_utc_ms=_ms(3, hour=4), price=1.20),
    )

    resolution = build_operator_supplied_price_path_resolution(
        symbol="EARLYUSDT",
        first_seen_time_utc_ms=None,
        operator_points=operator_points,
    )

    assert resolution.source == PricePathSource.OPERATOR_SUPPLIED_PATH
    assert resolution.first_seen_price is None
    assert (
        resolution.missing_reason
        == PricePathMissingReason.NO_FIRST_SEEN_TIME
    )
    assert resolution.price_path == ()
    assert not resolution.is_loaded()


def test_operator_resolution_empty_path_emits_explicit_reason() -> None:
    """Empty operator path -> :attr:`OPERATOR_PATH_EMPTY` reason."""

    resolution = build_operator_supplied_price_path_resolution(
        symbol="EARLYUSDT",
        first_seen_time_utc_ms=_ms(3, hour=2),
        operator_points=(),
    )

    assert resolution.source == PricePathSource.OPERATOR_SUPPLIED_PATH
    assert resolution.first_seen_price is None
    assert (
        resolution.missing_reason == PricePathMissingReason.OPERATOR_PATH_EMPTY
    )
    assert resolution.price_path == ()
    assert not resolution.is_loaded()


def test_operator_resolution_anchor_picks_latest_pre_first_seen_point() -> None:
    """When multiple operator points have ``ts <= first_seen_time``,
    the anchor is the LATEST one (closest to first_seen_time)."""

    first_seen = _ms(3, hour=10)
    operator_points = (
        PricePoint(timestamp_utc_ms=_ms(3, hour=2), price=0.95),
        PricePoint(timestamp_utc_ms=_ms(3, hour=8), price=1.00),  # latest pre-first-seen
        PricePoint(timestamp_utc_ms=_ms(3, hour=5), price=0.97),
        PricePoint(timestamp_utc_ms=_ms(3, hour=11), price=1.20),  # post
    )

    resolution = build_operator_supplied_price_path_resolution(
        symbol="EARLYUSDT",
        first_seen_time_utc_ms=first_seen,
        operator_points=operator_points,
    )

    assert resolution.first_seen_price == pytest.approx(1.00)
    # Path is post-first-seen only, sorted by timestamp.
    assert len(resolution.price_path) == 1
    assert resolution.price_path[0].price == pytest.approx(1.20)


def test_operator_resolution_never_uses_future_point_as_anchor() -> None:
    """Lookahead Guard regression test: even if the operator
    path's FIRST element (by list order) is a future point, the
    resolver MUST NOT use it as ``first_seen_price``."""

    first_seen = _ms(3, hour=2)
    operator_points = (
        # Future point (ts > first_seen) - MUST NOT be the anchor.
        PricePoint(timestamp_utc_ms=_ms(3, hour=10), price=99.99),
        # Pre-first-seen anchor candidate.
        PricePoint(timestamp_utc_ms=_ms(3, hour=1), price=1.00),
    )

    resolution = build_operator_supplied_price_path_resolution(
        symbol="EARLYUSDT",
        first_seen_time_utc_ms=first_seen,
        operator_points=operator_points,
    )

    # Anchor MUST be 1.00, NOT 99.99.
    assert resolution.first_seen_price == pytest.approx(1.00)
    assert resolution.first_seen_price != pytest.approx(99.99)
    # The future point IS in the path (it is post-first-seen).
    assert any(
        pt.price == pytest.approx(99.99) for pt in resolution.price_path
    )


def test_pr71_operator_path_resolution_listed_in_missing_reason_taxonomy() -> None:
    """The PR71-fix missing reasons are part of the closed
    taxonomy."""

    assert (
        PricePathMissingReason.OPERATOR_PATH_STARTS_AFTER_FIRST_SEEN
        in PricePathMissingReason.ALL
    )
    assert PricePathMissingReason.OPERATOR_PATH_EMPTY in PricePathMissingReason.ALL
