"""AMA-RT Altcoin Momentum Agent - Right Tail Edition.

Phase 8.5: Learning-Ready Data Contract + Test Data Export Contract.

This package is paper-mode by default and contains NO live trading code.
The Phase 1 safety lock, the Phase 3 read-only Exchange Gateway
contract, the Phase 4 Market Data Buffer boundary, the Phase 5
Regime / Universe / Liquidity contract, the Phase 6 Scanner /
Confirmation / Manipulation contract, the Phase 7 State Machine /
Risk Engine contract, and the Phase 8 Capital Flow Engine contract
all remain in force - see app.config.settings, app.exchanges.base,
app.market_data, app.regime / app.universe / app.liquidity,
app.scanner / app.confirmation / app.manipulation,
app.risk / app.state_machine, and app.capital.

Phase 8.5 ships ONLY:
  - app.learning.*: passive data contract for future Replay / MFE-MAE /
    Tail Labeling / Dataset Builder / AI Learning. Pure value objects;
    no model training; no Feature Store; no LLM.
  - app.exports.*: Test Data Export Service + redaction. Reads
    EventRepository, writes a redacted zip bundle to
    data/reports/exports/. No outbound network; no Telegram outbound;
    Telegram /export_* commands are deferred to Issue #10 and only
    documented (docs/PHASE_8_5_TELEGRAM_EXPORT_CONTRACT.md).

Phase 8.5 does NOT implement Issue #9 (Execution FSM driver,
Reconciliation), Issue #10 (LLM, Telegram outbound, Replay diff
reports, Reflection), full AI Learning, Feature Store, model
training, or any complex data collection / reporting pipeline.
"""

__version__ = "1.4.0a8.5"
__phase__ = "Phase 8.5 - Learning-Ready Data Contract + Test Data Export Contract"
