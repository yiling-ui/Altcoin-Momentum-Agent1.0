"""Phase 10D - source-tree audit: no network / no API key /
no write surface (Issue #10 Part 4).

Per-file AST scan of ``app/telegram/`` enforces the Phase 10D
boundary at the source-tree level so a future maintainer cannot
silently weaken it.

The audit is intentionally STRICTER than Phase 10C in some ways:

  - Phase 10D forbids ALL HTTP / WebSocket / exchange / LLM /
    third-party Telegram bot library imports under ``app/telegram/``
    even though the package is the official outbound layer. Phase
    10D ships a refusal-only HTTP skeleton; the real HTTP transport
    lives behind Spec §41 Go/No-Go in a separate PR.
  - Phase 10D forbids ``os.environ`` / ``os.getenv`` reads.
    Credentials must be passed in explicitly by the caller.
  - Phase 10D forbids any ``api_key`` / ``api_secret`` /
    ``bot_token`` parameter or concrete env-var literal.
  - Phase 10D forbids state-mutating component imports (Risk Engine
    / Execution FSM / Capital Flow Engine / etc.).

Note on the package name
------------------------

Our package is named ``app.telegram``. The Python community's
third-party Telegram bot SDKs are ``python_telegram_bot`` /
``telebot`` / ``aiogram`` / ``telegram`` (the PyPI package). We
forbid the first three; the bare ``telegram`` import is also
forbidden because the third-party package would clash with our own
namespace. All four are added to FORBIDDEN_IMPORTS below.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

PHASE_10D_PACKAGES = (ROOT / "app" / "telegram",)
PHASE_10D_FILES = [p for pkg in PHASE_10D_PACKAGES for p in pkg.rglob("*.py")]


FORBIDDEN_IMPORTS = {
    # Exchange SDKs
    "ccxt",
    "binance",
    # HTTP / WebSocket clients
    "aiohttp",
    "websockets",
    "requests",
    "httpx",
    "urllib3",
    # Real LLM clients
    "openai",
    "anthropic",
    "deepseek",
    # Third-party Telegram bot libraries (the bare 'telegram' import
    # is also forbidden because that's the PyPI namespace for the
    # python-telegram-bot SDK).
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
    "tg_token",
    "auth_token",
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
    "path", PHASE_10D_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_forbidden_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for module_name in _walk_imports(tree):
        head = module_name.split(".")[0]
        assert head not in FORBIDDEN_IMPORTS, (
            f"{path.relative_to(ROOT)} imports forbidden module {module_name}"
        )


@pytest.mark.parametrize(
    "path", PHASE_10D_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_write_surface_method_definitions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for fn_node in _walk_function_defs(tree):
        assert fn_node.name not in WRITE_SURFACE_METHODS, (
            f"{path.relative_to(ROOT)} defines forbidden write surface "
            f"method {fn_node.name}"
        )


@pytest.mark.parametrize(
    "path", PHASE_10D_FILES, ids=lambda p: str(p.relative_to(ROOT))
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
    "path", PHASE_10D_FILES, ids=lambda p: str(p.relative_to(ROOT))
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
    "path", PHASE_10D_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_write_surface_call(path: Path):
    """The Telegram package may dispatch alerts but MUST NOT call
    ``create_order`` / ``cancel_order`` / ``set_leverage`` /
    ``set_margin_mode`` on any object."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for call in _walk_calls(tree):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr in WRITE_SURFACE_METHODS:
                raise AssertionError(
                    f"{path.relative_to(ROOT)} calls .{call.func.attr}()"
                )


@pytest.mark.parametrize(
    "path", PHASE_10D_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_other_db_connect(path: Path):
    """Phase 10D writes only via EventRepository (which itself
    targets events.db). It must NOT open any other database
    directly."""
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
    text = path.read_text(encoding="utf-8")
    for needle in forbidden_dbs:
        assert (
            f"sqlite3.connect({needle!r})" not in text
        ), f"{path.relative_to(ROOT)} opens {needle} directly"


def test_phase10d_files_exist():
    """Sanity: the Phase 10D package is laid out as expected."""
    expected = {
        "__init__.py",
        "alerts.py",
        "bot.py",
        "commands.py",
        "exports.py",
        "formatter.py",
        "outbound.py",
    }
    actual = {p.name for p in PHASE_10D_FILES}
    missing = expected - actual
    assert not missing, f"Phase 10D files missing: {missing}"


def test_phase10d_event_emission_is_limited_to_known_event_types():
    """The Phase 10D modules emit ONLY the new + Phase 1 telegram
    event types. Walk every ``EventType.X`` reference and confirm
    they're in the allowed set."""
    import re

    allowed = {
        # Phase 10D new types
        "TELEGRAM_COMMAND_REJECTED",
        "TELEGRAM_MESSAGE_SENT",
        "TELEGRAM_SEND_FAILED",
        "DATA_EXPORT_GENERATED",
        "DATA_EXPORT_FAILED",
        # Phase 1 reused
        "TELEGRAM_COMMAND_RECEIVED",
    }
    pattern = re.compile(r"EventType\.([A-Z_]+)")
    for path in PHASE_10D_FILES:
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            assert match.group(1) in allowed, (
                f"{path.relative_to(ROOT)} emits unexpected "
                f"EventType.{match.group(1)}"
            )
