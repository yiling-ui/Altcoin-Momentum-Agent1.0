"""Phase 11C.1C-A - Label-queue contract builder.

The :class:`LabelQueueContract` records the candidate's identity +
the tracking windows the future MFE / MAE / Tail-label processor
must evaluate. Phase 11C.1C-A does NOT implement that processor;
this module only ships the *contract* so the persistence layer
(events.db + Phase 8.5 export + Phase 10A replay) can carry the
queue forward.

Phase 11C.1C-A boundary
-----------------------

  - Pure function; no I/O, no global state.
  - The queue is descriptive; nothing here triggers a label
    computation, opens a position, or mutates exchange state.
"""

from __future__ import annotations

from typing import Iterable

from app.adaptive.models import LabelQueueContract


#: Default tracking windows the brief enumerates: 5m / 15m / 30m / 1h / 4h.
DEFAULT_TRACKING_WINDOWS: tuple[str, ...] = (
    "5m",
    "15m",
    "30m",
    "1h",
    "4h",
)


def build_label_queue_contract(
    *,
    opportunity_id: str,
    scan_batch_id: str,
    symbol: str,
    enqueued_at_ms: int,
    reference_price: float = 0.0,
    tracking_windows: Iterable[str] | None = None,
    notes: Iterable[str] | None = None,
    mfe_mae_label_pending: bool = True,
    future_tail_label_pending: bool = True,
) -> LabelQueueContract:
    """Build a :class:`LabelQueueContract` for one candidate.

    The queue starts with both pending flags True (no labels have
    been produced yet) and the default 5m / 15m / 30m / 1h / 4h
    tracking windows.
    """
    if tracking_windows is None:
        windows: tuple[str, ...] = DEFAULT_TRACKING_WINDOWS
    else:
        seen: set[str] = set()
        deduped: list[str] = []
        for w in tracking_windows:
            text = str(w).strip()
            if text and text not in seen:
                seen.add(text)
                deduped.append(text)
        windows = tuple(deduped) if deduped else DEFAULT_TRACKING_WINDOWS
    if notes is None:
        note_tuple: tuple[str, ...] = ()
    else:
        note_tuple = tuple(str(n) for n in notes)
    return LabelQueueContract(
        opportunity_id=str(opportunity_id),
        scan_batch_id=str(scan_batch_id),
        symbol=str(symbol),
        enqueued_at_ms=int(enqueued_at_ms),
        mfe_mae_label_pending=bool(mfe_mae_label_pending),
        future_tail_label_pending=bool(future_tail_label_pending),
        tracking_windows=windows,
        reference_price=float(reference_price or 0.0),
        notes=note_tuple,
    )


__all__ = [
    "DEFAULT_TRACKING_WINDOWS",
    "build_label_queue_contract",
]
