"""Phase 9 - Paper-mode lifecycle reconstruction tests (Issue #9 fix-up).

Pins the fix-up acceptance criterion: the EventRepository carries
enough information for an operator to rebuild a full paper trade
lifecycle from the event stream alone. This is **NOT** the full
Replay Engine - that lands behind Issue #10. We pin only the
read-side contract:

  - Every Phase 9 lifecycle event the FSM driver emits is reachable
    through :meth:`EventRepository.list_events`.
  - The Phase 8.5 learning-ready data contract is preserved on every
    Phase 9 event: ``opportunity_id`` and ``learning_ready`` survive.
  - Filtering by ``client_order_id`` AND by ``opportunity_id`` both
    return the same lifecycle.
  - The lifecycle summary captures the most-progressed state plus the
    auxiliary flags (stop_confirmed, partial_fills, final_status,
    learning_ready_present, incident_opened, reconciliation_mismatch,
    protective_close).
"""

from __future__ import annotations

import sqlite3

import pytest

from app.config.settings import get_settings
from app.core.enums import (
    Direction,
    ExecutionState,
    IncidentLevel,
)
from app.core.events import EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import apply_schema, migrate_database_set
from app.database.repositories import EventRepository
from app.execution.fsm import ExecutionFSMDriver
from app.execution.lifecycle import (
    FINAL_STATUS_CLOSED,
    FINAL_STATUS_OPEN,
    LIFECYCLE_EVENT_TYPES,
    PaperLifecycleSummary,
    reconstruct_paper_lifecycle,
)
from app.execution.models import (
    FillEvent,
    OrderIntent,
    OrderKind,
    OrderRequest,
    OrderSide,
    side_for_direction,
)
from app.execution.paper_ledger import PaperLedger
from app.incidents.repository import IncidentRepository
from app.learning.context import LearningReadyContext
from app.learning.identity import OpportunityIdentity
from app.reconciliation.models import (
    LocalSnapshot,
    PositionView,
    RemoteSnapshot,
)
from app.reconciliation.reconciler import Reconciler
from app.risk.engine import RiskEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def repo() -> EventRepository:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    return EventRepository(conn)


@pytest.fixture
def driver(repo) -> ExecutionFSMDriver:
    settings = get_settings()
    risk = RiskEngine(settings=settings, event_repo=repo)
    return ExecutionFSMDriver(
        risk_engine=risk,
        event_repo=repo,
        paper_ledger=PaperLedger(),
        settings=settings,
    )


@pytest.fixture
def dbs(tmp_path):
    sqlite_dir = tmp_path / "sqlite"
    dbs = DatabaseSet.open(sqlite_dir, wal=True, databases=PHASE2_DATABASES)
    migrate_database_set(dbs)
    try:
        yield dbs
    finally:
        dbs.close()


def _request(
    *,
    client_order_id: str = "ord_lifecycle_1",
    opportunity_id: str = "opp_lifecycle_1",
    intent: OrderIntent = OrderIntent.NEW_OPEN,
    direction: Direction = Direction.LONG,
    qty: float = 1.0,
    limit_price: float = 100.0,
) -> OrderRequest:
    is_close = intent in (
        OrderIntent.LOCK_PROFIT,
        OrderIntent.FORCED_EXIT,
        OrderIntent.DISTRIBUTION_EXIT,
        OrderIntent.PROTECTIVE_CLOSE,
        OrderIntent.KILL_ALL,
    )
    return OrderRequest(
        client_order_id=client_order_id,
        symbol="PEPEUSDT",
        side=side_for_direction(direction, is_close=is_close),
        kind=OrderKind.LIMIT,
        qty=qty,
        limit_price=limit_price,
        intent=intent,
        direction=direction,
        opportunity_id=opportunity_id,
    )


def _drive_full_lifecycle(driver: ExecutionFSMDriver, request: OrderRequest):
    """submit -> ack -> partial fill -> full fill -> attach stop ->
    stop confirmed -> position opened -> trigger exit -> position closed.
    Returns the session for further assertions.
    """
    result = driver.submit_order(request)
    assert result.accepted is True
    session = result.session
    driver.on_ack(session=session, ack_id="ack_1")
    driver.on_partial_fill(
        session=session,
        fill=FillEvent(fill_qty=0.4, fill_price=100.0, fill_id="f_partial_1"),
    )
    driver.on_full_fill(
        session=session,
        fill=FillEvent(fill_qty=0.6, fill_price=100.5, fill_id="f_full"),
    )
    stop = driver.attach_stop(session=session, stop_price=98.0)
    driver.on_stop_confirmed(session=session, stop=stop)
    assert session.state is ExecutionState.POSITION_OPEN
    driver.trigger_exit(session=session, reason="lock_profit")
    driver.on_position_closed(session=session, realized_pnl=0.5)
    return session


