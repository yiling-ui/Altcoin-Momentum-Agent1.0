"""Phase 10C - source-tree audit: no network / no API key /
no write surface (Issue #10 Part 3).

AST scan of ``app/llm/`` enforces the Phase 10C boundary at the
source-tree level so a future maintainer cannot silently weaken it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

PHASE_10C_PACKAGES = (ROOT / "app" / "llm",)
PHASE_10C_FILES = [p for pkg in PHASE_10C_PACKAGES for p in pkg.rglob("*.py")]


FORBIDDEN_IMPORTS = {
    # Exchange SDKs
    "ccxt",
    "binance",
    # HTTP / WebSocket clients
    "aiohttp",
    "websockets",
    "requests",
    "httpx",
    # Real LLM clients (Phase 10C is sandboxed)
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
    "path", PHASE_10C_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_forbidden_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for module_name in _walk_imports(tree):
        head = module_name.split(".")[0]
        assert head not in FORBIDDEN_IMPORTS, (
            f"{path.relative_to(ROOT)} imports forbidden module {module_name}"
        )


@pytest.mark.parametrize(
    "path", PHASE_10C_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_write_surface_method_definitions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for fn_node in _walk_function_defs(tree):
        assert fn_node.name not in WRITE_SURFACE_METHODS, (
            f"{path.relative_to(ROOT)} defines forbidden write surface "
            f"method {fn_node.name}"
        )


@pytest.mark.parametrize(
    "path", PHASE_10C_FILES, ids=lambda p: str(p.relative_to(ROOT))
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
    "path", PHASE_10C_FILES, ids=lambda p: str(p.relative_to(ROOT))
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
    "path", PHASE_10C_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_telegram_outbound_calls(path: Path):
    """Phase 10C must not reference the Phase 10D Telegram outbound surfaces."""
    text = path.read_text(encoding="utf-8")
    for needle in ("send_message", "send_document", "send_photo"):
        assert needle not in text, (
            f"{path.relative_to(ROOT)} mentions {needle}; "
            "Phase 10D owns Telegram outbound."
        )


def test_phase10c_does_not_open_other_dbs():
    """Phase 10C may write LLM_INTERPRETED / LLM_DEGRADED /
    LLM_SCHEMA_REJECTED events to events.db via EventRepository, but
    must NOT open any other database directly."""
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
    for path in PHASE_10C_FILES:
        text = path.read_text(encoding="utf-8")
        for needle in forbidden_dbs:
            assert (
                f"sqlite3.connect({needle!r})" not in text
            ), f"{path.relative_to(ROOT)} opens {needle} directly"


def test_phase10c_does_not_import_state_mutating_components():
    """The LLM package must not import any state-mutating component."""
    forbidden = {
        "CapitalFlowEngine",
        "ExecutionFSMDriver",
        "ExecutionFSM",
        "Reconciler",
        "MockExchangeClient",
        "BinanceClient",
        "MarketDataBuffer",
        "TelegramCommandCenter",
        "RiskEngine",
        "RiskRequest",
        "RegimeEngine",
        "IncidentRepository",
        "PaperLedger",
        "OrderRequest",
    }
    for path in PHASE_10C_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert alias.name not in forbidden, (
                        f"{path.relative_to(ROOT)} imports forbidden state-mutating "
                        f"class {alias.name}"
                    )


@pytest.mark.parametrize(
    "path", PHASE_10C_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_create_order_call(path: Path):
    """The LLM package may emit events but MUST NOT call
    ``create_order`` / ``cancel_order`` / ``set_leverage`` /
    ``set_margin_mode`` on any object."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for call in _walk_calls(tree):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr in WRITE_SURFACE_METHODS:
                raise AssertionError(
                    f"{path.relative_to(ROOT)} calls .{call.func.attr}()"
                )


def test_phase10c_files_exist():
    """Sanity: the Phase 10C package is laid out as expected."""
    expected = {
        "__init__.py",
        "models.py",
        "schema.py",
        "prompts.py",
        "guardrails.py",
        "cache.py",
        "client.py",
        "interpreter.py",
    }
    actual = {p.name for p in PHASE_10C_FILES}
    missing = expected - actual
    assert not missing, f"Phase 10C files missing: {missing}"


def test_phase10c_event_emission_is_limited_to_three_event_types():
    """The interpreter is the only Phase 10C module that emits events.
    Walk all `EventType.X` references in app/llm/ and confirm only
    LLM_INTERPRETED / LLM_DEGRADED / LLM_SCHEMA_REJECTED are referenced
    as targets of an event emission."""
    text = (ROOT / "app" / "llm" / "interpreter.py").read_text(encoding="utf-8")
    # Allowed event types in interpreter.
    allowed = {
        "LLM_INTERPRETED",
        "LLM_DEGRADED",
        "LLM_SCHEMA_REJECTED",
    }
    # Conservative scan: every occurrence of `EventType.X` must be in
    # the allowed set. The interpreter does NOT reference any other
    # event type today.
    import re

    for match in re.finditer(r"EventType\.([A-Z_]+)", text):
        assert match.group(1) in allowed, (
            f"interpreter.py emits unexpected EventType.{match.group(1)}"
        )
