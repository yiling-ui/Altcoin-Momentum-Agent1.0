"""Phase 9 - source-tree audit: no network / no LLM / no API key /
no write surface (Issue #9).

AST scan of ``app/execution/``, ``app/incidents/``,
``app/reconciliation/`` enforces:

  - No exchange SDK / HTTP / WebSocket / LLM client import
  - No write surface (``create_order`` / ``cancel_order`` /
    ``set_leverage`` / ``set_margin_mode``) method definition
  - No ``api_key`` / ``api_secret`` parameter or concrete literal
  - No ``os.environ`` / ``os.getenv`` / ``getenv()`` call
  - No subscriber to a real exchange WebSocket / REST adapter
  - No reference to ``send_message`` / ``send_document`` /
    ``send_photo`` (Phase 10 Telegram outbound stays deferred)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

PHASE_9_PACKAGES = (
    ROOT / "app" / "execution",
    ROOT / "app" / "incidents",
    ROOT / "app" / "reconciliation",
)
PHASE_9_FILES = [p for pkg in PHASE_9_PACKAGES for p in pkg.rglob("*.py")]


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
    # Telegram bot libraries (Phase 10)
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


@pytest.mark.parametrize("path", PHASE_9_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_forbidden_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for module_name in _walk_imports(tree):
        head = module_name.split(".")[0]
        assert head not in FORBIDDEN_IMPORTS, (
            f"{path.relative_to(ROOT)} imports forbidden module {module_name}"
        )


@pytest.mark.parametrize("path", PHASE_9_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_write_surface_method_definitions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for fn_node in _walk_function_defs(tree):
        assert fn_node.name not in WRITE_SURFACE_METHODS, (
            f"{path.relative_to(ROOT)} defines forbidden write surface "
            f"method {fn_node.name}"
        )


@pytest.mark.parametrize("path", PHASE_9_FILES, ids=lambda p: str(p.relative_to(ROOT)))
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


@pytest.mark.parametrize("path", PHASE_9_FILES, ids=lambda p: str(p.relative_to(ROOT)))
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


@pytest.mark.parametrize("path", PHASE_9_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_telegram_outbound_calls(path: Path):
    """Phase 9 must not reference the Phase 10 Telegram outbound surfaces."""
    text = path.read_text(encoding="utf-8")
    for needle in ("send_message", "send_document", "send_photo"):
        assert needle not in text, (
            f"{path.relative_to(ROOT)} mentions {needle}; "
            "Phase 10 owns Telegram outbound."
        )


def test_phase9_packages_do_not_open_other_dbs():
    """Phase 9 may write to events.db (via EventRepository) and incidents.db
    (via IncidentRepository) ONLY. trades.db / positions.db / market.db /
    orders.db / reflection.db / llm_cache.db must NOT be touched directly.
    """
    forbidden_dbs = (
        "trades.db",
        "positions.db",
        "market.db",
        "orders.db",
        "reflection.db",
        "llm_cache.db",
    )
    for path in PHASE_9_FILES:
        text = path.read_text(encoding="utf-8")
        for needle in forbidden_dbs:
            assert (
                f"sqlite3.connect({needle!r})" not in text
            ), f"{path.relative_to(ROOT)} opens {needle} directly"
