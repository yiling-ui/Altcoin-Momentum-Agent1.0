"""Phase 6 - Pre-Anomaly + Anomaly scanner package (Issue #6).

Two pure stateless classifiers on top of the Phase 4 :class:`MarketDataBuffer`
and the Phase 5 :class:`RegimeSnapshot`. Neither classifier opens a
socket, places an order, or imports an exchange SDK. Each produces ONE
event per evaluation:

  - :class:`PreAnomalyScanner`  ->  ``PRE_ANOMALY_DETECTED``
  - :class:`AnomalyScanner`     ->  ``ANOMALY_DETECTED``

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
