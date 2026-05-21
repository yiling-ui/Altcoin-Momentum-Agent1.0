"""Phase 11C - source-tree audit.

Verifies that the Phase 11C public-market read-only client and the
runner script:

  - do NOT import any third-party HTTP / WebSocket / exchange / LLM /
    Telegram bot library;
  - do NOT define a write surface;
  - do NOT contain any concrete credential literal;
  - do NOT call any signed Binance endpoint;
  - do NOT read ``os.environ`` for credential values.

Phase 11C is the first phase allowed to talk to a real public-market
endpoint, so this audit is the load-bearing guard against drift.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

PHASE_11C_FILES = [
    ROOT / "app" / "exchanges" / "binance_public.py",
    ROOT / "app" / "exchanges" / "binance_public_ws.py",
    ROOT / "app" / "market_data_public" / "__init__.py",
    ROOT / "app" / "market_data_public" / "candidate_pool.py",
    ROOT / "app" / "market_data_public" / "event_chain.py",
    ROOT / "app" / "market_data_public" / "ingest.py",
    ROOT / "app" / "market_data_public" / "radar.py",
    ROOT / "app" / "market_data_public" / "ws_radar_chain.py",
    ROOT / "scripts" / "run_public_market_paper.py",
]


# Phase 11C MUST NOT import any third-party HTTP / WebSocket / SDK.
# The ONE permitted transport is :mod:`urllib.request` from the
# Python standard library. Phase 11C.1B (PR-B) ships the public WS
# client as a stdlib-only abstraction with an explicit message-pump
# interface. The brief says: allow Binance public / market WebSocket;
# forbid private WebSocket / user data stream / listenKey / trading
# WebSocket API. The audit therefore keeps every third-party WS
# package on the deny-list (the in-process pump + the future stdlib
# adapter cover the public surface) and a SECOND audit
# (:func:`test_no_private_websocket_artefacts`) blocks listenKey /
# user-data references in the source set.
FORBIDDEN_TOP_LEVEL_PACKAGES = {
    # Exchange SDKs
    "ccxt",
    "binance",
    "binance_connector",
    "python_binance",
    # HTTP / WebSocket clients (third party). The Phase 11C.1B WS
    # client uses the stdlib only; any deployment that wires a real
    # WS adapter MUST come through a separate review and a stdlib
    # implementation - third-party WS packages remain forbidden in
    # the Phase 11C source set.
    "aiohttp",
    "websockets",
    "websocket",
    "websocket_client",
    "requests",
    "httpx",
    "urllib3",
    # LLM clients
    "openai",
    "anthropic",
    "deepseek",
    # Third-party Telegram bot libraries.
    "python_telegram_bot",
    "telebot",
    "aiogram",
    "telegram",
}

WRITE_SURFACE_METHODS = (
    "create_order",
    "cancel_order",
    "set_leverage",
    "set_margin_mode",
)

FORBIDDEN_PARAM_FRAGMENTS = (
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
    "path", PHASE_11C_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_forbidden_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for module_name in _walk_imports(tree):
        head = module_name.split(".")[0]
        assert head not in FORBIDDEN_TOP_LEVEL_PACKAGES, (
            f"{path.relative_to(ROOT)} imports forbidden module {module_name}"
        )


@pytest.mark.parametrize(
    "path", PHASE_11C_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_write_surface_method_definitions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for fn_node in _walk_function_defs(tree):
        assert fn_node.name not in WRITE_SURFACE_METHODS, (
            f"{path.relative_to(ROOT)} defines forbidden write surface "
            f"method {fn_node.name}"
        )


@pytest.mark.parametrize(
    "path", PHASE_11C_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_write_surface_calls(path: Path):
    """No file in the Phase 11C source set may *call* any of the four
    write surfaces. The Phase 3 base class still REFUSES them; we just
    make sure no Phase 11C code attempts the call."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for call in _walk_calls(tree):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr in WRITE_SURFACE_METHODS:
                raise AssertionError(
                    f"{path.relative_to(ROOT)} calls .{call.func.attr}()"
                )