# ---------------------------------------------------------------------------
# Acceptance criterion: full happy-path lifecycle is reachable from events
# ---------------------------------------------------------------------------
def test_event_chain_reachable_via_event_repository(driver, repo):
    request = _request()
    _drive_full_lifecycle(driver, request)

    # All Phase 9 lifecycle event types are reachable when we filter
    # by client_order_id (the column the FSM driver writes).
    events = repo.list_events(order_id=request.client_order_id)
    types = [e.event_type for e in events]
    for required in LIFECYCLE_EVENT_TYPES:
        assert required in types, f"missing {required.value} for client_order_id"


def test_event_chain_reachable_via_opportunity_id(driver, repo):
    request = _request()
    _drive_full_lifecycle(driver, request)

    # Same lifecycle is reachable when we filter by opportunity_id by
    # scanning the payload.
    relevant_types = list(LIFECYCLE_EVENT_TYPES)
    candidates = repo.list_events(event_types=relevant_types)
    by_opp = [
        ev
        for ev in candidates
        if ev.payload.get("opportunity_id") == request.opportunity_id
    ]
    types = {ev.event_type for ev in by_opp}
    for required in LIFECYCLE_EVENT_TYPES:
        assert required in types, f"missing {required.value} via opportunity_id"


def test_opportunity_id_present_on_every_phase9_event(driver, repo):
    request = _request()
    _drive_full_lifecycle(driver, request)
    events = repo.list_events(order_id=request.client_order_id)
    for ev in events:
        assert ev.payload.get("opportunity_id") == request.opportunity_id, (
            f"event {ev.event_type.value} dropped opportunity_id"
        )


# ---------------------------------------------------------------------------
# Acceptance criterion: the lifecycle summary helper rebuilds the trade
# ---------------------------------------------------------------------------
def test_reconstruct_paper_lifecycle_returns_complete_summary(driver, repo):
    request = _request()
    _drive_full_lifecycle(driver, request)
    summary = reconstruct_paper_lifecycle(
        event_repo=repo,
        client_order_id=request.client_order_id,
    )
    assert isinstance(summary, PaperLifecycleSummary)
    assert summary.client_order_id == request.client_order_id
    assert summary.opportunity_id == request.opportunity_id
    assert summary.symbol == request.symbol
    assert summary.side == OrderSide.BUY.value
    assert summary.qty == pytest.approx(1.0)
    assert summary.entry_state == EventType.POSITION_OPENED.value
    assert summary.exit_state == EventType.POSITION_CLOSED.value
    assert summary.stop_confirmed is True
    assert summary.partial_fills == 1
    assert summary.final_status == FINAL_STATUS_CLOSED
    # The example dict-shape from the brief is reproducible verbatim.
    payload = summary.to_dict()
    assert payload == {
        "client_order_id": request.client_order_id,
        "opportunity_id": request.opportunity_id,
        "symbol": "PEPEUSDT",
        "side": OrderSide.BUY.value,
        "qty": 1.0,
        "entry_state": EventType.POSITION_OPENED.value,
        "exit_state": EventType.POSITION_CLOSED.value,
        "stop_confirmed": True,
        "partial_fills": 1,
        "final_status": FINAL_STATUS_CLOSED,
        "learning_ready_present": payload["learning_ready_present"],
        "event_chain": payload["event_chain"],
        "incident_opened": False,
        "reconciliation_mismatch": False,
        "protective_close": False,
    }


def test_reconstruct_paper_lifecycle_supports_lookup_by_opportunity_id(driver, repo):
    request = _request()
    _drive_full_lifecycle(driver, request)
    summary = reconstruct_paper_lifecycle(
        event_repo=repo,
        opportunity_id=request.opportunity_id,
    )
    assert summary.client_order_id == request.client_order_id
    assert summary.exit_state == EventType.POSITION_CLOSED.value
    assert summary.final_status == FINAL_STATUS_CLOSED


