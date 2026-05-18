"""Phase 5 - PR #16 review-fix tests.

Pins the four follow-up clarifications requested on PR #16:

1. ``RiskPermission`` is a regime-cycle gate, NOT a trade approval.
   The enum docstring must contain the regime-gate vs.
   trade-approval distinction so a future reader cannot collapse
   the two notions.
2. ``ALT_RISK_OFF -> ALLOW_SCOUT`` permits OBSERVE / tiny SCOUT
   only. The docstring must spell out that Issue #7 has to further
   restrict (no ATTACK, no RIGHT_TAIL_AMPLIFY).
3. ``LiquidityFilter.can_exit_position`` docstring must spell out
   the upper-bound nature of the ``volume_5m / 300s`` throughput
   estimate, recommend Issue #7 discounts, and pin the
   degraded-data contract.
4. ``UniverseConfig.event_emit_enabled`` /
   ``LiquidityConfig.event_emit_enabled`` exist with the right
   defaults; the per-call ``emit_event`` resolution rule
   (True / False / None) is honoured by every entry point;
   ``*_events_skipped`` counters track suppressed emissions.

These tests are documentation-pinning + observability tests.
They do NOT exercise behaviour beyond what the existing Phase 5
test suite already covers.
"""

from __future__ import annotations

import re

from app.core.enums import (
    LiquidityRejectReason,
    MarketRegime,
    RiskPermission,
)
from app.core.events import EventType
from app.exchanges.models import OrderBook, OrderBookLevel
from app.liquidity import (
    LiquidityConfig,
    LiquidityFilter,
    LiquidityInput,
    Side,
)
from app.liquidity.filter import can_exit_position as can_exit_position_fn
from app.regime.models import REGIME_TO_RISK_PERMISSION
from app.universe import UniverseConfig, UniverseFilter, UniverseInput


def _flat(s: str) -> str:
    """Whitespace-flatten + lowercase a docstring so tests can match
    semantic phrases that may be split across line wraps. We pin
    *meaning*, not formatting."""
    return re.sub(r"\s+", " ", s or "").lower()


# ---------------------------------------------------------------------------
# Item 1 + 2: docstring boundary - regime-gate vs. trade-approval
# ---------------------------------------------------------------------------
def test_risk_permission_docstring_states_it_is_not_a_trade_approval():
    """The enum docstring must explicitly say so. A future reader
    must not collapse 'cycle permission' with 'trade authorisation'.
    """
    doc = _flat(RiskPermission.__doc__)
    assert "regime-cycle permission" in doc
    assert "not a trade approval" in doc


def test_risk_permission_docstring_lists_the_eight_step_ladder():
    """The eight-step conjunctive ladder a real opening must clear
    is the spine of the regime-gate-vs-trade-approval distinction.
    Pin a few of the unique tokens so a future edit cannot quietly
    drop one of the gates.
    """
    doc = RiskPermission.__doc__ or ""
    for token in (
        "RegimeSnapshot.risk_permission",
        "UniverseDecision.eligible",
        "LiquidityDecision.passed",
        "can_exit_position",
        "Real-trade confirmation",
        "Manipulation level",
        "RiskEngine.evaluate",
        "ExecutionFSM",
    ):
        assert token in doc, f"RiskPermission docstring missing token: {token!r}"


def test_risk_permission_docstring_states_allow_scout_bans_attack_and_right_tail():
    """ALLOW_SCOUT (the ALT_RISK_OFF fallback) must NOT authorise
    attack-sized positions or right-tail amplification. Pin that
    in the docstring.
    """
    doc = _flat(RiskPermission.__doc__)
    # Must mention the two banned states by name.
    assert "no attack" in doc
    assert "no right_tail_amplify" in doc
    # Must mention the ALLOW_SCOUT label so readers know which arm
    # the bans apply to.
    assert "allow_scout" in doc


def test_regime_to_risk_permission_module_doc_mentions_the_distinction():
    """The source-of-truth dict in app/regime/models.py must carry
    the same warning - a reader who only consults the dict (not the
    enum) must still see the regime-gate vs. trade-approval line.
    """
    import app.regime.models as regime_models

    src = regime_models.__file__
    with open(src, encoding="utf-8") as fh:
        text = fh.read().lower()
    assert "regime semantics, not trade authorisation" in text
    assert "necessary but not sufficient" in text


