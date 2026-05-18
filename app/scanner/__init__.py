"""Phase 6 - Pre-Anomaly + Anomaly scanner package (Issue #6).

Two pure stateless classifiers on top of the Phase 4 :class:`MarketDataBuffer`
and the Phase 5 :class:`RegimeSnapshot`. Neither classifier opens a
socket, places an order, or imports an exchange SDK. Each produces ONE
event per evaluation:

  - :class:`PreAnomalyScanner`  ->  ``PRE_ANOMALY_DETECTED``
  - :class:`AnomalyScanner`     ->  ``ANOMALY_DETECTED``

**``pre_anomaly_score`` and ``anomaly_score`` are CANDIDATE and
ANOMALY INDICATORS only - NOT entry signals.** A high score does
not authorise opening a position by itself. Both classifiers return
:class:`PreAnomalyDecision` / :class:`AnomalyDecision` value objects
(``score`` + ``reason_tags`` + ``notes``). They never construct a
:class:`app.core.models.TradeDecision`, never enqueue an order,
never mutate any position, and never call any
:class:`app.exchanges.base.ExchangeClientBase` write surface (those
inherit a base-class :class:`SafeModeViolation` refusal anyway).

Whether a real opening is permitted is the conjunction of the
Phase 5 regime / universe / liquidity decisions, the Phase 6 confirmation
tier (T2+ for ATTACK), the Phase 6 manipulation tier (M0 / M1 for
ATTACK), the Phase 7 No-Trade Gate + Risk Engine final adjudication,
and the Phase 9 Execution FSM transition. The non-generation
invariant is pinned by ``tests/unit/test_pre_anomaly_scanner.py`` and
``tests/unit/test_anomaly_scanner.py``.

Phase 6 boundary (declared here so the next PR cannot drift):

  1. Pre-Anomaly / Anomaly ONLY. No Real-Trade Confirmation, no
     Manipulation Detector (those live in :mod:`app.confirmation` and
     :mod:`app.manipulation`); no Strategy Engine, no State Machine
     (Issue #7), no Capital Flow (Issue #8), no Execution FSM (Issue #9),
     no LLM (Issue #10).
  2. The classifiers consume :class:`MarketSnapshot` value objects and
     optional bar history; they do NOT call any write surface.
  3. No API key, no ``os.environ`` lookup, no ``ExchangeClientBase``
     subclass.
  4. **Indicators only, NOT entry signals.** Decisions are passive
     scores + reason tags. The Risk Engine in Phase 7 owns the
     opening decision.
"""

from app.scanner.anomaly import AnomalyScanner
from app.scanner.models import (
    AnomalyConfig,
    AnomalyDecision,
    AnomalyInput,
    PreAnomalyConfig,
    PreAnomalyDecision,
    PreAnomalyInput,
)
from app.scanner.pre_anomaly import PreAnomalyScanner

__all__ = [
    "AnomalyConfig",
    "AnomalyDecision",
    "AnomalyInput",
    "AnomalyScanner",
    "PreAnomalyConfig",
    "PreAnomalyDecision",
    "PreAnomalyInput",
    "PreAnomalyScanner",
]
