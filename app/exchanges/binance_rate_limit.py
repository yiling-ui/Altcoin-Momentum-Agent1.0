"""Binance public-market REST Rate-Limit Governor (Phase 11C.1A).

Why this module exists
----------------------

Phase 11C wired :class:`app.exchanges.binance_public.BinancePublicClient`
to the real Binance USDT-M perpetual public-market endpoints. The first
24h paper observation against the real exchange exposed two failure
modes the existing transport never protected against:

  - HTTP 429 (Too Many Requests). Binance returns this when the
    sliding-window weight budget for the source IP is exceeded. The
    response carries a ``Retry-After`` header (seconds). If the
    gateway keeps issuing requests during the backoff window Binance
    escalates to:
  - HTTP 418 (I'm a teapot). Binance uses 418 to signal a real IP
    ban. Every subsequent request from the same IP will fail until
    the ban expires. The response also carries a ``Retry-After``
    header.

The Phase 11C runner originally fired six REST calls per symbol per
poll loop (``aggTrades`` + ``depth`` + ``fundingRate`` +
``openInterest`` + ``premiumIndex`` + ``bookTicker``) and the loop ran
every 5s. With the default ``symbol_limit=20`` the gateway issued
around 24 requests/sec which is well above the per-IP weight budget,
which is why the 24h test triggered a 418 ban.

This module ships the **Binance Public REST Rate-Limit Governor** that
wraps every public REST call so the gateway:

  - records :rfc:`X-MBX-USED-WEIGHT-1M` from every successful response
    (Binance documents this as the consumed weight in the trailing
    minute window);
  - tracks a rolling weight budget per minute, supports a soft and a
    hard threshold, and refuses to issue a request once the hard
    threshold is crossed;
  - sleeps the requested ``Retry-After`` (or a configured default,
    300 s) on HTTP 429 and emits ``RATE_LIMIT_429`` /
    ``RATE_LIMIT_BACKOFF_STARTED`` / ``RATE_LIMIT_BACKOFF_ENDED`` so
    the daily report and the replay can rebuild the protection
    timeline;
  - latches into a permanent **protection mode** on HTTP 418, emits
    ``RATE_LIMIT_418`` and ``RATE_LIMIT_PROTECTION_ENTERED``, opens a
    P1 incident through :class:`IncidentRepository`, and raises
    :class:`RateLimitProtectionError` on every subsequent call so the
    runner can shut down gracefully;
  - exposes JSON-safe counters the daily report ships verbatim:
    ``rate_limit_429_count``, ``rate_limit_418_count``,
    ``retry_after_seconds_last``, ``retry_after_seconds_total``,
    ``used_weight_1m_last``, ``used_weight_1m_max``,
    ``rest_requests_total``, ``rest_requests_skipped_by_budget``,
    ``rate_limit_protection_triggered``, ``rate_limit_ban``.

Phase 11C.1A boundary
---------------------

  - opens NO socket of its own
  - imports NO third-party HTTP / WebSocket / SDK
  - reads NO ``os.environ``
  - holds NO API credential parameter or literal
  - the four ExchangeClientBase write surfaces are unaffected and
    continue to refuse with :class:`SafeModeViolation`
  - flipping ``mode=paper`` / ``live_trading=False`` /
    ``right_tail=False`` / ``llm=False`` /
    ``exchange_live_orders=False`` /
    ``telegram_outbound_enabled=False`` /
    ``binance_private_api_enabled=False`` is a Phase 12+ concern

The whole module is single-threaded by construction: the Phase 11C
runner is a single-thread polling loop and the governor's
counters are not guarded by a lock. A future async / multi-threaded
runner (Phase 11C.2 PR-B WebSocket-first radar) MUST wrap the
``before_request`` / ``record_response`` / ``handle_*`` calls with
its own mutex.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from loguru import logger

from app.core.clock import now_ms
from app.core.enums import IncidentLevel
from app.core.errors import SafeModeViolation
from app.core.events import Event, EventType


# ---------------------------------------------------------------------------
# Default endpoint weights (Phase 11C public-market subset)
# ---------------------------------------------------------------------------

#: Default per-endpoint weight cost for Binance USDT-M perpetual
#: public-market endpoints. The numbers track Binance's public
#: documentation as of Phase 11C; they err on the conservative side so
#: a future rate-card change cannot accidentally exhaust the budget.
#:
#: Source: Binance Futures public-market REST docs. The values below
#: pin the endpoints Phase 11C actually calls; everything else falls
#: back to ``DEFAULT_FALLBACK_ENDPOINT_WEIGHT``.
DEFAULT_ENDPOINT_WEIGHTS: Mapping[str, int] = {
    "/fapi/v1/exchangeInfo": 1,
    "/fapi/v1/ticker/24hr": 40,
    "/fapi/v1/ticker/bookTicker": 5,
    "/fapi/v1/depth": 20,
    "/fapi/v1/aggTrades": 20,
    "/fapi/v1/trades": 5,
    "/fapi/v1/klines": 5,
    "/fapi/v1/fundingRate": 1,
    "/fapi/v1/openInterest": 1,
    "/fapi/v1/premiumIndex": 1,
}

#: Endpoint weight applied when an unknown path is offered. Keep this
#: pessimistic so a future endpoint addition cannot over-spend the
#: budget before the operator updates the table.
DEFAULT_FALLBACK_ENDPOINT_WEIGHT: int = 10


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class RateLimitProtectionError(SafeModeViolation):
    """Raised once the governor has latched into rate-limit protection.

    A :class:`SafeModeViolation` subclass so the existing Phase 11C
    runner code paths that already catch ``SafeModeViolation`` (env
    guard, allowlist refusal) also catch the protection-mode refusal
    without an additional ``except`` clause. The runner converts this
    exception into ``rc=2`` and shuts down gracefully; it MUST NOT
    auto-retry, MUST NOT swap endpoints, MUST NOT change source IP.
    """


class RateLimitBackoffActive(SafeModeViolation):
    """Raised while a Retry-After backoff window is active.

    The governor uses this to refuse fresh requests during the
    sleep window when callers bypass the synchronous sleep (e.g. a
    test harness that monkeypatches ``time.sleep`` to return
    immediately, or a future async runner that wants to defer the
    next request). The runner treats it the same way as
    ``RateLimitBudgetExceeded``: skip and re-evaluate next loop.
    """


class RateLimitBudgetExceeded(SafeModeViolation):
    """Raised when the configured hard weight budget is exhausted.

    The governor refuses the request before it is sent so we never
    expose ourselves to another 429 / 418. The skipped-by-budget
    counter is incremented so the daily report shows how often this
    fired; the safety flags remain unchanged.
    """


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RestGovernorConfig:
    """Operator-facing configuration knobs.

    All defaults are conservative. The Phase 11C runner reads these
    from ``app.config.settings`` so a YAML / env override flows
    through automatically; tests construct the dataclass inline.

    Attributes:
        weight_budget_per_minute:
            Total weight the governor may consume in any rolling
            60-second window. Phase 11C.1A default is 300, half of
            Binance's documented 1200/min budget for public futures
            data, with extra headroom for shared-IP deployments.
        soft_weight_ratio:
            Once ``used + weight >= soft_ratio * budget`` the governor
            logs at WARNING and flags the next response as ``soft``.
            The request still goes through.
        hard_weight_ratio:
            Once ``used + weight >= hard_ratio * budget`` the governor
            REFUSES the request (raises
            :class:`RateLimitBudgetExceeded`). The skipped-by-budget
            counter is incremented.
        retry_after_default_seconds:
            Sleep length used when an HTTP 429 / 418 response is
            missing the ``Retry-After`` header. Phase 11C.1A defaults
            to 300 s.
        on_429:
            Action to take when an HTTP 429 lands. ``"backoff"`` is
            the only supported value in PR-A (sleep + emit events).
        on_418:
            Action to take when an HTTP 418 lands. ``"shutdown"`` is
            the only supported value in PR-A (latch protection mode +
            raise :class:`RateLimitProtectionError` on every call).
        endpoint_weights:
            Optional overrides to merge on top of
            :data:`DEFAULT_ENDPOINT_WEIGHTS`.
        fallback_endpoint_weight:
            Weight used for any path not covered by
            ``endpoint_weights`` or :data:`DEFAULT_ENDPOINT_WEIGHTS`.
        window_seconds:
            Width of the rolling weight-budget window. Defaults to 60
            because Binance's used-weight header is also a 1-minute
            window.
        enabled:
            ``False`` disables every check (used by the deterministic
            offline test fixture so Phase 11C.0 tests keep passing).
    """

    weight_budget_per_minute: int = 300
    soft_weight_ratio: float = 0.50
    hard_weight_ratio: float = 0.75
    retry_after_default_seconds: int = 300
    on_429: str = "backoff"
    on_418: str = "shutdown"
    endpoint_weights: Mapping[str, int] = field(
        default_factory=lambda: dict(DEFAULT_ENDPOINT_WEIGHTS)
    )
    fallback_endpoint_weight: int = DEFAULT_FALLBACK_ENDPOINT_WEIGHT
    window_seconds: int = 60
    enabled: bool = True

    def __post_init__(self) -> None:
        # Defensive: refuse pathological configs at construction time
        # so a misconfigured operator sees the failure at boot, not at
        # the first 429.
        if self.weight_budget_per_minute <= 0:
            raise ValueError(
                "RestGovernorConfig.weight_budget_per_minute must be > 0"
            )
        if not (0.0 < self.soft_weight_ratio <= 1.0):
            raise ValueError(
                "RestGovernorConfig.soft_weight_ratio must be in (0, 1]"
            )
        if not (0.0 < self.hard_weight_ratio <= 1.0):
            raise ValueError(
                "RestGovernorConfig.hard_weight_ratio must be in (0, 1]"
            )
        if self.soft_weight_ratio > self.hard_weight_ratio:
            raise ValueError(
                "RestGovernorConfig: soft_weight_ratio must be <= "
                "hard_weight_ratio"
            )
        if self.retry_after_default_seconds <= 0:
            raise ValueError(
                "RestGovernorConfig.retry_after_default_seconds must be > 0"
            )
        if self.on_429 not in {"backoff"}:
            raise ValueError(
                "RestGovernorConfig.on_429 must be 'backoff' in PR-A"
            )
        if self.on_418 not in {"shutdown"}:
            raise ValueError(
                "RestGovernorConfig.on_418 must be 'shutdown' in PR-A"
            )
        if self.window_seconds <= 0:
            raise ValueError(
                "RestGovernorConfig.window_seconds must be > 0"
            )
        if self.fallback_endpoint_weight <= 0:
            raise ValueError(
                "RestGovernorConfig.fallback_endpoint_weight must be > 0"
            )


# ---------------------------------------------------------------------------
# Response envelope
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PublicRestResponse:
    """Transport-agnostic response envelope.

    The Phase 11C transport (urllib + the dry-run fixture) wraps every
    response in this dataclass so the governor can inspect the HTTP
    status and any rate-limit headers without leaking transport
    details into :class:`BinancePublicClient`.

    Tests inject a transport that returns plain dicts / lists (the
    legacy contract); the client adapts that to a default 200/no-header
    envelope so the governor still sees a consistent shape.
    """

    body: Any
    status: int = 200
    headers: Mapping[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Optional protection hook (duck-typed; usually IncidentRepository)
# ---------------------------------------------------------------------------
class _ProtectionHookProtocol:
    """Minimal callable surface the governor needs.

    :class:`app.incidents.repository.IncidentRepository` satisfies
    this duck-typed protocol. Tests pass a recording stub.
    """

    def open_incident(  # pragma: no cover - protocol illustration only
        self,
        *,
        level: IncidentLevel,
        title: str,
        description: str,
        source_module: str,
        symbol: str | None,
        position_id: str | None,
        payload: dict[str, Any],
    ) -> str:
        ...


# ---------------------------------------------------------------------------
# Governor
# ---------------------------------------------------------------------------


class BinancePublicRestGovernor:
    """Sliding-window weight budget + 429/418 protection.

    Lifecycle:

      1. The client calls :meth:`before_request` BEFORE a REST call.
         The governor:
           - refuses if protection mode is latched
             (:class:`RateLimitProtectionError`);
           - refuses if a Retry-After backoff is still active
             (:class:`RateLimitBackoffActive`);
           - refuses if the hard weight budget is exhausted
             (:class:`RateLimitBudgetExceeded`).
         Otherwise it RESERVES the planned weight and returns the
         resolved endpoint cost.

      2. The client issues the request, then calls
         :meth:`record_response` with the resulting
         :class:`PublicRestResponse`. The governor:
           - reads ``X-MBX-USED-WEIGHT-1M`` and
             ``X-MBX-ORDER-COUNT-1M`` if present;
           - on status 429: emits ``RATE_LIMIT_429`` +
             ``RATE_LIMIT_BACKOFF_STARTED``, sleeps the requested
             ``Retry-After`` (or the configured default), emits
             ``RATE_LIMIT_BACKOFF_ENDED``;
           - on status 418: emits ``RATE_LIMIT_418`` +
             ``RATE_LIMIT_PROTECTION_ENTERED``, opens a P1 incident
             through the configured :class:`ProtectionHook`, and
             raises :class:`RateLimitProtectionError`.

      3. If the transport itself raised before producing a response
         (e.g. a TCP failure), the client calls
         :meth:`record_transport_error`. The governor releases the
         reserved weight so the transient failure does not double-bill
         the budget.
    """

    SOURCE_MODULE = "exchanges.binance_rate_limit"

    USED_WEIGHT_HEADER = "X-MBX-USED-WEIGHT-1M"
    USED_WEIGHT_HEADER_LOWER = "x-mbx-used-weight-1m"
    RETRY_AFTER_HEADER = "Retry-After"
    RETRY_AFTER_HEADER_LOWER = "retry-after"

    def __init__(
        self,
        *,
        config: RestGovernorConfig | None = None,
        event_repo: Any = None,
        protection_hook: _ProtectionHookProtocol | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock_fn: Callable[[], float] = time.monotonic,
        wallclock_fn: Callable[[], int] = now_ms,
    ) -> None:
        self._config = config or RestGovernorConfig()
        self._event_repo = event_repo
        self._protection_hook = protection_hook
        self._sleep_fn = sleep_fn
        self._clock_fn = clock_fn
        self._wallclock_fn = wallclock_fn

        # Sliding-window weight ledger: (timestamp_seconds, weight).
        self._weight_window: deque[tuple[float, int]] = deque()
        self._reserved_weight: int = 0

        # Protection-mode latch.
        self._protection_mode: bool = False
        self._protection_reason: str | None = None
        self._protection_triggered_at_ms: int | None = None
        self._rate_limit_ban: bool = False

        # Backoff window state (set by 429 handler).
        self._backoff_until_monotonic: float | None = None
        self._backoff_started_at_ms: int | None = None

        # Counters. All are JSON-safe and exposed verbatim by
        # :meth:`metrics_payload` for the daily report.
        self._rest_requests_total: int = 0
        self._rest_requests_skipped_by_budget: int = 0
        self._rate_limit_429_count: int = 0
        self._rate_limit_418_count: int = 0
        self._retry_after_seconds_last: int = 0
        self._retry_after_seconds_total: int = 0
        self._used_weight_1m_last: int = 0
        self._used_weight_1m_max: int = 0
        self._soft_threshold_breached_count: int = 0
        self._backoff_started_count: int = 0
        self._backoff_ended_count: int = 0
        self._protection_incident_id: str | None = None

    # ------------------------------------------------------------------
    # Public introspection
    # ------------------------------------------------------------------
    @property
    def config(self) -> RestGovernorConfig:
        return self._config

    @property
    def in_protection_mode(self) -> bool:
        return self._protection_mode

    @property
    def rate_limit_ban(self) -> bool:
        return self._rate_limit_ban

    @property
    def used_weight_1m_last(self) -> int:
        return self._used_weight_1m_last

    @property
    def used_weight_1m_max(self) -> int:
        return self._used_weight_1m_max

    @property
    def rest_requests_total(self) -> int:
        return self._rest_requests_total

    @property
    def rest_requests_skipped_by_budget(self) -> int:
        return self._rest_requests_skipped_by_budget

    @property
    def rate_limit_429_count(self) -> int:
        return self._rate_limit_429_count

    @property
    def rate_limit_418_count(self) -> int:
        return self._rate_limit_418_count

    @property
    def retry_after_seconds_last(self) -> int:
        return self._retry_after_seconds_last

    @property
    def retry_after_seconds_total(self) -> int:
        return self._retry_after_seconds_total

    @property
    def protection_incident_id(self) -> str | None:
        return self._protection_incident_id

    # ------------------------------------------------------------------
    # Endpoint weight lookup
    # ------------------------------------------------------------------
    def weight_for(self, endpoint_path: str) -> int:
        """Return the weight cost the governor will charge for
        ``endpoint_path``.

        Lookup precedence:

          1. Operator overrides via ``config.endpoint_weights``;
          2. :data:`DEFAULT_ENDPOINT_WEIGHTS`;
          3. ``config.fallback_endpoint_weight``.
        """
        if not endpoint_path:
            return self._config.fallback_endpoint_weight
        path = endpoint_path.split("?", 1)[0]
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")
        if path in self._config.endpoint_weights:
            return int(self._config.endpoint_weights[path])
        if path in DEFAULT_ENDPOINT_WEIGHTS:
            return int(DEFAULT_ENDPOINT_WEIGHTS[path])
        return int(self._config.fallback_endpoint_weight)

    # ------------------------------------------------------------------
    # Rolling-window budget arithmetic
    # ------------------------------------------------------------------
    def _purge_window(self, *, now_seconds: float | None = None) -> None:
        if not self._weight_window:
            return
        now = now_seconds if now_seconds is not None else self._clock_fn()
        cutoff = now - float(self._config.window_seconds)
        while self._weight_window and self._weight_window[0][0] <= cutoff:
            self._weight_window.popleft()

    def _used_weight_in_window(self) -> int:
        self._purge_window()
        return sum(weight for _, weight in self._weight_window)

    @property
    def reserved_weight(self) -> int:
        return self._reserved_weight

    # ------------------------------------------------------------------
    # Backoff window
    # ------------------------------------------------------------------
    def _is_in_backoff(self) -> bool:
        if self._backoff_until_monotonic is None:
            return False
        if self._clock_fn() >= self._backoff_until_monotonic:
            self._end_backoff()
            return False
        return True

    def _end_backoff(self) -> None:
        if self._backoff_until_monotonic is None:
            return
        self._backoff_until_monotonic = None
        started_ms = self._backoff_started_at_ms
        self._backoff_started_at_ms = None
        self._backoff_ended_count += 1
        self._emit_event(
            event_type=EventType.RATE_LIMIT_BACKOFF_ENDED,
            payload={
                "started_at_ms": started_ms,
                "ended_at_ms": self._wallclock_fn(),
                "retry_after_seconds_last": self._retry_after_seconds_last,
                "retry_after_seconds_total": self._retry_after_seconds_total,
                "rate_limit_429_count": self._rate_limit_429_count,
            },
        )

    # ------------------------------------------------------------------
    # Public lifecycle hooks
    # ------------------------------------------------------------------
    def before_request(
        self,
        endpoint_path: str,
        *,
        weight: int | None = None,
    ) -> int:
        """Reserve weight for an upcoming REST request.

        Returns the resolved weight cost. Raises
        :class:`RateLimitProtectionError` /
        :class:`RateLimitBackoffActive` /
        :class:`RateLimitBudgetExceeded` per the governor contract.
        """
        if not self._config.enabled:
            return 0

        if self._protection_mode:
            raise RateLimitProtectionError(
                "BinancePublicRestGovernor: protection mode is latched. "
                "No further public REST request may be issued. "
                f"Reason: {self._protection_reason!r}"
            )

        if self._is_in_backoff():
            raise RateLimitBackoffActive(
                "BinancePublicRestGovernor: Retry-After backoff window is "
                "still active; refusing to issue a public REST request."
            )

        cost = int(weight) if weight is not None else self.weight_for(endpoint_path)
        if cost <= 0:
            cost = self._config.fallback_endpoint_weight

        used = self._used_weight_in_window() + self._reserved_weight
        budget = int(self._config.weight_budget_per_minute)
        soft = int(budget * self._config.soft_weight_ratio)
        hard = int(budget * self._config.hard_weight_ratio)

        if used + cost > hard:
            self._rest_requests_skipped_by_budget += 1
            logger.warning(
                "[phase11c.1a] rest budget exhausted: used={} reserved={} "
                "cost={} hard={} budget={} endpoint={}",
                used - self._reserved_weight,
                self._reserved_weight,
                cost,
                hard,
                budget,
                endpoint_path,
            )
            raise RateLimitBudgetExceeded(
                f"BinancePublicRestGovernor: refusing {endpoint_path!r} "
                f"(cost={cost}); used+reserved={used} would exceed hard "
                f"budget {hard}/{budget}."
            )

        if used + cost > soft:
            # Soft-budget warning: log but DO NOT refuse. The runner
            # may use this signal to slow itself down.
            self._soft_threshold_breached_count += 1
            logger.warning(
                "[phase11c.1a] rest soft-budget breach: used+cost={} "
                "soft={} hard={} budget={} endpoint={}",
                used + cost,
                soft,
                hard,
                budget,
                endpoint_path,
            )

        self._reserved_weight += cost
        return cost

    def record_response(
        self,
        endpoint_path: str,
        response: PublicRestResponse,
        *,
        weight: int | None = None,
    ) -> None:
        """Record a (real or fixture) response.

        Always commits the previously-reserved weight to the rolling
        window (so a 429 still costs the budget that triggered it).
        Then dispatches to the 429 / 418 handlers based on
        ``response.status``.
        """
        if not self._config.enabled:
            return

        cost = int(weight) if weight is not None else self.weight_for(endpoint_path)
        if cost <= 0:
            cost = self._config.fallback_endpoint_weight
        # Move the reservation into the rolling window.
        self._reserved_weight = max(0, self._reserved_weight - cost)
        self._weight_window.append((self._clock_fn(), cost))
        self._rest_requests_total += 1
        self._purge_window()

        # Update used-weight headers if present.
        used_weight = _read_header(response.headers, self.USED_WEIGHT_HEADER)
        if used_weight is not None:
            try:
                weight_value = int(used_weight)
            except (TypeError, ValueError):
                weight_value = None
            if weight_value is not None and weight_value >= 0:
                self._used_weight_1m_last = weight_value
                if weight_value > self._used_weight_1m_max:
                    self._used_weight_1m_max = weight_value

        if response.status == 429:
            self._handle_429(endpoint_path=endpoint_path, response=response)
            return
        if response.status == 418:
            self._handle_418(endpoint_path=endpoint_path, response=response)
            return
        # Defensive: any other 4xx / 5xx is the client's problem; the
        # governor's job is bounded to 429 / 418 in PR-A. Phase 11C.1B
        # PR-B may add WS-side handling here.

    def record_transport_error(
        self,
        endpoint_path: str,
        *,
        weight: int | None = None,
        error: BaseException | None = None,
    ) -> None:
        """Release the reserved weight after a transport-level failure.

        Called when the transport raised before producing any response
        (DNS failure, TCP reset, JSON decode error). The governor
        un-reserves the planned weight so the failure does not
        double-bill the rolling budget. The request is NOT counted
        in ``rest_requests_total`` because no REST byte landed.
        """
        if not self._config.enabled:
            return
        cost = int(weight) if weight is not None else self.weight_for(endpoint_path)
        if cost <= 0:
            cost = self._config.fallback_endpoint_weight
        self._reserved_weight = max(0, self._reserved_weight - cost)
        if error is not None:
            logger.debug(
                "[phase11c.1a] transport error released weight={} endpoint={} "
                "error={}",
                cost,
                endpoint_path,
                error,
            )

    # ------------------------------------------------------------------
    # 429 handler
    # ------------------------------------------------------------------
    def _handle_429(
        self,
        *,
        endpoint_path: str,
        response: PublicRestResponse,
    ) -> None:
        retry_after = _parse_retry_after(
            response.headers,
            default_seconds=self._config.retry_after_default_seconds,
        )
        self._rate_limit_429_count += 1
        self._retry_after_seconds_last = int(retry_after)
        self._retry_after_seconds_total += int(retry_after)
        started_ms = self._wallclock_fn()
        self._backoff_started_at_ms = started_ms
        self._backoff_started_count += 1
        self._backoff_until_monotonic = self._clock_fn() + float(retry_after)

        used_weight_header = _read_header(
            response.headers, self.USED_WEIGHT_HEADER
        )
        self._emit_event(
            event_type=EventType.RATE_LIMIT_429,
            payload={
                "endpoint": endpoint_path,
                "retry_after_seconds": int(retry_after),
                "used_weight_1m": used_weight_header,
                "used_weight_1m_last_recorded": self._used_weight_1m_last,
                "rate_limit_429_count": self._rate_limit_429_count,
                "started_at_ms": started_ms,
            },
        )
        self._emit_event(
            event_type=EventType.RATE_LIMIT_BACKOFF_STARTED,
            payload={
                "endpoint": endpoint_path,
                "retry_after_seconds": int(retry_after),
                "started_at_ms": started_ms,
                "rate_limit_429_count": self._rate_limit_429_count,
            },
        )
        logger.error(
            "[phase11c.1a] HTTP 429 from {}; sleeping retry_after={}s",
            endpoint_path,
            retry_after,
        )

        # PR-A only ships the synchronous backoff. The brief is
        # explicit: the runner must NOT keep firing requests during
        # the backoff window. We sleep here so any caller using the
        # default monotonic clock observes the gate.
        try:
            self._sleep_fn(float(retry_after))
        finally:
            # Always end the backoff window so a monkeypatched sleep
            # (tests) and a real sleep (production) both terminate
            # cleanly.
            self._end_backoff()

    # ------------------------------------------------------------------
    # 418 handler
    # ------------------------------------------------------------------
    def _handle_418(
        self,
        *,
        endpoint_path: str,
        response: PublicRestResponse,
    ) -> None:
        retry_after = _parse_retry_after(
            response.headers,
            default_seconds=self._config.retry_after_default_seconds,
        )
        self._rate_limit_418_count += 1
        self._retry_after_seconds_last = int(retry_after)
        self._retry_after_seconds_total += int(retry_after)
        self._protection_mode = True
        self._rate_limit_ban = True
        self._protection_reason = (
            f"http_418_from_{endpoint_path} "
            f"retry_after={int(retry_after)}s"
        )
        self._protection_triggered_at_ms = self._wallclock_fn()

        self._emit_event(
            event_type=EventType.RATE_LIMIT_418,
            payload={
                "endpoint": endpoint_path,
                "retry_after_seconds": int(retry_after),
                "rate_limit_418_count": self._rate_limit_418_count,
                "rate_limit_ban": True,
                "triggered_at_ms": self._protection_triggered_at_ms,
            },
        )
        self._emit_event(
            event_type=EventType.RATE_LIMIT_PROTECTION_ENTERED,
            payload={
                "endpoint": endpoint_path,
                "reason": self._protection_reason,
                "retry_after_seconds": int(retry_after),
                "rate_limit_429_count": self._rate_limit_429_count,
                "rate_limit_418_count": self._rate_limit_418_count,
                "triggered_at_ms": self._protection_triggered_at_ms,
            },
        )
        if self._protection_hook is not None:
            try:
                incident_id = self._protection_hook.open_incident(
                    level=IncidentLevel.P1,
                    title="Binance public REST: HTTP 418 IP ban",
                    description=(
                        "Phase 11C public REST gateway received an HTTP "
                        "418 (I'm a teapot) from Binance. This signals "
                        "an IP-level rate-limit ban. The governor has "
                        "latched into protection mode and refuses every "
                        "subsequent public REST request. The Phase 11C "
                        "runner must shut down gracefully without "
                        "auto-retry, without endpoint switching, and "
                        "without source-IP rotation. Safety flags are "
                        "preserved (mode=paper, live_trading=False, "
                        "right_tail=False, llm=False, "
                        "exchange_live_orders=False, "
                        "telegram_outbound_enabled=False, "
                        "binance_private_api_enabled=False)."
                    ),
                    source_module=self.SOURCE_MODULE,
                    symbol=None,
                    position_id=None,
                    payload={
                        "endpoint": endpoint_path,
                        "retry_after_seconds": int(retry_after),
                        "rate_limit_429_count": self._rate_limit_429_count,
                        "rate_limit_418_count": self._rate_limit_418_count,
                        "rate_limit_ban": True,
                        "triggered_at_ms": self._protection_triggered_at_ms,
                    },
                )
            except Exception as exc:  # pragma: no cover - protective
                logger.error(
                    "[phase11c.1a] protection hook failed to open incident: {}",
                    exc,
                )
                incident_id = None
            self._protection_incident_id = incident_id

        logger.critical(
            "[phase11c.1a] HTTP 418 from {}; latching protection mode "
            "(retry_after={}s)",
            endpoint_path,
            retry_after,
        )
        raise RateLimitProtectionError(
            "BinancePublicRestGovernor: HTTP 418 received from Binance. "
            f"Endpoint: {endpoint_path!r}. Retry-After: {int(retry_after)}s. "
            "Protection mode is latched; no further public REST request "
            "will be issued. Phase 11C runner must shut down."
        )

    # ------------------------------------------------------------------
    # Daily report payload
    # ------------------------------------------------------------------
    def metrics_payload(self) -> dict[str, Any]:
        """Return the JSON-safe metrics block.

        Field names match the Phase 11C.1A daily-report spec verbatim.
        """
        return {
            "rate_limit_429_count": int(self._rate_limit_429_count),
            "rate_limit_418_count": int(self._rate_limit_418_count),
            "retry_after_seconds_last": int(self._retry_after_seconds_last),
            "retry_after_seconds_total": int(self._retry_after_seconds_total),
            "used_weight_1m_last": int(self._used_weight_1m_last),
            "used_weight_1m_max": int(self._used_weight_1m_max),
            "rest_requests_total": int(self._rest_requests_total),
            "rest_requests_skipped_by_budget": int(
                self._rest_requests_skipped_by_budget
            ),
            "rate_limit_protection_triggered": bool(self._protection_mode),
            "rate_limit_ban": bool(self._rate_limit_ban),
            "soft_threshold_breached_count": int(
                self._soft_threshold_breached_count
            ),
            "backoff_started_count": int(self._backoff_started_count),
            "backoff_ended_count": int(self._backoff_ended_count),
            "weight_budget_per_minute": int(
                self._config.weight_budget_per_minute
            ),
            "soft_weight_ratio": float(self._config.soft_weight_ratio),
            "hard_weight_ratio": float(self._config.hard_weight_ratio),
            "retry_after_default_seconds": int(
                self._config.retry_after_default_seconds
            ),
            "on_429": str(self._config.on_429),
            "on_418": str(self._config.on_418),
            "protection_incident_id": self._protection_incident_id,
        }

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------
    def _emit_event(self, *, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_repo is None:
            return
        try:
            self._event_repo.append(
                Event(
                    event_type=event_type,
                    source_module=self.SOURCE_MODULE,
                    symbol=None,
                    timestamp=self._wallclock_fn(),
                    payload=dict(payload),
                )
            )
        except Exception as exc:  # pragma: no cover - protective
            logger.error(
                "[phase11c.1a] failed to emit {}: {}",
                event_type.value,
                exc,
            )


# ---------------------------------------------------------------------------
# Header helpers
# ---------------------------------------------------------------------------
def _read_header(headers: Mapping[str, str], name: str) -> str | None:
    """Return the first matching header value (case-insensitive)."""
    if not headers:
        return None
    if name in headers:
        return headers[name]
    lower = name.lower()
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == lower:
            return value
    return None


def _parse_retry_after(
    headers: Mapping[str, str],
    *,
    default_seconds: int,
) -> int:
    """Return the Retry-After header value in seconds.

    Binance documents Retry-After as an integer number of seconds. We
    accept that form plus fractional seconds (rounded down) and the
    HTTP-date form (RFC 7231) parsed by :mod:`email.utils.parsedate_tz`.
    Anything malformed falls back to ``default_seconds`` so the
    governor never sleeps for zero.
    """
    raw = _read_header(headers, "Retry-After")
    if raw is None:
        return int(default_seconds)
    text = str(raw).strip()
    if not text:
        return int(default_seconds)
    try:
        seconds = int(float(text))
        if seconds <= 0:
            return int(default_seconds)
        return seconds
    except (TypeError, ValueError):
        pass
    # HTTP-date form. Use the stdlib parser so we never pull in a
    # third-party dependency (Phase 11C.1A audit forbids it).
    try:
        from email.utils import parsedate_to_datetime
        from datetime import datetime, timezone

        parsed = parsedate_to_datetime(text)
        if parsed is None:
            return int(default_seconds)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        delta = (parsed - datetime.now(timezone.utc)).total_seconds()
        if delta <= 0:
            return int(default_seconds)
        return int(delta)
    except Exception:
        return int(default_seconds)


__all__ = [
    "BinancePublicRestGovernor",
    "DEFAULT_ENDPOINT_WEIGHTS",
    "DEFAULT_FALLBACK_ENDPOINT_WEIGHT",
    "PublicRestResponse",
    "RateLimitBackoffActive",
    "RateLimitBudgetExceeded",
    "RateLimitProtectionError",
    "RestGovernorConfig",
]