def test_regime_snapshot_risk_permission_docstring_warns():
    """The RegimeSnapshot value object's class docstring must point
    the first reader at RiskPermission for the full ladder.
    """
    from app.regime.models import RegimeSnapshot

    doc = _flat(RegimeSnapshot.__doc__)
    # Match-friendly, not exact-string-friendly: pin the unique words.
    assert "regime-cycle gate" in doc
    assert "not a trade authorisation" in doc
    # Must explicitly mention BOTH ALLOW_ATTACK and ALLOW_SCOUT
    # constraints so the warning covers both code paths.
    assert "allow_attack" in doc
    assert "allow_scout" in doc


def test_alt_risk_off_maps_to_allow_scout():
    """Wire-up sanity: the regime that triggers the ALLOW_SCOUT
    discussion in the docstrings must in fact map to ALLOW_SCOUT
    in the source-of-truth dict.
    """
    assert (
        REGIME_TO_RISK_PERMISSION[MarketRegime.ALT_RISK_OFF]
        is RiskPermission.ALLOW_SCOUT
    )


# ---------------------------------------------------------------------------
# Item 3: can_exit_position throughput-discount + degraded contract
# ---------------------------------------------------------------------------
def test_can_exit_position_docstring_states_throughput_is_upper_bound():
    """The method docstring must explicitly say the
    ``volume_5m / 300s`` fallback is an upper bound, not a
    conservative estimate.
    """
    doc = _flat(LiquidityFilter.can_exit_position.__doc__)
    assert "upper bound" in doc
    assert "not a conservative estimate" in doc


def test_can_exit_position_docstring_recommends_issue7_discount():
    """The docstring must direct Issue #7 to apply a conservative
    discount on top of the returned throughput / feasibility.
    """
    doc = _flat(LiquidityFilter.can_exit_position.__doc__)
    assert "issue #7" in doc
    assert "conservative discount" in doc
    # And at least one concrete recommended discount direction.
    assert any(
        token in doc for token in ("atr-expansion", "fraction of recent average")
    )


def test_can_exit_position_docstring_pins_degraded_data_contract():
    """The docstring must spell out the degraded-data contract:
    pass MarketDataBuffer.is_degraded through, never invert
    feasible=False, never feed a stale book with
    is_data_degraded=False.
    """
    doc = _flat(LiquidityFilter.can_exit_position.__doc__)
    assert "is_degraded(symbol)" in doc
    assert "single source of truth" in doc
    assert "never invert" in doc


def test_free_can_exit_position_docstring_points_at_method_form():
    """The free-function variant must point readers at the method
    docstring for the full contract; it must not silently lose the
    upper-bound / degraded warnings.
    """
    doc = _flat(can_exit_position_fn.__doc__)
    assert "upper bound" in doc
    assert "issue #7" in doc
    assert "data_degraded" in doc


def test_volume_window_constant_block_warns_about_upper_bound():
    """The ``_VOLUME_WINDOW_5M_SECONDS`` module constant has its own
    warning comment block so a reader of the constant alone sees
    the upper-bound assumption set.
    """
    import app.liquidity.filter as filter_mod

    with open(filter_mod.__file__, encoding="utf-8") as fh:
        text = fh.read()
    # The block-comment warning must mention the constant AND the
    # upper-bound phrase AND the Issue #7 discount direction.
    assert "_VOLUME_WINDOW_5M_SECONDS" in text
    assert "upper bound" in text.lower()
    assert "Issue #7" in text


# ---------------------------------------------------------------------------
# Item 4: event_emit_enabled throttle + skipped counters
# ---------------------------------------------------------------------------
# Helpers
def _good_universe_input(**overrides):
    base = dict(
        symbol="BTCUSDT",
        contract_status="TRADING",
        spread_pct=0.001,
        orderbook_depth_usdt=200_000.0,
        trade_count_5m=50,
        volume_5m=1_000.0,
        reliability=__import__(
            "app.core.enums", fromlist=["DataReliability"]
        ).DataReliability.A,
        is_data_degraded=False,
        abnormal_data_flag=False,
        market_regime=MarketRegime.MEME_RISK_ON,
        risk_permission=RiskPermission.ALLOW_ATTACK,
    )
    base.update(overrides)
    return UniverseInput(**base)


def _book():
    return OrderBook(
        symbol="BTCUSDT",
        timestamp=1,
        bids=tuple(
            OrderBookLevel(price=100.0 - 0.1 * (i + 1), qty=5.0)
            for i in range(3)
        ),
        asks=tuple(
            OrderBookLevel(price=100.1 + 0.1 * i, qty=5.0)
            for i in range(3)
        ),
    )


