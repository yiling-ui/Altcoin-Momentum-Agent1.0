"""Phase 9 - ExecutionFSMDriver tests (Issue #9 acceptance criteria).

Covers:
  - submit_order risk approval / rejection paths
  - reduce_only auto-resolution for reduce-only intents
  - opportunity_id propagation onto every Phase 9 event
  - learning_ready_context propagation onto every Phase 9 event
  - on_ack / on_partial_fill / on_full_fill happy path
  - partial fill recomputes risk (Spec §30.2)
  - attach_stop / on_stop_confirmed -> POSITION_OPEN
  - on_stop_failed -> ERROR_PROTECTION + protective close + P0 incident
  - trigger_exit calls Risk Engine with is_new_open=False
  - M3 + new_open is rejected; M3 + protective close passes
  - REBASE_IN_PROGRESS + new_open is rejected; protective close passes
  - market order on NEW_OPEN is refused (Spec §30.2 default)
  - SafeModeViolation construction-time refusals when safety lock has drifted
"""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from app.config.settings import Settings, get_settings
from app.core.enums import (
    Direction,
    ExchangeConnectionState,
    ExecutionState,
    IncidentLevel,
    ManipulationLevel,
    TradingMode,
)
from app.core.errors import ExecutionError, SafeModeViolation
from app.core.events import EventType
from app.database.migrations import apply_schema
from app.database.repositories import EventRepository
from app.execution.fsm import (
    ExecutionFSMDriver,
    IllegalTransition,
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
from app.learning.context import LearningReadyContext
from app.learning.identity import OpportunityIdentity
from app.risk.engine import RiskEngine


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------
class _RecordingProtectionHook:
    """Records every protection-hook call without persisting anywhere."""

    def __init__(self) -> None:
        self.opens: list[dict[str, Any]] = []
        self.entered: list[dict[str, Any]] = []
        self.exited: list[dict[str, Any]] = []

    def open_incident(
        self,
        *,
        level,
        title,
        description,
        source_module,
        symbol,
        position_id,
        payload,
    ) -> str:
        record = {
            "level": level,
            "title": title,
            "description": description,
            "source_module": source_module,
            "symbol": symbol,
            "position_id": position_id,
            "payload": payload,
        }
        self.opens.append(record)
        return f"inc_{len(self.opens):04d}"

    def enter_protection_mode(self, *, reason, source_module, symbol, payload) -> None:
        self.entered.append(
            {
                "reason": reason,
                "source_module": source_module,
                "symbol": symbol,
                "payload": payload,
            }
        )

    def exit_protection_mode(self, *, reason, source_module, symbol, payload) -> None:
        self.exited.append(
            {
                "reason": reason,
                "source_module": source_module,
                "symbol": symbol,
                "payload": payload,
            }
        )


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
        protection_hook=_RecordingProtectionHook(),
    )


