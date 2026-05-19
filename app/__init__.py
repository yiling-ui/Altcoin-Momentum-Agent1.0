"""AMA-RT Altcoin Momentum Agent - Right Tail Edition.

Phase 9: Execution FSM + Reconciliation.

This package is paper-mode by default and contains NO live trading
code. Every Phase 1-8.5 contract remains in force. Phase 9 ADDS:

  - app.execution.*: Phase 9 Execution FSM driver, OrderRequest /
    OrderIntent vocabulary, FillEvent / StopEvent value objects,
    PaperLedger in-memory paper-mode store. The Phase 1 ExecutionFSM
    skeleton is preserved verbatim.
  - app.reconciliation.*: Reconciler engine with 5 mismatch types
    (orders / positions / stops / equity / WS-vs-REST) plus 3 P0
    sub-types (ghost_position / missing_remote_position /
    unattached_stop). Pure-function design over LocalSnapshot /
    RemoteSnapshot value objects.
  - app.incidents.*: IncidentRepository - first writer of
    incidents.db. Emits INCIDENT_OPENED / INCIDENT_RESOLVED /
    PROTECTION_MODE_ENTERED / PROTECTION_MODE_EXITED through
    EventRepository.

Phase 9 runs ENTIRELY in paper / mock mode. The four
ExchangeClientBase write surfaces (create_order, cancel_order,
set_leverage, set_margin_mode) continue to raise SafeModeViolation;
Phase 9 NEVER overrides them. Paper-mode execution state lives in a
separate PaperLedger; it is NOT a substitute for trades.db /
positions.db (those land behind a real exchange adapter in a future
PR).

Phase 9 does NOT implement Issue #10 (LLM, Telegram outbound,
Replay diff reports, Reflection), full AI Learning, Feature Store,
model training, complex data collection / reporting pipeline,
real-trade persistence, or live trading.
"""

__version__ = "1.4.0a9"
__phase__ = "Phase 9 - Execution FSM Reconciliation"
