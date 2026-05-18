"""Phase 4 - repository-wide network sanity checks.

The Phase 3 ``test_phase3_no_network.py`` already enforces a no-SDK /
no-outbound-import rule at the repo level. Phase 4 adds the same scan
specifically against ``app/market_data/`` so that a future reviewer
cannot miss a sneaky import added under the new package.

Phase 4 boundary recap (Issue #4 + the user's hard constraints):

  - Market Data Buffer ONLY.
  - MockExchangeClient / fixture data by default.
  - **No real Binance WebSocket and no real REST.**
  - **No API key.** No write surface. No auto-connect.
  - ``BinanceClient.get_account_snapshot`` remains mock-only / skeleton-
    only in both Phase 3 and Phase 4.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Same set as test_phase3_no_network.py - kept in lock-step on purpose.
FORBIDDEN_PACKAGES = (
    "ccxt",
    "binance-connector",
    "python-binance",
    "binance.client",
    "aiohttp",
    "websockets",
    "websocket-client",
    "requests",
    "httpx",
)


def test_market_data_package_imports_no_network_library():
    forbidden_imports = tuple(
        f.replace("-", "_").split(".")[0] for f in FORBIDDEN_PACKAGES
    )
    package = ROOT / "app" / "market_data"
    assert package.is_dir(), "app/market_data/ must exist in Phase 4"
    for path in package.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            for token in forbidden_imports:
                assert not stripped.startswith(f"import {token}"), (
                    f"{path} imports {token}; forbidden in Phase 4"
                )
                assert not stripped.startswith(f"from {token}"), (
                    f"{path} imports from {token}; forbidden in Phase 4"
                )


def test_market_data_package_does_not_mention_api_key():
    """Defence in depth: no file under ``app/market_data/`` should even
    *parameterise* an API key. The Phase 4 boundary forbids it.
    """
    package = ROOT / "app" / "market_data"
    forbidden_substrings = ("api_key", "api_secret", "binance_api")
    for path in package.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden_substrings:
            assert token not in text, (
                f"{path} mentions {token!r}; Phase 4 forbids any API key "
                f"path inside the Market Data Buffer."
            )


def test_market_data_package_does_not_create_market_db():
    """Phase 4 must NOT introduce ``market.db``. The buffer is
    in-memory only (Spec §33.1 + the Issue #2 boundary that explicitly
    excluded market.db from Phase 2's PHASE2_DATABASES tuple)."""
    package = ROOT / "app" / "market_data"
    for path in package.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "market.db" not in text, (
            f"{path} mentions market.db. Phase 4 keeps the buffer in-memory."
        )


def test_binance_client_get_account_snapshot_remains_skeleton():
    """Phase 4 must NOT relax the rule. The Phase 3 review locked in:
    real account snapshots cannot land before the limited-live phase.
    """
    from app.exchanges.binance import BinanceClient

    client = BinanceClient()
    try:
        client.get_account_snapshot()
    except NotImplementedError as exc:
        msg = str(exc).lower()
        assert "skeleton" in msg
        assert "phase 4" in msg
        assert "api key" in msg
    else:
        raise AssertionError(
            "BinanceClient.get_account_snapshot must raise NotImplementedError "
            "in Phase 4."
        )
