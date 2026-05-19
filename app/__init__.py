"""AMA-RT Altcoin Momentum Agent - Right Tail Edition.

Phase 10B: Reflection Engine (Issue #10 Part 2).

This package is paper-mode by default and contains NO live trading
code. Every Phase 1-10A contract remains in force. Phase 10B ADDS
the read-only :mod:`app.reflection` package that consumes Phase 10A
:class:`ReplayEngine` outputs and the Phase 8.5 ``learning_ready``
payload to produce one structured :class:`ReflectionResult` per
paper-trade lifecycle. The result carries a typed ``mistake_tags``
list, MFE / MAE / tail_contribution metrics (deterministic; ``None``
when data is insufficient), and four :class:`QualityScore` axes.

Phase 10B is **read-only**: it opens no socket, imports no exchange
/ HTTP / WebSocket / LLM / Telegram client, defines no write surface,
calls no ``EventRepository.append_event``, and never instantiates a
state-mutating component. Issue #10 Parts 10C (LLM Guarded
Interpreter) and 10D (Telegram outbound + Export commands) land in
separate PRs. Issue #10 will be closed by Part 10D.

Phase 9 contracts that remain in force:

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

Phase 10B does NOT implement the rest of Issue #10 (LLM Guarded
Interpreter, Telegram outbound, Export commands), full AI Learning,
Feature Store, model training, complex data collection / reporting
pipeline, real-trade persistence, free-form natural-language
reflection, or live trading.
"""

__version__ = "1.4.0a10b"
__phase__ = "Phase 10B - Reflection Engine"
