"""AMA-RT Altcoin Momentum Agent - Right Tail Edition.

Phase 10C: LLM Guarded Interpreter (Issue #10 Part 3).

This package is paper-mode by default and contains NO live trading
code. Every Phase 1-10B contract remains in force. Phase 10C ADDS
the receive-only :mod:`app.llm` package: a sandboxed,
schema-validated, never-trading LLM intelligence layer that
compresses community / catalyst / narrative text into a small,
strictly typed intelligence payload (Spec §22). The output is
informational only; it never carries a trade direction, a leverage,
a target price, an order, a stop, or any other field that could move
money. The Risk Engine remains the single gate.

Phase 10C is constrained:

  - The five Phase 1 safety flags remain locked. ``llm_enabled``
    stays ``False`` at boot; the Phase 10C boot self-check exercises
    the orchestrator with ``llm_enabled=False`` and a deterministic
    :class:`FakeLLMClient`, producing a degraded result that is
    persisted as exactly one ``LLM_DEGRADED`` event.
  - No exchange SDK / HTTP / WebSocket / LLM client / Telegram bot
    library is imported anywhere under :mod:`app.llm`.
  - No write surface (``create_order`` / ``cancel_order`` /
    ``set_leverage`` / ``set_margin_mode``) is added.
  - No ``api_key`` / ``api_secret`` / ``bot_token`` parameter or
    concrete literal lives anywhere under :mod:`app.llm`.
  - No ``os.environ`` / ``getenv`` reads anywhere under
    :mod:`app.llm` - credentials must be passed in explicitly.
  - The interpreter NEVER raises into the caller; every failure -
    transport, schema, exception - converts into a degraded
    :class:`LLMInterpretationResult`.
  - Phase 10D (Telegram outbound + Export commands) ships in a
    separate PR; Phase 10C does NOT introduce a Telegram surface.

Phase 10B contracts that remain in force:

  - app.reflection.*: read-only Reflection Engine on top of Phase
    10A Replay outputs and the Phase 8.5 ``learning_ready`` payload.
  - app.replay.*: read-only Replay Engine over events.db. Never
    writes; never opens a socket.

Phase 9 contracts that remain in force:

  - app.execution.*: paper-mode Execution FSM driver. The four
    ExchangeClientBase write surfaces continue to raise
    SafeModeViolation; Phase 10C NEVER overrides them.
  - app.reconciliation.*: pure-function reconciler.
  - app.incidents.*: incident repository (writes incidents.db).

Phase 10C does NOT implement:

  - Any real LLM transport (DeepSeek client is a refusal-only
    skeleton)
  - Telegram outbound / bot client / file export commands
  - Free-form natural-language reflection
  - LLM-driven trade decisions / direction / leverage / target_price
  - Real network access at boot
  - Real-trade persistence into trades.db / positions.db
"""

__version__ = "1.4.0a10c"
__phase__ = "Phase 10C - LLM Guarded Interpreter"
