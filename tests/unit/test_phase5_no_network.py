"""Phase 5 - repository-wide network sanity checks (Issue #5).

The Phase 3 ``test_phase3_no_network.py`` and the Phase 4
``test_phase4_no_network.py`` both still apply repo-wide. Phase 5
adds the same scan specifically against ``app/regime/``,
``app/universe/`` and ``app/liquidity/`` so a future reviewer cannot
miss a sneaky import added under the new packages.

Phase 5 boundary recap:

  - Regime / Universe / Liquidity ONLY. No Scanner, no Confirmation,
    no Manipulation, no Strategy, no State Machine.
  - Reads only. **No write surface added.**
  - **No real Binance WebSocket and no real REST.**
  - **No API key.** None of the three packages references
    ``api_key`` / ``api_secret`` / ``binance_api`` / ``os.environ``
    for credentials.
  - **No auto-connect.** None of the three packages instantiates a
    :class:`MarketDataBuffer` or an :class:`ExchangeClientBase` for
    itself; each is wired in by callers.
  - Tests do not depend on real network.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PHASE5_PACKAGES = ("regime", "universe", "liquidity")

# Same forbidden set as Phase 3 / Phase 4.
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

# Phase 5 must not introduce any of these write-surface methods on the
# new modules. The base-class refusals on ExchangeClientBase remain
# the only path; subclassing or adding new write-side methods anywhere
# under these packages is a hard fail.
FORBIDDEN_METHOD_TOKENS = (
    "def create_order",
    "def cancel_order",
    "def set_leverage",
    "def set_margin_mode",
)


def _iter_py(*pkgs: str):
    for pkg in pkgs:
        package = ROOT / "app" / pkg
        assert package.is_dir(), f"app/{pkg}/ must exist in Phase 5"
        for path in package.rglob("*.py"):
            yield path


def test_phase5_packages_import_no_network_library():
    forbidden_imports = tuple(
        f.replace("-", "_").split(".")[0] for f in FORBIDDEN_PACKAGES
    )
    for path in _iter_py(*PHASE5_PACKAGES):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            for token in forbidden_imports:
                assert not stripped.startswith(f"import {token}"), (
                    f"{path} imports {token}; forbidden in Phase 5"
                )
                assert not stripped.startswith(f"from {token}"), (
                    f"{path} imports from {token}; forbidden in Phase 5"
                )


def test_phase5_packages_do_not_mention_api_key():
    forbidden_substrings = ("api_key", "api_secret", "binance_api")
    for path in _iter_py(*PHASE5_PACKAGES):
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden_substrings:
            assert token not in text, (
                f"{path} mentions {token!r}; Phase 5 forbids any API key "
                f"path inside the regime / universe / liquidity packages."
            )


def test_phase5_packages_do_not_define_write_surfaces():
    for path in _iter_py(*PHASE5_PACKAGES):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_METHOD_TOKENS:
            assert token not in text, (
                f"{path} defines {token!r}; Phase 5 must not add a "
                f"write surface."
            )


def test_phase5_packages_do_not_create_market_or_orders_db():
    for path in _iter_py(*PHASE5_PACKAGES):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("market.db", "orders.db"):
            assert forbidden not in text, (
                f"{path} mentions {forbidden}; Phase 5 must remain "
                f"in-memory and emit only through the existing "
                f"events.db substrate."
            )


def test_phase5_packages_do_not_read_environ_for_credentials():
    """Phase 5 modules must not look up credentials via os.environ.

    A simple substring scan is enough because the production code never
    needs to *legitimately* read os.environ.
    """
    for path in _iter_py(*PHASE5_PACKAGES):
        text = path.read_text(encoding="utf-8")
        assert "os.environ" not in text, (
            f"{path} reads os.environ; Phase 5 modules must not look up "
            f"credentials or runtime config that way."
        )
        assert "getenv" not in text, (
            f"{path} calls getenv; Phase 5 modules must not look up "
            f"credentials or runtime config that way."
        )


def test_phase5_packages_do_not_subclass_exchange_client_base():
    """Phase 5 modules consume the gateway, they MUST NOT extend it.

    Subclassing :class:`ExchangeClientBase` is the path that Issue #9
    will eventually take to introduce a real adapter; we forbid it
    here so a Phase 5 PR cannot sneak past the boundary.
    """
    for path in _iter_py(*PHASE5_PACKAGES):
        text = path.read_text(encoding="utf-8")
        # Allow `ExchangeClientBase` as a typed parameter (`base` import)
        # but forbid actual subclassing.
        assert "ExchangeClientBase)" not in text, (
            f"{path} subclasses ExchangeClientBase; that is forbidden in "
            f"Phase 5. Issue #9 owns the next concrete adapter."
        )


def test_phase5_packages_do_not_import_strategy_or_scanner_or_state_machine():
    """The Phase 5 boundary is explicit: no Scanner / no Confirmation /
    no Manipulation Detector / no Strategy / no State Machine.

    None of these packages exist yet on main, but if any future PR adds
    one and Phase 5 modules start importing it, the boundary has drifted.
    """
    forbidden_imports = (
        "app.scanner",
        "app.confirmation",
        "app.manipulation",
        "app.strategies",
        "app.state_machine",
    )
    for path in _iter_py(*PHASE5_PACKAGES):
        text = path.read_text(encoding="utf-8")
        for token in forbidden_imports:
            assert token not in text, (
                f"{path} imports {token}; Phase 5 must not depend on "
                f"Issue #6 / #7 modules."
            )
