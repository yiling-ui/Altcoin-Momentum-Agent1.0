"""Phase 11B - source-tree audit (Issue #11B).

AST scan of ``app/paper_run/`` and ``scripts/run_paper_cloud.py``
enforces the Phase 11B boundary at the source-tree level so a
future maintainer cannot silently weaken it:

  - No HTTP / WebSocket / exchange / LLM / third-party Telegram bot
    library imports.
  - No write-surface method DEFINITIONS or CALLS
    (``create_order`` / ``cancel_order`` / ``set_leverage`` /
    ``set_margin_mode``). Note that the supervisor calls
    :meth:`ExchangeClientBase.assert_read_only` which exercises the
    refusal probe; that is allowed because it is the read-only
    check, not a real write surface.
  - No ``api_key`` / ``api_secret`` / ``bot_token`` parameter or
    concrete env-var literal. The bare env-var NAMES (e.g.
    ``BINANCE_API_KEY``) appear only inside
    ``app/paper_run/config.py`` as a default tuple of inspected
    names; they are NEVER read for value.
  - No ``os.environ.get(...)`` call EXCEPT in
    ``app/paper_run/env_guard.py``, which is the only file allowed
    to inspect the process environment - and even there only for
    PRESENCE checks (the value is never read).
  - No second EventRepository write-surface on a database other
    than events.db / incidents.db / capital.db (the three Phase 9 +
    Phase 11B persisters).
  - No live transport configured by default; the boot path uses
    :class:`FakeTelegramClient` and :class:`FakeLLMClient`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

PHASE_11B_PACKAGE = ROOT / "app" / "paper_run"
PHASE_11B_SCRIPT = ROOT / "scripts" / "run_paper_cloud.py"

PHASE_11B_FILES = [
    *PHASE_11B_PACKAGE.rglob("*.py"),
    PHASE_11B_SCRIPT,
]


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
    # Third-party Telegram bot libraries.
    "python_telegram_bot",
    "telebot",
    "aiogram",
    # The bare 'telegram' import is the PyPI namespace for the
    # python-telegram-bot SDK. Phase 11B does NOT need it because the
    # supervisor uses :class:`FakeTelegramClient` from app.telegram.outbound.
    "telegram",
}

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

WRITE_SURFACE_METHODS = (
    "create_order",
    "cancel_order",
    "set_leverage",
    "set_margin_mode",
)

# Files allowed to call ``os.environ.get(...)`` etc. The Phase 11B
# brief explicitly requires the env-guard to inspect a closed list of
# environment variable NAMES; only env_guard.py is allowed to do this.
ENV_READ_ALLOWED = {
    str(PHASE_11B_PACKAGE / "env_guard.py"),
}


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
    "path", PHASE_11B_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_forbidden_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for module_name in _walk_imports(tree):
        head = module_name.split(".")[0]
        assert head not in FORBIDDEN_IMPORTS, (
            f"{path.relative_to(ROOT)} imports forbidden module {module_name}"
        )


@pytest.mark.parametrize(
    "path", PHASE_11B_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_write_surface_method_definitions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for fn_node in _walk_function_defs(tree):
        assert fn_node.name not in WRITE_SURFACE_METHODS, (
            f"{path.relative_to(ROOT)} defines forbidden write surface "
            f"method {fn_node.name}"
        )


@pytest.mark.parametrize(
    "path", PHASE_11B_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_write_surface_calls(path: Path):
    """No file under ``app/paper_run/`` may call any of the four
    write surfaces. The supervisor uses
    :meth:`ExchangeClientBase.assert_read_only` which probes them
    and expects :class:`SafeModeViolation`; the calls happen INSIDE
    :func:`assert_paper_cloud_safety` via ``getattr(client, fn_name)()``,
    not as a direct attribute access. AST scan would not flag those
    indirect calls anyway."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for call in _walk_calls(tree):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr in WRITE_SURFACE_METHODS:
                raise AssertionError(
                    f"{path.relative_to(ROOT)} calls .{call.func.attr}()"
                )


