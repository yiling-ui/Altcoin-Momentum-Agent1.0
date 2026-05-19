"""Phase 9 Reconciler (Issue #9, Spec §31).

Compares a :class:`LocalSnapshot` to a :class:`RemoteSnapshot` and
returns a :class:`ReconciliationDecision`. Emits one
``RECONCILIATION_STARTED`` event, one ``RECONCILIATION_MISMATCH``
event per mismatch found, and one ``RECONCILIATION_RESOLVED`` event
on completion.

Hard rules (per Spec §31.3 + Issue #9):

  - Any non-empty mismatch list -> ``new_opens_paused=True``.
  - Local empty + remote has position -> P0 ghost-position incident.
  - Local has stop attached + remote has no stop on that position
    -> P0 unattached-stop incident.
  - WebSocket / REST conflict -> ``new_opens_paused=True``.
  - Equity drift > tolerance -> P1 incident + ``new_opens_paused=True``.
  - The reconciler NEVER opens a real exchange call; it operates on
    the two supplied snapshots only.
  - The reduce-only / protective-exit / kill_all flow is **not**
    blocked by ``new_opens_paused`` - that flag advises the Phase 9
    Execution FSM driver to refuse new ``submit_order`` calls whose
    intent is ``NEW_OPEN`` / ``SCALE_IN``.

P0 latched-pause rule (Issue #9 fix-up)
---------------------------------------

A clean reconciliation pass auto-clears the pause for **P1-only**
mismatches (``ORDER_MISMATCH`` / ``EQUITY_DRIFT`` / ``WS_REST_CONFLICT``).
Once a **P0** mismatch has fired (``GHOST_POSITION`` /
``MISSING_REMOTE_POSITION`` / ``POSITION_MISMATCH`` / ``STOP_MISMATCH`` /
``UNATTACHED_STOP``) the pause is **latched**: a clean reconciliation
alone is not sufficient to resume new opens. Resumption requires all
of the following:

  1. ``has_open_p0_incident`` is False (operator marked the P0 incidents
     as resolved via :meth:`mark_p0_incidents_resolved`).
  2. ``protection_mode_active`` is False (the protection hook has been
     instructed to exit protection mode).
  3. ``operator_resume_confirmed`` is True (an explicit operator /
     manual confirmation has landed via :meth:`confirm_operator_resume`).
  4. The current reconciliation pass is clean (no mismatches).
  5. The Risk Engine separately allows the next ``submit_order`` (the
     reconciler advertises ``new_opens_paused``; the FSM driver / Risk
     Engine still own the final go / no-go decision).

The ``operator_resume_confirmed`` flag is **consumed** when the latch
clears, so a stale confirmation cannot survive across multiple P0
incidents.

Phase 9 boundary
----------------

The reconciler:

  - opens NO socket
  - imports NO exchange SDK / HTTP / WebSocket / LLM client
  - reads NO ``os.environ``
  - defines NO ``create_order`` / ``cancel_order`` / ``set_leverage``
    / ``set_margin_mode``
  - is a write surface only for ``events.db`` (mismatch + resolution
    events) and the ``IncidentRepository`` (P0 / P1 incidents).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.core.clock import now_ms
from app.core.enums import IncidentLevel
from app.core.events import Event, EventType
from app.database.repositories import EventRepository
from app.reconciliation.models import (
    LocalSnapshot,
    Mismatch,
    MismatchSeverity,
    MismatchType,
    PositionView,
    ReconciliationDecision,
    RemoteSnapshot,
    StopView,
    default_severity_for,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ReconcilerConfig:
    """Tunable thresholds. Defaults match the Phase 9 conservative policy.

    The thresholds are kept narrow so Phase 9 does not need a YAML
    pull-through; Issue #10 may surface them in ``risk.yaml`` if a
    real exchange adapter exposes more granular accounting.
    """

    equity_drift_tolerance_abs: float = 0.01  # absolute USDT
    equity_drift_tolerance_rel: float = 0.005  # 0.5 %
    qty_tolerance: float = 1e-9
    price_tolerance: float = 1e-6
    stop_price_tolerance_pct: float = 0.001  # 0.1 %


# ---------------------------------------------------------------------------
# Reconciler
# ---------------------------------------------------------------------------
class Reconciler:
    """Phase 9 reconciliation engine.

    See module docstring for the contract. The class holds three
    cumulative counters so monitoring / tests can assert progress
    without inspecting private state.
    """

    SOURCE_MODULE = "reconciliation"

    def __init__(
        self,
        *,
        event_repo: EventRepository,
        protection_hook: Any | None = None,
        config: ReconcilerConfig | None = None,
    ) -> None:
        self._repo = event_repo
        self._protection_hook = protection_hook
        self._config = config or ReconcilerConfig()
        self._reconciliations_run: int = 0
        self._mismatches_total: int = 0
        self._p0_incidents_opened: int = 0
        self._p1_incidents_opened: int = 0
        self._new_opens_paused: bool = False
        self._last_pause_reason: str | None = None
        # Phase 9 fix-up (Issue #9): P0 latched-pause state.
        # ``_p0_latched_pause`` stays True until ALL of:
        #   - has_open_p0_incident == False
        #   - protection_mode_active == False
        #   - operator_resume_confirmed == True
        #   - current pass is clean
        # are simultaneously satisfied. This prevents a single clean
        # reconciliation from auto-resuming new opens after a P0 event.
        self._p0_latched_pause: bool = False
        self._has_open_p0_incident: bool = False
        # Local fallback for protection-mode tracking when no hook is
        # wired (the hook is the canonical source when present).
        self._protection_mode_latched: bool = False
        self._operator_resume_confirmed: bool = False

    # ------------------------------------------------------------------
    # Counters
    # ------------------------------------------------------------------
    @property
    def reconciliations_run(self) -> int:
        return self._reconciliations_run

    @property
    def mismatches_total(self) -> int:
        return self._mismatches_total

    @property
    def p0_incidents_opened(self) -> int:
        return self._p0_incidents_opened

    @property
    def p1_incidents_opened(self) -> int:
        return self._p1_incidents_opened

    @property
    def new_opens_paused(self) -> bool:
        return self._new_opens_paused

    @property
    def last_pause_reason(self) -> str | None:
        return self._last_pause_reason

    @property
    def config(self) -> ReconcilerConfig:
        return self._config

    # ------------------------------------------------------------------
    # P0 latched-pause state (Issue #9 fix-up)
    # ------------------------------------------------------------------
    @property
    def p0_latched_pause(self) -> bool:
        """True if a P0 mismatch has fired and the pause has not yet
        been cleared by operator confirmation + protection-exit +
        incident-resolved + a subsequent clean reconciliation."""
        return self._p0_latched_pause

    @property
    def has_open_p0_incident(self) -> bool:
        """True if any P0 incident is currently unresolved.

        Reads through the wired :class:`ProtectionHook` (canonical
        source) when one is available - this counts ALL open P0
        incidents in the IncidentRepository, regardless of which
        module opened them. That's deliberately conservative: if any
        P0 is unresolved anywhere in the system, new opens stay
        paused.

        Falls back to a local latch when no hook is wired (e.g.
        minimal unit tests). The local latch is the OR of "this
        reconciler opened a P0 in this process lifetime that has not
        been cleared via :meth:`mark_p0_incidents_resolved`".

        Note on process restart: the local fallback flag is
        process-bounded. After a restart, the next reconciliation
        pass re-establishes protection from the on-disk state of the
        IncidentRepository (when wired) or from the next mismatch it
        observes. The brief Issue #9 fix-up does not require
        cross-restart persistence of operator-acknowledgement state.
        """
        hook = self._protection_hook
        if hook is not None and hasattr(hook, "list_open_incidents"):
            try:
                from app.core.enums import IncidentLevel as _IncidentLevel

                open_p0 = hook.list_open_incidents(level=_IncidentLevel.P0)
                return bool(open_p0)
            except Exception:  # pragma: no cover - defensive
                pass
        return self._has_open_p0_incident

    @property
    def protection_mode_active(self) -> bool:
        """True if protection mode is currently active.

        Reads through the wired :class:`ProtectionHook` (canonical
        source) when one is available; falls back to a local latch
        when no hook is wired (e.g. minimal unit tests)."""
        hook = self._protection_hook
        if hook is not None and hasattr(hook, "in_protection_mode"):
            try:
                return bool(hook.in_protection_mode)
            except Exception:  # pragma: no cover - defensive
                pass
        return self._protection_mode_latched

    @property
    def operator_resume_confirmed(self) -> bool:
        """True if the operator has staged an explicit resume
        confirmation that has not yet been consumed.

        Set via :meth:`confirm_operator_resume`; consumed (reset to
        False) the first time the P0 latch is cleared so it cannot
        survive across multiple P0 events.
        """
        return self._operator_resume_confirmed

    # ------------------------------------------------------------------
    # Operator / incident lifecycle hooks (Issue #9 fix-up)
    # ------------------------------------------------------------------
    def mark_p0_incidents_resolved(
        self,
        *,
        note: str | None = None,
    ) -> None:
        """Operator / incident-side signal that every P0 incident
        opened by this reconciler has been resolved.

        Clears only the LOCAL fallback flag. When a protection hook
        is wired, :attr:`has_open_p0_incident` reads from
        :meth:`IncidentRepository.list_open_incidents` directly, so
        an operator who calls this method without ALSO resolving the
        incidents in the repository (via
        :meth:`IncidentRepository.resolve_incident`) will still see
        ``has_open_p0_incident=True`` from the canonical source, and
        the latch will not clear. That decoupling is deliberate: the
        on-disk record is the source of truth.

        Does NOT by itself unpause new opens; the pause only clears
        when :meth:`reconcile` next runs and finds a clean state with
        protection mode exited and an operator confirmation staged.
        """
        self._has_open_p0_incident = False
        if note is not None:
            logger.info(
                "Reconciler.mark_p0_incidents_resolved: {}",
                note,
            )

    def confirm_operator_resume(
        self,
        *,
        reason: str = "operator_confirmation",
    ) -> None:
        """Stage an operator confirmation that new opens may resume on
        the next clean reconciliation.

        The flag is consumed once the P0 latch clears, so a stale
        confirmation cannot resume new opens after a fresh P0 event.
        """
        self._operator_resume_confirmed = True
        logger.info(
            "Reconciler.confirm_operator_resume: {}",
            reason,
        )

    def exit_protection_mode(
        self,
        *,
        reason: str = "operator_resume",
        symbol: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Pass-through helper that drives protection-mode exit through
        the wired hook AND clears the local latch.

        Callers that already drive
        :meth:`IncidentRepository.exit_protection_mode` directly may
        skip this helper; the :attr:`protection_mode_active` property
        will pick up the change either way.
        """
        if self._protection_hook is not None and hasattr(
            self._protection_hook, "exit_protection_mode"
        ):
            try:
                self._protection_hook.exit_protection_mode(
                    reason=reason,
                    source_module=self.SOURCE_MODULE,
                    symbol=symbol,
                    payload=payload or {},
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Reconciler.exit_protection_mode hook raised: {}",
                    exc,
                )
        self._protection_mode_latched = False

    def can_clear_pause_after_clean_reconciliation(self) -> bool:
        """Whether the next clean reconciliation may resume new opens.

        Distinguishes between P1 and P0 latches per Issue #9:

          - P1-only pause: always clearable on a clean pass.
          - P0 latched pause: clearable only when
            :attr:`has_open_p0_incident` is False, the protection mode
            is not active, and an operator confirmation is staged.

        Reads ``has_open_p0_incident`` and ``protection_mode_active``
        through their PROPERTIES, not the underlying local fields, so
        the canonical-source semantics (read from the wired
        :class:`IncidentRepository` when available) are honoured.

        Risk Engine approval is enforced separately by the FSM driver
        on the next ``submit_order`` call.
        """
        if not self._p0_latched_pause:
            return True
        return (
            (not self.has_open_p0_incident)
            and (not self.protection_mode_active)
            and self._operator_resume_confirmed
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def reconcile(
        self,
        *,
        local: LocalSnapshot,
        remote: RemoteSnapshot,
    ) -> ReconciliationDecision:
        """Run one reconciliation pass.

        Always emits ``RECONCILIATION_STARTED`` and ``RECONCILIATION_RESOLVED``
        events. Emits one ``RECONCILIATION_MISMATCH`` per mismatch
        found.
        """
        started_at = now_ms()
        self._repo.append_event(
            Event(
                event_type=EventType.RECONCILIATION_STARTED,
                source_module=self.SOURCE_MODULE,
                payload={
                    "local_orders": len(local.orders),
                    "remote_orders": len(remote.orders),
                    "local_positions": len(local.positions),
                    "remote_positions": len(remote.positions),
                    "local_stops": len(local.stops),
                    "remote_stops": len(remote.stops),
                    "started_at": started_at,
                },
                timestamp=started_at,
            )
        )

        mismatches: list[Mismatch] = []
        mismatches.extend(self._check_link(local, remote))
        mismatches.extend(self._check_orders(local, remote))
        mismatches.extend(self._check_positions(local, remote))
        mismatches.extend(self._check_stops(local, remote))
        mismatches.extend(self._check_equity(local, remote))

        # Emit mismatches and open incidents.
        incident_ids: list[str] = []
        for mismatch in mismatches:
            self._emit_mismatch(mismatch)
            incident_id = self._maybe_open_incident(mismatch)
            if incident_id is not None:
                incident_ids.append(incident_id)

        new_opens_paused = bool(mismatches)
        protection_entered = False
        notes: list[str] = []
        has_p0_in_pass = any(
            m.severity is MismatchSeverity.P0 for m in mismatches
        )
        if new_opens_paused:
            self._mismatches_total += len(mismatches)
            reason = "; ".join(
                f"{m.mismatch_type.value}({m.severity.value})" for m in mismatches
            )
            self._new_opens_paused = True
            self._last_pause_reason = reason
            notes.append(f"new_opens_paused: {reason}")
            if has_p0_in_pass:
                # Latch the P0 pause + the open-P0-incident flag. The
                # pause can only clear once an operator confirmation
                # plus protection-exit plus incident-resolved plus a
                # clean reconciliation all line up (Issue #9 fix-up).
                self._p0_latched_pause = True
                self._has_open_p0_incident = True
                # Invalidate any stale operator confirmation. A
                # confirmation staged BEFORE this P0 (e.g. for an
                # earlier incident, or pre-emptively) must not carry
                # forward - the operator has to re-confirm AFTER they
                # have inspected this fresh P0.
                if self._operator_resume_confirmed:
                    notes.append(
                        "operator_resume_confirmed_invalidated_by_new_p0"
                    )
                    self._operator_resume_confirmed = False
                notes.append("p0_latched_pause")
        else:
            # Clean pass. Distinguish P1-only vs P0-latched pauses.
            if self._p0_latched_pause:
                if self.can_clear_pause_after_clean_reconciliation():
                    # All four conditions met: clear the latch and
                    # consume the operator confirmation so it cannot
                    # carry over to a future P0 event.
                    self._p0_latched_pause = False
                    self._operator_resume_confirmed = False
                    if self._new_opens_paused:
                        notes.append(
                            "new_opens_unpaused: clean_after_p0_resolved"
                        )
                    self._new_opens_paused = False
                    self._last_pause_reason = None
                else:
                    # Latched: clean alone is not enough.
                    blockers: list[str] = []
                    if self.has_open_p0_incident:
                        blockers.append("has_open_p0_incident")
                    if self.protection_mode_active:
                        blockers.append("protection_mode_active")
                    if not self._operator_resume_confirmed:
                        blockers.append("operator_resume_not_confirmed")
                    new_opens_paused = True
                    self._new_opens_paused = True
                    blocker_str = ",".join(blockers) or "p0_latched"
                    self._last_pause_reason = f"p0_latched: {blocker_str}"
                    notes.append(
                        f"new_opens_paused: p0_latched({blocker_str})"
                    )
            else:
                # P1-only pause is cleared by a clean reconciliation,
                # mirroring the original Phase 9 behaviour.
                if self._new_opens_paused:
                    notes.append("new_opens_unpaused: clean_reconciliation")
                self._new_opens_paused = False
                self._last_pause_reason = None

        # P0 mismatches additionally drive protection mode if a hook is
        # available.
        if has_p0_in_pass:
            self._protection_mode_latched = True
            if self._protection_hook is not None:
                try:
                    self._protection_hook.enter_protection_mode(
                        reason="reconciliation_p0_mismatch",
                        source_module=self.SOURCE_MODULE,
                        symbol=None,
                        payload={
                            "p0_count": sum(
                                1 for m in mismatches if m.severity is MismatchSeverity.P0
                            ),
                            "incident_ids": incident_ids,
                        },
                    )
                    protection_entered = True
                except Exception as exc:
                    logger.warning(
                        "Reconciler.enter_protection_mode hook raised: {}",
                        exc,
                    )

        finished_at = now_ms()
        self._reconciliations_run += 1

        decision = ReconciliationDecision(
            started_at=started_at,
            finished_at=finished_at,
            mismatches=tuple(mismatches),
            incidents_opened=tuple(incident_ids),
            new_opens_paused=self._new_opens_paused,
            protection_mode_entered=protection_entered,
            notes=tuple(notes),
        )

        self._repo.append_event(
            Event(
                event_type=EventType.RECONCILIATION_RESOLVED,
                source_module=self.SOURCE_MODULE,
                payload={
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "mismatch_count": len(mismatches),
                    "p0_count": sum(
                        1 for m in mismatches if m.severity is MismatchSeverity.P0
                    ),
                    "p1_count": sum(
                        1 for m in mismatches if m.severity is MismatchSeverity.P1
                    ),
                    "new_opens_paused": self._new_opens_paused,
                    "p0_latched_pause": self._p0_latched_pause,
                    "has_open_p0_incident": self.has_open_p0_incident,
                    "protection_mode_active": self.protection_mode_active,
                    "operator_resume_confirmed": self._operator_resume_confirmed,
                    "protection_mode_entered": protection_entered,
                    "incident_ids": list(incident_ids),
                    "notes": list(notes),
                },
                timestamp=finished_at,
            )
        )
        return decision

    # ==================================================================
    # Individual check helpers
    # ==================================================================
    def _check_link(
        self,
        local: LocalSnapshot,
        remote: RemoteSnapshot,
    ) -> list[Mismatch]:
        # The link health is supplied on either snapshot (the local
        # adapter usually carries both views). We accept either.
        link = local.link or remote.link
        if link is None:
            return []
        if not link.conflicts:
            return []
        return [
            Mismatch(
                mismatch_type=MismatchType.WS_REST_CONFLICT,
                severity=default_severity_for(MismatchType.WS_REST_CONFLICT),
                symbol=None,
                summary=(
                    f"WebSocket={link.websocket_state.value} disagrees with "
                    f"REST={link.rest_state.value}"
                ),
                details={
                    "websocket_state": link.websocket_state.value,
                    "rest_state": link.rest_state.value,
                    "timestamp": int(link.timestamp),
                },
            )
        ]

    def _check_orders(
        self,
        local: LocalSnapshot,
        remote: RemoteSnapshot,
    ) -> list[Mismatch]:
        local_by_id = {o.order_id: o for o in local.orders}
        remote_by_id = {o.order_id: o for o in remote.orders}
        mismatches: list[Mismatch] = []
        # Orders local-not-remote.
        for order_id in local_by_id.keys() - remote_by_id.keys():
            o = local_by_id[order_id]
            mismatches.append(
                Mismatch(
                    mismatch_type=MismatchType.ORDER_MISMATCH,
                    severity=default_severity_for(MismatchType.ORDER_MISMATCH),
                    symbol=o.symbol,
                    summary=(
                        f"Local order {order_id} on {o.symbol} not present remotely"
                    ),
                    details={
                        "side": "local_only",
                        "order": o.to_payload(),
                    },
                )
            )
        # Orders remote-not-local.
        for order_id in remote_by_id.keys() - local_by_id.keys():
            o = remote_by_id[order_id]
            mismatches.append(
                Mismatch(
                    mismatch_type=MismatchType.ORDER_MISMATCH,
                    severity=default_severity_for(MismatchType.ORDER_MISMATCH),
                    symbol=o.symbol,
                    summary=(
                        f"Remote order {order_id} on {o.symbol} not present locally"
                    ),
                    details={
                        "side": "remote_only",
                        "order": o.to_payload(),
                    },
                )
            )
        # Orders on both sides but with a qty / filled-qty mismatch.
        for order_id in local_by_id.keys() & remote_by_id.keys():
            lo = local_by_id[order_id]
            ro = remote_by_id[order_id]
            if (
                abs(lo.qty - ro.qty) > self._config.qty_tolerance
                or abs(lo.filled_qty - ro.filled_qty) > self._config.qty_tolerance
                or lo.side != ro.side
            ):
                mismatches.append(
                    Mismatch(
                        mismatch_type=MismatchType.ORDER_MISMATCH,
                        severity=default_severity_for(MismatchType.ORDER_MISMATCH),
                        symbol=lo.symbol,
                        summary=(
                            f"Order {order_id} qty / fill / side disagrees: "
                            f"local={lo.to_payload()} vs remote={ro.to_payload()}"
                        ),
                        details={
                            "side": "qty_mismatch",
                            "local": lo.to_payload(),
                            "remote": ro.to_payload(),
                        },
                    )
                )
        return mismatches

    def _check_positions(
        self,
        local: LocalSnapshot,
        remote: RemoteSnapshot,
    ) -> list[Mismatch]:
        local_by_symbol: dict[str, PositionView] = {p.symbol: p for p in local.positions}
        remote_by_symbol: dict[str, PositionView] = {p.symbol: p for p in remote.positions}
        mismatches: list[Mismatch] = []

        # Symbols local-not-remote: local thinks we hold a position the
        # exchange has no record of. Could mean we got de-leveraged or
        # the position was closed remotely. Phase 9 P0.
        for symbol in local_by_symbol.keys() - remote_by_symbol.keys():
            lp = local_by_symbol[symbol]
            mismatches.append(
                Mismatch(
                    mismatch_type=MismatchType.POSITION_MISMATCH,
                    severity=MismatchSeverity.P0,
                    symbol=symbol,
                    summary=(
                        f"Local position on {symbol} not present remotely - "
                        "investigate before resuming new opens"
                    ),
                    details={
                        "side": "local_only",
                        "local": lp.to_payload(),
                    },
                )
            )
            mismatches.append(
                Mismatch(
                    mismatch_type=MismatchType.MISSING_REMOTE_POSITION,
                    severity=MismatchSeverity.P0,
                    symbol=symbol,
                    summary=(
                        f"Local has position on {symbol} but exchange does not"
                    ),
                    details={"local": lp.to_payload()},
                )
            )

        # Symbols remote-not-local: a ghost position. Local thinks we
        # are flat, exchange disagrees. Phase 9 P0 - this is the
        # canonical "money is on the line and we don't know" case.
        for symbol in remote_by_symbol.keys() - local_by_symbol.keys():
            rp = remote_by_symbol[symbol]
            mismatches.append(
                Mismatch(
                    mismatch_type=MismatchType.POSITION_MISMATCH,
                    severity=MismatchSeverity.P0,
                    symbol=symbol,
                    summary=(
                        f"Ghost position on {symbol}: local empty but remote "
                        "has open exposure"
                    ),
                    details={
                        "side": "remote_only",
                        "remote": rp.to_payload(),
                    },
                )
            )
            mismatches.append(
                Mismatch(
                    mismatch_type=MismatchType.GHOST_POSITION,
                    severity=MismatchSeverity.P0,
                    symbol=symbol,
                    summary=f"Ghost position detected on {symbol}",
                    details={"remote": rp.to_payload()},
                )
            )

        # Symbols on both sides: qty / direction must agree.
        for symbol in local_by_symbol.keys() & remote_by_symbol.keys():
            lp = local_by_symbol[symbol]
            rp = remote_by_symbol[symbol]
            if (
                abs(lp.qty - rp.qty) > self._config.qty_tolerance
                or lp.direction != rp.direction
            ):
                mismatches.append(
                    Mismatch(
                        mismatch_type=MismatchType.POSITION_MISMATCH,
                        severity=MismatchSeverity.P0,
                        symbol=symbol,
                        summary=(
                            f"Position qty / direction disagrees on {symbol}: "
                            f"local={lp.qty} {lp.direction} vs "
                            f"remote={rp.qty} {rp.direction}"
                        ),
                        details={
                            "side": "qty_mismatch",
                            "local": lp.to_payload(),
                            "remote": rp.to_payload(),
                        },
                    )
                )
        return mismatches

    def _check_stops(
        self,
        local: LocalSnapshot,
        remote: RemoteSnapshot,
    ) -> list[Mismatch]:
        # We index stops by stop_order_id AND by position_id so we can
        # detect both "remote stop missing" and "local stop missing".
        local_by_stop_id: dict[str, StopView] = {s.stop_order_id: s for s in local.stops}
        remote_by_stop_id: dict[str, StopView] = {s.stop_order_id: s for s in remote.stops}

        mismatches: list[Mismatch] = []

        # Stop ids on local but not remote -> P0 unattached_stop. Local
        # thinks the stop is attached, exchange has nothing.
        for stop_id in local_by_stop_id.keys() - remote_by_stop_id.keys():
            ls = local_by_stop_id[stop_id]
            mismatches.append(
                Mismatch(
                    mismatch_type=MismatchType.STOP_MISMATCH,
                    severity=MismatchSeverity.P0,
                    symbol=ls.symbol,
                    summary=(
                        f"Stop {stop_id} on {ls.symbol} present locally but "
                        "missing on exchange"
                    ),
                    details={
                        "side": "local_only",
                        "local": ls.to_payload(),
                    },
                )
            )
            mismatches.append(
                Mismatch(
                    mismatch_type=MismatchType.UNATTACHED_STOP,
                    severity=MismatchSeverity.P0,
                    symbol=ls.symbol,
                    summary=(
                        f"Position {ls.position_id} on {ls.symbol} has no "
                        "remote stop attached"
                    ),
                    details={"local_stop": ls.to_payload()},
                )
            )

        # Stop ids on remote but not local -> ORDER side mismatch. Less
        # severe (P0 still per default mapping); reflection / replay
        # will surface the orphan stop.
        for stop_id in remote_by_stop_id.keys() - local_by_stop_id.keys():
            rs = remote_by_stop_id[stop_id]
            mismatches.append(
                Mismatch(
                    mismatch_type=MismatchType.STOP_MISMATCH,
                    severity=default_severity_for(MismatchType.STOP_MISMATCH),
                    symbol=rs.symbol,
                    summary=(
                        f"Remote stop {stop_id} on {rs.symbol} not tracked locally"
                    ),
                    details={
                        "side": "remote_only",
                        "remote": rs.to_payload(),
                    },
                )
            )

        # Stop ids on both sides but with diverging qty / price.
        for stop_id in local_by_stop_id.keys() & remote_by_stop_id.keys():
            ls = local_by_stop_id[stop_id]
            rs = remote_by_stop_id[stop_id]
            qty_drift = abs(ls.qty - rs.qty) > self._config.qty_tolerance
            price_drift_abs = abs(ls.stop_price - rs.stop_price)
            price_drift_rel = (
                price_drift_abs / abs(ls.stop_price)
                if ls.stop_price not in (0.0, -0.0)
                else math.inf
            )
            if (
                qty_drift
                or price_drift_rel > self._config.stop_price_tolerance_pct
                or ls.side != rs.side
            ):
                mismatches.append(
                    Mismatch(
                        mismatch_type=MismatchType.STOP_MISMATCH,
                        severity=default_severity_for(MismatchType.STOP_MISMATCH),
                        symbol=ls.symbol,
                        summary=(
                            f"Stop {stop_id} on {ls.symbol} qty / price / side "
                            f"disagrees"
                        ),
                        details={
                            "side": "qty_or_price_mismatch",
                            "local": ls.to_payload(),
                            "remote": rs.to_payload(),
                        },
                    )
                )
        return mismatches

    def _check_equity(
        self,
        local: LocalSnapshot,
        remote: RemoteSnapshot,
    ) -> list[Mismatch]:
        if local.equity is None or remote.equity is None:
            return []
        diff = abs(local.equity.total_equity - remote.equity.total_equity)
        rel = (
            diff / abs(remote.equity.total_equity)
            if remote.equity.total_equity not in (0.0, -0.0)
            else math.inf
        )
        if (
            diff <= self._config.equity_drift_tolerance_abs
            or rel <= self._config.equity_drift_tolerance_rel
        ):
            return []
        return [
            Mismatch(
                mismatch_type=MismatchType.EQUITY_DRIFT,
                severity=default_severity_for(MismatchType.EQUITY_DRIFT),
                symbol=None,
                summary=(
                    f"Equity drift {diff:.4f} ({rel:.4%}) exceeds tolerance "
                    f"{self._config.equity_drift_tolerance_abs:.4f} abs / "
                    f"{self._config.equity_drift_tolerance_rel:.4%} rel"
                ),
                details={
                    "local_equity": float(local.equity.total_equity),
                    "remote_equity": float(remote.equity.total_equity),
                    "abs_diff": float(diff),
                    "rel_diff": float(rel),
                    "tolerance_abs": float(self._config.equity_drift_tolerance_abs),
                    "tolerance_rel": float(self._config.equity_drift_tolerance_rel),
                },
            )
        ]

    # ------------------------------------------------------------------
    # Emit / incident helpers
    # ------------------------------------------------------------------
    def _emit_mismatch(self, mismatch: Mismatch) -> None:
        self._repo.append_event(
            Event(
                event_type=EventType.RECONCILIATION_MISMATCH,
                source_module=self.SOURCE_MODULE,
                symbol=mismatch.symbol,
                payload=mismatch.to_payload(),
            )
        )

    def _maybe_open_incident(self, mismatch: Mismatch) -> str | None:
        if self._protection_hook is None:
            return None
        # P2 mismatches are informational only; we do not open an
        # incident for them.
        if mismatch.severity is MismatchSeverity.P2:
            return None
        level = (
            IncidentLevel.P0
            if mismatch.severity is MismatchSeverity.P0
            else IncidentLevel.P1
        )
        try:
            incident_id = self._protection_hook.open_incident(
                level=level,
                title=f"reconciliation:{mismatch.mismatch_type.value}",
                description=mismatch.summary,
                source_module=self.SOURCE_MODULE,
                symbol=mismatch.symbol,
                position_id=None,
                payload=mismatch.to_payload(),
            )
        except Exception as exc:
            logger.warning(
                "Reconciler.open_incident hook raised: {} (mismatch={})",
                exc,
                mismatch.mismatch_type.value,
            )
            return None
        if level is IncidentLevel.P0:
            self._p0_incidents_opened += 1
        else:
            self._p1_incidents_opened += 1
        return incident_id


__all__ = [
    "Reconciler",
    "ReconcilerConfig",
]