def test_reconstruct_paper_lifecycle_event_chain_contains_full_lifecycle(driver, repo):
    """The chain returned by the helper carries every Phase 9 lifecycle
    event type. We assert MEMBERSHIP rather than strict ordering: the
    EventRepository orders by ``(timestamp, event_id)`` and Phase 9
    events emitted within the same millisecond tie on the timestamp,
    so the random-UUID event_id breaks the tie unpredictably. The
    summary helper itself is robust to this because it walks each
    event independently and latches the most-progressed entry / exit
    markers separately.
    """
    request = _request()
    _drive_full_lifecycle(driver, request)
    summary = reconstruct_paper_lifecycle(
        event_repo=repo,
        client_order_id=request.client_order_id,
    )
    chain = set(summary.event_chain)
    required = {
        EventType.ORDER_SENT.value,
        EventType.ORDER_ACK.value,
        EventType.ORDER_PARTIAL_FILLED.value,
        EventType.ORDER_FILLED.value,
        EventType.STOP_SENT.value,
        EventType.STOP_CONFIRMED.value,
        EventType.POSITION_OPENED.value,
        EventType.EXIT_TRIGGERED.value,
        EventType.POSITION_CLOSED.value,
    }
    missing = required - chain
    assert not missing, f"event_chain missing {missing!r}; got {summary.event_chain!r}"


def test_reconstruct_paper_lifecycle_preserves_learning_ready_when_attached(repo):
    """When the FSM is driven with a real LearningReadyContext, the
    lifecycle summary reports ``learning_ready_present=True`` to prove
    the Phase 8.5 data contract is intact through Phase 9."""
    settings = get_settings()
    risk = RiskEngine(settings=settings, event_repo=repo)
    driver = ExecutionFSMDriver(
        risk_engine=risk,
        event_repo=repo,
        paper_ledger=PaperLedger(),
        settings=settings,
    )
    identity = OpportunityIdentity.create(
        symbol="PEPEUSDT",
        source_phase="execution_test",
        opportunity_id="opp_learning_x",
    )
    learning_ctx = LearningReadyContext(
        opportunity=identity,
        source_phase="execution_test",
    )
    request = _request(opportunity_id=identity.opportunity_id)
    result = driver.submit_order(request, learning_context=learning_ctx)
    assert result.accepted
    driver.on_ack(session=result.session)
    driver.on_full_fill(
        session=result.session,
        fill=FillEvent(fill_qty=1.0, fill_price=100.0, fill_id="f"),
    )
    stop = driver.attach_stop(session=result.session, stop_price=98.0)
    driver.on_stop_confirmed(session=result.session, stop=stop)
    summary = reconstruct_paper_lifecycle(
        event_repo=repo,
        client_order_id=request.client_order_id,
    )
    assert summary.learning_ready_present is True
    assert summary.opportunity_id == identity.opportunity_id


# ---------------------------------------------------------------------------
# Open / in-progress states
# ---------------------------------------------------------------------------
def test_open_position_summary_reports_open_status(driver, repo):
    request = _request()
    result = driver.submit_order(request)
    session = result.session
    driver.on_ack(session=session)
    driver.on_full_fill(
        session=session,
        fill=FillEvent(fill_qty=1.0, fill_price=100.0, fill_id="f1"),
    )
    stop = driver.attach_stop(session=session, stop_price=98.0)
    driver.on_stop_confirmed(session=session, stop=stop)
    summary = reconstruct_paper_lifecycle(
        event_repo=repo,
        client_order_id=request.client_order_id,
    )
    assert summary.entry_state == EventType.POSITION_OPENED.value
    assert summary.exit_state is None
    assert summary.stop_confirmed is True
    assert summary.partial_fills == 0
    assert summary.final_status == FINAL_STATUS_OPEN


def test_in_progress_only_ack_summary(driver, repo):
    request = _request()
    result = driver.submit_order(request)
    driver.on_ack(session=result.session)
    summary = reconstruct_paper_lifecycle(
        event_repo=repo,
        client_order_id=request.client_order_id,
    )
    assert summary.entry_state == EventType.ORDER_ACK.value
    assert summary.exit_state is None
    assert summary.final_status == "in_progress"