def _good_liquidity_input(**overrides):
    base = dict(
        symbol="BTCUSDT",
        side=Side.LONG,
        planned_qty=0.001,
        last_price=100.0,
        spread_pct=0.0001,
        orderbook=_book(),
        volume_5m=10_000.0,
        is_data_degraded=False,
        market_regime=MarketRegime.MEME_RISK_ON,
        risk_permission=RiskPermission.ALLOW_ATTACK,
    )
    base.update(overrides)
    return LiquidityInput(**base)


# --- Universe ---------------------------------------------------------------
def test_universe_config_default_event_emit_enabled_is_true():
    cfg = UniverseConfig()
    assert cfg.event_emit_enabled is True


def test_universe_filter_exposes_skipped_counter_starting_at_zero():
    f = UniverseFilter()
    assert f.universe_filtered_events_skipped == 0


def test_universe_config_disabled_skips_event_and_increments_counter(events_repo):
    cfg = UniverseConfig(event_emit_enabled=False)
    f = UniverseFilter(config=cfg, event_repo=events_repo)
    f.evaluate(_good_universe_input())
    assert events_repo.count_events(event_type=EventType.UNIVERSE_FILTERED) == 0
    assert f.universe_filtered_events_emitted == 0
    assert f.universe_filtered_events_skipped == 1


def test_universe_config_disabled_but_per_call_true_still_emits(events_repo):
    """Per-call override beats the config flag."""
    cfg = UniverseConfig(event_emit_enabled=False)
    f = UniverseFilter(config=cfg, event_repo=events_repo)
    f.evaluate(_good_universe_input(), emit_event=True)
    assert events_repo.count_events(event_type=EventType.UNIVERSE_FILTERED) == 1
    assert f.universe_filtered_events_emitted == 1
    assert f.universe_filtered_events_skipped == 0


def test_universe_config_enabled_but_per_call_false_still_skips(events_repo):
    """Per-call override beats the config flag (the other direction)."""
    cfg = UniverseConfig(event_emit_enabled=True)
    f = UniverseFilter(config=cfg, event_repo=events_repo)
    f.evaluate(_good_universe_input(), emit_event=False)
    assert events_repo.count_events(event_type=EventType.UNIVERSE_FILTERED) == 0
    assert f.universe_filtered_events_emitted == 0
    assert f.universe_filtered_events_skipped == 1


def test_universe_evaluate_many_inherits_throttle(events_repo):
    """A 3-symbol scan with the throttle off must produce zero events
    and increment skipped by 3.
    """
    cfg = UniverseConfig(event_emit_enabled=False)
    f = UniverseFilter(config=cfg, event_repo=events_repo)
    f.evaluate_many(
        [
            _good_universe_input(symbol="BTCUSDT"),
            _good_universe_input(symbol="ETHUSDT"),
            _good_universe_input(symbol="PEPEUSDT"),
        ]
    )
    assert events_repo.count_events(event_type=EventType.UNIVERSE_FILTERED) == 0
    assert f.universe_filtered_events_skipped == 3
    assert f.universe_filtered_events_emitted == 0


def test_universe_evaluate_snapshot_inherits_throttle(events_repo):
    """The convenience helper must honour the same flag."""
    from app.core.enums import DataReliability
    from app.core.models import MarketSnapshot
    from app.exchanges.models import ExchangeSymbol

    cfg = UniverseConfig(event_emit_enabled=False)
    f = UniverseFilter(config=cfg, event_repo=events_repo)
    snap = MarketSnapshot(
        symbol="BTCUSDT",
        timestamp=1,
        last_price=100.0,
        bid=99.99,
        ask=100.01,
        spread_pct=0.0001,
        volume_5m=2_000.0,
        orderbook_depth_usdt=100_000.0,
    )
    sym_meta = ExchangeSymbol(
        symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT"
    )
    f.evaluate_snapshot(
        snap,
        symbol_meta=sym_meta,
        regime=None,
        is_data_degraded=False,
        reliability=DataReliability.A,
        trade_count_5m=50,
    )
    assert events_repo.count_events(event_type=EventType.UNIVERSE_FILTERED) == 0
    assert f.universe_filtered_events_skipped == 1


