"""Phase 10B - Reflection Engine (Issue #10 Part 2).

Read-only, deterministic, structured reflection over the Phase 10A
:class:`ReplayEngine` outputs and the Phase 8.5 ``learning_ready``
payload. Produces one :class:`ReflectionResult` per paper-trade
lifecycle.

Issue #10 Part 10B mandate:

  - Reflection MUST be tagged - no free-form natural-language
    reflection is allowed.
  - The Reflection Engine MUST consume the Phase 10A Replay output;
    it MUST NOT re-implement Replay.
  - MFE / MAE / tail_contribution MUST be deterministic; when data
    is insufficient the metric is ``None`` and the reason is recorded
    in :class:`UnknownReason`.

Phase 10B boundary
------------------

Nothing in this module:

  - imports an exchange SDK / HTTP / WebSocket / LLM client / Telegram
    bot library
  - reads ``os.environ`` for credentials
  - opens a socket
  - calls an LLM
  - defines a write surface (``create_order`` / ``cancel_order`` /
    ``set_leverage`` / ``set_margin_mode``)
  - mutates global state
  - calls :meth:`EventRepository.append_event` / ``append_many``
  - subclasses :class:`ExchangeClientBase`
  - imports a state-mutating component
    (:class:`CapitalFlowEngine`, :class:`ExecutionFSMDriver`,
    :class:`Reconciler`, :class:`RiskEngine`,
    :class:`IncidentRepository`, :class:`MockExchangeClient`,
    :class:`BinanceClient`, :class:`MarketDataBuffer`,
    :class:`TelegramCommandCenter`, :class:`RegimeEngine`)

Out of scope for Part 10B
-------------------------

Part 10B intentionally does NOT ship:

  - LLM Guarded Interpreter / DeepSeek client (Part 10C)
  - Telegram outbound + Export commands (Part 10D)
  - Real-trade persistence into ``trades.db`` / ``positions.db``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.core.events import Event, EventType
from app.database.repositories import EventRepository
from app.execution.lifecycle import (
    FINAL_STATUS_CLOSED,
    FINAL_STATUS_OPEN,
    FINAL_STATUS_PROTECTED,
    FINAL_STATUS_REJECTED,
    PaperLifecycleSummary,
)
from app.reflection.metrics import (
    MetricResult,
    compute_mae,
    compute_mfe,
    compute_tail_contribution,
    realized_pnl_for,
)
from app.reflection.models import (
    QualityScore,
    ReflectionInput,
    ReflectionResult,
    TradeOutcome,
    UnknownReason,
)
from app.reflection.tags import MistakeTag
from app.replay import (
    IncidentReplay,
    PaperTradeReplay,
    ReplayEngine,
    RiskDecisionReplay,
    StateTransitionReplay,
)


# ---------------------------------------------------------------------------
# Tunable thresholds (Spec §35 + Phase 9 paper-mode defaults)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ReflectionConfig:
    """Caller-tunable thresholds for tag-rule firing.

    Defaults match the Phase 9 paper-mode contract; tests override
    them per case.
    """

    # late_entry: |fill_price - virtual_entry| / virtual_entry
    late_entry_pct: float = 0.005
    # slippage_error: |fill_price - limit_price| / limit_price (above
    # request.max_slippage_pct).
    slippage_overrun_pct: float = 0.001
    # execution_delay: ack_ts - sent_ts (ms).
    execution_delay_ms: int = 1500
    # weak_volume: anomaly_score below threshold (Spec §18.2).
    weak_volume_anomaly_threshold: float = 50.0
    # high_trap_score: SignalSnapshot trap signals or no_trade_reason
    # contains "trap_*".
    trap_score_threshold: float = 0.6


# ---------------------------------------------------------------------------
# ReflectionEngine
# ---------------------------------------------------------------------------
class ReflectionEngine:
    """Read-only Reflection Engine (Phase 10B).

    Consume one Phase 10A :class:`PaperTradeReplay` plus optional
    surrounding context (risk decisions, state transitions, incidents,
    learning_ready) and produce one :class:`ReflectionResult` of
    typed :class:`MistakeTag` values.

    The engine never writes to events.db. It optionally accepts a
    :class:`ReplayEngine` so callers can ask for "reflect on
    client_order_id X" without first reconstructing the replay
    themselves; the read remains a pure read.
    """

    SOURCE_MODULE = "reflection_engine"

    def __init__(
        self,
        *,
        replay: ReplayEngine | None = None,
        event_repo: EventRepository | None = None,
        config: ReflectionConfig | None = None,
    ) -> None:
        if replay is None and event_repo is None:
            raise ValueError(
                "ReflectionEngine requires either replay= or event_repo="
            )
        if replay is None:
            assert event_repo is not None
            replay = ReplayEngine(event_repo=event_repo)
        self._replay = replay
        self._config = config or ReflectionConfig()

    # ------------------------------------------------------------------
    @property
    def replay(self) -> ReplayEngine:
        return self._replay

    @property
    def config(self) -> ReflectionConfig:
        return self._config

    # ==================================================================
    # Convenience entry points
    # ==================================================================
    def reflect_paper_trade(
        self,
        *,
        client_order_id: str | None = None,
        opportunity_id: str | None = None,
    ) -> ReflectionResult:
        """Reflect on one paper-trade lifecycle, identified by
        ``client_order_id`` or ``opportunity_id``.

        Phase 10B uses Phase 10A's existing replay surface to load the
        paper-trade lifecycle, the risk decisions for the symbol /
        opportunity, the state-transition trail, and the surrounding
        incidents. The Reflection Engine never re-reads events.db
        directly when a Replay handle is wired.
        """
        paper_trade = self._replay.replay_paper_trade(
            client_order_id=client_order_id,
            opportunity_id=opportunity_id,
        )
        return self.reflect(self._build_input_from_replay(paper_trade))

    # ==================================================================
    # Core entry point
    # ==================================================================
    def reflect(self, inp: ReflectionInput) -> ReflectionResult:
        """Reflect on one paper-trade lifecycle bundle."""
        paper_trade = inp.paper_trade
        if not isinstance(paper_trade, PaperTradeReplay):
            raise TypeError(
                "ReflectionInput.paper_trade must be a PaperTradeReplay; got "
                f"{type(paper_trade).__name__}"
            )
        summary: PaperLifecycleSummary = paper_trade.summary
        events: tuple[Event, ...] = tuple(paper_trade.events)
        learning_ready = inp.learning_ready
        # Caller may pass a learning_ready directly (tests do) or rely
        # on the one Phase 10A picked up from the events. Caller wins.
        if learning_ready is None and events:
            for ev in events:
                block = (ev.payload or {}).get("learning_ready")
                if isinstance(block, dict):
                    learning_ready = dict(block)
                    break

        result_outcome = self._classify_result(summary, events)
        notes: list[UnknownReason] = []
        tags: set[MistakeTag] = set()

        # Diagnostic guard: trade with no Phase 9 lifecycle at all.
        if not events:
            tags.add(MistakeTag.NO_LIFECYCLE_OBSERVED)
            notes.append(UnknownReason.NO_LIFECYCLE_EVENTS)

        # MFE / MAE / tail_contribution.
        mfe_result = compute_mfe(events)
        mae_result = compute_mae(events)
        notes.extend(mfe_result.unknown_reasons)
        # Avoid duplicate INSUFFICIENT_PRICE_PATH: include MAE reasons
        # only if they introduce a new code.
        for reason in mae_result.unknown_reasons:
            if reason not in notes:
                notes.append(reason)

        plan = self._extract_virtual_trade_plan(learning_ready)
        signal_snapshot = self._extract_signal_snapshot(learning_ready)
        config_versions = self._extract_config_versions(learning_ready)
        if config_versions is None:
            notes.append(UnknownReason.NO_CONFIG_VERSIONS)
        if signal_snapshot is None:
            notes.append(UnknownReason.NO_SIGNAL_SNAPSHOT)
        if plan is None:
            notes.append(UnknownReason.NO_VIRTUAL_TRADE_PLAN)

        states: tuple[tuple[str, str], ...] = self._extract_state_transitions(inp)
        if not states:
            notes.append(UnknownReason.NO_STATE_TRANSITION_TRAIL)
        if not inp.risk_decisions:
            notes.append(UnknownReason.NO_RISK_DECISION_TRAIL)

        rpnl = realized_pnl_for(events)
        if rpnl is None and result_outcome is not TradeOutcome.OPEN:
            notes.append(UnknownReason.NO_REALISED_PNL)

        tail_result = compute_tail_contribution(
            events=events,
            state_transitions=states,
            realized_pnl=rpnl,
            virtual_trade_plan=plan,
        )
        # Tail unknown reasons feed the same notes channel.
        for reason in tail_result.unknown_reasons:
            if reason not in notes:
                notes.append(reason)

        # ----- Tag rules -------------------------------------------------
        # stop_not_confirmed: stop never confirmed OR explicit STOP_FAILED.
        if not summary.stop_confirmed or any(
            ev.event_type is EventType.STOP_FAILED for ev in events
        ):
            tags.add(MistakeTag.STOP_NOT_CONFIRMED)

        # ignored_no_trade_gate: a RISK_REJECTED for the same opportunity
        # / symbol was followed by a POSITION_OPENED. This MUST NOT
        # happen in Phase 9 (Risk Engine is the single gate); if it
        # does, the tag fires loudly so Reflection users notice the
        # contract has drifted.
        if self._was_no_trade_gate_ignored(inp.risk_decisions, summary, events):
            tags.add(MistakeTag.IGNORED_NO_TRADE_GATE)

        # slippage_error: |fill_price - limit_price| over the request's
        # max_slippage_pct.
        if self._slippage_overrun(events, self._config):
            tags.add(MistakeTag.SLIPPAGE_ERROR)

        # execution_delay: ack_ts - sent_ts above the configured ms.
        if self._execution_delayed(events, self._config):
            tags.add(MistakeTag.EXECUTION_DELAY)

        # late_entry: |fill_price - virtual_entry| / virtual_entry above
        # threshold (only when virtual_trade_plan is supplied).
        if self._late_entry(events, plan, self._config):
            tags.add(MistakeTag.LATE_ENTRY)

        # weak_volume: signal snapshot anomaly_score below threshold.
        if self._weak_volume(signal_snapshot, self._config):
            tags.add(MistakeTag.WEAK_VOLUME)

        # high_trap_score: signal snapshot indicates a trap.
        if self._high_trap_score(signal_snapshot, self._config):
            tags.add(MistakeTag.HIGH_TRAP_SCORE)

        # fake_breakout: state chain shows CONFIRM/ATTACK -> back-step
        # within the trail.
        if self._fake_breakout(states):
            tags.add(MistakeTag.FAKE_BREAKOUT)

        # right_tail / tail_saved / tail_failed: tied to whether the
        # state machine entered RIGHT_TAIL_AMPLIFY plus realised PnL.
        entered_rta = any(to == "right_tail_amplify" for _, to in states)
        if entered_rta and rpnl is not None:
            if rpnl > 0:
                tags.add(MistakeTag.TAIL_SAVED_TRADE)
                if plan is not None and self._right_tail_target_hit(events, plan):
                    tags.add(MistakeTag.RIGHT_TAIL_SUCCESS)
            elif rpnl < 0:
                tags.add(MistakeTag.TAIL_FAILED)

        # early_exit: trade was closed before the virtual_tp1 was
        # reached AND the realised PnL was below the plan's tp1
        # delta. Phase 9 paper-mode emits a single fill_price; we can
        # only fire this rule when the plan is supplied AND we have a
        # realised exit price.
        if self._early_exit(events, plan):
            tags.add(MistakeTag.EARLY_EXIT)

        # incident_during_lifecycle: any incident rebuilt by
        # ReplayEngine that overlaps with the lifecycle window.
        if self._incident_during_lifecycle(events, inp.incidents):
            tags.add(MistakeTag.INCIDENT_DURING_LIFECYCLE)

        # If we accumulated any data-quality notes AND we ended up with
        # zero issue-required tags, surface ``insufficient_data`` so a
        # consumer can distinguish "clean trade" from "we couldn't tell".
        issue_tags = tags - {
            MistakeTag.INSUFFICIENT_DATA,
            MistakeTag.NO_LIFECYCLE_OBSERVED,
            MistakeTag.INCIDENT_DURING_LIFECYCLE,
        }
        if notes and not issue_tags:
            tags.add(MistakeTag.INSUFFICIENT_DATA)

        # ----- Quality scores -------------------------------------------
        entry_quality = self._score_entry_quality(events, plan, tags)
        exit_quality = self._score_exit_quality(events, summary, tags, rpnl)
        risk_quality = self._score_risk_quality(inp.risk_decisions, tags)
        execution_quality = self._score_execution_quality(events, summary, tags)

        # ----- Setup label / source events ------------------------------
        setup = self._extract_setup(plan, signal_snapshot)
        source_event_ids = tuple(ev.event_id for ev in events)

        return ReflectionResult(
            opportunity_id=summary.opportunity_id,
            client_order_id=summary.client_order_id,
            symbol=summary.symbol,
            setup=setup,
            result=result_outcome,
            mistake_tags=tuple(sorted(tags, key=lambda t: t.value)),
            mfe=mfe_result.value,
            mae=mae_result.value,
            tail_contribution=tail_result.value,
            entry_quality=entry_quality,
            exit_quality=exit_quality,
            risk_process_quality=risk_quality,
            execution_quality=execution_quality,
            data_quality_notes=tuple(self._dedupe_notes(notes)),
            source_event_ids=source_event_ids,
            learning_ready=(dict(learning_ready) if learning_ready is not None else None),
        )

    # ==================================================================
    # Internal helpers
    # ==================================================================
    def _build_input_from_replay(
        self, paper_trade: PaperTradeReplay
    ) -> ReflectionInput:
        """Construct a :class:`ReflectionInput` by asking the Replay
        engine for the surrounding context."""
        symbol = paper_trade.summary.symbol
        opp = paper_trade.summary.opportunity_id
        risk_decisions: list[RiskDecisionReplay] = []
        if symbol:
            risk_decisions.extend(
                self._replay.replay_risk_rejections(symbol=symbol)
            )
        if opp:
            for ev in paper_trade.events:
                payload = ev.payload or {}
                if payload.get("opportunity_id") == opp:
                    # ORDER_SENT has the matching opportunity; we
                    # already captured the risk-rejected events above.
                    pass
        state_transitions: StateTransitionReplay | None = None
        if symbol:
            state_transitions = self._replay.replay_state_transitions(
                symbol=symbol
            )
        # Phase 10A loaders only know how to enumerate P0 incidents.
        incidents: tuple[IncidentReplay, ...] = tuple(
            self._replay.replay_p0_incidents()
        )
        return ReflectionInput(
            paper_trade=paper_trade,
            risk_decisions=tuple(risk_decisions),
            state_transitions=state_transitions,
            incidents=incidents,
            learning_ready=None,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _classify_result(
        summary: PaperLifecycleSummary,
        events: Iterable[Event],
    ) -> TradeOutcome:
        if summary.final_status == FINAL_STATUS_REJECTED:
            return TradeOutcome.UNKNOWN
        if summary.final_status == FINAL_STATUS_OPEN:
            return TradeOutcome.OPEN
        if summary.final_status == FINAL_STATUS_PROTECTED:
            return TradeOutcome.PROTECTED
        if summary.final_status != FINAL_STATUS_CLOSED:
            return TradeOutcome.UNKNOWN
        # Closed: pull realised PnL from the closing event.
        rpnl = realized_pnl_for(events)
        if rpnl is None:
            return TradeOutcome.UNKNOWN
        if rpnl > 0:
            return TradeOutcome.WIN
        if rpnl < 0:
            return TradeOutcome.LOSS
        return TradeOutcome.BREAKEVEN

    @staticmethod
    def _extract_virtual_trade_plan(
        learning_ready: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(learning_ready, dict):
            return None
        plan = learning_ready.get("virtual_trade_plan")
        if isinstance(plan, dict):
            return dict(plan)
        return None

    @staticmethod
    def _extract_signal_snapshot(
        learning_ready: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(learning_ready, dict):
            return None
        snap = learning_ready.get("signal_snapshot")
        if isinstance(snap, dict):
            return dict(snap)
        return None

    @staticmethod
    def _extract_config_versions(
        learning_ready: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(learning_ready, dict):
            return None
        cfg = learning_ready.get("config_versions")
        if isinstance(cfg, dict):
            return dict(cfg)
        return None

    @staticmethod
    def _extract_state_transitions(
        inp: ReflectionInput,
    ) -> tuple[tuple[str, str], ...]:
        st = inp.state_transitions
        if isinstance(st, StateTransitionReplay):
            return tuple(st.transitions)
        if isinstance(st, tuple):
            # Already a tuple of (from, to) pairs.
            out: list[tuple[str, str]] = []
            for entry in st:
                if (
                    isinstance(entry, tuple)
                    and len(entry) == 2
                    and isinstance(entry[0], str)
                    and isinstance(entry[1], str)
                ):
                    out.append(entry)
            return tuple(out)
        return ()

    @staticmethod
    def _was_no_trade_gate_ignored(
        risk_decisions: tuple[Any, ...],
        summary: PaperLifecycleSummary,
        events: tuple[Event, ...],
    ) -> bool:
        """A REJECTED risk decision for the same opportunity_id followed
        by an ORDER_SENT for the same opportunity is a hard contract
        violation (Risk Engine is the single gate). Phase 10B flags it
        as ``ignored_no_trade_gate``."""
        if not risk_decisions:
            return False
        opp_id = summary.opportunity_id
        if not opp_id:
            return False
        rejected_before_order: list[int] = []
        order_sent_ts: int | None = None
        for ev in events:
            if (
                ev.event_type is EventType.ORDER_SENT
                and (ev.payload or {}).get("opportunity_id") == opp_id
            ):
                order_sent_ts = int(ev.timestamp)
                break
        if order_sent_ts is None:
            return False
        for decision in risk_decisions:
            if not getattr(decision, "rejected", False):
                continue
            if getattr(decision, "opportunity_id", None) != opp_id:
                continue
            ev = getattr(decision, "event", None)
            if ev is None:
                continue
            if int(ev.timestamp) <= order_sent_ts:
                rejected_before_order.append(int(ev.timestamp))
        return bool(rejected_before_order)

    def _slippage_overrun(
        self,
        events: tuple[Event, ...],
        config: ReflectionConfig,
    ) -> bool:
        request_payload: dict[str, Any] | None = None
        fill_price: float | None = None
        for ev in events:
            if ev.event_type is EventType.ORDER_SENT and request_payload is None:
                request_payload = (ev.payload or {}).get("request") or (
                    ev.payload or {}
                )
            elif ev.event_type is EventType.ORDER_FILLED and fill_price is None:
                p = (ev.payload or {})
                for key in ("avg_fill_price", "fill_price", "price"):
                    candidate = p.get(key)
                    if candidate is not None:
                        try:
                            fill_price = float(candidate)
                        except (TypeError, ValueError):
                            fill_price = None
                        break
        if request_payload is None or fill_price is None:
            return False
        limit_price = request_payload.get("limit_price")
        if limit_price is None:
            return False
        try:
            limit_price = float(limit_price)
        except (TypeError, ValueError):
            return False
        if limit_price <= 0:
            return False
        slippage = abs(fill_price - limit_price) / limit_price
        max_slippage = float(
            request_payload.get("max_slippage_pct")
            or config.slippage_overrun_pct
        )
        # The error fires only when the slippage exceeds BOTH:
        #   - the request's own configured max_slippage_pct, AND
        #   - the engine-level threshold (defence in depth)
        return slippage > max(max_slippage, config.slippage_overrun_pct)

    @staticmethod
    def _execution_delayed(
        events: tuple[Event, ...],
        config: ReflectionConfig,
    ) -> bool:
        sent_ts: int | None = None
        ack_ts: int | None = None
        for ev in events:
            if ev.event_type is EventType.ORDER_SENT and sent_ts is None:
                sent_ts = int(ev.timestamp)
            elif ev.event_type is EventType.ORDER_ACK and ack_ts is None:
                ack_ts = int(ev.timestamp)
            if sent_ts is not None and ack_ts is not None:
                break
        if sent_ts is None or ack_ts is None:
            return False
        return (ack_ts - sent_ts) > config.execution_delay_ms

    @staticmethod
    def _late_entry(
        events: tuple[Event, ...],
        plan: dict[str, Any] | None,
        config: ReflectionConfig,
    ) -> bool:
        if plan is None:
            return False
        try:
            virtual_entry = float(plan["virtual_entry"])
        except (KeyError, TypeError, ValueError):
            return False
        if virtual_entry <= 0:
            return False
        fill_price: float | None = None
        for ev in events:
            if ev.event_type is EventType.ORDER_FILLED:
                p = ev.payload or {}
                for key in ("avg_fill_price", "fill_price", "price"):
                    candidate = p.get(key)
                    if candidate is not None:
                        try:
                            fill_price = float(candidate)
                        except (TypeError, ValueError):
                            fill_price = None
                        break
                break
        if fill_price is None:
            return False
        return abs(fill_price - virtual_entry) / virtual_entry > config.late_entry_pct

    @staticmethod
    def _weak_volume(
        signal_snapshot: dict[str, Any] | None,
        config: ReflectionConfig,
    ) -> bool:
        if signal_snapshot is None:
            return False
        score = signal_snapshot.get("anomaly_score")
        if score is None:
            return False
        try:
            score_f = float(score)
        except (TypeError, ValueError):
            return False
        return score_f < config.weak_volume_anomaly_threshold

    @staticmethod
    def _high_trap_score(
        signal_snapshot: dict[str, Any] | None,
        config: ReflectionConfig,
    ) -> bool:
        if signal_snapshot is None:
            return False
        # Two heuristics:
        #   1. an explicit ``trap_score`` field above the threshold
        #   2. ``no_trade_reason`` contains a ``trap_*`` substring
        trap_score = signal_snapshot.get("trap_score")
        if trap_score is not None:
            try:
                if float(trap_score) >= config.trap_score_threshold:
                    return True
            except (TypeError, ValueError):
                pass
        no_trade_reasons = signal_snapshot.get("no_trade_reason") or []
        if isinstance(no_trade_reasons, list):
            for reason in no_trade_reasons:
                if isinstance(reason, str) and "trap" in reason.lower():
                    return True
        return False

    @staticmethod
    def _fake_breakout(
        states: tuple[tuple[str, str], ...],
    ) -> bool:
        # We mark a fake breakout when the state chain shows a promotion
        # to CONFIRM or ATTACK followed immediately by a downgrade
        # (back to OBSERVE / SCOUT / NO_TRADE) without first reaching
        # LOCK_PROFIT or POSITION_OPEN.
        for index, (from_state, to_state) in enumerate(states):
            if to_state in {"confirm", "attack"}:
                # Look ahead for the next transition.
                if index + 1 < len(states):
                    next_from, next_to = states[index + 1]
                    if next_to in {"observe", "scout", "no_trade"}:
                        return True
        return False

    @staticmethod
    def _right_tail_target_hit(
        events: tuple[Event, ...],
        plan: dict[str, Any],
    ) -> bool:
        tp2 = plan.get("virtual_tp2")
        if tp2 is None:
            return False
        try:
            target = float(tp2)
        except (TypeError, ValueError):
            return False
        for ev in events:
            payload = ev.payload or {}
            for key in ("mark_price", "last_price", "exit_price", "close_price"):
                value = payload.get(key)
                if value is None:
                    continue
                try:
                    p = float(value)
                except (TypeError, ValueError):
                    continue
                if p >= target:
                    return True
        return False

    @staticmethod
    def _early_exit(
        events: tuple[Event, ...],
        plan: dict[str, Any] | None,
    ) -> bool:
        if plan is None:
            return False
        try:
            tp1 = float(plan["virtual_tp1"])
            entry = float(plan["virtual_entry"])
        except (KeyError, TypeError, ValueError):
            return False
        if tp1 <= 0 or entry <= 0:
            return False
        # Find the close price.
        close_price: float | None = None
        for ev in events:
            if ev.event_type is EventType.POSITION_CLOSED:
                payload = ev.payload or {}
                for key in ("exit_price", "close_price", "mark_price", "last_price"):
                    candidate = payload.get(key)
                    if candidate is not None:
                        try:
                            close_price = float(candidate)
                        except (TypeError, ValueError):
                            close_price = None
                        break
                break
        if close_price is None:
            return False
        # LONG: fired when close_price < tp1 AND entry < tp1 (i.e. the
        # plan was an upside plan and we exited before reaching tp1).
        if entry < tp1:
            return close_price < tp1
        # SHORT: fired when close_price > tp1 AND entry > tp1.
        if entry > tp1:
            return close_price > tp1
        return False

    @staticmethod
    def _incident_during_lifecycle(
        events: tuple[Event, ...],
        incidents: tuple[Any, ...],
    ) -> bool:
        if not incidents or not events:
            return False
        ts_min = min(int(ev.timestamp) for ev in events)
        ts_max = max(int(ev.timestamp) for ev in events)
        for incident in incidents:
            opened_at = getattr(incident, "opened_at", None)
            if opened_at is None:
                continue
            try:
                opened_at = int(opened_at)
            except (TypeError, ValueError):
                continue
            if ts_min <= opened_at <= ts_max:
                return True
            # Also flag if the incident's resolved_at falls inside or
            # the incident window straddles the lifecycle.
            resolved_at = getattr(incident, "resolved_at", None)
            if resolved_at is not None:
                try:
                    resolved_at = int(resolved_at)
                except (TypeError, ValueError):
                    continue
                if ts_min <= resolved_at <= ts_max:
                    return True
                if opened_at <= ts_min <= resolved_at:
                    return True
        return False

    @staticmethod
    def _dedupe_notes(notes: list[UnknownReason]) -> list[UnknownReason]:
        seen: set[UnknownReason] = set()
        out: list[UnknownReason] = []
        for note in notes:
            if note in seen:
                continue
            seen.add(note)
            out.append(note)
        return out

    # ------------------------------------------------------------------
    # Quality scoring
    # ------------------------------------------------------------------
    def _score_entry_quality(
        self,
        events: tuple[Event, ...],
        plan: dict[str, Any] | None,
        tags: set[MistakeTag],
    ) -> QualityScore:
        if not events:
            return QualityScore.UNKNOWN
        if MistakeTag.LATE_ENTRY in tags:
            return QualityScore.LOW
        if MistakeTag.SLIPPAGE_ERROR in tags:
            return QualityScore.LOW
        if MistakeTag.HIGH_TRAP_SCORE in tags:
            return QualityScore.LOW
        if plan is None:
            return QualityScore.UNKNOWN
        # Plan supplied + no late_entry + no slippage_error -> medium.
        return QualityScore.MEDIUM

    def _score_exit_quality(
        self,
        events: tuple[Event, ...],
        summary: PaperLifecycleSummary,
        tags: set[MistakeTag],
        realized_pnl: float | None,
    ) -> QualityScore:
        if summary.final_status == FINAL_STATUS_OPEN:
            return QualityScore.UNKNOWN
        if MistakeTag.STOP_NOT_CONFIRMED in tags:
            return QualityScore.LOW
        if MistakeTag.EARLY_EXIT in tags:
            return QualityScore.LOW
        if MistakeTag.TAIL_FAILED in tags:
            return QualityScore.LOW
        if MistakeTag.RIGHT_TAIL_SUCCESS in tags or MistakeTag.TAIL_SAVED_TRADE in tags:
            return QualityScore.HIGH
        if realized_pnl is None:
            return QualityScore.UNKNOWN
        if realized_pnl > 0:
            return QualityScore.HIGH
        if realized_pnl == 0:
            return QualityScore.MEDIUM
        return QualityScore.LOW

    def _score_risk_quality(
        self,
        risk_decisions: tuple[Any, ...],
        tags: set[MistakeTag],
    ) -> QualityScore:
        if MistakeTag.IGNORED_NO_TRADE_GATE in tags:
            return QualityScore.LOW
        if not risk_decisions:
            return QualityScore.UNKNOWN
        return QualityScore.HIGH

    def _score_execution_quality(
        self,
        events: tuple[Event, ...],
        summary: PaperLifecycleSummary,
        tags: set[MistakeTag],
    ) -> QualityScore:
        if not events:
            return QualityScore.UNKNOWN
        if MistakeTag.EXECUTION_DELAY in tags:
            return QualityScore.LOW
        if MistakeTag.STOP_NOT_CONFIRMED in tags:
            return QualityScore.LOW
        if summary.final_status == FINAL_STATUS_PROTECTED:
            return QualityScore.LOW
        if summary.partial_fills > 0 and summary.final_status != FINAL_STATUS_CLOSED:
            return QualityScore.MEDIUM
        return QualityScore.HIGH

    @staticmethod
    def _extract_setup(
        plan: dict[str, Any] | None,
        signal_snapshot: dict[str, Any] | None,
    ) -> str:
        """Pick the most descriptive setup label available.

        Preference order: ``virtual_trade_plan.setup_type`` ->
        ``signal_snapshot.opportunity_grade`` -> ``"unknown"``.
        """
        if isinstance(plan, dict):
            setup = plan.get("setup_type")
            if isinstance(setup, str) and setup:
                return setup
        if isinstance(signal_snapshot, dict):
            grade = signal_snapshot.get("opportunity_grade")
            if isinstance(grade, str) and grade:
                return f"grade_{grade}"
        return "unknown"


__all__ = [
    "ReflectionConfig",
    "ReflectionEngine",
]
