"""Phase 7 - repository-wide network / no-leak sanity (Issue #7).

Phase 7 introduces ``app/state_machine/`` and extends ``app/risk/``;
both packages must respect the cumulative defence-in-depth invariants:

  - No exchange SDK / network library import.
  - No LLM client import.
  - No write surface (``create_order`` etc).
  - No ``api_key`` / ``api_secret`` / ``binance_api`` substring.
  - No ``os.environ`` / ``getenv`` lookup (AST scan).
  - No ``ExchangeClientBase`` subclass.
  - No premature import of the Issue #8 (Capital Flow), Issue #9
    (Execution FSM / Reconciliation), Issue #10 (LLM / Telegram
    outbound / Replay / Reflection) modules.
  - No ``MarketDataBuffer`` / ``MockExchangeClient`` / ``BinanceClient``
    constructor call.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PHASE7_PACKAGES = ("state_machine", "risk")

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
        assert package.is_dir(), f"app/{pkg}/ must exist in Phase 7"
        for path in package.rglob("*.py"):
            yield path


def test_phase7_packages_import_no_network_or_llm_library():
    forbidden_imports = tuple(
        f.replace("-", "_").split(".")[0] for f in FORBIDDEN_PACKAGES
    )
    for path in _iter_py(*PHASE7_PACKAGES):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            for token in forbidden_imports:
                assert not stripped.startswith(f"import {token}"), (
                    f"{path} imports {token}; forbidden in Phase 7"
                )
                assert not stripped.startswith(f"from {token}"), (
                    f"{path} imports from {token}; forbidden in Phase 7"
                )


def test_phase7_packages_do_not_mention_api_key():
    forbidden_substrings = ("api_key", "api_secret", "binance_api")
    for path in _iter_py(*PHASE7_PACKAGES):
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden_substrings:
            assert token not in text, (
                f"{path} mentions {token!r}; Phase 7 forbids any API "
                f"key path inside the state-machine / risk packages."
            )


def test_phase7_packages_do_not_define_write_surfaces():
    for path in _iter_py(*PHASE7_PACKAGES):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_METHOD_TOKENS:
            assert token not in text, (
                f"{path} defines {token!r}; Phase 7 must not add a "
                f"write surface."
            )


def test_phase7_packages_do_not_mention_market_or_orders_db():
    for path in _iter_py(*PHASE7_PACKAGES):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("market.db", "orders.db"):
            assert forbidden not in text, (
                f"{path} mentions {forbidden}; Phase 7 must remain "
                f"in-memory / events.db only."
            )


def test_phase7_packages_do_not_read_environ_for_credentials():
    import ast

    for path in _iter_py(*PHASE7_PACKAGES):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if (
                    isinstance(node.value, ast.Name)
                    and node.value.id == "os"
                    and node.attr == "environ"
                ):  # pragma: no cover
                    raise AssertionError(
                        f"{path} reads os.environ; Phase 7 modules must "
                        f"not look up credentials or runtime config that way."
                    )
            if isinstance(node, ast.Call):
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                    and func.attr == "getenv"
                ):  # pragma: no cover
                    raise AssertionError(
                        f"{path} calls os.getenv; Phase 7 modules must "
                        f"not look up credentials or runtime config that way."
                    )
                if isinstance(func, ast.Name) and func.id == "getenv":  # pragma: no cover
                    raise AssertionError(
                        f"{path} calls getenv; Phase 7 modules must "
                        f"not look up credentials or runtime config that way."
                    )


def test_phase7_packages_do_not_subclass_exchange_client_base():
    for path in _iter_py(*PHASE7_PACKAGES):
        text = path.read_text(encoding="utf-8")
        assert "ExchangeClientBase)" not in text, (
            f"{path} subclasses ExchangeClientBase; that is forbidden in "
            f"Phase 7. Issue #9 owns the next concrete adapter."
        )


def test_phase7_packages_do_not_import_issue_8_9_10_modules():
    """Phase 7 hard ban: no Capital Flow Engine, no Execution FSM
    extension, no Reconciliation, no LLM, no Telegram outbound, no
    Replay, no Reflection. Those belong to Issue #8 / #9 / #10."""
    forbidden_imports = (
        "app.llm",
        "app.capital",
        "app.capital_flow",
        "app.execution.order_manager",  # Issue #9 full FSM lives here
        "app.reconciliation",
        "app.replay",
        "app.reflection",
    )
    for path in _iter_py(*PHASE7_PACKAGES):
        text = path.read_text(encoding="utf-8")
        for token in forbidden_imports:
            assert token not in text, (
                f"{path} imports {token}; Phase 7 must not depend on "
                f"Issue #8 / #9 / #10 modules."
            )


def test_phase7_packages_do_not_instantiate_buffer_or_exchange():
    for path in _iter_py(*PHASE7_PACKAGES):
        text = path.read_text(encoding="utf-8")
        assert "MarketDataBuffer(" not in text, (
            f"{path} instantiates MarketDataBuffer; that is forbidden "
            f"in Phase 7."
        )
        assert "MockExchangeClient(" not in text, (
            f"{path} instantiates MockExchangeClient; that is forbidden "
            f"in Phase 7."
        )
        assert "BinanceClient(" not in text, (
            f"{path} instantiates BinanceClient; that is forbidden "
            f"in Phase 7."
        )


def test_phase7_packages_do_not_introduce_new_btc_eth_modules():
    """Phase 7 semantic lock #7: BTC/ETH may only feed Regime / No-Trade
    Gate inputs; no separate trading module is permitted. Phase 7 does
    NOT add ``app/btc_module/`` or similar."""
    forbidden_dirs = (
        "btc",
        "eth",
        "btc_eth",
    )
    app_dir = ROOT / "app"
    for entry in app_dir.iterdir():
        if entry.is_dir() and entry.name.lower() in forbidden_dirs:
            raise AssertionError(
                f"Phase 7 forbids a stand-alone {entry.name}/ module."
            )


def test_phase7_packages_do_not_add_orders_or_capital_db_files():
    """Phase 7 must not introduce new persistent database files. The
    five Phase 2 databases remain the only data plane."""
    for path in _iter_py(*PHASE7_PACKAGES):
        text = path.read_text(encoding="utf-8")
        for forbidden in (
            "trades.db",
            "positions.db",
            "incidents.db",
            "reflection.db",
            "llm_cache.db",
        ):
            assert (
                f"sqlite3.connect({forbidden!r})" not in text
            ), f"{path} opens {forbidden} directly; not a Phase 7 surface."