def _new_open_request(
    *,
    client_order_id: str = "ord_1",
    symbol: str = "PEPEUSDT",
    qty: float = 1.0,
    limit_price: float = 100.0,
    intent: OrderIntent = OrderIntent.NEW_OPEN,
    direction: Direction = Direction.LONG,
    opportunity_id: str | None = "opp_test",
) -> OrderRequest:
    return OrderRequest(
        client_order_id=client_order_id,
        symbol=symbol,
        side=side_for_direction(direction, is_close=intent in (
            OrderIntent.LOCK_PROFIT,
            OrderIntent.FORCED_EXIT,
            OrderIntent.DISTRIBUTION_EXIT,
            OrderIntent.PROTECTIVE_CLOSE,
            OrderIntent.KILL_ALL,
        )),
        kind=OrderKind.LIMIT,
        qty=qty,
        limit_price=limit_price,
        intent=intent,
        direction=direction,
        opportunity_id=opportunity_id,
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------
def test_driver_refuses_to_construct_with_live_trading_enabled(monkeypatch, repo):
    settings = get_settings()
    object.__setattr__(settings.defaults.mode, "live_trading_enabled", True)
    try:
        risk = RiskEngine(settings=settings, event_repo=repo)
        with pytest.raises(SafeModeViolation):
            ExecutionFSMDriver(
                risk_engine=risk,
                event_repo=repo,
                settings=settings,
            )
    finally:
        object.__setattr__(settings.defaults.mode, "live_trading_enabled", False)


def test_driver_refuses_to_construct_with_exchange_live_orders(repo):
    settings = get_settings()
    object.__setattr__(settings.defaults.mode, "exchange_live_order_enabled", True)
    try:
        risk = RiskEngine(settings=settings, event_repo=repo)
        with pytest.raises(SafeModeViolation):
            ExecutionFSMDriver(
                risk_engine=risk,
                event_repo=repo,
                settings=settings,
            )
    finally:
        object.__setattr__(settings.defaults.mode, "exchange_live_order_enabled", False)


def test_driver_refuses_to_construct_when_trading_mode_not_paper(repo):
    settings = get_settings()
    object.__setattr__(settings.defaults.mode, "trading_mode", "live_limited")
    try:
        risk = RiskEngine(settings=settings, event_repo=repo)
        with pytest.raises(SafeModeViolation):
            ExecutionFSMDriver(
                risk_engine=risk,
                event_repo=repo,
                settings=settings,
            )
    finally:
        object.__setattr__(settings.defaults.mode, "trading_mode", "paper")


# ---------------------------------------------------------------------------
# Submit order - happy path
# ---------------------------------------------------------------------------
def test_submit_order_advances_idle_to_order_sent(driver: ExecutionFSMDriver):
    result = driver.submit_order(_new_open_request())
    assert result.accepted is True
    assert result.session.state is ExecutionState.ORDER_SENT
    assert driver.counters.orders_submitted == 1
    assert driver.counters.orders_rejected_by_risk == 0
    # paper ledger has the order
    order = driver.ledger.get_order("ord_1")
    assert order is not None
    assert order.exchange_order_id.startswith("paper_ord_")


def test_submit_order_writes_order_sent_event_with_opportunity_id(driver, repo):
    driver.submit_order(_new_open_request(opportunity_id="opp_alpha"))
    events = repo.list_events(event_type=EventType.ORDER_SENT)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["client_order_id"] == "ord_1"
    assert payload["opportunity_id"] == "opp_alpha"
    assert payload["intent"] == "new_open"
    # request payload is preserved end-to-end
    assert payload["request"]["margin_mode"] == "isolated"
    assert payload["request"]["reduce_only"] is False


def test_submit_order_with_learning_context_propagates_to_event(driver, repo):
    opp = OpportunityIdentity.create(
        symbol="PEPEUSDT",
        source_phase="execution_test",
        opportunity_id="opp_learning_x",
    )
    ctx = LearningReadyContext(
        opportunity=opp,
        source_phase="execution_test",
    )
    driver.submit_order(
        _new_open_request(opportunity_id="opp_learning_x"),
        learning_context=ctx,
    )
    events = repo.list_events(event_type=EventType.ORDER_SENT)
    assert len(events) == 1
    assert "learning_ready" in events[0].payload
    assert events[0].payload["learning_ready"]["opportunity"]["opportunity_id"] == "opp_learning_x"


def test_submit_order_duplicate_client_order_id_is_refused(driver: ExecutionFSMDriver):
    driver.submit_order(_new_open_request(client_order_id="dupe"))
    with pytest.raises(ExecutionError):
        driver.submit_order(_new_open_request(client_order_id="dupe"))


def test_market_order_for_new_open_is_refused(driver: ExecutionFSMDriver):
    """Spec §30.2 default: 默认禁止裸市价追单."""
    req = OrderRequest(
        client_order_id="market_open",
        symbol="PEPEUSDT",
        side=OrderSide.BUY,
        kind=OrderKind.MARKET,
        qty=1.0,
        intent=OrderIntent.NEW_OPEN,
        direction=Direction.LONG,
    )
    with pytest.raises(ExecutionError):
        driver.submit_order(req)


def test_market_order_for_protective_close_is_admissible(driver: ExecutionFSMDriver):
    """Reduce-only intents may use market orders to flatten under stress."""
    req = OrderRequest(
        client_order_id="market_close",
        symbol="PEPEUSDT",
        side=OrderSide.SELL,
        kind=OrderKind.MARKET,
        qty=1.0,
        intent=OrderIntent.FORCED_EXIT,
        direction=Direction.LONG,
        reduce_only=True,
    )
    result = driver.submit_order(req)
    assert result.accepted is True
    assert result.session.state is ExecutionState.ORDER_SENT


def test_reduce_only_intent_auto_resolves_reduce_only_flag(driver: ExecutionFSMDriver):
    req = OrderRequest(
        client_order_id="lp_close",
        symbol="PEPEUSDT",
        side=OrderSide.SELL,
        kind=OrderKind.LIMIT,
        qty=0.5,
        limit_price=110.0,
        intent=OrderIntent.LOCK_PROFIT,
        direction=Direction.LONG,
        reduce_only=False,  # caller forgot
    )
    result = driver.submit_order(req)
    assert result.accepted is True
    # The request stored on the session reflects the auto-resolved flag.
    assert result.session.request.reduce_only is True


# ---------------------------------------------------------------------------
# Submit order - risk rejection
# ---------------------------------------------------------------------------
def test_submit_order_rejected_by_risk_reverts_to_idle(driver: ExecutionFSMDriver, repo):
    """A rejected open does not leave the session in RISK_CHECKED."""
    result = driver.submit_order(
        _new_open_request(client_order_id="ord_attack_m3"),
        manipulation_level=ManipulationLevel.M3,
        attack_intent=False,
    )
    assert result.accepted is False
    assert "manipulation_m3" in result.reasons
    # No paper order was recorded.
    assert driver.ledger.get_order("ord_attack_m3") is None
    # Both RISK_REJECTED and ORDER_SENT? Should only see RISK_REJECTED, no ORDER_SENT.
    sent = repo.list_events(event_type=EventType.ORDER_SENT)
    assert len(sent) == 0


def test_submit_order_for_protective_close_under_m3_passes(driver: ExecutionFSMDriver):
    """Phase 7 protective-exit caveat: M3 must not block reduce-only paths."""
    req = OrderRequest(
        client_order_id="m3_close",
        symbol="PEPEUSDT",
        side=OrderSide.SELL,
        kind=OrderKind.MARKET,
        qty=1.0,
        intent=OrderIntent.FORCED_EXIT,
        direction=Direction.LONG,
        reduce_only=True,
    )
    result = driver.submit_order(req, manipulation_level=ManipulationLevel.M3)
    assert result.accepted is True


def test_submit_order_under_data_degraded_protective_close_passes(driver):
    req = OrderRequest(
        client_order_id="degraded_close",
        symbol="PEPEUSDT",
        side=OrderSide.SELL,
        kind=OrderKind.MARKET,
        qty=1.0,
        intent=OrderIntent.PROTECTIVE_CLOSE,
        direction=Direction.LONG,
        reduce_only=True,
    )
    result = driver.submit_order(
        req,
        is_data_degraded=True,
        exchange_connection_state=ExchangeConnectionState.DEGRADED,
    )
    assert result.accepted is True


def test_submit_order_under_rebase_in_progress_protective_close_passes(driver, repo):
    """Phase 8 hard rule: REBASE_IN_PROGRESS blocks new opens but NOT exits."""

    class _FakeCapital:
        is_rebase_in_progress = True
        trading_capital = 100.0
        initial_capital = 100.0

    driver._risk.set_capital_flow_engine(_FakeCapital())  # noqa: SLF001
    try:
        # New open is rejected.
        new_open = driver.submit_order(_new_open_request(client_order_id="ord_new_rebase"))
        assert new_open.accepted is False
        assert "rebase_in_progress" in new_open.reasons

        # Protective close is approved.
        req = OrderRequest(
            client_order_id="rebase_close",
            symbol="PEPEUSDT",
            side=OrderSide.SELL,
            kind=OrderKind.MARKET,
            qty=1.0,
            intent=OrderIntent.PROTECTIVE_CLOSE,
            direction=Direction.LONG,
            reduce_only=True,
        )
        result = driver.submit_order(req)
        assert result.accepted is True
    finally:
        driver._risk.set_capital_flow_engine(None)  # noqa: SLF001


# ---------------------------------------------------------------------------
# Lifecycle: ack / fill / stop / position
# ---------------------------------------------------------------------------
def test_full_lifecycle_writes_every_phase9_event(driver: ExecutionFSMDriver, repo):
    session = driver.simulate_paper_lifecycle(
        _new_open_request(),
        fill_price=100.0,
        stop_price=98.0,
    )
    assert session.state is ExecutionState.POSITION_OPEN
    types = {e.event_type for e in repo.list_events()}
    for required in (
        EventType.ORDER_SENT,
        EventType.ORDER_ACK,
        EventType.ORDER_FILLED,
        EventType.STOP_SENT,
        EventType.STOP_CONFIRMED,
        EventType.POSITION_OPENED,
    ):
        assert required in types, f"missing {required}"


def test_partial_fill_recomputes_risk_on_each_step(driver: ExecutionFSMDriver, repo):
    """Spec §30.2 hard rule: 部分成交必须重算风险."""
    result = driver.submit_order(_new_open_request())
    session = result.session
    driver.on_ack(session=session, ack_id="ack_1")
    # Two partial fills + one full fill.
    risk_decisions = repo.count_events(event_type=EventType.RISK_APPROVED)
    driver.on_partial_fill(
        session=session,
        fill=FillEvent(fill_qty=0.3, fill_price=100.0, fill_id="f1"),
    )
    driver.on_partial_fill(
        session=session,
        fill=FillEvent(fill_qty=0.3, fill_price=100.5, fill_id="f2"),
    )
    new_risk_decisions = repo.count_events(event_type=EventType.RISK_APPROVED)
    assert new_risk_decisions - risk_decisions == 2
    # avg fill VWAP is correct
    assert session.avg_fill_price == pytest.approx((0.3 * 100 + 0.3 * 100.5) / 0.6)


def test_partial_fill_event_payload_includes_filled_qty_total(driver, repo):
    result = driver.submit_order(_new_open_request())
    session = result.session
    driver.on_ack(session=session)
    driver.on_partial_fill(
        session=session,
        fill=FillEvent(fill_qty=0.5, fill_price=100.0, fill_id="f1"),
    )
    pf = repo.list_events(event_type=EventType.ORDER_PARTIAL_FILLED)
    assert len(pf) == 1
    assert pf[0].payload["filled_qty_total"] == pytest.approx(0.5)
    assert pf[0].payload["remaining_qty"] == pytest.approx(0.5)


def test_full_fill_consumes_remaining_qty_and_writes_order_filled(driver, repo):
    result = driver.submit_order(_new_open_request())
    session = result.session
    driver.on_ack(session=session)
    driver.on_partial_fill(
        session=session,
        fill=FillEvent(fill_qty=0.5, fill_price=100.0, fill_id="f1"),
    )
    driver.on_full_fill(
        session=session,
        fill=FillEvent(fill_qty=0.5, fill_price=100.0, fill_id="f2"),
    )
    assert session.state is ExecutionState.FULL_FILLED
    assert driver.ledger.get_order(session.client_order_id) is None
    assert repo.count_events(event_type=EventType.ORDER_FILLED) == 1


def test_full_fill_size_must_match_remaining(driver: ExecutionFSMDriver):
    result = driver.submit_order(_new_open_request())
    session = result.session
    driver.on_ack(session=session)
    with pytest.raises(ExecutionError):
        driver.on_full_fill(
            session=session,
            fill=FillEvent(fill_qty=0.4, fill_price=100.0, fill_id="f1"),
        )


# ---------------------------------------------------------------------------
# Stop attachment + ERROR_PROTECTION
# ---------------------------------------------------------------------------
def test_attach_stop_emits_stop_sent_with_reduce_only(driver, repo):
    result = driver.submit_order(_new_open_request())
    session = result.session
    driver.on_ack(session=session)
    driver.on_full_fill(
        session=session,
        fill=FillEvent(fill_qty=1.0, fill_price=100.0, fill_id="f1"),
    )
    stop = driver.attach_stop(session=session, stop_price=98.0)
    assert stop.reduce_only is True
    sent = repo.list_events(event_type=EventType.STOP_SENT)
    assert len(sent) == 1
    assert sent[0].payload["stop"]["reduce_only"] is True


def test_on_stop_failed_drives_error_protection_and_p0_incident(driver, repo):
    """Spec §30.3: 止损挂不上 -> 立即保护平仓."""
    hook = driver._protection_hook  # noqa: SLF001
    result = driver.submit_order(_new_open_request())
    session = result.session
    driver.on_ack(session=session)
    driver.on_full_fill(
        session=session,
        fill=FillEvent(fill_qty=1.0, fill_price=100.0, fill_id="f1"),
    )
    driver.attach_stop(session=session, stop_price=98.0)

    driver.on_stop_failed(session=session, reason="exchange_rejected")

    assert session.state is ExecutionState.ERROR_PROTECTION
    assert session.in_protection_mode is True
    # The hook saw the open_incident call with P0.
    assert any(o["level"] is IncidentLevel.P0 for o in hook.opens)
    assert any(e["reason"].startswith("stop_failed:") for e in hook.entered)
    # Phase 9 events: STOP_FAILED + PROTECTION_MODE_ENTERED.
    assert repo.count_events(event_type=EventType.STOP_FAILED) == 1
    assert repo.count_events(event_type=EventType.PROTECTION_MODE_ENTERED) == 1


def test_stop_confirmed_writes_position_opened_with_paper_position(driver, repo):
    result = driver.submit_order(_new_open_request())
    session = result.session
    driver.on_ack(session=session)
    driver.on_full_fill(
        session=session,
        fill=FillEvent(fill_qty=1.0, fill_price=100.0, fill_id="f1"),
    )
    stop = driver.attach_stop(session=session, stop_price=98.0)
    pos_id = driver.on_stop_confirmed(session=session, stop=stop)
    assert session.state is ExecutionState.POSITION_OPEN
    assert pos_id.startswith("paper_pos_")
    assert driver.ledger.get_position(pos_id) is not None
    opened = repo.list_events(event_type=EventType.POSITION_OPENED)
    assert len(opened) == 1
    assert opened[0].payload["position"]["margin_mode"] == "isolated"
    assert opened[0].payload["position"]["stop_confirmed"] is True
    # opportunity_id is propagated.
    assert opened[0].payload["opportunity_id"] == "opp_test"


# ---------------------------------------------------------------------------
# Exit path
# ---------------------------------------------------------------------------
def test_trigger_exit_calls_risk_with_is_new_open_false(driver, repo):
    """The reduce-only closing flow must NOT be blocked by M3."""
    session = driver.simulate_paper_lifecycle(
        _new_open_request(),
        stop_price=98.0,
    )
    driver.trigger_exit(
        session=session,
        reason="lock_profit",
        manipulation_level=ManipulationLevel.M3,
        is_data_degraded=True,
    )
    assert session.state is ExecutionState.POSITION_CLOSING
    driver.on_position_closed(session=session, realized_pnl=5.0)
    assert session.state is ExecutionState.IDLE
    assert session.realized_pnl == 5.0
    assert repo.count_events(event_type=EventType.EXIT_TRIGGERED) == 1
    closed = repo.list_events(event_type=EventType.POSITION_CLOSED)
    assert len(closed) == 1
    assert closed[0].payload["realized_pnl"] == 5.0


def test_protective_exit_under_m3_does_not_open_incident(driver):
    """trigger_exit on a healthy POSITION_OPEN does not fire ERROR_PROTECTION."""
    hook = driver._protection_hook  # noqa: SLF001
    session = driver.simulate_paper_lifecycle(
        _new_open_request(),
        stop_price=98.0,
    )
    pre_open_count = len(hook.opens)
    driver.trigger_exit(
        session=session,
        reason="m3_protective",
        manipulation_level=ManipulationLevel.M3,
    )
    driver.on_position_closed(session=session)
    assert len(hook.opens) == pre_open_count


# ---------------------------------------------------------------------------
# enter_error_protection / exit_protection_mode
# ---------------------------------------------------------------------------
def test_enter_error_protection_writes_protection_mode_entered(driver, repo):
    result = driver.submit_order(_new_open_request())
    session = result.session
    driver.enter_error_protection(
        session=session,
        reason="manual_test",
        incident_level=IncidentLevel.P0,
    )
    assert session.state is ExecutionState.ERROR_PROTECTION
    pme = repo.list_events(event_type=EventType.PROTECTION_MODE_ENTERED)
    assert len(pme) == 1
    assert pme[0].payload["reason"] == "manual_test"


def test_exit_protection_mode_returns_to_idle(driver, repo):
    result = driver.submit_order(_new_open_request())
    session = result.session
    driver.enter_error_protection(session=session, reason="manual")
    driver.exit_protection_mode(session=session, reason="operator_resume")
    assert session.state is ExecutionState.IDLE
    assert session.in_protection_mode is False
    assert repo.count_events(event_type=EventType.PROTECTION_MODE_EXITED) == 1


def test_exit_protection_mode_refuses_when_not_in_error_state(driver):
    result = driver.submit_order(_new_open_request())
    session = result.session
    with pytest.raises(IllegalTransition):
        driver.exit_protection_mode(session=session, reason="too_early")
