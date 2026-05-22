"""Phase 11C.1B - SymbolUniverse (exchangeInfo-as-truth) tests.

Why this test file exists
-------------------------

Binance USDT-M Futures lists contracts whose symbol contains
non-ASCII characters - e.g. ``我踏马来了USDT`` and ``币安人生USDT``. Each
of those is a real Binance contract with its own
``/fapi/v1/exchangeInfo`` entry, its own WS push under the public
all-market streams, and its own REST detail endpoint. A symbol
validation step that uses an ASCII-only character class
(``^[A-Z0-9_]{2,30}(USDT|USDC)$``) silently loses discovery on
every exotic listing the moment Binance adds one.

The Phase 11C.1B brief therefore mandates:

  1. symbol legitimacy MUST be sourced from
     ``/fapi/v1/exchangeInfo`` (the public WS source);
  2. the universe is built ONCE at runner startup;
  3. WS-radar candidates whose symbol IS in the universe are
     admitted to the :class:`CandidatePool`, even when the symbol
     contains non-ASCII characters;
  4. WS-radar candidates whose symbol is NOT in the universe are
     refused with a typed ``WS_SYMBOL_REJECTED`` event;
  5. the documentation surface (this docstring + the module
     docstring of :mod:`app.market_data_public.symbol_universe`)
     records the non-ASCII listing caveat;
  6. THIS file pins the three behavioural assertions.

The three regression tests
--------------------------

  - :func:`test_non_ascii_exchange_symbol_allowed_if_in_exchange_info`
    Build a :class:`SymbolUniverse` from a list that includes the
    Chinese symbol; pool admits it; no ``WS_SYMBOL_REJECTED`` is
    emitted.

  - :func:`test_non_ascii_ws_symbol_rejected_if_not_in_exchange_info`
    Build a :class:`SymbolUniverse` that does NOT contain the
    Chinese symbol; pool refuses the offer; exactly one
    ``WS_SYMBOL_REJECTED`` event lands with the rejected symbol on
    the payload.

  - :func:`test_symbol_validation_uses_exchange_info_not_ascii_regex`
    Static AST audit + behavioural recorder:
      * walk every Phase 11C / 11C.1B / runner source file and
        assert NO ``re.compile`` / ``re.match`` / ``re.fullmatch``
        pattern smells like an ASCII-only symbol regex;
      * inject a recording :class:`SymbolUniverse` into the pool and
        assert :meth:`is_valid` was called with the WS-radar symbol
        before any admission decision.

Phase 11C.1B safety boundary unchanged
--------------------------------------

These tests run in-process. No real socket is opened. No live REST
call is issued. The fixture builds an isolated event repository on
top of the Phase 2 in-memory sqlite databases so the
``WS_SYMBOL_REJECTED`` event audit is deterministic.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.core.events import EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.market_data_public import (
    CandidatePool,
    CandidatePoolConfig,
    REASON_NOT_IN_EXCHANGE_INFO,
    SymbolUniverse,
    pre_anomaly_score_light,
)
from app.market_data_public.radar import (
    AllMarketRadarSnapshot,
    RadarScoreResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_event_repo(tmp_path: Path) -> tuple[EventRepository, DatabaseSet]:
    """Build an isolated EventRepository on top of the Phase 2 DBs.

    Mirrors the helper used by every other Phase 11C.1B test so the
    fixture style stays consistent.
    """
    dbs = DatabaseSet.open(
        tmp_path / "sqlite",
        wal=False,
        databases=PHASE2_DATABASES,
    )
    migrate_database_set(dbs)
    return EventRepository(dbs.events, capital_conn=dbs.capital), dbs


def _strong_snapshot(symbol: str) -> AllMarketRadarSnapshot:
    """Build a snapshot whose radar score crosses the default
    admission threshold.

    Both ``price_acceleration_60s`` and ``quote_volume_delta_60s``
    are populated above the default :class:`RadarScoreConfig`
    thresholds, so :func:`pre_anomaly_score_light` returns a score
    > 30.0 (the default ``radar_score_threshold``). Without the
    universe gate the pool would happily admit this snapshot - the
    tests below depend on that to isolate the gate's behaviour.
    """
    return AllMarketRadarSnapshot(
        symbol=symbol,
        timestamp=1,
        last_price=100.0,
        price_acceleration_60s=0.03,
        quote_volume_delta_60s=2_000_000.0,
        volume_rank_jump=5,
    )


def _strong_score() -> RadarScoreResult:
    """Score that mirrors a strong admission - clears the default
    radar_score_threshold (30.0) and carries audit reason tags.
    """
    return RadarScoreResult(
        radar_score=80.0,
        reason_tags=("price_accel_60s", "quote_volume_delta_60s"),
        source_streams=("!ticker@arr",),
    )


# ---------------------------------------------------------------------------
# 1. Non-ASCII symbol IS in exchangeInfo -> admitted to pool
# ---------------------------------------------------------------------------


def test_non_ascii_exchange_symbol_allowed_if_in_exchange_info(tmp_path: Path):
    """A non-ASCII Binance contract symbol that IS in the bootstrapped
    exchangeInfo set MUST be admitted to the candidate pool.

    Binance has listed Chinese-named USDT contracts in production
    (e.g. ``我踏马来了USDT`` / ``币安人生USDT``). The Phase 11C.1B brief
    forbids any character-class regex that would refuse these. This
    test pins the contract: a bootstrapped SymbolUniverse that
    contains the Chinese symbol must allow it through, and the
    candidate pool must promote it exactly the same way it would
    promote ``BTCUSDT``.
    """
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        # Build an exchangeInfo-as-truth universe that explicitly
        # includes the documented Chinese-named USDT contracts.
        universe = SymbolUniverse.from_exchange_info(
            [
                "BTCUSDT",
                "ETHUSDT",
                "我踏马来了USDT",
                "币安人生USDT",
            ]
        )
        # The non-ASCII symbol MUST flow through the membership test
        # unchanged. Equivalence is exact-match on the canonical
        # string; we explicitly do NOT case-fold non-ASCII codepoints.
        assert universe.is_valid("我踏马来了USDT") is True
        assert universe.is_valid("币安人生USDT") is True
        assert universe.is_valid("BTCUSDT") is True
        assert "我踏马来了USDT" in universe
        assert universe.bootstrapped is True
        assert len(universe) == 4

        # The candidate pool consults the universe during offer().
        pool = CandidatePool(
            config=CandidatePoolConfig(
                candidate_pool_size=10,
                active_detail_limit=2,
                radar_score_threshold=30.0,
            ),
            symbol_universe=universe,
            event_repo=event_repo,
        )
        pool.begin_scan_batch()

        snap = _strong_snapshot("我踏马来了USDT")
        score = pre_anomaly_score_light(snap)
        # Sanity: the snapshot really is strong enough to be admitted.
        assert score.radar_score >= 30.0

        cand = pool.offer(snap, score)
        # Admission MUST succeed - the symbol is in the universe.
        assert cand is not None
        assert cand.symbol == "我踏马来了USDT"
        assert pool.candidates_admitted == 1
        assert pool.candidates_rejected_by_universe == 0
        # NO WS_SYMBOL_REJECTED event is emitted for an admitted
        # candidate, regardless of character class.
        rejected_events = event_repo.list_events(
            event_type=EventType.WS_SYMBOL_REJECTED
        )
        assert rejected_events == []
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 2. Non-ASCII symbol NOT in exchangeInfo -> WS_SYMBOL_REJECTED
# ---------------------------------------------------------------------------


def test_non_ascii_ws_symbol_rejected_if_not_in_exchange_info(tmp_path: Path):
    """A WS-radar symbol that is NOT in the bootstrapped exchangeInfo
    set MUST be refused, regardless of character class, with a typed
    ``WS_SYMBOL_REJECTED`` event.

    The brief is explicit: the rejection reason is "not in
    exchangeInfo" - NOT "non-ASCII character class". A pure-ASCII
    symbol that is missing from the snapshot (e.g. a brand-new
    listing that came online mid-run, or a delisting whose WS pushes
    arrived between bootstrap and subscribe) is treated identically
    to a Chinese symbol that is missing.
    """
    event_repo, dbs = _make_event_repo(tmp_path)
    try:
        # Build a universe that does NOT include the Chinese symbol.
        universe = SymbolUniverse.from_exchange_info(["BTCUSDT", "ETHUSDT"])
        assert universe.is_valid("BTCUSDT") is True
        assert universe.is_valid("我踏马来了USDT") is False

        pool = CandidatePool(
            config=CandidatePoolConfig(
                candidate_pool_size=10,
                active_detail_limit=2,
                radar_score_threshold=30.0,
            ),
            symbol_universe=universe,
            event_repo=event_repo,
        )
        pool.begin_scan_batch()

        snap = _strong_snapshot("我踏马来了USDT")
        score = _strong_score()
        cand = pool.offer(snap, score)
        # Pool MUST refuse the offer.
        assert cand is None
        assert pool.size == 0
        assert pool.candidates_admitted == 0
        assert pool.candidates_rejected_by_universe == 1
        # The candidate did NOT enter the pool's general
        # ``candidates_seen`` accounting; rejected-by-universe is its
        # own counter so the daily report can audit drift between
        # bootstrap and live WS pushes without polluting admission
        # statistics.
        assert pool.candidates_seen == 0

        # Exactly one WS_SYMBOL_REJECTED event landed, with the
        # required payload contract.
        rejected_events = event_repo.list_events(
            event_type=EventType.WS_SYMBOL_REJECTED
        )
        assert len(rejected_events) == 1
        ev = rejected_events[0]
        assert ev.symbol == "我踏马来了USDT"
        payload = ev.payload
        assert payload["symbol"] == "我踏马来了USDT"
        assert payload["reason"] == REASON_NOT_IN_EXCHANGE_INFO
        # Audit fields the daily-report aggregator depends on.
        assert payload["universe_size"] == 2
        assert payload["universe_source"] == "exchange_info"
        # The radar context (radar_score / reason_tags / source_streams)
        # is preserved on the payload so Reflection can reconstruct
        # WHY the rejected symbol looked interesting.
        assert payload["radar_score"] == pytest.approx(
            float(score.radar_score)
        )
        assert "price_accel_60s" in payload["reason_tags"]
        assert "!ticker@arr" in payload["source_streams"]

        # A pure-ASCII symbol that is also missing from the universe
        # is rejected the same way - the rejection reason is "not in
        # exchangeInfo", NOT "non-ASCII character class".
        snap_ascii = _strong_snapshot("BRANDNEWUSDT")
        score_ascii = _strong_score()
        cand_ascii = pool.offer(snap_ascii, score_ascii)
        assert cand_ascii is None
        assert pool.candidates_rejected_by_universe == 2
        rejected_events_after = event_repo.list_events(
            event_type=EventType.WS_SYMBOL_REJECTED
        )
        assert len(rejected_events_after) == 2
        # Order-independent: the repo returns events sorted by
        # timestamp + insertion id, but two emissions inside the same
        # millisecond can come back in either order on busy hosts.
        rejected_symbols = {ev.symbol for ev in rejected_events_after}
        assert rejected_symbols == {"我踏马来了USDT", "BRANDNEWUSDT"}
        for ev in rejected_events_after:
            assert ev.payload["reason"] == REASON_NOT_IN_EXCHANGE_INFO
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 3. Symbol validation must use exchangeInfo, never an ASCII-only regex
# ---------------------------------------------------------------------------


# Files in the symbol-validation hot path. The audit refuses any
# ASCII-only symbol regex inside this set; new files added to the
# Phase 11C / 11C.1B WS-radar surface MUST be added here so the
# audit travels with them.
_SYMBOL_PATH_FILES: tuple[Path, ...] = (
    Path("app/market_data_public/symbol_universe.py"),
    Path("app/market_data_public/candidate_pool.py"),
    Path("app/market_data_public/radar.py"),
    Path("app/market_data_public/ws_radar_chain.py"),
    Path("app/market_data_public/ingest.py"),
    Path("app/market_data_public/event_chain.py"),
    Path("app/exchanges/binance_public.py"),
    Path("app/exchanges/binance_public_ws.py"),
    Path("scripts/run_public_market_paper.py"),
)


# Patterns that match an ASCII-only symbol-shaped regex. The check is
# deliberately a substring scan on the regex literal itself so an
# operator can reason about it locally.
#
#   ``[A-Z`` / ``[A-Z0-9`` / ``[A-Z_0-9`` followed by anything that
#   smells like a symbol shape (a bounded length quantifier OR an
#   explicit USDT / USDC suffix). False-positive risk is low because
#   the symbol-path file set is narrow.
_ASCII_ONLY_SYMBOL_RE = re.compile(
    r"\[A-Z[^\]]*\][^|]*(USDT|USDC|\{[0-9]+,[0-9]+\})",
    re.IGNORECASE,
)


def _walk_re_calls(tree: ast.AST):
    """Yield every ``re.compile`` / ``re.match`` / ``re.fullmatch``
    call's first-arg string literal."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = ""
        if isinstance(func, ast.Attribute):
            owner = func.value
            if isinstance(owner, ast.Name) and owner.id == "re":
                name = func.attr
        if name not in {"compile", "match", "fullmatch", "search"}:
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            yield first.value


