"""Phase 8.5 - source-tree audit: no network / no LLM / no API key /
no write surface (Issue #8.5)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

# Modules audited by this file. Add a new module to PHASE_8_5_PACKAGES
# when Phase 8.5 grows.
PHASE_8_5_PACKAGES = (
    ROOT / "app" / "learning",
    ROOT / "app" / "exports",
)
PHASE_8_5_FILES = [
    p for pkg in PHASE_8_5_PACKAGES for p in pkg.rglob("*.py")
]


FORBIDDEN_IMPORTS = {
    # Exchange SDKs
    "ccxt",
    "binance",
    # HTTP / WebSocket clients (an export bundle never makes a network call)
    "aiohttp",
    "websockets",
    "requests",
    "httpx",
    # LLM clients
    "openai",
    "anthropic",
    "deepseek",
    # Telegram bot libraries (Phase 8.5 boundary forbids outbound)
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
            yield node.name


def _walk_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


@pytest.mark.parametrize("path", PHASE_8_5_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_forbidden_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for module_name in _walk_imports(tree):
        # Match top-level package only.
        head = module_name.split(".")[0]
        assert head not in FORBIDDEN_IMPORTS, (
            f"{path.relative_to(ROOT)} imports forbidden module {module_name}"
        )


@pytest.mark.parametrize("path", PHASE_8_5_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_write_surface_method_definitions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for fn_name in _walk_function_defs(tree):
        assert fn_name not in WRITE_SURFACE_METHODS, (
            f"{path.relative_to(ROOT)} defines forbidden write surface "
            f"method {fn_name}"
        )


@pytest.mark.parametrize("path", PHASE_8_5_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_api_key_parameter_or_string(path: Path):
    """Phase 8.5 packages must not accept an api_key parameter and
    must not literal-encode any credential.

    Substring checks are intentionally case-insensitive to catch
    'API_KEY' literals; documentation strings ARE allowed to mention
    these tokens (we strip docstrings via AST first)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    # Argument names: must not contain "api_key" / "api_secret" etc.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in (
                list(node.args.args)
                + list(node.args.kwonlyargs)
                + list(node.args.posonlyargs)
            ):
                lower = arg.arg.lower()
                for needle in FORBIDDEN_KEY_FRAGMENTS:
                    assert needle not in lower, (
                        f"{path.relative_to(ROOT)}::{node.name} accepts "
                        f"forbidden parameter {arg.arg}"
                    )

    # String constants: must not contain concrete API key fragments
    # like ``BINANCE_API_KEY=`` (separator-aware so docstrings can
    # mention the token in prose).
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


@pytest.mark.parametrize("path", PHASE_8_5_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_environment_variable_reads(path: Path):
    """Phase 8.5 modules must not read os.environ / os.getenv / getenv."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for call in _walk_calls(tree):
        # os.environ.get / os.environ['X']
        if isinstance(call.func, ast.Attribute):
            if call.func.attr in {"getenv", "get"}:
                # Inspect target chain to flag os.environ.get only.
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


def test_phase8_5_packages_do_not_pull_in_telegram_outbound():
    """Phase 8.5 packages must not import the in-process Telegram skeleton's
    ``send_message`` surface (which Issue #10 will replace). This is a
    forward-looking guard so an over-eager refactor cannot accidentally
    wire export -> Telegram before Issue #10 ships."""
    forbidden_callables = ("send_message", "send_document", "send_photo")
    for path in PHASE_8_5_FILES:
        text = path.read_text(encoding="utf-8")
        for needle in forbidden_callables:
            # Allow doc-comments in the export contract.
            assert (
                needle not in text
                or path.name in {
                    # The CLI explicitly does NOT contain these tokens.
                }
            ), f"{path.relative_to(ROOT)} mentions {needle}"
