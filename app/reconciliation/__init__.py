"""Phase 9 Reconciliation package (Issue #9, Spec §31).

Phase 9 ships the Reconciliation loop that compares the local view
of orders / positions / stops / equity against the exchange's view
and writes typed mismatches as events + incidents.

The Reconciler is a **pure function** of two snapshots: it does NOT
poll the exchange itself, does NOT call any write surface, does NOT
mutate the paper ledger or the FSM driver. The caller is responsible
for assembling the two snapshots:

  - The **local** snapshot is built from the
    :class:`app.execution.paper_ledger.PaperLedger` and the
    :class:`app.execution.fsm.ExecutionFSMDriver` sessions.
  - The **remote** snapshot is built from the gateway client's
    read-only methods (in paper mode the same paper ledger; in
    tests, hand-crafted divergent snapshots).

Public surface
--------------

    LocalSnapshot                         dataclass
    RemoteSnapshot                        dataclass
    ReconciliationDecision                dataclass

    OrderView / PositionView / StopView   value objects
    EquitySnapshot                        value object
    LinkHealth                            value object

    MismatchType                          typed enum
    MismatchSeverity                      typed enum
    Mismatch                              typed value object

    Reconciler                            engine class

Phase 9 hard rules
------------------

  - Any non-empty mismatch list -> ``new_opens_paused=True``.
  - ``ghost_position`` (local empty + remote has position) -> P0
    incident.
  - ``unattached_stop`` (local thinks stop is attached, remote has
    no stop on that position) -> P0 incident.
  - WebSocket / REST conflict -> ``new_opens_paused=True``.
  - Equity drift > tolerance -> ``new_opens_paused=True`` + P1
    incident.
  - The Reconciler NEVER opens a real exchange call; it operates on
    the two supplied snapshots only.
"""

from app.reconciliation.models import (
    EquitySnapshot,
    LinkHealth,
    LocalSnapshot,
    Mismatch,
    MismatchSeverity,
    MismatchType,
    OrderView,
    PositionView,
    ReconciliationDecision,
    RemoteSnapshot,
    StopView,
    local_snapshot_from_paper_ledger,
    remote_snapshot_from_paper_ledger,
)
from app.reconciliation.reconciler import Reconciler

__all__ = [
    "EquitySnapshot",
    "LinkHealth",
    "LocalSnapshot",
    "Mismatch",
    "MismatchSeverity",
    "MismatchType",
    "OrderView",
    "PositionView",
    "Reconciler",
    "ReconciliationDecision",
    "RemoteSnapshot",
    "StopView",
    "local_snapshot_from_paper_ledger",
    "remote_snapshot_from_paper_ledger",
]
