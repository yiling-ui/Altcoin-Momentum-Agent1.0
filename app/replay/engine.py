"""Phase 10A Replay Engine (Issue #10 Part 1).

Read-only replay over events.db. Produces deterministic, JSON-safe
value objects for:

  - Paper trade lifecycle (Phase 9)
  - Capital flow / Capital Rebase (Phase 8)
  - Risk decisions (Phase 7 + Phase 8.5)
  - P0 / P1 incident timeline (Phase 9)
  - Trade State Machine transitions (Phase 7)
  - Telegram command audit (Phase 1, ready for Phase 10D)
  - Phase 8.5 learning-ready payload extraction
  - P0 latched-pause invariant verification (Phase 9 fix-up)

Phase 10A boundary
------------------

The Replay Engine:

  - opens NO socket
  - imports NO exchange SDK / HTTP / WebSocket / LLM client / Telegram
    bot library
  - reads NO ``os.environ``
  - defines NO ``create_order`` / ``cancel_order`` / ``set_leverage``
    / ``set_margin_mode``
  - does NOT instantiate :class:`ExecutionFSMDriver`,
    :class:`Reconciler`, :class:`RiskEngine`, :class:`CapitalFlowEngine`,
    :class:`MarketDataBuffer`, :class:`MockExchangeClient`, or any
    other state-mutating component
  - does NOT call :meth:`EventRepository.append_event` (it has no write
    surface)
  - is therefore SAFE to run against a production-grade events.db
    without any risk of mutating trading / capital / risk state

What Phase 10A does NOT ship (deferred to later parts of Issue #10):

  - LLM Guarded Interpreter (Part 10C)
  - Telegram outbound + Export commands (Part 10D)
  - Reflection Engine + mistake_tags (Part 10B)
  - Real-trade persistence into trades.db / positions.db (future PR)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from app.core.events import Event, EventType
from app.database.repositories import EventRepository
from app.execution.lifecycle import (
    PaperLifecycleSummary,
    reconstruct_paper_lifecycle,
)
from app.replay.diff import (
    DiffEntry,
    DiffKind,
    ReplayDiffReport,
    compare_event_chains,
)
from app.replay.loaders import (
    CAPITAL_FLOW_EVENT_TYPES,
    INCIDENT_LIFECYCLE_EVENT_TYPES,
    PAPER_LIFECYCLE_EVENT_TYPES,
    RECONCILIATION_EVENT_TYPES,
    RISK_DECISION_EVENT_TYPES,
    extract_learning_ready,
    has_learning_ready,
    load_capital_flow_events,
    load_events_for_order,
    load_incident_lifecycle_events,
    load_reconciliation_events,
    load_risk_decision_events,
    load_state_transition_events,
    load_telegram_command_events,
    pair_reconciliation_passes,
)


# ===========================================================================
# Replay value objects
# ===========================================================================
@dataclass(frozen=True)
class PaperTradeReplay:
    """One paper trade, fully reconstructed from events.db.

    Phase 10A reuses the existing :func:`reconstruct_paper_lifecycle`
    helper as the source of truth for the most-progressed marker, then
    layers a :class:`ReplayDiffReport` on top by comparing the observed
    event chain against the canonical Phase 9 happy-path ordering.

    The trade is identified by either ``client_order_id`` or
    ``opportunity_id``.
    """

    client_order_id: str | None
    opportunity_id: str | None
    summary: PaperLifecycleSummary
    events: tuple[Event, ...]
    diff_against_canonical: ReplayDiffReport
    learning_ready_event_count: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "client_order_id": self.client_order_id,
            "opportunity_id": self.opportunity_id,
            "summary": self.summary.to_dict(),
            "event_count": len(self.events),
            "diff_against_canonical": self.diff_against_canonical.to_payload(),
            "learning_ready_event_count": self.learning_ready_event_count,
        }


@dataclass(frozen=True)
class CapitalRebaseReplay:
    """One capital rebase reconstructed from events.db.

    Built from a ``CAPITAL_REBASE`` event plus the surrounding
    ``CAPITAL_DEPOSIT`` / ``CAPITAL_WITHDRAWAL`` / ``PROFIT_HARVEST`` /
    ``RISK_BUDGET_RECALCULATED`` events that share the same trigger
    timestamp window. Phase 10A keeps the window narrow: the
    immediately-preceding non-rebase capital event up to the
    rebase's own ``RISK_BUDGET_RECALCULATED`` follower.
    """

    rebase_event: Event
    trigger: str
    related_events: tuple[Event, ...]
    previous_exchange_equity: float | None
    new_exchange_equity: float | None
    previous_lifetime_account_value: float | None
    new_lifetime_account_value: float | None
    previous_net_trading_pnl: float | None
    new_net_trading_pnl: float | None
    previous_risk_budget: float | None
    new_risk_budget: float | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "rebase_event_id": self.rebase_event.event_id,
            "rebase_timestamp": int(self.rebase_event.timestamp),
            "trigger": self.trigger,
            "related_event_count": len(self.related_events),
            "related_event_types": [
                ev.event_type.value for ev in self.related_events
            ],
            "previous_exchange_equity": self.previous_exchange_equity,
            "new_exchange_equity": self.new_exchange_equity,
            "previous_lifetime_account_value": self.previous_lifetime_account_value,
            "new_lifetime_account_value": self.new_lifetime_account_value,
            "previous_net_trading_pnl": self.previous_net_trading_pnl,
            "new_net_trading_pnl": self.new_net_trading_pnl,
            "previous_risk_budget": self.previous_risk_budget,
            "new_risk_budget": self.new_risk_budget,
        }


@dataclass(frozen=True)
class RiskDecisionReplay:
    """One Risk Engine decision (RISK_APPROVED or RISK_REJECTED).

    Phase 8.5 may attach a ``learning_ready`` block; Phase 10A reads
    it back without interpretation.
    """

    event: Event
    approved: bool
    reasons: tuple[str, ...]
    no_trade_gate_reasons: tuple[str, ...]
    manipulation_level: str | None
    trade_confirmation_level: str | None
    account_tier: str | None
    regime: str | None
    risk_permission: str | None
    is_data_degraded: bool
    is_new_open: bool
    attack_intent: bool
    daily_loss_breaker_state: str | None
    consecutive_loss_breaker_state: str | None
    learning_ready: dict[str, Any] | None
    opportunity_id: str | None

    @property
    def rejected(self) -> bool:
        return not self.approved

    def to_payload(self) -> dict[str, Any]:
        return {
            "event_id": self.event.event_id,
            "timestamp": int(self.event.timestamp),
            "event_type": self.event.event_type.value,
            "approved": self.approved,
            "reasons": list(self.reasons),
            "no_trade_gate_reasons": list(self.no_trade_gate_reasons),
            "manipulation_level": self.manipulation_level,
            "trade_confirmation_level": self.trade_confirmation_level,
            "account_tier": self.account_tier,
            "regime": self.regime,
            "risk_permission": self.risk_permission,
            "is_data_degraded": self.is_data_degraded,
            "is_new_open": self.is_new_open,
            "attack_intent": self.attack_intent,
            "daily_loss_breaker_state": self.daily_loss_breaker_state,
            "consecutive_loss_breaker_state": self.consecutive_loss_breaker_state,
            "opportunity_id": self.opportunity_id,
            "learning_ready_present": self.learning_ready is not None,
        }


@dataclass(frozen=True)
class IncidentReplay:
    """One incident lifecycle reconstructed from events.db.

    Built from one ``INCIDENT_OPENED`` plus zero-or-one
    ``INCIDENT_RESOLVED`` and the surrounding
    ``PROTECTION_MODE_ENTERED`` / ``PROTECTION_MODE_EXITED`` events
    that share the same incident_id (when present).
    """

    incident_id: str
    level: str
    title: str
    description: str
    opened_at: int
    resolved_at: int | None
    resolution: str | None
    opened_event: Event
    resolved_event: Event | None
    related_events: tuple[Event, ...]
    protection_mode_entered: bool
    protection_mode_exited: bool

    @property
    def open(self) -> bool:
        return self.resolved_event is None

    def to_payload(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "level": self.level,
            "title": self.title,
            "description": self.description,
            "opened_at": int(self.opened_at),
            "resolved_at": (
                int(self.resolved_at) if self.resolved_at is not None else None
            ),
            "resolution": self.resolution,
            "open": self.open,
            "related_event_types": [
                ev.event_type.value for ev in self.related_events
            ],
            "protection_mode_entered": self.protection_mode_entered,
            "protection_mode_exited": self.protection_mode_exited,
        }


@dataclass(frozen=True)
class StateTransitionReplay:
    """Trade State Machine transitions for one symbol (or all).

    Phase 7 emits one ``STATE_TRANSITION`` per transition with payload
    ``{"from", "to", "trigger", "reasons"}``. Replay walks the event
    stream for the symbol and produces a chain of ``from -> to``
    pairs alongside the original events.
    """

    symbol: str | None
    events: tuple[Event, ...]
    chain: tuple[str, ...]
    transitions: tuple[tuple[str, str], ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "event_count": len(self.events),
            "chain": list(self.chain),
            "transitions": [list(t) for t in self.transitions],
        }


@dataclass(frozen=True)
class TelegramCommandReplay:
    """One ``TELEGRAM_COMMAND_RECEIVED`` event reconstructed."""

    event: Event
    name: str | None
    user_id: str | None
    args: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "event_id": self.event.event_id,
            "timestamp": int(self.event.timestamp),
            "name": self.name,
            "user_id": self.user_id,
            "args": list(self.args),
        }


@dataclass(frozen=True)
class LearningReadyReplay:
    """The Phase 8.5 learning-ready block extracted from one event.

    Phase 10A reads the block back exactly as Phase 8.5 wrote it. The
    dict is shallow-copied so the caller cannot mutate the source.
    """

    event: Event
    block: dict[str, Any]
    has_opportunity: bool
    has_signal_snapshot: bool
    has_virtual_trade_plan: bool
    has_config_versions: bool
    has_risk_decision: bool

    @property
    def opportunity_id(self) -> str | None:
        opp = self.block.get("opportunity")
        if isinstance(opp, dict):
            opp_id = opp.get("opportunity_id")
            if isinstance(opp_id, str):
                return opp_id
        return None

    def to_payload(self) -> dict[str, Any]:
        return {
            "event_id": self.event.event_id,
            "event_type": self.event.event_type.value,
            "has_opportunity": self.has_opportunity,
            "has_signal_snapshot": self.has_signal_snapshot,
            "has_virtual_trade_plan": self.has_virtual_trade_plan,
            "has_config_versions": self.has_config_versions,
            "has_risk_decision": self.has_risk_decision,
            "opportunity_id": self.opportunity_id,
        }


@dataclass(frozen=True)
class P0LatchedPauseInvariantReport:
    """Auditor over a sequence of reconciliation passes.

    Phase 9 fix-up rule: once a P0 mismatch lands the ``new_opens_paused``
    flag is **latched**. A subsequent CLEAN reconciliation alone must
    NOT auto-clear the pause - the operator must also resolve the
    incident in IncidentRepository, exit protection mode, and confirm
    resume. Phase 10A reads the trail and flags any pass that violates
    the invariant.

    A violation is recorded when:

      - a ``RECONCILIATION_RESOLVED`` event reports
        ``has_open_p0_incident=True`` AND ``new_opens_paused=False``;
        the latch should have prevented unpause.
      - a ``RECONCILIATION_RESOLVED`` event reports
        ``protection_mode_active=True`` AND ``new_opens_paused=False``;
        protection mode must keep the pause latched.
      - a ``RECONCILIATION_RESOLVED`` event reports
        ``p0_latched_pause=True`` AND ``new_opens_paused=False`` and
        any of the three blockers is still active.
    """

    pass_count: int
    p0_latched_passes: tuple[Event, ...]
    clean_passes: tuple[Event, ...]
    violations: tuple[dict[str, Any], ...]
    every_clean_pass_with_open_p0_kept_pause: bool

    @property
    def held(self) -> bool:
        """True iff no violations were observed."""
        return not self.violations

    def to_payload(self) -> dict[str, Any]:
        return {
            "pass_count": self.pass_count,
            "p0_latched_pass_count": len(self.p0_latched_passes),
            "clean_pass_count": len(self.clean_passes),
            "violations": [dict(v) for v in self.violations],
            "every_clean_pass_with_open_p0_kept_pause": (
                self.every_clean_pass_with_open_p0_kept_pause
            ),
            "held": self.held,
        }


# ===========================================================================
# Canonical Phase 9 paper-trade happy-path chain
# ===========================================================================
#
# This is the reference chain Replay diffs each paper trade against.
# The chain is the CLOSED-position happy-path: any divergence other
# than ORDER_PARTIAL_FILLED (which may repeat zero-or-many times) is
# flagged in the diff so a Replay consumer can spot e.g. a missing
# STOP_CONFIRMED or an unexpected STOP_FAILED.
CANONICAL_CLOSED_PAPER_TRADE_CHAIN: tuple[str, ...] = (
    EventType.ORDER_SENT.value,
    EventType.ORDER_ACK.value,
    EventType.ORDER_FILLED.value,
    EventType.STOP_SENT.value,
    EventType.STOP_CONFIRMED.value,
    EventType.POSITION_OPENED.value,
    EventType.EXIT_TRIGGERED.value,
    EventType.POSITION_CLOSED.value,
)

# Subset chain for an order that only reached POSITION_OPEN.
CANONICAL_OPEN_PAPER_TRADE_CHAIN: tuple[str, ...] = (
    EventType.ORDER_SENT.value,
    EventType.ORDER_ACK.value,
    EventType.ORDER_FILLED.value,
    EventType.STOP_SENT.value,
    EventType.STOP_CONFIRMED.value,
    EventType.POSITION_OPENED.value,
)


# ===========================================================================
# Replay Engine
# ===========================================================================
class ReplayEngine:
    """Read-only replay of events.db (Phase 10A).

    Construct ONCE per process / test. The engine holds a reference to
    the supplied :class:`EventRepository` but never writes through it;
    the underlying ``conn`` is consumed via the public read API only.

    Phase 10A boundary: see module docstring.
    """

    SOURCE_MODULE = "replay_engine"

    def __init__(self, *, event_repo: EventRepository) -> None:
        self._repo = event_repo

    # ------------------------------------------------------------------
    @property
    def event_repo(self) -> EventRepository:
        return self._repo

    # ==================================================================
    # Paper trade lifecycle
    # ==================================================================
    def replay_paper_trade(
        self,
        *,
        client_order_id: str | None = None,
        opportunity_id: str | None = None,
    ) -> PaperTradeReplay:
        """Replay one paper trade lifecycle from events.db.

        Exactly one of ``client_order_id`` / ``opportunity_id`` must be
        supplied. The Phase 9 lifecycle helper does the heavy lifting;
        Replay layers a :class:`ReplayDiffReport` on top.
        """
        summary = reconstruct_paper_lifecycle(
            event_repo=self._repo,
            client_order_id=client_order_id,
            opportunity_id=opportunity_id,
        )
        # Pull the underlying events for the diff. Prefer the explicit
        # client_order_id key when available because it indexes on
        # Event.order_id directly; fall back to the resolved id from
        # the summary otherwise.
        resolved_coid = summary.client_order_id or client_order_id
        if resolved_coid is not None:
            events = tuple(load_events_for_order(self._repo, client_order_id=resolved_coid))
        else:
            events = ()
        observed_chain = tuple(ev.event_type.value for ev in events)
        # Pick the canonical chain that best matches the observed
        # final-status. A closed trade is diffed against the closed
        # canonical chain; an open trade against the open canonical
        # chain.
        if EventType.POSITION_CLOSED.value in observed_chain:
            canonical = CANONICAL_CLOSED_PAPER_TRADE_CHAIN
        else:
            canonical = CANONICAL_OPEN_PAPER_TRADE_CHAIN
        # Strip ORDER_PARTIAL_FILLED before diffing - the canonical
        # chain treats partials as zero-or-many. Replay surfaces the
        # partial count separately on the summary.
        observed_for_diff = tuple(
            t for t in observed_chain if t != EventType.ORDER_PARTIAL_FILLED.value
        )
        # NORMALISE the observed chain into canonical progression
        # order before diffing. EventRepository sorts events by
        # (timestamp ASC, event_id ASC); Phase 9 emits the entire
        # paper trade lifecycle within a single millisecond, which
        # means the secondary event_id sort (random UUID) drives the
        # within-ms ordering non-deterministically. The Replay diff
        # should be structural ("did the canonical SET of events
        # land?"), not "did they land in event_id-sort order". The
        # existing :func:`reconstruct_paper_lifecycle` helper uses the
        # same progression-rank approach to compute the
        # most-progressed lifecycle marker.
        observed_normalised = _normalise_observed_to_canonical(
            observed_for_diff, canonical
        )
        diff = compare_event_chains(
            list(canonical),
            list(observed_normalised),
            label=(
                f"paper_trade:{resolved_coid}"
                if resolved_coid is not None
                else f"paper_trade_opportunity:{opportunity_id}"
            ),
        )
        learning_count = sum(1 for ev in events if has_learning_ready(ev))
        return PaperTradeReplay(
            client_order_id=summary.client_order_id,
            opportunity_id=summary.opportunity_id,
            summary=summary,
            events=events,
            diff_against_canonical=diff,
            learning_ready_event_count=learning_count,
        )

    # ==================================================================
    # Capital flow
    # ==================================================================
    def replay_capital_rebase(
        self,
        *,
        rebase_event_id: str | None = None,
        timestamp: int | None = None,
    ) -> CapitalRebaseReplay:
        """Replay one capital rebase by event_id or by timestamp.

        Replay walks the capital event stream once and pairs the rebase
        event with the immediately-surrounding capital events
        (``CAPITAL_DEPOSIT`` / ``CAPITAL_WITHDRAWAL`` / ``PROFIT_HARVEST`` /
        ``RISK_BUDGET_RECALCULATED``). The Capital Flow Engine emits
        these in the same millisecond by design (Phase 8 fix-up); we
        capture every event whose timestamp is within
        :data:`_CAPITAL_FLOW_PAIRING_WINDOW_MS` of the rebase.
        """
        if (rebase_event_id is None) == (timestamp is None):
            raise ValueError(
                "replay_capital_rebase requires exactly one of "
                "rebase_event_id / timestamp"
            )
        capital_events = load_capital_flow_events(self._repo)
        rebase_event: Event | None = None
        if rebase_event_id is not None:
            for ev in capital_events:
                if (
                    ev.event_type is EventType.CAPITAL_REBASE
                    and ev.event_id == rebase_event_id
                ):
                    rebase_event = ev
                    break
        else:
            assert timestamp is not None
            rebases = [
                ev
                for ev in capital_events
                if ev.event_type is EventType.CAPITAL_REBASE
                and int(ev.timestamp) == int(timestamp)
            ]
            if rebases:
                rebase_event = rebases[0]
        if rebase_event is None:
            raise ValueError(
                f"replay_capital_rebase: no CAPITAL_REBASE event found for "
                f"rebase_event_id={rebase_event_id!r} timestamp={timestamp!r}"
            )
        related = self._related_capital_events(rebase_event, capital_events)
        payload = rebase_event.payload or {}
        trigger = str(payload.get("trigger") or "")
        return CapitalRebaseReplay(
            rebase_event=rebase_event,
            trigger=trigger,
            related_events=tuple(related),
            previous_exchange_equity=_optional_float(payload.get("previous_exchange_equity")),
            new_exchange_equity=_optional_float(payload.get("exchange_equity")),
            previous_lifetime_account_value=_optional_float(
                payload.get("previous_lifetime_account_value")
            ),
            new_lifetime_account_value=_optional_float(
                payload.get("lifetime_account_value")
            ),
            previous_net_trading_pnl=_optional_float(
                payload.get("previous_net_trading_pnl")
            ),
            new_net_trading_pnl=_optional_float(payload.get("net_trading_pnl")),
            previous_risk_budget=_optional_float(payload.get("previous_risk_budget")),
            new_risk_budget=_optional_float(payload.get("risk_budget_total")),
        )

    def _related_capital_events(
        self,
        rebase_event: Event,
        all_capital_events: list[Event],
    ) -> list[Event]:
        rebase_ts = int(rebase_event.timestamp)
        return [
            ev
            for ev in all_capital_events
            if abs(int(ev.timestamp) - rebase_ts) <= _CAPITAL_FLOW_PAIRING_WINDOW_MS
            and ev.event_id != rebase_event.event_id
        ]

    # ==================================================================
    # Risk decisions
    # ==================================================================
    def replay_risk_decision(self, *, event_id: str) -> RiskDecisionReplay:
        events = load_risk_decision_events(self._repo)
        for ev in events:
            if ev.event_id == event_id:
                return self._build_risk_replay(ev)
        raise ValueError(
            f"replay_risk_decision: no RISK_APPROVED / RISK_REJECTED event "
            f"with event_id={event_id!r}"
        )

    def replay_risk_rejections(
        self,
        *,
        symbol: str | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
    ) -> list[RiskDecisionReplay]:
        events = load_risk_decision_events(
            self._repo,
            only_rejected=True,
            symbol=symbol,
            since_ts=since_ts,
            until_ts=until_ts,
        )
        return [self._build_risk_replay(ev) for ev in events]

    def _build_risk_replay(self, ev: Event) -> RiskDecisionReplay:
        payload = ev.payload or {}
        approved = ev.event_type is EventType.RISK_APPROVED
        return RiskDecisionReplay(
            event=ev,
            approved=approved,
            reasons=tuple(payload.get("reasons") or ()),
            no_trade_gate_reasons=tuple(payload.get("no_trade_gate_reasons") or ()),
            manipulation_level=payload.get("manipulation_level"),
            trade_confirmation_level=payload.get("trade_confirmation_level"),
            account_tier=payload.get("account_tier"),
            regime=payload.get("regime"),
            risk_permission=payload.get("risk_permission"),
            is_data_degraded=bool(payload.get("is_data_degraded", False)),
            is_new_open=bool(payload.get("is_new_open", True)),
            attack_intent=bool(payload.get("attack_intent", False)),
            daily_loss_breaker_state=payload.get("daily_loss_breaker_state"),
            consecutive_loss_breaker_state=payload.get(
                "consecutive_loss_breaker_state"
            ),
            learning_ready=extract_learning_ready(ev),
            opportunity_id=_extract_opportunity_id_from_payload(payload),
        )

    # ==================================================================
    # Incident lifecycle
    # ==================================================================
    def replay_incident(self, *, incident_id: str) -> IncidentReplay:
        events = load_incident_lifecycle_events(
            self._repo, incident_id=incident_id
        )
        if not events:
            raise ValueError(
                f"replay_incident: no incident events for incident_id={incident_id!r}"
            )
        opened: Event | None = None
        resolved: Event | None = None
        protection_entered = False
        protection_exited = False
        for ev in events:
            if ev.event_type is EventType.INCIDENT_OPENED:
                opened = ev
            elif ev.event_type is EventType.INCIDENT_RESOLVED:
                resolved = ev
            elif ev.event_type is EventType.PROTECTION_MODE_ENTERED:
                protection_entered = True
            elif ev.event_type is EventType.PROTECTION_MODE_EXITED:
                protection_exited = True
        if opened is None:
            raise ValueError(
                f"replay_incident: incident_id={incident_id!r} has no "
                "INCIDENT_OPENED event"
            )
        opened_payload = opened.payload or {}
        return IncidentReplay(
            incident_id=incident_id,
            level=str(opened_payload.get("level") or ""),
            title=str(opened_payload.get("title") or ""),
            description=str(opened_payload.get("description") or ""),
            opened_at=int(opened.timestamp),
            resolved_at=(
                int(resolved.timestamp) if resolved is not None else None
            ),
            resolution=(
                str((resolved.payload or {}).get("resolution") or "")
                if resolved is not None
                else None
            ),
            opened_event=opened,
            resolved_event=resolved,
            related_events=tuple(events),
            protection_mode_entered=protection_entered,
            protection_mode_exited=protection_exited,
        )

    def replay_p0_incidents(
        self,
        *,
        since_ts: int | None = None,
        until_ts: int | None = None,
    ) -> list[IncidentReplay]:
        """Replay every P0 incident in the window."""
        opened = self._repo.list_events(
            event_type=EventType.INCIDENT_OPENED,
            since_ts=since_ts,
            until_ts=until_ts,
        )
        out: list[IncidentReplay] = []
        for ev in opened:
            payload = ev.payload or {}
            if str(payload.get("level")) != "P0":
                continue
            incident_id = payload.get("incident_id")
            if not isinstance(incident_id, str):
                continue
            out.append(self.replay_incident(incident_id=incident_id))
        return out

    # ==================================================================
    # State machine
    # ==================================================================
    def replay_state_transitions(
        self,
        *,
        symbol: str | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
    ) -> StateTransitionReplay:
        events = load_state_transition_events(
            self._repo,
            symbol=symbol,
            since_ts=since_ts,
            until_ts=until_ts,
        )
        chain: list[str] = []
        transitions: list[tuple[str, str]] = []
        for ev in events:
            payload = ev.payload or {}
            from_state = payload.get("from")
            to_state = payload.get("to")
            if isinstance(to_state, str):
                chain.append(to_state)
            if isinstance(from_state, str) and isinstance(to_state, str):
                transitions.append((from_state, to_state))
        return StateTransitionReplay(
            symbol=symbol,
            events=tuple(events),
            chain=tuple(chain),
            transitions=tuple(transitions),
        )

    # ==================================================================
    # Telegram
    # ==================================================================
    def replay_telegram_commands(
        self,
        *,
        name: str | None = None,
        user_id: str | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
    ) -> list[TelegramCommandReplay]:
        events = load_telegram_command_events(
            self._repo,
            name=name,
            user_id=user_id,
            since_ts=since_ts,
            until_ts=until_ts,
        )
        out: list[TelegramCommandReplay] = []
        for ev in events:
            payload = ev.payload or {}
            args_raw = payload.get("args") or ()
            if isinstance(args_raw, list):
                args = tuple(str(a) for a in args_raw)
            elif isinstance(args_raw, tuple):
                args = tuple(str(a) for a in args_raw)
            else:
                args = ()
            out.append(
                TelegramCommandReplay(
                    event=ev,
                    name=payload.get("name") if isinstance(payload.get("name"), str) else None,
                    user_id=(
                        str(payload.get("user_id"))
                        if payload.get("user_id") is not None
                        else None
                    ),
                    args=args,
                )
            )
        return out

    # ==================================================================
    # Phase 8.5 learning-ready payload
    # ==================================================================
    def extract_learning_ready_for(
        self, *, event_id: str
    ) -> LearningReadyReplay | None:
        """Read the Phase 8.5 ``learning_ready`` payload off one event.

        Returns ``None`` if the event has no learning-ready block.
        """
        # We do not have a get_by_id helper on the repo, so we list
        # events filtered by id via a tight time window (the event
        # carries its own timestamp). Phase 10A is read-only and
        # narrow; this is acceptable for replay use.
        for ev in self._repo.replay_events():
            if ev.event_id == event_id:
                block = extract_learning_ready(ev)
                if block is None:
                    return None
                return LearningReadyReplay(
                    event=ev,
                    block=dict(block),
                    has_opportunity=isinstance(block.get("opportunity"), dict),
                    has_signal_snapshot=isinstance(
                        block.get("signal_snapshot"), dict
                    ),
                    has_virtual_trade_plan=isinstance(
                        block.get("virtual_trade_plan"), dict
                    ),
                    has_config_versions=isinstance(
                        block.get("config_versions"), dict
                    ),
                    has_risk_decision=isinstance(
                        block.get("risk_decision"), dict
                    ),
                )
        return None

    def find_learning_ready_events(
        self,
        *,
        event_type: EventType | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
    ) -> list[Event]:
        """All events in the window that carry a Phase 8.5 ``learning_ready`` block."""
        events = self._repo.list_events(
            event_type=event_type,
            since_ts=since_ts,
            until_ts=until_ts,
        )
        return [ev for ev in events if has_learning_ready(ev)]

    # ==================================================================
    # P0 latched-pause invariant
    # ==================================================================
    def verify_p0_latched_pause_invariant(
        self,
        *,
        since_ts: int | None = None,
        until_ts: int | None = None,
    ) -> P0LatchedPauseInvariantReport:
        """Audit reconciliation passes for the Phase 9 P0 latched-pause rule.

        Reads every ``RECONCILIATION_RESOLVED`` event in the window and
        verifies that every clean pass that observed an open P0
        incident, an active protection mode, or an unconfirmed operator
        resume kept ``new_opens_paused=True``.
        """
        events = load_reconciliation_events(
            self._repo, since_ts=since_ts, until_ts=until_ts
        )
        passes = pair_reconciliation_passes(events)
        p0_latched: list[Event] = []
        clean: list[Event] = []
        violations: list[dict[str, Any]] = []
        every_clean_pass_with_open_p0_kept_pause = True
        for pass_ in passes:
            resolved = pass_.get("resolved")
            if resolved is None:
                continue
            payload = resolved.payload or {}
            mismatch_count = int(payload.get("mismatch_count", 0))
            new_opens_paused = bool(payload.get("new_opens_paused", False))
            p0_latched_pause = bool(payload.get("p0_latched_pause", False))
            has_open_p0 = bool(payload.get("has_open_p0_incident", False))
            protection_active = bool(payload.get("protection_mode_active", False))
            operator_confirmed = bool(payload.get("operator_resume_confirmed", False))
            if p0_latched_pause:
                p0_latched.append(resolved)
            if mismatch_count == 0:
                clean.append(resolved)
            # Invariant 1: any blocker active + new_opens_paused=False
            # is a violation.
            if (has_open_p0 or protection_active) and not new_opens_paused:
                violations.append(
                    {
                        "event_id": resolved.event_id,
                        "timestamp": int(resolved.timestamp),
                        "rule": "blocker_active_but_unpaused",
                        "has_open_p0_incident": has_open_p0,
                        "protection_mode_active": protection_active,
                        "operator_resume_confirmed": operator_confirmed,
                        "new_opens_paused": new_opens_paused,
                        "mismatch_count": mismatch_count,
                    }
                )
                every_clean_pass_with_open_p0_kept_pause = False
            # Invariant 2: p0_latched_pause=True with at least one
            # blocker active and new_opens_paused=False is a violation.
            if (
                p0_latched_pause
                and (has_open_p0 or protection_active or not operator_confirmed)
                and not new_opens_paused
            ):
                violations.append(
                    {
                        "event_id": resolved.event_id,
                        "timestamp": int(resolved.timestamp),
                        "rule": "latched_but_unpaused",
                        "has_open_p0_incident": has_open_p0,
                        "protection_mode_active": protection_active,
                        "operator_resume_confirmed": operator_confirmed,
                        "new_opens_paused": new_opens_paused,
                        "mismatch_count": mismatch_count,
                    }
                )
                every_clean_pass_with_open_p0_kept_pause = False
        return P0LatchedPauseInvariantReport(
            pass_count=len(passes),
            p0_latched_passes=tuple(p0_latched),
            clean_passes=tuple(clean),
            violations=tuple(violations),
            every_clean_pass_with_open_p0_kept_pause=(
                every_clean_pass_with_open_p0_kept_pause
            ),
        )

    # ==================================================================
    # Diff helper
    # ==================================================================
    @staticmethod
    def diff_event_chains(
        expected: Iterable[str],
        observed: Iterable[str],
        *,
        label: str | None = None,
    ) -> ReplayDiffReport:
        """Forward to :func:`compare_event_chains` for caller convenience."""
        return compare_event_chains(list(expected), list(observed), label=label)


# ===========================================================================
# Helpers
# ===========================================================================
# Capital Flow Engine emits the deposit/withdrawal/profit_harvest +
# CAPITAL_REBASE + RISK_BUDGET_RECALCULATED triplet within the same
# millisecond (Phase 8). 50 ms is comfortably above wall-clock jitter
# while still narrow enough to scope to one rebase.
_CAPITAL_FLOW_PAIRING_WINDOW_MS: int = 50


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalise_observed_to_canonical(
    observed: tuple[str, ...],
    canonical: tuple[str, ...],
) -> tuple[str, ...]:
    """Normalise an observed event chain into canonical progression order.

    Phase 9 emits the entire paper trade lifecycle inside a single
    millisecond. ``EventRepository`` sorts by ``(timestamp, event_id)``
    where the secondary key is a random UUID, so the within-ms order
    is not stable across runs.

    The Replay diff is **structural** ("did the canonical events
    land?"), not strictly positional. To get a deterministic
    structural diff:

      1. We project every observed value onto its rank in
         ``canonical`` (events not in ``canonical`` get a synthetic
         tail rank so they show up at the end as EXTRA entries).
      2. We sort the observed chain by (canonical_rank, observed_index).

    The result is:

      - canonical events appear in canonical order even if events.db
        returned them out of order;
      - missing canonical events show up as MISSING entries in the
        diff;
      - unexpected events (e.g. STOP_FAILED) show up as EXTRA entries
        at the end.
    """
    canonical_rank = {value: idx for idx, value in enumerate(canonical)}
    tail_rank = len(canonical_rank)

    indexed: list[tuple[int, int, str]] = []
    for observed_index, value in enumerate(observed):
        rank = canonical_rank.get(value, tail_rank + observed_index)
        indexed.append((rank, observed_index, value))
    indexed.sort()
    return tuple(value for _, _, value in indexed)


def _extract_opportunity_id_from_payload(payload: dict[str, Any]) -> str | None:
    direct = payload.get("opportunity_id")
    if isinstance(direct, str):
        return direct
    block = payload.get("learning_ready")
    if isinstance(block, dict):
        opp = block.get("opportunity")
        if isinstance(opp, dict):
            opp_id = opp.get("opportunity_id")
            if isinstance(opp_id, str):
                return opp_id
    return None


__all__ = [
    "PaperTradeReplay",
    "CapitalRebaseReplay",
    "RiskDecisionReplay",
    "IncidentReplay",
    "StateTransitionReplay",
    "TelegramCommandReplay",
    "LearningReadyReplay",
    "P0LatchedPauseInvariantReport",
    "ReplayEngine",
    "CANONICAL_CLOSED_PAPER_TRADE_CHAIN",
    "CANONICAL_OPEN_PAPER_TRADE_CHAIN",
    # Re-exports for convenience
    "PAPER_LIFECYCLE_EVENT_TYPES",
    "CAPITAL_FLOW_EVENT_TYPES",
    "INCIDENT_LIFECYCLE_EVENT_TYPES",
    "RECONCILIATION_EVENT_TYPES",
    "RISK_DECISION_EVENT_TYPES",
]
