"""Phase 10B - source-tree audit: no network / no LLM / no API key /
no write surface (Issue #10 Part 2).

AST scan of ``app/reflection/`` enforces:

  - No exchange SDK / HTTP / WebSocket / LLM client import
  - No Telegram bot library import (Phase 10D)
  - No write surface (``create_order`` / ``cancel_order`` /
    ``set_leverage`` / ``set_margin_mode``) method definition
  - No ``api_key`` / ``api_secret`` / ``bot_token`` parameter or
    concrete literal
  - No ``os.environ`` / ``os.getenv`` / bare ``getenv()`` call
  - No reference to ``send_message`` / ``send_document`` /
    ``send_photo`` (Phase 10D Telegram outbound stays deferred)
  - No ``EventRepository.append_event`` / ``append_many`` /
    ``record_*`` helper invocation - Reflection is read-only
  - No write to other databases (trades.db / positions.db /
    market.db / orders.db / reflection.db / llm_cache.db /
    capital.db / incidents.db) - Reflection is read-only against
    events.db only
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

PHASE_10B_PACKAGES = (ROOT / "app" / "reflection",)
PHASE_10B_FILES = [p for pkg in PHASE_10B_PACKAGES for p in pkg.rglob("*.py")]


FORBIDDEN_IMPORTS = {
    # Exchange SDKs
    "ccxt",
    "binance",
    # HTTP / WebSocket clients
    "aiohttp",
    "websockets",
    "requests",
    "httpx",
    # LLM clients
    "openai",
    "anthropic",
    "deepseek",
    # Telegram bot libraries (Phase 10D)
    "python_telegram_bot",
    "telebot",
    "aiogram",
    "telegram",
}


FORBIDDEN_KEY_FRAGMENTS = (
    "api_key",
    "api_secret",
    "binance_api",
    "deepseek_api",
    "openai_api",
    "anthropic_api",
    "bot_token",
    "telegram_token",
)


WRITE_SURFACE_METHODS = (
    "create_order",
    "cancel_order",
    "set_leverage",
    "set_margin_mode",
)


def _walk_imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.module


def _walk_function_defs(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _walk_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


@pytest.mark.parametrize(
    "path", PHASE_10B_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_forbidden_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for module_name in _walk_imports(tree):
        head = module_name.split(".")[0]
        assert head not in FORBIDDEN_IMPORTS, (
            f"{path.relative_to(ROOT)} imports forbidden module {module_name}"
        )


@pytest.mark.parametrize(
    "path", PHASE_10B_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_write_surface_method_definitions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for fn_node in _walk_function_defs(tree):
        assert fn_node.name not in WRITE_SURFACE_METHODS, (
            f"{path.relative_to(ROOT)} defines forbidden write surface "
            f"method {fn_node.name}"
        )


@pytest.mark.parametrize(
    "path", PHASE_10B_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_api_key_parameter_or_literal(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for fn_node in _walk_function_defs(tree):
        for arg in (
            list(fn_node.args.args)
            + list(fn_node.args.kwonlyargs)
            + list(fn_node.args.posonlyargs)
        ):
            lower = arg.arg.lower()
            for needle in FORBIDDEN_KEY_FRAGMENTS:
                assert needle not in lower, (
                    f"{path.relative_to(ROOT)}::{fn_node.name} accepts "
                    f"forbidden parameter {arg.arg}"
                )

    blacklist_in_strings = (
        "BINANCE_API_KEY=",
        "BINANCE_API_SECRET=",
        "TELEGRAM_BOT_TOKEN=",
        "DEEPSEEK_API_KEY=",
        "OPENAI_API_KEY=",
        "ANTHROPIC_API_KEY=",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for needle in blacklist_in_strings:
                assert needle not in node.value, (
                    f"{path.relative_to(ROOT)} contains forbidden literal {needle}"
                )


@pytest.mark.parametrize(
    "path", PHASE_10B_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_environment_variable_reads(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for call in _walk_calls(tree):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr in {"getenv", "get"}:
                tgt = call.func.value
                names: list[str] = []
                while isinstance(tgt, ast.Attribute):
                    names.append(tgt.attr)
                    tgt = tgt.value
                if isinstance(tgt, ast.Name):
                    names.append(tgt.id)
                joined = ".".join(reversed(names))
                if joined.endswith("os.environ") or joined == "os":
                    raise AssertionError(
                        f"{path.relative_to(ROOT)} reads {joined}.{call.func.attr}"
                    )
        elif isinstance(call.func, ast.Name) and call.func.id == "getenv":
            raise AssertionError(
                f"{path.relative_to(ROOT)} calls bare getenv()"
            )


@pytest.mark.parametrize(
    "path", PHASE_10B_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_telegram_outbound_calls(path: Path):
    """Phase 10B must not reference the Phase 10D Telegram outbound surfaces."""
    text = path.read_text(encoding="utf-8")
    for needle in ("send_message", "send_document", "send_photo"):
        assert needle not in text, (
            f"{path.relative_to(ROOT)} mentions {needle}; "
            "Phase 10D owns Telegram outbound."
        )


def test_phase10b_does_not_open_other_dbs():
    """Phase 10B is read-only against events.db. No file under
    `app/reflection/` opens any other database directly."""
    forbidden_dbs = (
        "trades.db",
        "positions.db",
        "market.db",
        "orders.db",
        "reflection.db",
        "llm_cache.db",
        "capital.db",
        "incidents.db",
    )
    for path in PHASE_10B_FILES:
        text = path.read_text(encoding="utf-8")
        for needle in forbidden_dbs:
            assert (
                f"sqlite3.connect({needle!r})" not in text
            ), f"{path.relative_to(ROOT)} opens {needle} directly"


@pytest.mark.parametrize(
    "path", PHASE_10B_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_append_event_writes(path: Path):
    """Phase 10B is read-only. The Reflection package must NOT call
    ``EventRepository.append_event`` or ``append_many`` anywhere in
    its source tree."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for call in _walk_calls(tree):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr in {"append_event", "append_many"}:
                raise AssertionError(
                    f"{path.relative_to(ROOT)} calls .{call.func.attr}() - "
                    "Reflection must be read-only."
                )


