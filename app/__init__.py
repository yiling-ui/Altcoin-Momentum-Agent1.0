"""AMA-RT Altcoin Momentum Agent - Right Tail Edition.

Phase 7: State Machine + Risk Engine.
This package is paper-mode by default and contains NO live trading code.
The Phase 1 safety lock, the Phase 3 read-only Exchange Gateway
contract, the Phase 4 Market Data Buffer boundary, the Phase 5
Regime / Universe / Liquidity contract, and the Phase 6 Scanner /
Confirmation / Manipulation contract all remain in force - see
app.config.settings, app.exchanges.base, app.market_data,
app.regime / app.universe / app.liquidity, app.scanner /
app.confirmation / app.manipulation, and app.risk / app.state_machine.
"""

__version__ = "1.4.0a7"
__phase__ = "Phase 7 - State Machine Risk Engine"