# --- Liquidity --------------------------------------------------------------
def test_liquidity_config_default_event_emit_enabled_is_true():
    cfg = LiquidityConfig()
    assert cfg.event_emit_enabled is True


def test_liquidity_filter_exposes_skipped_counter_starting_at_zero():
    f = LiquidityFilter()
    assert f.liquidity_checked_events_skipped == 0


def test_liquidity_config_disabled_skips_event_and_increments_counter(events_repo):
    """evaluate() path."""
    cfg = LiquidityConfig(event_emit_enabled=False)
    f = LiquidityFilter(config=cfg, event_repo=events_repo)
    f.evaluate(_good_liquidity_input())
    assert events_repo.count_events(event_type=EventType.LIQUIDITY_CHECKED) == 0
    assert f.liquidity_checked_events_emitted == 0
    assert f.liquidity_checked_events_skipped == 1


def test_liquidity_config_disabled_skips_can_exit_position(events_repo):
    """can_exit_position path."""
    cfg = LiquidityConfig(event_emit_enabled=False)
    f = LiquidityFilter(config=cfg, event_repo=events_repo)
    f.can_exit_position(
        "BTCUSDT",
        qty=0.001,
        max_slippage_pct=0.01,
        max_seconds=60.0,
        side=Side.LONG,
        orderbook=_book(),
        volume_5m=10_000.0,
    )
    assert events_repo.count_events(event_type=EventType.LIQUIDITY_CHECKED) == 0
    assert f.liquidity_checked_events_emitted == 0
    assert f.liquidity_checked_events_skipped == 1


def test_liquidity_per_call_true_overrides_disabled_config(events_repo):
    cfg = LiquidityConfig(event_emit_enabled=False)
    f = LiquidityFilter(config=cfg, event_repo=events_repo)
    f.evaluate(_good_liquidity_input(), emit_event=True)
    f.can_exit_position(
        "BTCUSDT",
        qty=0.001,
        max_slippage_pct=0.01,
        max_seconds=60.0,
        side=Side.LONG,
        orderbook=_book(),
        volume_5m=10_000.0,
        emit_event=True,
    )
    assert events_repo.count_events(event_type=EventType.LIQUIDITY_CHECKED) == 2
    assert f.liquidity_checked_events_emitted == 2
    assert f.liquidity_checked_events_skipped == 0


def test_liquidity_per_call_false_overrides_enabled_config(events_repo):
    cfg = LiquidityConfig(event_emit_enabled=True)
    f = LiquidityFilter(config=cfg, event_repo=events_repo)
    f.evaluate(_good_liquidity_input(), emit_event=False)
    f.can_exit_position(
        "BTCUSDT",
        qty=0.001,
        max_slippage_pct=0.01,
        max_seconds=60.0,
        side=Side.LONG,
        orderbook=_book(),
        volume_5m=10_000.0,
        emit_event=False,
    )
    assert events_repo.count_events(event_type=EventType.LIQUIDITY_CHECKED) == 0
    assert f.liquidity_checked_events_emitted == 0
    assert f.liquidity_checked_events_skipped == 2


def test_liquidity_evaluate_with_buffer_inherits_throttle(events_repo):
    """``evaluate_with_buffer`` must honour the same config flag.

    Use a tiny stub that mimics the Phase 4 buffer surface
    (``snapshot``, ``is_degraded``, ``_state_for``).
    """
    from app.core.models import MarketSnapshot

    class _StubState:
        def __init__(self, book):
            self.orderbook = book

    class _StubBuffer:
        def __init__(self, book):
            self._book = book

        def snapshot(self, symbol, *, emit_event=False):
            return MarketSnapshot(
                symbol=symbol,
                timestamp=1,
                last_price=100.0,
                bid=99.99,
                ask=100.01,
                spread_pct=0.0001,
                volume_5m=10_000.0,
                orderbook_depth_usdt=200_000.0,
            )

        def is_degraded(self, symbol):
            return False

        def _state_for(self, symbol):
            return _StubState(self._book)

    cfg = LiquidityConfig(event_emit_enabled=False)
    f = LiquidityFilter(config=cfg, event_repo=events_repo)
    f.evaluate_with_buffer(
        "BTCUSDT",
        side=Side.LONG,
        planned_qty=0.001,
        market_data_buffer=_StubBuffer(_book()),
    )
    assert events_repo.count_events(event_type=EventType.LIQUIDITY_CHECKED) == 0
    assert f.liquidity_checked_events_skipped == 1