@pytest.mark.parametrize(
    "path", PHASE_10B_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_capital_recorder_calls(path: Path):
    """Reflection must not invoke the EventRepository capital helpers
    (``record_capital_*`` / ``record_profit_harvest`` /
    ``record_risk_budget_recalculated``). Those write to events.db."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for call in _walk_calls(tree):
        if isinstance(call.func, ast.Attribute):
            attr = call.func.attr
            if attr.startswith("record_capital_") or attr in {
                "record_profit_harvest",
                "record_risk_budget_recalculated",
            }:
                raise AssertionError(
                    f"{path.relative_to(ROOT)} calls .{attr}() - "
                    "Reflection must be read-only."
                )


def test_phase10b_does_not_import_state_mutating_components():
    """The Reflection package must not import any state-mutating component."""
    forbidden = {
        "CapitalFlowEngine",
        "ExecutionFSMDriver",
        "Reconciler",
        "MockExchangeClient",
        "BinanceClient",
        "MarketDataBuffer",
        "TelegramCommandCenter",
        "RiskEngine",
        "RegimeEngine",
        "IncidentRepository",
    }
    for path in PHASE_10B_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert alias.name not in forbidden, (
                        f"{path.relative_to(ROOT)} imports forbidden state-mutating "
                        f"class {alias.name}"
                    )


def test_phase10b_files_exist():
    """Sanity: the Phase 10B package is laid out as expected."""
    expected = {
        "__init__.py",
        "tags.py",
        "models.py",
        "metrics.py",
        "engine.py",
    }
    actual = {p.name for p in PHASE_10B_FILES}
    missing = expected - actual
    assert not missing, f"Phase 10B files missing: {missing}"
