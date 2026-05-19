"""Capital Flow Engine (Phase 8, Spec §28).

Orchestrates the full capital lifecycle:
  - Deposits (seed + external top-ups)
  - Withdrawals (profit harvest, principal withdrawal, mixed)
  - Capital Rebase
  - Risk budget recalculation
  - Account life tier updates
  - Integration with Risk Engine

Core invariants (Spec §28.2 + Issue #8 fix):
  - lifetime_equity         = exchange_equity + withdrawn_profit
  - trading_capital         = exchange_equity
  - risk_budget             = trading_capital
  - performance             = net_trading_pnl
                            = lifetime_account_value
                                - initial_capital
                                - external_deposits_total
  - lifetime_account_value  = exchange_equity
                                + withdrawn_profit
                                + principal_withdrawn_total
  - net_contributed_capital = initial_capital
                                + external_deposits_total
                                - principal_withdrawn_total

Hard rules:
  - Withdrawal is NOT a loss
  - External deposit is NOT trading profit
  - Principal withdrawal is NOT a drawdown and never lands in
    ``withdrawn_profit``
  - Profit withdrawal is NOT a drawdown
  - ``initial_capital`` MUST NOT change after construction
  - Rebase is a capital base reset
  - No new opens during rebase
  - Withdrawn profit excluded from risk budget
  - All capital events must be persisted
  - Risk budget recalculation must be persisted
  - After a rebase, the Risk Engine still decides whether new opens
    may resume (No-Trade Gate, stop_unconfirmed, unknown_position,
    etc.)

Prohibitions:
  - No real withdrawal execution
  - No exchange withdrawal API calls
  - No live trading
  - No right-tail amplification with principal
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from loguru import logger

from app.capital.models import (
    CapitalSnapshot,
    HarvestSuggestion,
    RebaseResult,
    RebaseState,
    WithdrawalRequest,
)
from app.capital.profit_harvest import suggest_harvest
from app.capital.rebase import execute_rebase, persist_capital_snapshot
from app.core.clock import now_ms
from app.core.enums import AccountLifeTier
from app.core.events import Event, EventType
from app.core.models import CapitalState
from app.database.repositories import EventRepository
from app.risk.account_tier import classify_account_tier


class CapitalFlowEngine:
    """Phase 8 Capital Flow Engine (Spec §28 + Issue #8 fix).

    Manages the authoritative CapitalState and exposes operations:
      - deposit()                    external top-up (NOT trading profit)
      - withdraw() / profit_harvest() withdraw with profit/principal split
      - update_equity()              trading P&L update (NOT a deposit)
      - get_state()
      - get_harvest_suggestion()
      - replay_capital_events()      reconstruct snapshot from events
      - is_rebase_in_progress

    The engine ensures:
      - ``initial_capital`` is set once at construction and NEVER mutated
      - Rebase blocks new opens (via ``is_rebase_in_progress`` flag)
      - After a rebase, resuming new opens is still subject to the
        Risk Engine (No-Trade Gate, stop_unconfirmed, unknown_position)
      - All mutations are event-sourced
      - Risk budget is always consistent with exchange equity
      - Performance is computed from ``net_trading_pnl`` (external
        deposits excluded)
      - Withdrawn profit never re-enters risk budget
      - Principal withdrawals never pollute ``withdrawn_profit``
    """

    def __init__(
        self,
        *,
        initial_capital: float,
        exchange_equity: float | None = None,
        withdrawn_profit: float = 0.0,
        external_deposits_total: float = 0.0,
        principal_withdrawn_total: float = 0.0,
        event_repo: EventRepository,
        capital_conn: sqlite3.Connection | None = None,
    ) -> None:
        if initial_capital <= 0:
            raise ValueError(
                f"initial_capital must be > 0; got {initial_capital}"
            )

        # Issue #8 hard rule: ``initial_capital`` is immutable after
        # construction. Stored under a name-mangled attribute and surfaced
        # via a read-only ``initial_capital`` property; the setter raises.
        self.__initial_capital = float(initial_capital)
        self._event_repo = event_repo
        self._capital_conn = capital_conn
        self._rebase_in_progress = False

        # Initialise CapitalState
        equity = exchange_equity if exchange_equity is not None else initial_capital
        self._state = CapitalState(
            initial_capital=initial_capital,
            exchange_equity=equity,
            withdrawn_profit=withdrawn_profit,
            external_deposits_total=external_deposits_total,
            principal_withdrawn_total=principal_withdrawn_total,
        )
        self._state.recompute()

        # Set initial tier
        self._state.account_life_tier = classify_account_tier(
            current_equity=self._state.exchange_equity,
            initial_capital=self.__initial_capital,
        )

        logger.info(
            "CapitalFlowEngine initialised: initial={}, equity={}, "
            "withdrawn_profit={}, principal_withdrawn={}, "
            "external_deposits={}, lifetime_account_value={}, tier={}",
            initial_capital,
            self._state.exchange_equity,
            self._state.withdrawn_profit,
            self._state.principal_withdrawn_total,
            self._state.external_deposits_total,
            self._state.lifetime_account_value,
            self._state.account_life_tier.value,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def state(self) -> CapitalState:
        """Current capital state (read-only view)."""
        return self._state

    @property
    def initial_capital(self) -> float:
        """Initial capital. Set once at construction; immutable thereafter
        (Issue #8 hard rule: ``initial_capital`` MUST NOT change after
        a withdrawal or rebase)."""
        return self.__initial_capital

    @initial_capital.setter
    def initial_capital(self, value: float) -> None:
        raise AttributeError(
            "initial_capital is immutable after construction (Issue #8 hard rule)"
        )

    @property
    def is_rebase_in_progress(self) -> bool:
        """True while a rebase is in progress. No new opens allowed.

        Phase 8 Issue #8 fix: when this flag is *cleared*, new opens are
        not automatically authorised. The Risk Engine must still run a
        full No-Trade Gate evaluation (stop_unconfirmed,
        unknown_position, regime, liquidity, account tier, circuit
        breakers, manipulation). The Capital Flow Engine never opens a
        position itself."""
        return self._rebase_in_progress

    @property
    def lifetime_equity(self) -> float:
        """exchange_equity + withdrawn_profit (Spec §28.2 metric)."""
        return self._state.lifetime_equity

    @property
    def lifetime_account_value(self) -> float:
        """exchange_equity + withdrawn_profit + principal_withdrawn_total.

        Issue #8 hard rule: this is the "real" performance figure and
        is invariant under withdrawals."""
        return self._state.lifetime_account_value

    @property
    def net_contributed_capital(self) -> float:
        """initial_capital + external_deposits_total - principal_withdrawn_total."""
        return self._state.net_contributed_capital

    @property
    def net_trading_pnl(self) -> float:
        """lifetime_account_value - initial_capital - external_deposits_total.

        External deposits NEVER show up here. This is the only figure
        performance reporting must use (Issue #8 hard rule)."""
        return self._state.net_trading_pnl

    @property
    def external_deposits_total(self) -> float:
        """Cumulative external top-up deposits since construction."""
        return self._state.external_deposits_total

    @property
    def principal_withdrawn_total(self) -> float:
        """Cumulative principal portion of all withdrawals."""
        return self._state.principal_withdrawn_total

    @property
    def withdrawn_profit(self) -> float:
        """Cumulative profit portion of all withdrawals (never includes
        principal - Issue #8 hard rule)."""
        return self._state.withdrawn_profit

    @property
    def trading_capital(self) -> float:
        """Risk budget base: exchange_equity."""
        return self._state.trading_capital

    @property
    def risk_budget(self) -> float:
        """Current risk budget = trading_capital. Always based on the
        current exchange_equity, never on historical peaks or already-
        withdrawn profit (Spec §28.5 hard rule)."""
        return self._state.risk_budget_total

    @property
    def account_tier(self) -> AccountLifeTier:
        """Current account life tier."""
        return self._state.account_life_tier

    @property
    def multiplier(self) -> float:
        """Current account multiplier (lifetime_equity / initial_capital).

        Note: this preserves the Phase 1-7 definition. For an external-
        deposit aware ratio see ``net_trading_pnl`` /
        ``net_contributed_capital``."""
        if self.__initial_capital <= 0:
            return 0.0
        return self._state.lifetime_equity / self.__initial_capital

    # ------------------------------------------------------------------
    # Deposit (external top-up / 中途追加资金)
    # ------------------------------------------------------------------
    def deposit(
        self,
        *,
        amount: float,
        new_exchange_equity: float | None = None,
        note: str | None = None,
    ) -> RebaseResult:
        """Record an external capital deposit (Issue #8 hard rules).

        Hard contract:
          1. Records a CAPITAL_DEPOSIT event.
          2. Increases ``external_deposits_total``.
          3. Updates ``exchange_equity`` (and therefore ``trading_capital``
             / ``risk_budget``).
          4. Emits CAPITAL_REBASE.
          5. Emits RISK_BUDGET_RECALCULATED.
          6. Does NOT increase ``net_trading_pnl``.
          7. Does NOT increase ``withdrawn_profit``.
          8. Does NOT mutate ``initial_capital``.
          9. Sets ``is_rebase_in_progress=True`` for the duration of the
             rebase so concurrent open requests are blocked.
         10. After completion, the rebase flag is cleared. The Risk Engine
             must still adjudicate any subsequent open request.

        Args:
            amount: positive USDT amount deposited.
            new_exchange_equity: explicit new equity (if known from exchange).
                If None, we add ``amount`` to current ``exchange_equity``.
            note: optional note.

        Returns:
            RebaseResult capturing the before/after snapshot for this deposit.
        """
        if amount <= 0:
            raise ValueError(f"Deposit amount must be > 0; got {amount}")

        # Block new opens for the duration of the deposit-triggered rebase.
        self._rebase_in_progress = True
        try:
            ts = now_ms()

            # Capture "before" state.
            prev_equity = self._state.exchange_equity
            prev_withdrawn = self._state.withdrawn_profit
            prev_principal_withdrawn = self._state.principal_withdrawn_total
            prev_external_deposits = self._state.external_deposits_total
            prev_lifetime = self._state.lifetime_equity
            prev_trading = self._state.trading_capital
            prev_budget = self._state.risk_budget_total
            prev_tier = self._state.account_life_tier
            prev_lifetime_account_value = self._state.lifetime_account_value
            prev_net_trading_pnl = self._state.net_trading_pnl

            # External deposit: bumps both ``external_deposits_total`` and
            # ``exchange_equity``. ``initial_capital`` and ``withdrawn_profit``
            # are untouched (Issue #8 hard rule).
            self._state.external_deposits_total += amount
            if new_exchange_equity is not None:
                self._state.exchange_equity = new_exchange_equity
            else:
                self._state.exchange_equity += amount

            self._state.recompute()
            self._state.last_rebase_ts = ts
            new_tier = classify_account_tier(
                current_equity=self._state.exchange_equity,
                initial_capital=self.__initial_capital,
            )
            self._state.account_life_tier = new_tier

            # 1. CAPITAL_DEPOSIT - external_deposits_total in the payload so a
            #    Replay engine can rebuild the running total deterministically.
            self._event_repo.append_event(
                Event(
                    event_type=EventType.CAPITAL_DEPOSIT,
                    source_module="capital_flow_engine",
                    payload={
                        "amount": float(amount),
                        "currency": "USDT",
                        "deposit_type": "external",
                        "external_deposits_total": float(
                            self._state.external_deposits_total
                        ),
                        "exchange_equity": float(self._state.exchange_equity),
                        "trading_capital": float(self._state.trading_capital),
                        "initial_capital": float(self.__initial_capital),
                        "note": note or f"Deposit of {amount} USDT",
                    },
                    timestamp=ts,
                )
            )

            # 4. CAPITAL_REBASE - deposit-triggered rebase.
            self._event_repo.append_event(
                Event(
                    event_type=EventType.CAPITAL_REBASE,
                    source_module="capital_flow_engine",
                    payload={
                        "amount": float(self._state.trading_capital),
                        "currency": "USDT",
                        "trigger": "deposit",
                        "deposit_amount": float(amount),
                        "exchange_equity": float(self._state.exchange_equity),
                        "withdrawn_profit": float(self._state.withdrawn_profit),
                        "principal_withdrawn_total": float(
                            self._state.principal_withdrawn_total
                        ),
                        "external_deposits_total": float(
                            self._state.external_deposits_total
                        ),
                        "lifetime_equity": float(self._state.lifetime_equity),
                        "lifetime_account_value": float(
                            self._state.lifetime_account_value
                        ),
                        "trading_capital": float(self._state.trading_capital),
                        "risk_budget_total": float(self._state.risk_budget_total),
                        "initial_capital": float(self.__initial_capital),
                        "net_contributed_capital": float(
                            self._state.net_contributed_capital
                        ),
                        "net_trading_pnl": float(self._state.net_trading_pnl),
                        "note": f"Rebase after deposit of {amount} USDT",
                    },
                    timestamp=ts,
                )
            )

            # 5. RISK_BUDGET_RECALCULATED.
            self._event_repo.record_risk_budget_recalculated(
                new_risk_budget=self._state.risk_budget_total,
                previous_risk_budget=prev_budget,
                source_module="capital_flow_engine",
                note=(
                    f"Risk budget recalculated after deposit: "
                    f"{prev_budget:.2f} -> {self._state.risk_budget_total:.2f}"
                ),
                timestamp=ts,
            )

            self._persist_snapshot(note=f"After deposit of {amount} USDT")

            logger.info(
                "Deposit recorded: amount={}, equity={}, "
                "external_deposits_total={}, tier={}",
                amount,
                self._state.exchange_equity,
                self._state.external_deposits_total,
                self._state.account_life_tier.value,
            )

            return RebaseResult(
                success=True,
                state=RebaseState.COMPLETED,
                previous_exchange_equity=prev_equity,
                previous_withdrawn_profit=prev_withdrawn,
                previous_lifetime_equity=prev_lifetime,
                previous_trading_capital=prev_trading,
                previous_risk_budget=prev_budget,
                previous_account_tier=prev_tier,
                new_exchange_equity=self._state.exchange_equity,
                new_withdrawn_profit=self._state.withdrawn_profit,
                new_lifetime_equity=self._state.lifetime_equity,
                new_trading_capital=self._state.trading_capital,
                new_risk_budget=self._state.risk_budget_total,
                new_account_tier=new_tier,
                deposit_amount=float(amount),
                note=note or f"Deposit of {amount} USDT",
                profit_part=0.0,
                principal_part=0.0,
                withdrawal_type="",
                available_profit_before=max(0.0, prev_net_trading_pnl),
                previous_principal_withdrawn_total=prev_principal_withdrawn,
                new_principal_withdrawn_total=self._state.principal_withdrawn_total,
                previous_external_deposits_total=prev_external_deposits,
                new_external_deposits_total=self._state.external_deposits_total,
                previous_lifetime_account_value=prev_lifetime_account_value,
                new_lifetime_account_value=self._state.lifetime_account_value,
                previous_net_trading_pnl=prev_net_trading_pnl,
                new_net_trading_pnl=self._state.net_trading_pnl,
            )
        finally:
            # The deposit-triggered rebase is always finite. Clear the
            # gate so subsequent open requests reach the Risk Engine,
            # which then makes the final go/no-go call.
            self._rebase_in_progress = False

    # ------------------------------------------------------------------
    # Withdrawal / Profit Harvest
    # ------------------------------------------------------------------
    def withdraw(
        self,
        *,
        amount: float,
        new_exchange_equity: float,
        note: str | None = None,
        positions_clear: bool = True,
        timestamp: int | None = None,
    ) -> RebaseResult:
        """Execute a withdrawal with full 13-step capital rebase.

        This is the PRIMARY interface for recording a withdrawal. It:
          1. Sets rebase_in_progress = True (blocks new opens)
          2. Executes the rebase flow (13 steps)
          3. Persists capital snapshot
          4. Clears rebase_in_progress (if rebase succeeded and risk allows)

        Args:
            amount: positive USDT amount withdrawn.
            new_exchange_equity: equity on exchange after withdrawal.
            note: optional note.
            positions_clear: caller confirms positions/stops are safe.
            timestamp: optional explicit timestamp.

        Returns:
            RebaseResult with full audit trail.
        """
        # Step 1: Block new opens
        self._rebase_in_progress = True

        try:
            request = WithdrawalRequest(
                amount=amount,
                new_exchange_equity=new_exchange_equity,
                note=note,
                timestamp=timestamp,
            )

            result = execute_rebase(
                capital_state=self._state,
                withdrawal=request,
                event_repo=self._event_repo,
                initial_capital=self.__initial_capital,
                positions_clear=positions_clear,
            )

            if result.success:
                self._persist_snapshot(
                    note=f"Rebase after withdrawal of {amount} USDT"
                )

            return result
        finally:
            # Step 13: Resume trading only if rebase succeeded
            # If failed, keep rebase_in_progress = True so system stays paused
            if result.success:
                self._rebase_in_progress = False
            else:
                logger.warning(
                    "Rebase failed; rebase_in_progress remains True. "
                    "Manual intervention required."
                )

    def profit_harvest(
        self,
        *,
        amount: float,
        new_exchange_equity: float,
        note: str | None = None,
        positions_clear: bool = True,
        timestamp: int | None = None,
    ) -> RebaseResult:
        """Alias for withdraw() with profit-harvest semantics.

        Identical to withdraw() but the note defaults to a harvest message.
        """
        return self.withdraw(
            amount=amount,
            new_exchange_equity=new_exchange_equity,
            note=note or f"Profit harvest of {amount} USDT",
            positions_clear=positions_clear,
            timestamp=timestamp,
        )

    # ------------------------------------------------------------------
    # Equity update (without withdrawal - e.g. from trading P&L)
    # ------------------------------------------------------------------
    def update_equity(self, *, new_exchange_equity: float) -> None:
        """Update exchange equity from trading P&L (not a deposit/withdrawal).

        This does NOT trigger a rebase. It simply updates the equity and
        recomputes derived fields. Used by the system to reflect trading
        gains/losses.
        """
        self._state.exchange_equity = new_exchange_equity
        self._state.recompute()
        self._state.account_life_tier = classify_account_tier(
            current_equity=self._state.exchange_equity,
            initial_capital=self.__initial_capital,
        )

    # ------------------------------------------------------------------
    # Harvest suggestion
    # ------------------------------------------------------------------
    def get_harvest_suggestion(self) -> HarvestSuggestion | None:
        """Get a profit-harvest suggestion based on current state.

        Returns None if there is no profit to harvest. Issue #8 fix:
        the suggestion is computed from ``net_trading_pnl`` so external
        deposits never inflate the apparent profit.
        """
        return suggest_harvest(
            current_equity=self._state.exchange_equity,
            initial_capital=self.__initial_capital,
            withdrawn_profit=self._state.withdrawn_profit,
            external_deposits_total=self._state.external_deposits_total,
            principal_withdrawn_total=self._state.principal_withdrawn_total,
        )

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------
    def get_state(self) -> CapitalState:
        """Return current CapitalState."""
        return self._state

    def is_withdrawal_not_loss(
        self,
        *,
        previous_lifetime_equity: float,
        current_lifetime_equity: float,
    ) -> bool:
        """Verify that a decrease in exchange equity after withdrawal
        is NOT a loss.

        Spec §28.5 hard rule: "提现不是亏损".
        If lifetime_equity is maintained or increased, the decrease
        in exchange_equity is a withdrawal, not a loss.
        """
        return current_lifetime_equity >= previous_lifetime_equity

    # ------------------------------------------------------------------
    # Issue #8 fix - event-sourced reconstruction (Spec §12, §28.3)
    # ------------------------------------------------------------------
    @classmethod
    def replay_capital_events(
        cls,
        *,
        initial_capital: float,
        events: Iterable[Event],
    ) -> CapitalState:
        """Reconstruct the current ``CapitalState`` from a stream of
        capital events (CAPITAL_DEPOSIT / CAPITAL_WITHDRAWAL /
        PROFIT_HARVEST / CAPITAL_REBASE / RISK_BUDGET_RECALCULATED).

        Hard rule (Issue #8 + Spec §12.2): the engine MUST be able to
        rebuild a snapshot from events alone, even before Phase 10's
        full Replay engine ships.

        Behaviour:
          - ``CAPITAL_DEPOSIT`` adds to ``external_deposits_total`` and
            ``exchange_equity``.
          - ``CAPITAL_WITHDRAWAL`` consumes the
            ``profit_part`` / ``principal_part`` carried in the payload
            (or, for legacy payloads without the split, falls back to
            classifying via the running ``net_trading_pnl``).
          - ``CAPITAL_REBASE`` payloads carry the post-rebase
            ``exchange_equity``; we trust them so a Phase-7 capital.db
            replays cleanly.
          - ``PROFIT_HARVEST`` is treated as a documentation event only
            - the underlying state mutation already happened on the
            associated ``CAPITAL_WITHDRAWAL``.
          - ``RISK_BUDGET_RECALCULATED`` is a side-effect event; it
            does not mutate state on its own.

        Args:
            initial_capital: the seed capital. Issue #8 hard rule:
                ``initial_capital`` is determined at engine construction
                and never recomputed from events.
            events: iterable of ``Event`` instances; the caller is
                responsible for ordering them (timestamp ASC).

        Returns:
            A fully recomputed ``CapitalState``.
        """
        if initial_capital <= 0:
            raise ValueError(
                f"initial_capital must be > 0; got {initial_capital}"
            )
        state = CapitalState(
            initial_capital=float(initial_capital),
            exchange_equity=float(initial_capital),
            withdrawn_profit=0.0,
            external_deposits_total=0.0,
            principal_withdrawn_total=0.0,
        )
        state.recompute()

        for event in events:
            payload = event.payload or {}
            etype = event.event_type

            if etype is EventType.CAPITAL_DEPOSIT:
                amount = float(payload.get("amount", 0.0) or 0.0)
                state.external_deposits_total += amount
                # Prefer the explicit post-deposit equity if the payload
                # carries one (deposit-triggered rebase records this);
                # otherwise add the amount to the running equity.
                if "exchange_equity" in payload:
                    state.exchange_equity = float(payload["exchange_equity"])
                else:
                    state.exchange_equity += amount

            elif etype is EventType.CAPITAL_WITHDRAWAL:
                amount = float(payload.get("amount", 0.0) or 0.0)
                if (
                    "profit_part" in payload
                    or "principal_part" in payload
                    or "withdrawal_type" in payload
                ):
                    profit_part = float(payload.get("profit_part", 0.0) or 0.0)
                    principal_part = float(
                        payload.get("principal_part", 0.0) or 0.0
                    )
                else:
                    # Legacy payload (no split) - classify using the
                    # running net_trading_pnl, the same rule the rebase
                    # path uses live.
                    available = max(0.0, state.net_trading_pnl)
                    if amount <= available:
                        profit_part = amount
                        principal_part = 0.0
                    else:
                        profit_part = available
                        principal_part = amount - available
                state.withdrawn_profit += profit_part
                state.principal_withdrawn_total += principal_part

            elif etype is EventType.CAPITAL_REBASE:
                # CAPITAL_REBASE carries the authoritative post-rebase
                # equity. Trust it so Phase 7 capital.db files replay.
                if "exchange_equity" in payload:
                    state.exchange_equity = float(payload["exchange_equity"])
                state.last_rebase_ts = int(event.timestamp)

            # PROFIT_HARVEST / RISK_BUDGET_RECALCULATED do not mutate
            # state on their own. They are recorded for Reflection.

        state.recompute()
        return state

    def reconstruct_current_snapshot(self) -> CapitalState:
        """Reconstruct the current ``CapitalState`` purely from events.db.

        Reads every CAPITAL_* event from the engine's ``EventRepository``
        in deterministic order: ``(timestamp ASC, rowid ASC)``. Using
        ROWID as the tiebreaker preserves the insertion order produced
        by ``EventRepository._insert``, which is critical for capital
        events because a single deposit / withdrawal flow emits 3-4
        events whose payload values can collide on ``timestamp`` at ms
        granularity.

        Hard rule (Issue #8): the reconstructed state MUST match the
        live engine's state for the deposit/withdrawal flows covered by
        ``replay_capital_events``.
        """
        from app.core.events import CAPITAL_EVENT_TYPES

        type_values = [t.value for t in CAPITAL_EVENT_TYPES]
        placeholders = ",".join("?" for _ in type_values)
        cursor = self._event_repo.conn.execute(
            f"""
            SELECT * FROM events
            WHERE event_type IN ({placeholders})
            ORDER BY timestamp ASC, rowid ASC
            """,
            type_values,
        )
        events = [self._event_repo._row_to_event(row) for row in cursor.fetchall()]
        return self.replay_capital_events(
            initial_capital=self.__initial_capital,
            events=events,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _persist_snapshot(self, note: str | None = None) -> CapitalSnapshot | None:
        """Persist current state to capital.db if connection available."""
        if self._capital_conn is None:
            return None
        return persist_capital_snapshot(
            capital_state=self._state,
            capital_conn=self._capital_conn,
            initial_capital=self.__initial_capital,
            note=note,
        )
