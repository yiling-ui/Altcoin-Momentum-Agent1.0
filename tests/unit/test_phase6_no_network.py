"""Phase 6 - repository-wide network sanity checks (Issue #6).

The Phase 3 / Phase 4 / Phase 5 no-network tests still apply repo-wide.
Phase 6 adds the same scan specifically against ``app/scanner/``,
``app/confirmation/`` and ``app/manipulation/`` so a future reviewer
cannot miss a sneaky import added under the new packages.

Phase 6 boundary recap (declared explicitly so the next PR cannot
drift):

  - Pre-Anomaly / Anomaly / Real-Trade Confirmation / Manipulation
    Detector ONLY. No Strategy Engine, no State Machine, no LLM, no
    Capital Flow, no Execution FSM, no Reconciliation.
  - Reads only. **No write surface added.**
  - **No real Binance WebSocket and no real REST.**
  - **No API key.** None of the three packages references
    ``api_key`` / ``api_secret`` / ``binance_api`` / ``os.environ``
    for credentials.
  - **No auto-connect.** None of the three packages instantiates a
    :class:`MarketDataBuffer` or an :class:`ExchangeClientBase` for
    itself; each is wired in by callers.
  - **No LLM.** Issue #6 forbids using an LLM to decide direction or
    to bypass the Risk Engine; Phase 6 modules MUST NOT import an
    LLM client.
  - Tests do not depend on real network.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PHASE6_PACKAGES = ("scanner", "confirmation", "manipulation")

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
    "openai",
    "anthropic",
    "deepseek",
)

FORBIDDEN_METHOD_TOKENS = (
    "def create_order",
    "def cancel_order",
    "def set_leverage",
    "def set_margin_mode",
)


def _iter_py(*pkgs: str):
    for pkg in pkgs:
        package = ROOT / "app" / pkg
        assert package.is_dir(), f"app/{pkg}/ must exist in Phase 6"
        for path in package.rglob("*.py"):
            yield path


def test_phase6_packages_import_no_network_or_llm_library():
    forbidden_imports = tuple(
        f.replace("-", "_").split(".")[0] for f in FORBIDDEN_PACKAGES
    )
    for path in _iter_py(*PHASE6_PACKAGES):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            for token in forbidden_imports:
                assert not stripped.startswith(f"import {token}"), (
                    f"{path} imports {token}; forbidden in Phase 6"
                )
                assert not stripped.startswith(f"from {token}"), (
                    f"{path} imports from {token}; forbidden in Phase 6"
                )


def test_phase6_packages_do_not_mention_api_key():
    forbidden_substrings = ("api_key", "api_secret", "binance_api")
    for path in _iter_py(*PHASE6_PACKAGES):
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden_substrings:
            assert token not in text, (
                f"{path} mentions {token!r}; Phase 6 forbids any API key "
                f"path inside the scanner / confirmation / manipulation packages."
            )


def test_phase6_packages_do_not_define_write_surfaces():
    for path in _iter_py(*PHASE6_PACKAGES):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_METHOD_TOKENS:
            assert token not in text, (
                f"{path} defines {token!r}; Phase 6 must not add a "
                f"write surface."
            )


def test_phase6_packages_do_not_create_market_or_orders_db():
    for path in _iter_py(*PHASE6_PACKAGES):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("market.db", "orders.db"):
            assert forbidden not in text, (
                f"{path} mentions {forbidden}; Phase 6 must remain "
                f"in-memory and emit only through the existing "
                f"events.db substrate."
            )


def test_phase6_packages_do_not_read_environ_for_credentials():
    """The Phase 6 modules must not look up credentials via os.environ.

    We scan executable code (Python AST), not docstrings, so the
    boundary tests can mention these tokens for documentation
    purposes without false-positiving the scan.
    """
    import ast

    for path in _iter_py(*PHASE6_PACKAGES):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            # Look for Attribute access ``os.environ`` and
            # Call to ``os.getenv`` / bare ``getenv``.
            if isinstance(node, ast.Attribute):
                if (
                    isinstance(node.value, ast.Name)
                    and node.value.id == "os"
                    and node.attr == "environ"
                ):  # pragma: no cover - regression
                    raise AssertionError(
                        f"{path} reads os.environ; Phase 6 modules must "
                        f"not look up credentials or runtime config that way."
                    )
            if isinstance(node, ast.Call):
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                    and func.attr == "getenv"
                ):  # pragma: no cover - regression
                    raise AssertionError(
                        f"{path} calls os.getenv; Phase 6 modules must "
                        f"not look up credentials or runtime config that way."
                    )
                if isinstance(func, ast.Name) and func.id == "getenv":  # pragma: no cover - regression
                    raise AssertionError(
                        f"{path} calls getenv; Phase 6 modules must "
                        f"not look up credentials or runtime config that way."
                    )


def test_phase6_packages_do_not_subclass_exchange_client_base():
    for path in _iter_py(*PHASE6_PACKAGES):
        text = path.read_text(encoding="utf-8")
        assert "ExchangeClientBase)" not in text, (
            f"{path} subclasses ExchangeClientBase; that is forbidden in "
            f"Phase 6. Issue #9 owns the next concrete adapter."
        )


def test_phase6_packages_do_not_import_llm_strategy_or_state_machine():
    """Phase 6 hard ban: no LLM, no Strategy Engine, no State Machine,
    no Capital Flow, no Execution FSM. These belong to Issue #7..#10."""
    forbidden_imports = (
        "app.llm",
        "app.strategies",
        "app.state_machine",
        "app.capital",
        "app.execution.order_manager",  # full FSM lives here in Issue #9
        "app.reconciliation",
        "app.replay",
        "app.reflection",
    )
    for path in _iter_py(*PHASE6_PACKAGES):
        text = path.read_text(encoding="utf-8")
        for token in forbidden_imports:
            assert token not in text, (
                f"{path} imports {token}; Phase 6 must not depend on "
                f"Issue #7 / #8 / #9 / #10 modules."
            )


def test_phase6_packages_do_not_instantiate_marketdatabuffer_or_exchange():
    """Scanners read snapshots that the caller hands them; they do
    NOT own a buffer or an exchange client."""
    for path in _iter_py(*PHASE6_PACKAGES):
        text = path.read_text(encoding="utf-8")
        # `MarketDataBuffer(...)` would be a constructor call. The
        # convenience helpers in the new modules accept a buffer as a
        # *parameter*, never instantiate one.
        assert "MarketDataBuffer(" not in text, (
            f"{path} instantiates MarketDataBuffer; that is forbidden "
            f"in Phase 6."
        )
        assert "MockExchangeClient(" not in text, (
            f"{path} instantiates MockExchangeClient; that is forbidden "
            f"in Phase 6."
        )
        assert "BinanceClient(" not in text, (
            f"{path} instantiates BinanceClient; that is forbidden "
            f"in Phase 6."
        )
