"""Phase 11C.1B - SymbolUniverse: exchangeInfo-as-truth symbol gate.

Why this module exists
----------------------

Binance USDT-M Futures lists contracts whose symbol contains
non-ASCII characters - e.g. ``我踏马来了USDT``, ``币安人生USDT``. Each
of those is a real Binance contract with its own
``/fapi/v1/exchangeInfo`` entry, its own WS push under
``!ticker@arr`` / ``!miniTicker@arr`` / ``!bookTicker`` /
``!markPrice@arr`` / ``!forceOrder@arr``, and its own
``/fapi/v1/depth`` / ``/fapi/v1/aggTrades`` REST detail endpoint. Any
symbol filter that uses an ASCII-only character class
(e.g. ``^[A-Z0-9_]{2,30}(USDT|USDC)$``) silently loses discovery of
every exotic listing the moment Binance adds one.

The Phase 11C.1B contract is therefore:

  - the ONLY authoritative symbol set is the snapshot pulled from
    ``/fapi/v1/exchangeInfo`` at runner startup;
  - the radar and the candidate pool admit any symbol that is in
    that set, regardless of character class (Chinese / Cyrillic /
    Arabic / emoji-bearing - all welcome IF Binance lists them);
  - symbols NOT in the set surface a typed ``WS_SYMBOL_REJECTED``
    event (a free-standing :class:`app.core.events.EventType`); the
    candidate is silently dropped from the pool.

Do NOT introduce
----------------

- any ASCII-only regex (e.g. ``^[A-Z0-9_]{2,30}USDT$``);
- any character-class filter that would refuse a symbol just because
  its codepoint is above 0x7f;
- any locale-dependent ``.upper()`` / ``.lower()`` that would mangle
  a Turkish dotless-I or other non-ASCII codepoint.

The audit test
``tests/unit/test_phase11c_1b_symbol_universe.py
::test_symbol_validation_uses_exchange_info_not_ascii_regex``
fails the next PR that does any of the above.

Phase 11C.1B safety boundary unchanged
--------------------------------------

This module reads NO credential, opens NO socket, calls NO REST
itself. It is a pure value object + a small membership test. The
runner is responsible for bootstrapping it from
``BinancePublicClient.get_symbols()`` (which the Phase 11C client
already exposes through the public ``/fapi/v1/exchangeInfo``
surface).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from loguru import logger

from app.core.clock import now_ms
from app.core.events import Event, EventType


#: Source-module tag for the typed ``WS_SYMBOL_REJECTED`` event. The
#: daily-report aggregator filters on this prefix to surface symbols
#: that drifted out of ``exchangeInfo`` between the bootstrap snapshot
#: and a live WS push.
SOURCE_MODULE: str = "market_data_public.symbol_universe"


#: Reason tag emitted on the ``WS_SYMBOL_REJECTED`` payload when the
#: rejected symbol is missing from the bootstrapped ``exchangeInfo``
#: set. A future reason-tag (e.g. ``not_perpetual``) can be added
#: without touching the event-vocabulary contract.
REASON_NOT_IN_EXCHANGE_INFO: str = "ws_symbol_not_in_exchange_info"


@dataclass(frozen=True)
class SymbolUniverse:
    """Read-only snapshot of the exchangeInfo valid-symbol set.

    Wraps a :class:`frozenset` of canonical symbols. The candidate
    pool consults :meth:`is_valid` for every WS-radar symbol it
    considers admitting; symbols missing from the set are NOT
    silently accepted - the pool emits :data:`EventType.WS_SYMBOL_REJECTED`
    via the supplied ``event_repo`` so the daily report can audit
    drift between the bootstrap exchangeInfo snapshot and live WS
    pushes.

    The ``empty()`` universe (``bootstrapped=False``) admits every
    symbol; this is the back-compat fallback for the existing
    in-process / dry-run / fixture tests that never opened a real
    REST connection. The runner only constructs an empty universe
    when ``--dry-run`` is set OR when the bootstrap REST call
    failed - and in the latter case the runner already emits its own
    degraded-mode event before falling back.

    Phase 11C.1B audit invariants
    -----------------------------

    1. The ``valid_symbol_set`` is built from
       ``BinancePublicClient.get_symbols()``, which itself filters
       ``/fapi/v1/exchangeInfo`` to ``contractType=PERPETUAL`` +
       ``quoteAsset=USDT``. There is NO further character-class
       filter before the symbol lands here.
    2. Membership is exact-match on the canonical string Binance
       returns. We do NOT case-fold (``.upper()`` / ``.lower()``)
       because non-ASCII codepoints can be locale-sensitive; we do
       strip surrounding whitespace because Binance occasionally
       round-trips trailing whitespace through JSON.
    3. The universe is immutable after construction. A subsequent
       mid-run refresh creates a fresh :class:`SymbolUniverse`; the
       runner swaps the reference atomically.
    """

    valid_symbol_set: frozenset[str] = frozenset()
    bootstrapped: bool = False
    bootstrap_ts_ms: int | None = None
    source: str = "exchange_info"

    @classmethod
    def empty(cls) -> "SymbolUniverse":
        """Return the 'admit everything' fallback.

        Used by:

          - :class:`scripts.run_public_market_paper.main` when
            ``--dry-run`` is set (the in-process pump pushes synthetic
            symbols that may not exist on Binance);
          - the existing in-process / fixture tests that never call
            ``/fapi/v1/exchangeInfo``.

        ``is_valid`` returns ``True`` for every non-empty symbol on
        an empty universe. The candidate pool therefore behaves
        EXACTLY as it did before Phase 11C.1B introduced the gate -
        no behavioural regression for any existing fixture.
        """
        return cls(
            valid_symbol_set=frozenset(),
            bootstrapped=False,
            bootstrap_ts_ms=None,
            source="empty_admit_all",
        )

    @classmethod
    def from_exchange_info(
        cls,
        symbols: Iterable[str],
        *,
        clock_fn=now_ms,
    ) -> "SymbolUniverse":
        """Build a bootstrapped universe from a list of symbol strings.

        ``symbols`` is typically ``[s.symbol for s in client.get_symbols()]``
        in the runner. Every entry is run through ``str(...).strip()``
        before insertion; empty entries are skipped. We do NOT
        case-fold because non-ASCII codepoints can be locale-sensitive
        and Binance returns symbols in the canonical case it intends
        to use over the WS streams.
        """
        canonical: set[str] = set()
        for raw in symbols:
            text = str(raw).strip()
            if not text:
                continue
            canonical.add(text)
        return cls(
            valid_symbol_set=frozenset(canonical),
            bootstrapped=True,
            bootstrap_ts_ms=int(clock_fn()),
            source="exchange_info",
        )

    def is_valid(self, symbol: str) -> bool:
        """Return ``True`` if the symbol is admissible.

        Empty / whitespace-only symbols are always rejected. On an
        un-bootstrapped (empty) universe every other non-empty symbol
        is admitted - this is the back-compat fallback. On a
        bootstrapped universe the check is exact-match on the
        canonical string Binance returned for ``/fapi/v1/exchangeInfo``;
        non-ASCII codepoints flow through unchanged.
        """
        if symbol is None:
            return False
        text = str(symbol).strip()
        if not text:
            return False
        if not self.bootstrapped:
            # Back-compat: admit anything non-empty. The runner is
            # responsible for emitting WS_SYMBOL_REJECTED only when
            # the universe was actually bootstrapped (i.e. the
            # exchangeInfo snapshot is reliable).
            return True
        return text in self.valid_symbol_set

    def __contains__(self, symbol: str) -> bool:
        return self.is_valid(symbol)

    def __len__(self) -> int:
        return len(self.valid_symbol_set)

    def metrics_payload(self) -> dict[str, Any]:
        """Return a JSON-safe metrics block for the daily report."""
        return {
            "ws_symbol_universe_bootstrapped": bool(self.bootstrapped),
            "ws_symbol_universe_size": int(len(self.valid_symbol_set)),
            "ws_symbol_universe_source": str(self.source),
            "ws_symbol_universe_bootstrap_ts_ms": (
                int(self.bootstrap_ts_ms)
                if self.bootstrap_ts_ms is not None
                else None
            ),
        }


def emit_symbol_rejected(
    event_repo: Any,
    *,
    symbol: str,
    reason: str = REASON_NOT_IN_EXCHANGE_INFO,
    extra_payload: dict[str, Any] | None = None,
    clock_fn=now_ms,
    source_module: str = SOURCE_MODULE,
) -> None:
    """Emit one ``WS_SYMBOL_REJECTED`` event.

    Centralised so every call site (candidate pool, future
    radar-side gates, runner-side validators) emits the same event
    shape with the same payload contract. Silent if ``event_repo``
    is ``None`` (back-compat for fixture tests that don't wire a
    repo).
    """
    if event_repo is None:
        return
    payload: dict[str, Any] = {
        "symbol": str(symbol),
        "reason": str(reason),
    }
    if extra_payload:
        payload.update(extra_payload)
    try:
        event_repo.append(
            Event(
                event_type=EventType.WS_SYMBOL_REJECTED,
                source_module=source_module,
                symbol=str(symbol),
                timestamp=int(clock_fn()),
                payload=payload,
            )
        )
    except Exception as exc:  # pragma: no cover - protective
        logger.warning(
            "[phase11c.1b] failed to emit WS_SYMBOL_REJECTED for {}: {}",
            symbol,
            exc,
        )


__all__ = [
    "REASON_NOT_IN_EXCHANGE_INFO",
    "SOURCE_MODULE",
    "SymbolUniverse",
    "emit_symbol_rejected",
]