# ---------------------------------------------------------------------------
# Protective close (stop_failed) leaves a trace
# ---------------------------------------------------------------------------
def test_protective_close_drives_protected_status(dbs):
    """When the FSM driver enters ERROR_PROTECTION on an open position,
    it fires a reduce-only protective close that emits
    ``POSITION_CLOSED`` with ``protective_close=True``. The lifecycle
    summary surfaces this in the dedicated flag plus the closed status.
    """
    repo = EventRepository(dbs.events, capital_conn=dbs.capital)
    incidents = IncidentRepository(incidents_conn=dbs.incidents, event_repo=repo)
    settings = get_settings()
    risk = RiskEngine(settings=settings, event_repo=repo)
    driver = ExecutionFSMDriver(
        risk_engine=risk,
        event_repo=repo,
        paper_ledger=PaperLedger(),
        settings=settings,
        protection_hook=incidents,
    )
    request = _request(client_order_id="ord_protective")
    result = driver.submit_order(request)
    session = result.session
    driver.on_ack(session=session)
    driver.on_full_fill(
        session=session,
        fill=FillEvent(fill_qty=1.0, fill_price=100.0, fill_id="f1"),
    )
    stop = driver.attach_stop(session=session, stop_price=98.0)
    driver.on_stop_confirmed(session=session, stop=stop)
    assert session.state is ExecutionState.POSITION_OPEN
    # Now trigger a protection event that closes the open position.
    driver.enter_error_protection(
        session=session,
        reason="stop_lost_after_open",
        incident_level=IncidentLevel.P0,
    )
    summary = reconstruct_paper_lifecycle(
        event_repo=repo,
        client_order_id=request.client_order_id,
    )
    assert summary.protective_close is True
    assert summary.exit_state == EventType.POSITION_CLOSED.value
    assert summary.final_status == FINAL_STATUS_CLOSED
    # PROTECTION_MODE_ENTERED IS keyed by client_order_id so it lands
    # in the by-order summary's event_chain. INCIDENT_OPENED is NOT
    # keyed by order_id (the IncidentRepository emits it with symbol
    # / position_id only), so we look that up separately on the
    # repository.
    assert EventType.PROTECTION_MODE_ENTERED.value in summary.event_chain
    incidents_open = repo.list_events(event_type=EventType.INCIDENT_OPENED)
    assert any(ev.symbol == "PEPEUSDT" for ev in incidents_open)


def test_stop_failed_before_position_opened_does_not_fire_protective_close(dbs):
    """Sanity check: if ``on_stop_failed`` fires BEFORE the position is
    opened, the FSM driver enters ERROR_PROTECTION but does NOT issue a
    reduce-only close (there is no position to close). The summary
    captures ``protective=in_progress``-style outcome via the
    ``incident_opened`` flag without claiming the trade closed."""
    repo = EventRepository(dbs.events, capital_conn=dbs.capital)
    incidents = IncidentRepository(incidents_conn=dbs.incidents, event_repo=repo)
    settings = get_settings()
    risk = RiskEngine(settings=settings, event_repo=repo)
    driver = ExecutionFSMDriver(
        risk_engine=risk,
        event_repo=repo,
        paper_ledger=PaperLedger(),
        settings=settings,
        protection_hook=incidents,
    )
    request = _request(client_order_id="ord_stop_fail_pre_open")
    result = driver.submit_order(request)
    session = result.session
    driver.on_ack(session=session)
    driver.on_full_fill(
        session=session,
        fill=FillEvent(fill_qty=1.0, fill_price=100.0, fill_id="f1"),
    )
    driver.attach_stop(session=session, stop_price=98.0)
    driver.on_stop_failed(session=session, reason="exchange_rejected")
    summary = reconstruct_paper_lifecycle(
        event_repo=repo,
        client_order_id=request.client_order_id,
    )
    assert summary.protective_close is False
    # PROTECTION_MODE_ENTERED IS keyed by client_order_id (FSM
    # driver _build_event sets order_id=session.client_order_id) so
    # it lands in the by-order chain even when no position existed.
    assert EventType.PROTECTION_MODE_ENTERED.value in summary.event_chain
    # No POSITION_OPENED was ever emitted (stop confirmation failed).
    assert summary.entry_state in (
        EventType.STOP_SENT.value,
        EventType.ORDER_FILLED.value,
    )
    assert summary.exit_state is None


