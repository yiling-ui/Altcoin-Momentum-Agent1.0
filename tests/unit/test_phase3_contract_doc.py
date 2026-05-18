"""Phase 3 (Issue #3) - assert the docs/PHASE_3_CONTRACT.md contract
document stays consistent with the runtime.

The contract document is the single source of truth for:

  - the reliability tier table (Spec §13.3)
  - the five Phase 4 invariants (mock-default, opt-in adapter, no API
    key, no write surface, no auto-connect)
  - the rule that `get_account_snapshot` is mock-only / skeleton-only
    in Phase 3 and Phase 4

If the document and the runtime ever disagree, this test fails. That
forces the contract change to land in a deliberate review (Spec §42
change control) rather than drift.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.enums import DataReliability
from app.exchanges.base import ExchangeClientBase

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "docs" / "PHASE_3_CONTRACT.md"


@pytest.fixture(scope="module")
def contract_text() -> str:
    assert CONTRACT_PATH.exists(), (
        f"docs/PHASE_3_CONTRACT.md is missing - the Phase 3 review "
        f"contract must live in version control."
    )
    return CONTRACT_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tier table consistency
# ---------------------------------------------------------------------------
def test_contract_doc_states_get_orderbook_is_tier_a(contract_text: str):
    """The reviewer's specific worry: the doc must state get_orderbook=A."""
    line_match = "| `get_orderbook`        | **A**"
    assert line_match in contract_text, (
        "docs/PHASE_3_CONTRACT.md must state `get_orderbook` is tier A "
        "explicitly."
    )


def test_contract_doc_states_get_recent_trades_is_tier_a(contract_text: str):
    line_match = "| `get_recent_trades`    | **A**"
    assert line_match in contract_text, (
        "docs/PHASE_3_CONTRACT.md must state `get_recent_trades` is tier A "
        "explicitly."
    )


def test_contract_doc_states_get_funding_rate_is_tier_b(contract_text: str):
    line_match = "| `get_funding_rate`     | **B**"
    assert line_match in contract_text


def test_contract_doc_states_get_open_interest_is_tier_b(contract_text: str):
    line_match = "| `get_open_interest`    | **B**"
    assert line_match in contract_text


def test_contract_doc_states_get_symbols_is_tier_b(contract_text: str):
    line_match = "| `get_symbols`          | **B**"
    assert line_match in contract_text


def test_contract_doc_states_get_account_snapshot_is_tier_b(contract_text: str):
    line_match = "| `get_account_snapshot` | **B**"
    assert line_match in contract_text


def test_contract_doc_explicitly_names_both_tier_a_surfaces(contract_text: str):
    """Reviewer's exact worry: 'Tier-A surfaces = get_orderbook,
    get_recent_trades'. Make sure the doc states this in a way no
    drive-by reader can misread. We normalise whitespace so the
    needle survives line wrapping in the markdown source.
    """
    normalised = " ".join(contract_text.split())
    needle = (
        "Both tier-A surfaces are explicitly **`get_orderbook` AND "
        "`get_recent_trades`**"
    )
    assert needle in normalised, (
        "docs/PHASE_3_CONTRACT.md must explicitly name both tier-A "
        "surfaces in a single unambiguous sentence."
    )


def test_contract_doc_matches_runtime_reliability_tiers():
    """The runtime mapping in `ExchangeClientBase.reliability_tiers`
    must match the document. We instantiate a tiny concrete subclass
    just to read the property without depending on BinanceClient /
    MockExchangeClient.
    """

    class _Probe(ExchangeClientBase):
        name = "probe"

        def get_symbols(self):  # pragma: no cover - never called
            raise NotImplementedError

        def get_orderbook(self, symbol, *, depth=20):  # pragma: no cover
            raise NotImplementedError

        def get_recent_trades(self, symbol, *, limit=100):  # pragma: no cover
            raise NotImplementedError

        def get_funding_rate(self, symbol):  # pragma: no cover
            raise NotImplementedError

        def get_open_interest(self, symbol):  # pragma: no cover
            raise NotImplementedError

        def get_account_snapshot(self):  # pragma: no cover
            raise NotImplementedError

    probe = _Probe()
    assert probe.reliability_tiers == {
        "get_symbols": DataReliability.B,
        "get_orderbook": DataReliability.A,
        "get_recent_trades": DataReliability.A,
        "get_funding_rate": DataReliability.B,
        "get_open_interest": DataReliability.B,
        "get_account_snapshot": DataReliability.B,
    }


# ---------------------------------------------------------------------------
# Phase 4 invariants
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "phrase",
    [
        "Mock / fixture data is the default",
        "Any real public read-only adapter is opt-in only",
        "No API key. No credentials.",
        "No write surface. Ever.",
        "Tests must not depend on real network",
    ],
)
def test_contract_doc_lists_each_phase4_invariant(
    contract_text: str, phrase: str
) -> None:
    assert phrase in contract_text, (
        f"docs/PHASE_3_CONTRACT.md must contain the Phase 4 invariant "
        f"'{phrase}' verbatim."
    )


def test_contract_doc_names_phase_9_as_earliest_for_real_account_snapshot(
    contract_text: str,
) -> None:
    """Account snapshot can ONLY land in Phase 9 (Reconciliation)."""
    assert "Phase 9 (Reconciliation)" in contract_text


def test_contract_doc_states_get_account_snapshot_remains_skeleton_in_phase4(
    contract_text: str,
) -> None:
    """Reviewer's item 3: doc must say `get_account_snapshot` stays a
    skeleton in BOTH Phase 3 and Phase 4. Whitespace-normalised so
    line wrapping in the source doesn't break the assertion.
    """
    normalised = " ".join(contract_text.split())
    needle = (
        "**Phase 4:** SAME. `BinanceClient.get_account_snapshot` "
        "continues to raise `NotImplementedError`."
    )
    assert needle in normalised


def test_contract_doc_names_the_four_write_surface_refusals(
    contract_text: str,
) -> None:
    """The Phase 3 hard refusals must be enumerated by name."""
    for surface in ("create_order", "cancel_order", "set_leverage", "set_margin_mode"):
        assert f"`{surface}`" in contract_text, (
            f"docs/PHASE_3_CONTRACT.md must list `{surface}` "
            f"as a banned write surface."
        )