def test_free_can_exit_position_honours_config_flag(events_repo):
    """The free function path must inherit the same throttle."""
    cfg = LiquidityConfig(event_emit_enabled=False)
    plan = can_exit_position_fn(
        "BTCUSDT",
        qty=0.001,
        max_slippage_pct=0.01,
        max_seconds=60.0,
        orderbook=_book(),
        side=Side.LONG,
        volume_5m=10_000.0,
        config=cfg,
        event_repo=events_repo,
        emit_event=None,
    )
    assert plan.feasible is True
    assert events_repo.count_events(event_type=EventType.LIQUIDITY_CHECKED) == 0


def test_free_can_exit_position_default_emit_event_false_still_skips(events_repo):
    """Backwards-compat check: the free function's default
    ``emit_event=False`` still produces zero events regardless of
    config (the default keeps existing tests / Issue #7 callers
    silent).
    """
    cfg = LiquidityConfig(event_emit_enabled=True)
    can_exit_position_fn(
        "BTCUSDT",
        qty=0.001,
        max_slippage_pct=0.01,
        max_seconds=60.0,
        orderbook=_book(),
        side=Side.LONG,
        volume_5m=10_000.0,
        config=cfg,
        event_repo=events_repo,
    )
    assert events_repo.count_events(event_type=EventType.LIQUIDITY_CHECKED) == 0


# ---------------------------------------------------------------------------
# Counter consistency: emitted + skipped == evaluations / exit_checks
# ---------------------------------------------------------------------------
def test_universe_emitted_plus_skipped_equals_evaluations(events_repo):
    cfg = UniverseConfig(event_emit_enabled=False)
    f = UniverseFilter(config=cfg, event_repo=events_repo)
    f.evaluate(_good_universe_input(symbol="BTCUSDT"))
    f.evaluate(_good_universe_input(symbol="ETHUSDT"), emit_event=True)
    f.evaluate(_good_universe_input(symbol="PEPEUSDT"))
    assert (
        f.universe_filtered_events_emitted + f.universe_filtered_events_skipped
        == f.evaluations
    )


def test_liquidity_emitted_plus_skipped_equals_evaluate_count(events_repo):
    cfg = LiquidityConfig(event_emit_enabled=False)
    f = LiquidityFilter(config=cfg, event_repo=events_repo)
    f.evaluate(_good_liquidity_input(symbol="BTCUSDT"))
    f.evaluate(_good_liquidity_input(symbol="ETHUSDT"), emit_event=True)
    f.evaluate(_good_liquidity_input(symbol="PEPEUSDT"))
    # evaluations counts evaluate() calls only.
    assert (
        f.liquidity_checked_events_emitted + f.liquidity_checked_events_skipped
        == f.evaluations
    )


def test_liquidity_emitted_plus_skipped_includes_can_exit_position(events_repo):
    """Both emit paths feed the same emitted/skipped pair, so
    ``emitted + skipped`` must equal ``evaluations + exit_checks``
    when every call goes through one of the two paths.
    """
    cfg = LiquidityConfig(event_emit_enabled=False)
    f = LiquidityFilter(config=cfg, event_repo=events_repo)
    f.evaluate(_good_liquidity_input(), emit_event=True)
    f.can_exit_position(
        "BTCUSDT",
        qty=0.001,
        max_slippage_pct=0.01,
        max_seconds=60.0,
        side=Side.LONG,
        orderbook=_book(),
        volume_5m=10_000.0,
    )
    assert (
        f.liquidity_checked_events_emitted + f.liquidity_checked_events_skipped
        == f.evaluations + f.exit_checks
    )


# ---------------------------------------------------------------------------
# Smoke: per-symbol reject still produces a typed reject reason even
# under throttle off (the throttle must NOT lose decision quality, only
# event volume).
# ---------------------------------------------------------------------------
def test_throttle_off_still_returns_full_reject_reason_set(events_repo):
    cfg = LiquidityConfig(event_emit_enabled=False)
    f = LiquidityFilter(config=cfg, event_repo=events_repo)
    decision = f.evaluate(
        _good_liquidity_input(spread_pct=0.05, planned_qty=0.001)
    )
    assert decision.passed is False
    assert LiquidityRejectReason.SPREAD_TOO_WIDE in decision.reject_reasons
    # Throttle off -> no event written.
    assert events_repo.count_events(event_type=EventType.LIQUIDITY_CHECKED) == 0
    assert f.liquidity_checked_events_skipped == 1