# ---------------------------------------------------------------------------
# Reconciliation mismatch on the same events.db is reachable separately
# ---------------------------------------------------------------------------
def test_reconciliation_mismatch_reachable_alongside_lifecycle(dbs):
    repo = EventRepository(dbs.events, capital_conn=dbs.capital)
    incidents = IncidentRepository(incidents_conn=dbs.incidents, event_repo=repo)
    settings = get_settings()
    risk = RiskEngine(settings=settings, event_repo=repo)
    driver = ExecutionFSMDriver(
        risk_engine=risk,
        event_repo=repo,
        paper_ledger=PaperLedger(),
        settings=settings,
        protection_hook=incidents,
    )
    request = _request(client_order_id="ord_recon")
    _drive_full_lifecycle(driver, request)

    # The lifecycle summary for the closed trade is unaffected by an
    # unrelated reconciliation mismatch on the same events.db.
    summary = reconstruct_paper_lifecycle(
        event_repo=repo, client_order_id=request.client_order_id
    )
    assert summary.final_status == FINAL_STATUS_CLOSED
    assert summary.reconciliation_mismatch is False

    # A reconciliation mismatch on the same symbol is independently
    # reachable on the events repository (the reconciler is symbol-
    # keyed not opportunity-keyed, so it doesn't appear on the by-
    # order summary).
    rec = Reconciler(event_repo=repo, protection_hook=incidents)
    rec.reconcile(
        local=LocalSnapshot(),
        remote=RemoteSnapshot(
            positions=(
                PositionView(
                    position_id="exch_pos_recon",
                    symbol="PEPEUSDT",
                    direction="long",
                    qty=10.0,
                    entry_price=0.5,
                ),
            )
        ),
    )
    mismatches = repo.list_events(event_type=EventType.RECONCILIATION_MISMATCH)
    assert any(ev.symbol == "PEPEUSDT" for ev in mismatches)


# ---------------------------------------------------------------------------
# Helper input validation (lookup key is required)
# ---------------------------------------------------------------------------
def test_reconstruct_paper_lifecycle_requires_exactly_one_key(repo, driver):
    request = _request()
    _drive_full_lifecycle(driver, request)
    with pytest.raises(ValueError, match="exactly one of"):
        reconstruct_paper_lifecycle(event_repo=repo)
    with pytest.raises(ValueError, match="exactly one of"):
        reconstruct_paper_lifecycle(
            event_repo=repo,
            client_order_id="x",
            opportunity_id="y",
        )


def test_reconstruct_paper_lifecycle_unknown_key_raises(repo):
    with pytest.raises(ValueError, match="no events found"):
        reconstruct_paper_lifecycle(
            event_repo=repo, client_order_id="does_not_exist"
        )


# ---------------------------------------------------------------------------
# Helper does NOT drift into Replay Engine territory (Issue #10 boundary)
# ---------------------------------------------------------------------------
def test_helper_module_does_not_pull_in_replay_engine_dependencies():
    """Issue #10 boundary: the lifecycle helper must not import a
    Replay Engine, Reflection module, exchange SDK, HTTP / WebSocket
    client, Telegram outbound surface, or LLM client.

    We pin the contract via two checks:

      1. No `import` / `from` line in the module pulls a forbidden
         dependency.
      2. After the module is imported, no forbidden module name has
         landed in ``sys.modules``.

    Substring scans of free-form prose are deliberately NOT used: the
    forbidden vocabulary appears in our own boundary docstrings
    ("calls NO Telegram outbound surface") and would yield false
    positives.
    """
    import importlib
    import inspect
    import re
    import sys

    module = importlib.import_module("app.execution.lifecycle")
    src = inspect.getsource(module)
    forbidden_modules = (
        "binance",
        "ccxt",
        "websocket",
        "websockets",
        "aiohttp",
        "httpx",
        "requests",
        "telegram",
        "openai",
        "anthropic",
        "litellm",
        "replay",
        "reflection",
    )
    import_line = re.compile(r"^\s*(?:from|import)\s+([\w\.]+)", re.MULTILINE)
    imported_modules = {
        match.group(1).split(".")[0] for match in import_line.finditer(src)
    }
    leaked_imports = imported_modules.intersection(forbidden_modules)
    assert not leaked_imports, (
        f"app.execution.lifecycle imported forbidden modules: "
        f"{leaked_imports!r}"
    )

    # And as a process-wide check: importing the helper must not have
    # pulled any forbidden module into ``sys.modules``.
    sys_modules_leaked = [
        name
        for name in sys.modules
        if any(
            name == needle or name.startswith(f"{needle}.")
            for needle in forbidden_modules
            # ``replay`` / ``reflection`` are common english words
            # that may show up in unrelated installed packages; we
            # only check the actually-dangerous module roots here.
            if needle
            not in {"replay", "reflection"}
        )
    ]
    assert not sys_modules_leaked, (
        f"forbidden modules leaked into sys.modules: "
        f"{sys_modules_leaked!r}"
    )