@pytest.mark.parametrize(
    "path", PHASE_11B_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_api_key_parameter_or_secret_literal(path: Path):
    """No function parameter may be named ``api_key`` / ``api_secret``
    / ``bot_token`` etc. No string literal may contain a credential
    pattern with a trailing ``=`` (e.g. ``BINANCE_API_KEY=...``).

    The bare env-var NAMES (``BINANCE_API_KEY``, ``TELEGRAM_BOT_TOKEN``)
    appear only inside ``app/paper_run/config.py`` as a list of
    inspected names; the env-guard reads them as DICT KEYS only. We
    forbid the form with a trailing ``=`` because that is the
    canonical ``.env`` line format which would imply a value is
    being embedded."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for fn_node in _walk_function_defs(tree):
        for arg in (
            list(fn_node.args.args)
            + list(fn_node.args.kwonlyargs)
            + list(fn_node.args.posonlyargs)
        ):
            lower = arg.arg.lower()
            for needle in FORBIDDEN_PARAM_FRAGMENTS:
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
    "path", PHASE_11B_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_environment_variable_reads_outside_env_guard(path: Path):
    """No file under ``app/paper_run/`` may call ``os.environ.get(...)``
    EXCEPT :file:`app/paper_run/env_guard.py`. The env-guard checks
    PRESENCE of a closed list of env-var names; it never logs a
    value."""
    if str(path) in ENV_READ_ALLOWED:
        return
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
    "path", PHASE_11B_FILES, ids=lambda p: str(p.relative_to(ROOT))
)
def test_no_other_db_connect(path: Path):
    """Phase 11B writes only via the existing :class:`EventRepository`
    + :class:`IncidentRepository`. It must NOT open any other
    database file directly."""
    forbidden_dbs = (
        "trades.db",
        "positions.db",
        "market.db",
        "orders.db",
        "reflection.db",
        "llm_cache.db",
    )
    text = path.read_text(encoding="utf-8")
    for needle in forbidden_dbs:
        assert (
            f"sqlite3.connect({needle!r})" not in text
        ), f"{path.relative_to(ROOT)} opens {needle} directly"


def test_phase11b_files_exist():
    """Sanity: the Phase 11B layout is what we expect."""
    expected = {
        "__init__.py",
        "config.py",
        "daily_report.py",
        "env_guard.py",
        "export_scheduler.py",
        "incident_drill.py",
        "safety_assert.py",
        "supervisor.py",
    }
    actual = {p.name for p in PHASE_11B_PACKAGE.glob("*.py")}
    missing = expected - actual
    assert not missing, f"Phase 11B package files missing: {missing}"
    assert PHASE_11B_SCRIPT.exists(), "scripts/run_paper_cloud.py missing"


def test_phase11b_supervisor_does_not_import_real_telegram_or_llm_transport():
    """The supervisor must wire ``FakeTelegramClient`` + use the
    Phase 10C ``LLMGuardedInterpreter`` short-circuit. It must NOT
    instantiate ``TelegramHttpClient`` (refusal-only skeleton) or
    ``DeepSeekClient`` (refusal-only skeleton)."""
    text = (PHASE_11B_PACKAGE / "supervisor.py").read_text(encoding="utf-8")
    # The supervisor MAY import these names for type-checking, but it
    # must not instantiate them. We use a coarse substring match here -
    # the AST-aware guard above blocks any forbidden import already.
    assert "TelegramHttpClient(" not in text, (
        "Supervisor must not instantiate TelegramHttpClient"
    )
    assert "DeepSeekClient(" not in text, (
        "Supervisor must not instantiate DeepSeekClient"
    )
    # Sanity - the supervisor MUST instantiate the fake transports.
    assert "FakeTelegramClient(" in text


def test_phase11b_run_paper_cloud_script_does_not_call_write_surface():
    """The CLI script must not call any write surface either."""
    text = PHASE_11B_SCRIPT.read_text(encoding="utf-8")
    for surface in WRITE_SURFACE_METHODS:
        assert f".{surface}(" not in text, (
            f"scripts/run_paper_cloud.py calls .{surface}()"
        )


def test_phase11b_event_emission_does_not_invent_new_event_types():
    """Phase 11B must NOT define any new EventType. Every audit row
    fits inside the Phase 1 - 10D vocabulary - the supervisor reuses
    the existing surfaces (Risk Engine, Reconciler, Capital Flow,
    Execution FSM, Telegram dispatcher, Export bridge)."""
    import re

    pattern = re.compile(r"EventType\.([A-Z0-9_]+)")
    paper_run_text = " ".join(
        p.read_text(encoding="utf-8") for p in PHASE_11B_FILES
    )
    paper_run_event_types = set(pattern.findall(paper_run_text))
    # Phase 11B paper_run code never invents a new EventType. The set
    # below is the closed list it MAY reference (read-only counters /
    # filters).
    allowed_phase_11b_references = {
        # Capital flow events - read by daily report aggregator
        "CAPITAL_DEPOSIT",
        "CAPITAL_WITHDRAWAL",
        "PROFIT_HARVEST",
        "CAPITAL_REBASE",
        "RISK_BUDGET_RECALCULATED",
        # Risk Engine events
        "RISK_APPROVED",
        "RISK_REJECTED",
        # State Machine
        "STATE_TRANSITION",
        # Execution FSM
        "ORDER_SENT",
        "ORDER_ACK",
        "ORDER_PARTIAL_FILLED",
        "ORDER_FILLED",
        "ORDER_CANCELLED",
        "STOP_SENT",
        "STOP_CONFIRMED",
        "STOP_FAILED",
        "POSITION_OPENED",
        "POSITION_UPDATED",
        "POSITION_CLOSED",
        "EXIT_TRIGGERED",
        # Reconciliation
        "RECONCILIATION_STARTED",
        "RECONCILIATION_MISMATCH",
        "RECONCILIATION_RESOLVED",
        # Incidents / protection mode
        "INCIDENT_OPENED",
        "INCIDENT_RESOLVED",
        "PROTECTION_MODE_ENTERED",
        "PROTECTION_MODE_EXITED",
        # LLM
        "LLM_INTERPRETED",
        "LLM_DEGRADED",
        "LLM_SCHEMA_REJECTED",
        # Telegram
        "TELEGRAM_COMMAND_RECEIVED",
        "TELEGRAM_COMMAND_REJECTED",
        "TELEGRAM_MESSAGE_SENT",
        "TELEGRAM_SEND_FAILED",
        "DATA_EXPORT_GENERATED",
        "DATA_EXPORT_FAILED",
        # Misc
        "MARKET_SNAPSHOT",
        "DATA_UNRELIABLE",
        "OPPORTUNITY_GRADED",
        # Phase 11C.1A - rate-limit governor read-only references in
        # the daily report aggregator. The aggregator counts these
        # event types but never emits them; emission lives in
        # app/exchanges/binance_rate_limit.py which is NOT a
        # paper_run file.
        "RATE_LIMIT_429",
        "RATE_LIMIT_418",
        "RATE_LIMIT_BACKOFF_STARTED",
        "RATE_LIMIT_BACKOFF_ENDED",
        "RATE_LIMIT_PROTECTION_ENTERED",
        # Phase 11C.1B - public WebSocket lifecycle read-only
        # references in the daily report aggregator. The aggregator
        # cross-checks event-log counts against the WS client's
        # metrics_payload; emission lives in
        # app/exchanges/binance_public_ws.py which is NOT a
        # paper_run file.
        "PUBLIC_WS_CONNECTED",
        "PUBLIC_WS_DISCONNECTED",
        "PUBLIC_WS_STALE",
        # Phase 11C.1C-A - adaptive candidate regime / strategy
        # selector read-only references in the daily report
        # aggregator. The aggregator counts these event types as a
        # cross-check against the WSRadarChainDriver's runner-side
        # ``adaptive_metrics_payload``; emission lives in
        # app/market_data_public/ws_radar_chain.py which is NOT a
        # paper_run file. None of these events authorise a real
        # trade; the strategy_mode field is paper / virtual only.
        "MARKET_REGIME_ASSESSED",
        "CANDIDATE_STAGE_CLASSIFIED",
        "OPPORTUNITY_SCORED",
        "STRATEGY_MODE_SELECTED",
        "CLUSTER_CONTEXT_ATTACHED",
        "LABEL_QUEUE_ENQUEUED",
        # Phase 11C.1C-C-A - MFE / MAE Label Queue Runtime + tail
        # outcome tracking. Emission lives in
        # app/adaptive/label_runtime.py; the paper_run daily-report
        # builder counts these events as a cross-check against the
        # runtime's runner-side ``metrics_payload``. None of these
        # events authorise a real trade; the runtime is paper /
        # virtual only.
        "LABEL_TRACKING_STARTED",
        "LABEL_WINDOW_UPDATED",
        "LABEL_WINDOW_COMPLETED",
        "TAIL_LABEL_ASSIGNED",
        "MISSED_TAIL_DETECTED",
        "FAKE_BREAKOUT_DETECTED",
        # Phase 11C.1C-C-B-A - Strategy Validation Lab v0 & Cluster
        # Exposure Control Contracts. Emission lives in
        # app/adaptive/strategy_validation_runtime.py; the paper_run
        # daily-report builder counts these events as a cross-check
        # against the runtime's runner-side ``metrics_payload``.
        # None of these events authorise a real trade; the runtime
        # is paper / report only and the
        # ``suggested_cluster_action`` field is descriptive
        # (``leader_only`` / ``observe_followers`` /
        # ``reject_cluster`` / ``no_action``). The Risk Engine
        # remains the single trade-decision gate.
        "STRATEGY_VALIDATION_SAMPLE_CREATED",
        "STRATEGY_VALIDATION_REPORT_GENERATED",
        "STRATEGY_MODE_VALIDATED",
        "CANDIDATE_STAGE_VALIDATED",
        "SCORE_BUCKET_VALIDATED",
        "CLUSTER_EXPOSURE_ASSESSED",
        "CLUSTER_LEADER_VALIDATED",
        # Phase 11C.1C-C-B-B-A - Strategy Validation Dataset Builder
        # & Quality Gate v0. Emission lives in
        # app/adaptive/strategy_validation_runtime.py; the paper_run
        # daily-report builder counts these events as a cross-check
        # against the runtime's runner-side ``metrics_payload``.
        # None of these events authorise a real trade; the
        # ``gate_status`` field is descriptive (``pass`` / ``warn``
        # / ``fail``) and **MUST NEVER trigger a real trade**. The
        # Risk Engine remains the single trade-decision gate.
        "STRATEGY_VALIDATION_DATASET_BUILT",
        "STRATEGY_VALIDATION_DATASET_EXPORTED",
        "STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED",
    }
    invented = paper_run_event_types - allowed_phase_11b_references
    assert not invented, (
        f"Phase 11B references unexpected EventType values: {invented}"
    )