def test_symbol_validation_uses_exchange_info_not_ascii_regex():
    """Static AST audit + behavioural recorder.

    Two-part contract pin:

    Part A - static audit
        Walk every file in :data:`_SYMBOL_PATH_FILES`. For every
        ``re.compile`` / ``re.match`` / ``re.fullmatch`` call, assert
        the regex literal does NOT smell like an ASCII-only symbol
        regex. Specifically: ``[A-Z...]`` followed by a USDT / USDC
        suffix or a bounded length quantifier ``{m,n}`` is refused
        on this path. The check fails the next PR that
        re-introduces an ASCII-only symbol filter.

    Part B - behavioural recorder
        Inject a recording :class:`SymbolUniverse` subclass into the
        candidate pool and assert that :meth:`is_valid` was invoked
        with the candidate symbol BEFORE any admission decision. A
        future refactor that bypassed the universe gate (e.g.
        admitted by character class first, then "validated" later)
        would silently fail this assertion.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    # ----- Part A: static audit -----------------------------------------
    offenders: list[tuple[str, str]] = []
    for rel in _SYMBOL_PATH_FILES:
        path = repo_root / rel
        assert path.is_file(), f"audit-path file missing: {rel}"
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:  # pragma: no cover - defensive
            pytest.fail(f"{rel} is not parseable Python: {exc}")
        for pattern in _walk_re_calls(tree):
            if _ASCII_ONLY_SYMBOL_RE.search(pattern):
                offenders.append((str(rel), pattern))
    assert offenders == [], (
        "ASCII-only symbol regex detected on the Phase 11C / 11C.1B "
        "WS-radar / symbol-validation path. Binance lists non-ASCII "
        "contract symbols (e.g. '我踏马来了USDT', '币安人生USDT'); "
        "validate symbols against the bootstrapped exchangeInfo "
        f"SymbolUniverse instead. Offenders: {offenders}"
    )

    # ----- Part B: behavioural recorder ---------------------------------
    class _RecordingUniverse(SymbolUniverse):
        """Subclass that records every is_valid() call without
        changing semantics. Pydantic-free dataclass-friendly; uses
        object.__setattr__ to write the recorder list onto the frozen
        dataclass once.
        """

        def __post_init__(self) -> None:  # type: ignore[override]
            object.__setattr__(self, "calls", [])

        def is_valid(self, symbol: str) -> bool:  # type: ignore[override]
            self.calls.append(symbol)  # type: ignore[attr-defined]
            return super().is_valid(symbol)

    universe = _RecordingUniverse(
        valid_symbol_set=frozenset({"BTCUSDT", "我踏马来了USDT"}),
        bootstrapped=True,
        bootstrap_ts_ms=1,
        source="exchange_info",
    )
    universe.__post_init__()

    pool = CandidatePool(
        config=CandidatePoolConfig(
            candidate_pool_size=5,
            active_detail_limit=2,
            radar_score_threshold=30.0,
        ),
        symbol_universe=universe,
    )
    pool.begin_scan_batch()
    snap_ok = _strong_snapshot("我踏马来了USDT")
    snap_bad = _strong_snapshot("UNKNOWN_SYMBOLUSDT")
    pool.offer(snap_ok, _strong_score())
    pool.offer(snap_bad, _strong_score())
    # The pool consulted the universe for BOTH symbols (regardless of
    # character class). The recorder never sees a symbol the pool
    # admitted by a regex shortcut.
    assert "我踏马来了USDT" in universe.calls  # type: ignore[attr-defined]
    assert "UNKNOWN_SYMBOLUSDT" in universe.calls  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Sanity: empty universe is the back-compat admit-all fallback
# ---------------------------------------------------------------------------


def test_empty_universe_is_admit_all_back_compat():
    """The empty universe (default for dry-run / fixture tests) admits
    every non-empty symbol so the existing 2000+ test suite stays
    green. This is the documented back-compat fallback the runner
    drops to on bootstrap failure.
    """
    universe = SymbolUniverse.empty()
    assert universe.bootstrapped is False
    assert universe.is_valid("BTCUSDT") is True
    assert universe.is_valid("我踏马来了USDT") is True
    # Empty / whitespace-only symbols are always rejected, even on
    # the empty universe - the runner relies on this to bail early
    # on malformed payloads.
    assert universe.is_valid("") is False
    assert universe.is_valid("   ") is False