@pytest.mark.parametrize(
    "path", PHASE_11C_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_credential_parameters(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for fn_node in _walk_function_defs(tree):
        for arg in (
            list(fn_node.args.args)
            + list(fn_node.args.kwonlyargs)
            + list(fn_node.args.posonlyargs)
        ):
            lower = arg.arg.lower()
            for needle in FORBIDDEN_PARAM_FRAGMENTS:
                # The BinancePublicClient constructor accepts an
                # `api_key` / `api_secret` parameter solely so it can
                # raise SafeModeViolation when a caller hands one in.
                # That refusal-only surface is allowed.
                if path.name == "binance_public.py" and arg.arg in (
                    "api_key",
                    "api_secret",
                ):
                    continue
                # The BinancePublicWSClient constructor follows the
                # same pattern: ``api_key`` / ``api_secret`` /
                # ``listen_key`` are accepted only so the constructor
                # can refuse them with PublicWSCredentialForbidden.
                if path.name == "binance_public_ws.py" and arg.arg in (
                    "api_key",
                    "api_secret",
                    "listen_key",
                ):
                    continue
                assert needle not in lower, (
                    f"{path.relative_to(ROOT)}::{fn_node.name} accepts "
                    f"forbidden parameter {arg.arg}"
                )


@pytest.mark.parametrize(
    "path", PHASE_11C_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_credential_string_literals(path: Path):
    """No source file in the Phase 11C set may carry a concrete
    credential literal of the form ``BINANCE_API_KEY=...``."""
    blacklist = (
        "BINANCE_API_KEY=",
        "BINANCE_API_SECRET=",
        "TELEGRAM_BOT_TOKEN=",
        "DEEPSEEK_API_KEY=",
        "OPENAI_API_KEY=",
        "ANTHROPIC_API_KEY=",
    )
    text = path.read_text(encoding="utf-8")
    for needle in blacklist:
        assert needle not in text, (
            f"{path.relative_to(ROOT)} contains forbidden literal {needle}"
        )


@pytest.mark.parametrize(
    "path", PHASE_11C_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_environment_variable_reads(path: Path):
    """Phase 11C must NOT call ``os.environ.get(...)`` / ``os.getenv(...)``
    anywhere in the public-market source set. The Phase 11C runner
    routes env inspection through :class:`EnvGuard` (Phase 11B), which
    is allowed; the binance_public + market_data_public + runner files
    must NOT read env directly."""
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


def test_phase_11c_does_not_reference_any_signed_endpoint_path():
    """The Phase 11C source set must not embed any signed-endpoint
    path as an *executable* string literal. The allowlist + denylist
    in ``app/exchanges/binance_public.py`` is permitted; everywhere
    else must stay clear OUTSIDE of module docstrings and comments
    (which DO mention the forbidden endpoints to document the
    boundary). The check below walks the AST and inspects only
    standalone ``ast.Constant`` strings that are NOT module-level
    docstrings.
    """
    forbidden_signed_paths = (
        "/fapi/v1/order",
        "/fapi/v2/account",
        "/fapi/v2/positionRisk",
        "/fapi/v1/leverage",
        "/fapi/v1/marginType",
    )
    for path in PHASE_11C_FILES:
        if path.name == "binance_public.py":
            # That file lists them in the FORBIDDEN_PRIVATE_ENDPOINTS
            # set on purpose.
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        # Collect every string-literal ast.Constant that is NOT a
        # docstring on Module / FunctionDef / AsyncFunctionDef / ClassDef.
        docstring_nodes: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(
                node,
                (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ):
                body = list(getattr(node, "body", []))
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    docstring_nodes.add(id(body[0].value))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstring_nodes
            ):
                for needle in forbidden_signed_paths:
                    assert needle not in node.value, (
                        f"{path.relative_to(ROOT)} embeds signed endpoint "
                        f"{needle} in a non-docstring string literal"
                    )


def test_phase_11c_files_exist():
    """Sanity: the Phase 11C source set is what we expect."""
    for p in PHASE_11C_FILES:
        assert p.exists(), f"Phase 11C file missing: {p}"



# ---------------------------------------------------------------------------
# Phase 11C.1B - Private-WebSocket / listenKey / user-data audit (PR-B).
#
# The Phase 11C.1B brief allows Binance public / market WebSocket streams
# (!ticker@arr / !miniTicker@arr / !bookTicker / !markPrice@arr /
# !forceOrder@arr) and explicitly forbids:
#
#   * listenKey
#   * user data stream
#   * private WebSocket
#   * trading WebSocket API
#   * account / position / leverage / margin / order WebSocket variants
#
# The audit below blocks every executable string literal that mentions
# one of these surfaces. The Phase 11C.1B source files document the
# refusal in their docstrings; the audit therefore inspects only
# non-docstring constants.
# ---------------------------------------------------------------------------

#: Substrings that mark a private-WebSocket / user-data / trading-WS path.
#: Any executable string literal containing one of these in the Phase 11C
#: source set is refused. The Phase 11C.1B WS client carries the same
#: substrings inside :data:`FORBIDDEN_WS_TOKENS` as load-bearing data,
#: which is permitted because the file ships the ALLOWLIST and DENYLIST
#: as constants. The other Phase 11C source files have no business
#: mentioning these surfaces in code.
PRIVATE_WS_FORBIDDEN_SUBSTRINGS = (
    "listenKey",
    "userDataStream",
    "wss://stream-api",
    "/ws-api",
    "/trading-api",
    "/userDataStream",
    "/listenKey",
)


def test_no_private_websocket_artefacts():
    """The Phase 11C source set MUST NOT embed any private-WebSocket
    / user-data-stream / trading-WS path as an executable string
    literal. The audit excludes module / function / class docstrings
    so the existing safety-boundary documentation continues to hold."""
    for path in PHASE_11C_FILES:
        # Two files own load-bearing data that names the private
        # surfaces explicitly:
        #   * binance_public_ws.py owns the public-WS allowlist + the
        #     private-WS denylist (FORBIDDEN_WS_TOKENS).
        #   * binance_public.py owns the REST private-endpoint
        #     denylist (FORBIDDEN_PRIVATE_ENDPOINTS) which lists
        #     ``/fapi/v1/listenKey`` and friends so the runtime
        #     allowlist check can refuse them by exact name.
        # Every other Phase 11C file has no legitimate reason to
        # mention a private-WS surface in code.
        if path.name in {"binance_public_ws.py", "binance_public.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstring_nodes: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(
                node,
                (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ):
                body = list(getattr(node, "body", []))
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    docstring_nodes.add(id(body[0].value))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstring_nodes
            ):
                for needle in PRIVATE_WS_FORBIDDEN_SUBSTRINGS:
                    assert needle not in node.value, (
                        f"{path.relative_to(ROOT)} embeds private-WS "
                        f"surface {needle!r} in a non-docstring string "
                        "literal"
                    )
