"""Phase 6 - non-generation invariant (PR #17 review feedback).

The Phase 6 classifiers MUST be passive scorers / level mappers. None
of them is an entry signal. None of them is a trade approval. None of
them constructs an :class:`app.core.models.TradeDecision`, enqueues
an order, or mutates a position.

This file pins the contract from three independent angles:

1. **Output shape.** The four decision value-objects expose only
   `score` / `level` + `reason_tags` + `notes` + `timestamp`. No
   `direction`, no `entry_zone`, no `qty`, no `stop_price`, no
   `position_id`, no `order_id`, no `take_profit_plan`. The Spec
   §11.3 :class:`TradeDecision` shape lives in
   :mod:`app.core.models` and the Phase 6 packages never produce it.

2. **Source-tree scan.** No source file under ``app/scanner/``,
   ``app/confirmation/`` or ``app/manipulation/`` imports
   :class:`TradeDecision` from :mod:`app.core.models`, mentions
   ``order`` / ``position`` / ``execution`` package paths, or
   instantiates :class:`app.core.models.TradeDecision`.

3. **Documentation pin.** The package and class docstrings carry the
   "indicators only / level only" + "NOT entry signal / NOT trade
   approval" wording, so the regime-gate-vs-trade-approval
   distinction the PR #16 review fix established is preserved across
   Phase 6 too.

Phase 7 (Issue #7) is the FIRST place a :class:`TradeDecision` is
allowed to be constructed, behind the Risk Engine. Phase 6 must not
ship any code path that produces one.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from app.confirmation import (
    ConfirmationDecision,
    ConfirmationInput,
    RealTradeConfirmation,
)
from app.core.enums import TradeConfirmationLevel
from app.core.models import TradeDecision
from app.manipulation import (
    ManipulationDecision,
    ManipulationDetector,
    ManipulationInput,
)
from app.scanner import (
    AnomalyDecision,
    AnomalyInput,
    AnomalyScanner,
    PreAnomalyDecision,
    PreAnomalyInput,
    PreAnomalyScanner,
)


ROOT = Path(__file__).resolve().parents[2]
PHASE6_PACKAGES = ("scanner", "confirmation", "manipulation")


# ---------------------------------------------------------------------------
# 1. Output shape: no TradeDecision-shaped fields on any Phase 6 decision
# ---------------------------------------------------------------------------
TRADE_DECISION_FIELDS = {
    "action",
    "direction",
    "state",
    "grade",
    "entry_zone",
    "stop_price",
    "take_profit_plan",
    "risk_budget_pct",
    "leverage",
    "qty",
    "position_id",
    "order_id",
    "client_order_id",
}


def _decision_field_names(model_cls) -> set[str]:
    return set(model_cls.model_fields.keys())


def test_pre_anomaly_decision_has_no_trade_decision_fields():
    fields = _decision_field_names(PreAnomalyDecision)
    leaked = fields & TRADE_DECISION_FIELDS
    assert not leaked, (
        f"PreAnomalyDecision leaks TradeDecision-shaped fields: {leaked}. "
        f"Phase 6 scanners must remain passive indicators."
    )
    assert "pre_anomaly_score" in fields
    assert "reason_tags" in fields


def test_anomaly_decision_has_no_trade_decision_fields():
    fields = _decision_field_names(AnomalyDecision)
    leaked = fields & TRADE_DECISION_FIELDS
    assert not leaked, (
        f"AnomalyDecision leaks TradeDecision-shaped fields: {leaked}. "
        f"Phase 6 scanners must remain passive indicators."
    )
    assert "anomaly_score" in fields
    assert "reason_tags" in fields


def test_confirmation_decision_has_no_trade_decision_fields():
    fields = _decision_field_names(ConfirmationDecision)
    leaked = fields & TRADE_DECISION_FIELDS
    assert not leaked, (
        f"ConfirmationDecision leaks TradeDecision-shaped fields: {leaked}. "
        f"T3/T4 is a confirmation LEVEL only, not a trade approval."
    )
    assert "level" in fields
    assert "reason_tags" in fields


def test_manipulation_decision_has_no_trade_decision_fields():
    fields = _decision_field_names(ManipulationDecision)
    leaked = fields & TRADE_DECISION_FIELDS
    assert not leaked, (
        f"ManipulationDecision leaks TradeDecision-shaped fields: {leaked}. "
        f"M-tier is a manipulation LEVEL only, not a trade approval."
    )
    assert "level" in fields
    assert "reason_tags" in fields


# ---------------------------------------------------------------------------
# 2. Behaviour: a fired evaluation never returns a TradeDecision
# ---------------------------------------------------------------------------
def _confirmation_t3_input():
    from app.confirmation import ConfirmationBarSummary

    bars = (
        ConfirmationBarSummary(
            open=1.00, high=1.02, low=0.99, close=1.01,
            volume=10.0, buy_volume=5.0, sell_volume=5.0, trade_count=10,
        ),
        ConfirmationBarSummary(
            open=1.01, high=1.03, low=1.005, close=1.02,
            volume=10.0, buy_volume=5.0, sell_volume=5.0, trade_count=10,
        ),
        ConfirmationBarSummary(
            open=1.02, high=1.04, low=1.015, close=1.03,
            volume=10.0, buy_volume=5.0, sell_volume=5.0, trade_count=10,
        ),
    )
    return ConfirmationInput(
        symbol="PEPEUSDT",
        last_price=1.04,
        prev_close_price=1.03,
        cvd_1m=30.0,
        cvd_5m=50.0,
        volume_1m=120.0,
        volume_5m=400.0,
        return_pct_1m=0.01,
        breakout_level=1.005,
        last_n_closed_bars=bars,
        largest_trade_qty_1m=0.5,
    )


def test_real_trade_confirmation_never_returns_trade_decision():
    """T3 / T4 is a confirmation LEVEL only, NOT a trade approval.

    Even on a clean T3 input the classifier's return type is
    :class:`ConfirmationDecision` and is NOT a :class:`TradeDecision`.
    No order, no position, no entry plan is produced.
    """
    decision = RealTradeConfirmation().evaluate(_confirmation_t3_input())
    assert isinstance(decision, ConfirmationDecision)
    assert not isinstance(decision, TradeDecision)
    assert decision.level is TradeConfirmationLevel.T3
    decision_dict = decision.model_dump()
    for forbidden in TRADE_DECISION_FIELDS:
        assert forbidden not in decision_dict


def test_pre_anomaly_scanner_never_returns_trade_decision():
    """``pre_anomaly_score`` is a candidate INDICATOR only, NOT an
    entry signal. The classifier returns a passive
    :class:`PreAnomalyDecision`, never a :class:`TradeDecision`."""
    decision = PreAnomalyScanner().evaluate(
        PreAnomalyInput(
            symbol="PEPEUSDT",
            last_price=1.05,
            prev_close_price=1.04,
            spread_pct=0.0005,
            baseline_spread_pct=0.001,
            volume_1m=130.0,
            volume_5m=500.0,
            cvd_1m=30.0,
            oi=1010.0,
            prev_oi=1000.0,
            funding_rate=0.0001,
        )
    )
    assert isinstance(decision, PreAnomalyDecision)
    assert not isinstance(decision, TradeDecision)
    decision_dict = decision.model_dump()
    for forbidden in TRADE_DECISION_FIELDS:
        assert forbidden not in decision_dict


def test_anomaly_scanner_never_returns_trade_decision():
    """``anomaly_score`` is an ANOMALY INDICATOR only, NOT an entry
    signal. A high score does NOT authorise opening a position."""
    decision = AnomalyScanner().evaluate(
        AnomalyInput(
            symbol="PEPEUSDT",
            last_price=1.05,
            volume_1m=300.0,
            volume_5m=500.0,
            cvd_1m=80.0,
            cvd_5m=80.0,
            atr_1m=0.05,
            atr_5m=0.02,
            oi=1100.0,
            prev_oi=1000.0,
            funding_rate=0.002,
            liquidations_qty_1m=200.0,
            sweep_legs=2,
            high_5m=1.04,
            high_15m=1.03,
            high_1h=1.02,
        )
    )
    assert isinstance(decision, AnomalyDecision)
    assert not isinstance(decision, TradeDecision)
    decision_dict = decision.model_dump()
    for forbidden in TRADE_DECISION_FIELDS:
        assert forbidden not in decision_dict


def test_manipulation_detector_never_returns_trade_decision():
    decision = ManipulationDetector().evaluate(
        ManipulationInput(
            symbol="PEPEUSDT",
            return_pct_1m=0.0,
            volume_1m=30.0,
            volume_5m=50.0,
            oi=1010.0,
            prev_oi=1000.0,
        )
    )
    assert isinstance(decision, ManipulationDecision)
    assert not isinstance(decision, TradeDecision)
    decision_dict = decision.model_dump()
    for forbidden in TRADE_DECISION_FIELDS:
        assert forbidden not in decision_dict


# ---------------------------------------------------------------------------
# 3. Source-tree scan: Phase 6 packages do not import / mention
#    TradeDecision, OrderManager, PositionManager, ExecutionFSM driver.
# ---------------------------------------------------------------------------
def _iter_phase6_py():
    for pkg in PHASE6_PACKAGES:
        package = ROOT / "app" / pkg
        for path in package.rglob("*.py"):
            yield path


def test_phase6_packages_do_not_import_trade_decision():
    for path in _iter_phase6_py():
        text = path.read_text(encoding="utf-8")
        assert (
            "from app.core.models import TradeDecision" not in text
        ), (
            f"{path} imports TradeDecision; Phase 6 must not generate one."
        )
        if "from app.core.models import" in text:
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("from app.core.models import"):
                    assert "TradeDecision" not in stripped, (
                        f"{path} imports TradeDecision via {stripped!r}; "
                        f"Phase 6 must not generate one."
                    )


def test_phase6_packages_do_not_construct_trade_decision():
    """No source file under the three new packages instantiates
    :class:`TradeDecision`."""
    for path in _iter_phase6_py():
        text = path.read_text(encoding="utf-8")
        assert "TradeDecision(" not in text, (
            f"{path} constructs TradeDecision(...); Phase 6 must not "
            f"generate one."
        )


def test_phase6_packages_do_not_import_order_or_position_modules():
    forbidden = (
        "app.execution.order_manager",
        "app.execution.stop_manager",
        "app.execution.execution_policy",
        "app.positions",
        "app.positions.manager",
        "app.positions.tail",
        "app.reconciliation",
    )
    for path in _iter_phase6_py():
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, (
                f"{path} mentions {token}; Phase 6 must remain a "
                f"passive classifier set."
            )


# ---------------------------------------------------------------------------
# 4. Documentation pin: the public docstrings carry the "level only" /
#    "indicators only" wording so the boundary cannot drift.
# ---------------------------------------------------------------------------
def test_real_trade_confirmation_module_docstring_pins_level_only_wording():
    import app.confirmation as conf
    import app.confirmation.real_trade as rt

    pkg_doc = (conf.__doc__ or "").lower()
    cls_doc = (rt.__doc__ or "").lower()

    assert "level only" in pkg_doc
    assert "not a trade approval" in pkg_doc
    assert "not a trade approval" in cls_doc
    for token in (
        "regime",
        "liquidity",
        "manipulation",
        "risk engine",
        "execution fsm",
    ):
        assert token in cls_doc, (
            f"app.confirmation.real_trade module docstring must reference {token!r}"
        )


def test_scanner_package_docstring_pins_indicators_only_wording():
    import app.scanner as scan

    pkg_doc = (scan.__doc__ or "").lower()
    assert "indicators only" in pkg_doc
    assert "not entry signals" in pkg_doc
    for token in (
        "regime",
        "universe",
        "liquidity",
        "confirmation",
        "manipulation",
        "risk engine",
        "execution fsm",
    ):
        assert token in pkg_doc, (
            f"app.scanner package docstring must reference {token!r}"
        )


def test_pre_anomaly_module_docstring_pins_indicator_only_wording():
    import app.scanner.pre_anomaly as mod

    doc = " ".join((mod.__doc__ or "").lower().split())
    assert "candidate indicator only" in doc
    assert "not an entry signal" in doc


def test_anomaly_module_docstring_pins_indicator_only_wording():
    import app.scanner.anomaly as mod

    doc = " ".join((mod.__doc__ or "").lower().split())
    assert "anomaly indicator only" in doc
    assert "not an entry signal" in doc


# ---------------------------------------------------------------------------
# 5. Risk Engine M3 caveat: the docstring + the inline branch comment
#    state that protective exits / reduce-only flows are NOT in scope
#    for Phase 6 and must be preserved by Phase 7 / 9.
# ---------------------------------------------------------------------------
def test_risk_engine_module_docstring_pins_m3_protective_exit_caveat():
    import app.risk.engine as engine

    doc = (engine.__doc__ or "").lower()
    assert "new opening" in doc or "new openings" in doc
    assert "protective" in doc
    assert "reduce-only" in doc or "reduce only" in doc
    assert "phase 7" in doc
    assert "phase 9" in doc


def test_risk_engine_inline_m3_branch_carries_protective_exit_caveat():
    """The inline comment immediately above the M3 branch must remind
    the reader that Phase 6 only implements the new-opening block."""
    import app.risk.engine as engine

    src = inspect.getsource(engine).lower()
    assert "manipulation_m3" in src
    assert "new openings only" in src or "new opening only" in src
    assert "protective" in src
    assert "reduce-only" in src or "reduce only" in src
    assert "phase 7" in src
    assert "phase 9" in src
