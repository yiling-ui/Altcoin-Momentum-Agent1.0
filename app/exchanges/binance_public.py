"""Binance public-market read-only client (Phase 11C - Issue #11C).

Phase 11C contract
------------------

This module is the FIRST gateway in the project allowed to talk to a
real exchange. It is **public-data-only**:

  - no Binance API key, no Binance API secret
  - no signed endpoint, no ``signature`` query parameter, no ``timestamp``
  - no account / order / position / leverage / margin endpoint
  - no write surface (the four ``SafeModeViolation`` refusals are
    inherited from :class:`ExchangeClientBase` unchanged)
  - no LLM, no Telegram, no DeepSeek
  - no real funds, no live trading, no right-tail amplification

The class enforces these rules itself:

  - Passing ``api_key`` / ``api_secret`` to the constructor raises
    :class:`SafeModeViolation` immediately (defence-in-depth above the
    Phase 3 :class:`BinanceClient` check).
  - Every URL passed through :meth:`_request` is run through
    :func:`assert_public_endpoint_allowed`. Any path not on the
    Phase 11C allowlist raises :class:`SafeModeViolation`.
  - Every URL must originate from a Binance public market data host
    (``fapi.binance.com`` for USDT-M perpetual futures public data).

The default transport uses :mod:`urllib.request` from the Python
standard library. No third-party HTTP / WebSocket library is imported,
so :file:`tests/unit/test_phase3_no_network.py` and the future
Phase 11C source-tree audit continue to hold for the wider package.
Tests inject a deterministic in-process ``transport`` callable so the
test suite never opens a real socket.

Spec references
---------------

  - §13   Exchange Gateway 交易所接入层
  - §14   Market Data Buffer health behaviour
  - §13.2 Mandatory rules: no real orders, no signed endpoints
  - §13.3 Data reliability tiers A/B/C/D
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from loguru import logger

from app.core.clock import now_ms
from app.core.enums import DataReliability
from app.core.errors import ExchangeError, SafeModeViolation
from app.exchanges.base import ExchangeClientBase, WebSocketManager
from app.exchanges.binance_rate_limit import (
    BinancePublicRestGovernor,
    PublicRestResponse,
    RateLimitBackoffActive,
    RateLimitBudgetExceeded,
    RateLimitProtectionError,
)
from app.exchanges.models import (
    AccountSnapshot,
    ExchangeSymbol,
    FundingRate,
    OpenInterest,
    OrderBook,
    OrderBookLevel,
    RecentTrade,
    TradeSide,
)


# ---------------------------------------------------------------------------
# Endpoint allowlist (Phase 11C-9)
# ---------------------------------------------------------------------------

#: Hard-coded set of Binance USDT-M perpetual futures **public market**
#: endpoint paths that this client is allowed to call. Any path not in
#: this set raises :class:`SafeModeViolation` regardless of how it is
#: composed (querystring, host, scheme).
PUBLIC_MARKET_ENDPOINT_ALLOWLIST: frozenset[str] = frozenset(
    {
        "/fapi/v1/exchangeInfo",
        "/fapi/v1/ticker/24hr",
        "/fapi/v1/ticker/bookTicker",
        "/fapi/v1/klines",
        "/fapi/v1/aggTrades",
        "/fapi/v1/trades",
        "/fapi/v1/depth",
        "/fapi/v1/fundingRate",
        "/fapi/v1/openInterest",
        "/fapi/v1/premiumIndex",
    }
)

#: Endpoints that REQUIRE an authenticated signature. They are NEVER
#: callable from this client. The list is exhaustive enough for
#: ``test_public_endpoint_allowlist_rejects_order_endpoint`` and the
#: future Phase 11D / Phase 12 audits to pin specific paths; the
#: allowlist above is the single source of truth at runtime.
FORBIDDEN_PRIVATE_ENDPOINTS: frozenset[str] = frozenset(
    {
        # Trading
        "/fapi/v1/order",
        "/fapi/v1/order/test",
        "/fapi/v1/batchOrders",
        "/fapi/v1/allOrders",
        "/fapi/v1/openOrders",
        "/fapi/v1/openOrder",
        "/fapi/v1/userTrades",
        # Account / position / leverage / margin
        "/fapi/v2/account",
        "/fapi/v2/balance",
        "/fapi/v2/positionRisk",
        "/fapi/v1/positionRisk",
        "/fapi/v1/positionSide/dual",
        "/fapi/v1/leverage",
        "/fapi/v1/marginType",
        "/fapi/v1/positionMargin",
        "/fapi/v1/income",
        "/fapi/v1/leverageBracket",
        "/fapi/v1/multiAssetsMargin",
        "/fapi/v1/listenKey",
    }
)

#: Forbidden query parameter names that imply a signed / authenticated
#: request. Any URL carrying one of these is refused, even if its path
#: appears in the allowlist (defence-in-depth).
FORBIDDEN_QUERY_PARAMETERS: frozenset[str] = frozenset(
    {"signature", "timestamp", "recvWindow", "apiKey"}
)

#: Hosts the client is permitted to talk to.
ALLOWED_PUBLIC_HOSTS: frozenset[str] = frozenset(
    {
        "fapi.binance.com",
        "fapi.binancefuture.com",  # Binance USDT-M testnet (still public-only)
    }
)

#: Default REST base URL for Binance USDT-M perpetual futures public data.
DEFAULT_REST_BASE_URL: str = "https://fapi.binance.com"


def _strip_path(path: str) -> str:
    """Return ``path`` reduced to a trailing-slash-free, querystring-free
    canonical form for allowlist lookup. ``/fapi/v1/depth?symbol=X``
    becomes ``/fapi/v1/depth``."""
    cleaned = path.split("?", 1)[0].split("#", 1)[0]
    if len(cleaned) > 1 and cleaned.endswith("/"):
        cleaned = cleaned.rstrip("/")
    return cleaned


def assert_public_endpoint_allowed(url_or_path: str) -> str:
    """Validate ``url_or_path`` against the Phase 11C allowlist.

    Returns the canonical path on success. Raises
    :class:`SafeModeViolation` if:

      - the URL targets an explicitly-private endpoint
      - the URL targets any path not in :data:`PUBLIC_MARKET_ENDPOINT_ALLOWLIST`
      - the URL carries a forbidden query parameter such as
        ``signature``, ``timestamp``, ``recvWindow`` or ``apiKey``
      - the URL targets a host that is not on :data:`ALLOWED_PUBLIC_HOSTS`
      - the URL uses a non-https scheme
    """
    if not url_or_path:
        raise SafeModeViolation(
            "BinancePublicClient: empty endpoint path; refusing"
        )

    parsed = urllib.parse.urlsplit(url_or_path)
    if parsed.scheme:
        if parsed.scheme not in {"https"}:
            raise SafeModeViolation(
                f"BinancePublicClient: refused non-https URL scheme "
                f"{parsed.scheme!r}; Phase 11C requires https."
            )
        host = (parsed.netloc or "").split(":", 1)[0].lower()
        if host and host not in ALLOWED_PUBLIC_HOSTS:
            raise SafeModeViolation(
                f"BinancePublicClient: refused URL host {host!r}; "
                "Phase 11C only allows Binance public market hosts "
                f"({sorted(ALLOWED_PUBLIC_HOSTS)})."
            )
        path = parsed.path or "/"
        query = parsed.query
    else:
        # Bare path like "/fapi/v1/depth?symbol=BTCUSDT".
        if "?" in url_or_path:
            head, _, query = url_or_path.partition("?")
            path = head
        else:
            path = url_or_path
            query = ""

    canonical = _strip_path(path)

    if canonical in FORBIDDEN_PRIVATE_ENDPOINTS:
        raise SafeModeViolation(
            f"BinancePublicClient: refused private endpoint {canonical!r}. "
            "Phase 11C is public-market read-only; trading / account / "
            "position / leverage / margin endpoints are forbidden."
        )

    if canonical not in PUBLIC_MARKET_ENDPOINT_ALLOWLIST:
        raise SafeModeViolation(
            f"BinancePublicClient: endpoint {canonical!r} is not in the "
            "Phase 11C public-market allowlist. Refusing. Allowed: "
            f"{sorted(PUBLIC_MARKET_ENDPOINT_ALLOWLIST)}"
        )

    if query:
        params = urllib.parse.parse_qsl(query, keep_blank_values=True)
        for name, _ in params:
            if name in FORBIDDEN_QUERY_PARAMETERS:
                raise SafeModeViolation(
                    f"BinancePublicClient: refused signed-request query "
                    f"parameter {name!r}. Phase 11C never sends signed "
                    "requests."
                )

    return canonical


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

#: Type alias for a transport callable. Takes a fully-qualified URL and
#: returns either a parsed JSON value (legacy contract used by tests
#: that pre-date the Phase 11C.1A rate-limit governor) or a
#: :class:`PublicRestResponse` envelope (preferred, exposes status code
#: + rate-limit headers to the governor). The client normalises both
#: forms into a :class:`PublicRestResponse` before handing it to the
#: governor.
PublicTransport = Callable[[str], Any]


def _default_transport(timeout_seconds: float = 5.0) -> PublicTransport:
    """Return a default REST transport using :mod:`urllib.request`.

    The transport is intentionally minimal: it issues a single GET, sets
    a short timeout, and parses the response as JSON. It does NOT
    follow redirects beyond what :mod:`urllib` does by default, does
    NOT add an ``Authorization`` header, and does NOT consume any
    credential.

    Phase 11C.1A: the transport returns a :class:`PublicRestResponse`
    on every successful response so the rate-limit governor can read
    the ``X-MBX-USED-WEIGHT-1M`` and ``Retry-After`` headers. HTTP 429
    and HTTP 418 are NOT raised: the transport captures the status +
    headers and returns them in the envelope so the governor can
    decide whether to back off (429) or latch protection mode (418).
    Every other non-200 status is converted into :class:`ExchangeError`
    as before so the existing event chain keeps treating transient
    transport failures as recoverable noise.
    """

    def _fetch(url: str) -> Any:
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "User-Agent": "ama-rt/phase-11c (public-market-readonly)",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                raw = resp.read()
                headers = _normalise_headers(resp.headers)
                if resp.status != 200:
                    if resp.status in (429, 418):
                        return PublicRestResponse(
                            body=None,
                            status=int(resp.status),
                            headers=headers,
                        )
                    raise ExchangeError(
                        f"binance_public: HTTP {resp.status} from {url}"
                    )
                return PublicRestResponse(
                    body=json.loads(raw.decode("utf-8")),
                    status=200,
                    headers=headers,
                )
        except urllib.error.HTTPError as exc:
            headers = _normalise_headers(getattr(exc, "headers", None))
            code = int(getattr(exc, "code", 0) or 0)
            if code in (429, 418):
                # Phase 11C.1A: the rate-limit governor handles 429 /
                # 418 explicitly. Hand it the envelope rather than
                # raising so it can read ``Retry-After`` and the used
                # weight header.
                return PublicRestResponse(
                    body=None,
                    status=code,
                    headers=headers,
                )
            raise ExchangeError(
                f"binance_public: HTTP error {code} from {url}: {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ExchangeError(
                f"binance_public: transport error talking to {url}: {exc.reason}"
            ) from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise ExchangeError(
                f"binance_public: malformed JSON response from {url}: {exc}"
            ) from exc

    return _fetch


def _normalise_headers(raw_headers: Any) -> dict[str, str]:
    """Convert a urllib / dict headers object into a plain ``str``-keyed dict.

    The :class:`http.client.HTTPMessage` object returned by
    ``urlopen`` exposes a mapping interface, but iteration order and
    case behave subtly differently on different Python versions. We
    normalise to a plain ``{header_name: header_value}`` dict so the
    governor can index by name without worrying about the underlying
    type.
    """
    if raw_headers is None:
        return {}
    out: dict[str, str] = {}
    try:
        items = raw_headers.items()
    except AttributeError:
        try:
            items = list(raw_headers)
        except TypeError:
            return {}
    for name, value in items:
        if name is None:
            continue
        out[str(name)] = "" if value is None else str(value)
    return out


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PublicMarkPrice:
    """Mark-price + premium index snapshot (``/fapi/v1/premiumIndex``).

    Phase 11C ships its own value object rather than reusing
    :class:`FundingRate` because the mark-price endpoint also returns
    the *index price* and the funding rate in one envelope, and we
    want the buffer / snapshot pipeline to consume mark-price and
    funding independently. The funding-rate part of the same response
    is emitted as a regular :class:`FundingRate`.
    """

    symbol: str
    timestamp: int
    mark_price: float
    index_price: float | None
    last_funding_rate: float | None
    next_funding_ts: int | None
    reliability: DataReliability = DataReliability.B


class BinancePublicClient(ExchangeClientBase):
    """Binance USDT-M perpetual futures **public-market read-only** client.

    Phase 11C contract:

      - inherits the four ``SafeModeViolation`` write-surface refusals
        from :class:`ExchangeClientBase` (create_order, cancel_order,
        set_leverage, set_margin_mode);
      - rejects ``api_key`` / ``api_secret`` parameters at construction;
      - validates every URL through :func:`assert_public_endpoint_allowed`;
      - never returns an :class:`AccountSnapshot` (the inherited
        :meth:`get_account_snapshot` raises :class:`SafeModeViolation`);
      - emits ``EXCHANGE_CONNECTED`` / ``EXCHANGE_DISCONNECTED`` /
        ``EXCHANGE_DEGRADED`` / ``DATA_UNRELIABLE`` events through the
        same plumbing the Phase 3 :class:`MockExchangeClient` uses.

    The class is **read-only**. There is no place in this file where a
    real order can be placed, and no place where ``api_key`` /
    ``api_secret`` is read or stored.
    """

    name = "binance_public"

    def __init__(
        self,
        *,
        rest_base_url: str = DEFAULT_REST_BASE_URL,
        transport: PublicTransport | None = None,
        request_timeout_seconds: float = 5.0,
        event_repo=None,
        ws_manager: WebSocketManager | None = None,
        governor: BinancePublicRestGovernor | None = None,
        autostart: bool = True,
        # The following kw-only parameters exist solely to make the
        # SafeModeViolation explicit when a caller mistakenly hands a
        # credential to this constructor. They are NEVER stored.
        api_key: str | None = None,
        api_secret: str | None = None,
        **forbidden_credentials: Any,
    ) -> None:
        # Defence-in-depth: explicit credential parameters land here
        # only when a caller insists on passing them. Refuse loudly.
        if api_key is not None or api_secret is not None:
            raise SafeModeViolation(
                "BinancePublicClient must not be instantiated with "
                "api_key / api_secret. Phase 11C is public-market "
                "read-only; credentials are forbidden."
            )
        for name in forbidden_credentials:
            lowered = name.lower()
            if any(
                needle in lowered
                for needle in (
                    "api_key",
                    "api_secret",
                    "apikey",
                    "secret",
                    "token",
                    "signature",
                    "passphrase",
                )
            ):
                raise SafeModeViolation(
                    f"BinancePublicClient: refused credential-shaped "
                    f"keyword argument {name!r}. Phase 11C is "
                    "public-market read-only."
                )
        if forbidden_credentials:
            # Any other unknown kwargs are still a typo; refuse them so
            # callers cannot smuggle in undocumented behaviour.
            raise TypeError(
                f"BinancePublicClient got unexpected keyword argument(s): "
                f"{sorted(forbidden_credentials)}"
            )

        self._rest_base_url = rest_base_url.rstrip("/")
        # Validate the base URL so misconfiguration fails immediately.
        assert_public_endpoint_allowed(
            urllib.parse.urlsplit(self._rest_base_url)._replace(
                path="/fapi/v1/exchangeInfo"
            ).geturl()
        )
        self._transport: PublicTransport = (
            transport
            if transport is not None
            else _default_transport(timeout_seconds=request_timeout_seconds)
        )
        self._request_timeout_seconds = float(request_timeout_seconds)
        self._endpoint_call_counts: dict[str, int] = {}
        self._governor: BinancePublicRestGovernor | None = governor
        super().__init__(event_repo=event_repo, ws_manager=ws_manager)
        if autostart:
            self.start()

    # ------------------------------------------------------------------
    # Public introspection
    # ------------------------------------------------------------------
    @property
    def rest_base_url(self) -> str:
        return self._rest_base_url

    @property
    def endpoint_call_counts(self) -> Mapping[str, int]:
        """Per-endpoint call counter, useful for the runner banner and
        the daily report. Counts only successful, allowlist-validated
        calls; refused calls are surfaced as :class:`SafeModeViolation`."""
        return dict(self._endpoint_call_counts)

    @property
    def total_calls(self) -> int:
        return sum(self._endpoint_call_counts.values())

    @property
    def governor(self) -> BinancePublicRestGovernor | None:
        """Phase 11C.1A: the optional rate-limit governor wrapping every
        public REST call. ``None`` means rate-limit protection is OFF
        (e.g. unit-tests that exercise the allowlist without the
        governor)."""
        return self._governor

    # ------------------------------------------------------------------
    # Internal request plumbing
    # ------------------------------------------------------------------
    def _require_at_least_degraded(self, *, surface: str) -> None:
        """Refuse a read call only when the link is fully DOWN.

        ``DEGRADED`` keeps REST usable per Spec §13.3, so REST-only
        surfaces like ``get_symbols`` and ``get_klines`` remain
        available even when the WS link is flapping. Tier-A surfaces
        use :meth:`_require_trustworthy` instead.
        """
        from app.core.enums import ExchangeConnectionState
        from app.core.errors import ExchangeConnectionError

        if self.health.state in (
            ExchangeConnectionState.DISCONNECTED,
            ExchangeConnectionState.UNINITIALISED,
        ):
            raise ExchangeConnectionError(
                f"{self.name}.{surface}() refused: connection state is "
                f"{self.health.state.value} (reason={self.health.reason})"
            )

    def _request(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """Issue a public GET against ``path`` with optional ``params``.

        Validates the path against the allowlist BEFORE building the
        URL so a forbidden path is refused before any string formatting
        could leak it into a log line.

        Phase 11C.1A: every request is routed through the
        :class:`BinancePublicRestGovernor` (when one is wired). The
        governor:

          - refuses the call if it has latched into protection mode
            after a previous HTTP 418 (raises
            :class:`RateLimitProtectionError`);
          - refuses the call while a Retry-After backoff window is
            still active (raises :class:`RateLimitBackoffActive`);
          - refuses the call when the configured hard weight budget
            is exhausted (raises :class:`RateLimitBudgetExceeded`);
          - records the response status + headers afterwards so 429 /
            418 can be handled centrally regardless of which surface
            issued the call.
        """
        canonical = assert_public_endpoint_allowed(path)
        query_pairs: list[tuple[str, str]] = []
        if params:
            for name, value in params.items():
                if name in FORBIDDEN_QUERY_PARAMETERS:
                    raise SafeModeViolation(
                        f"BinancePublicClient: refused signed-request "
                        f"query parameter {name!r}."
                    )
                if value is None:
                    continue
                query_pairs.append((str(name), str(value)))
        query = urllib.parse.urlencode(query_pairs)
        url = self._rest_base_url + canonical
        if query:
            url = f"{url}?{query}"
        # Re-validate the fully-formed URL: scheme, host, path, query.
        assert_public_endpoint_allowed(url)

        # Phase 11C.1A: route through the governor. ``before_request``
        # may raise; we let the exception propagate so the caller sees
        # the protection event without an additional except clause.
        weight: int | None = None
        if self._governor is not None:
            weight = self._governor.before_request(canonical)

        try:
            raw = self._transport(url)
        except Exception as exc:
            # Transport-level failure: release the reserved weight so
            # the rolling-window budget does not double-bill the
            # transient failure.
            if self._governor is not None:
                self._governor.record_transport_error(
                    canonical, weight=weight, error=exc
                )
            raise

        response = (
            raw
            if isinstance(raw, PublicRestResponse)
            else PublicRestResponse(body=raw, status=200, headers={})
        )

        # ``record_response`` raises :class:`RateLimitProtectionError`
        # on HTTP 418 (after emitting the protection events + opening a
        # P1 incident). On HTTP 429 it sleeps the configured
        # Retry-After window and returns; the caller treats the call as
        # "no body" by raising ExchangeError below.
        if self._governor is not None:
            self._governor.record_response(canonical, response, weight=weight)

        if response.status == 429:
            raise ExchangeError(
                f"binance_public: HTTP 429 from {url}; rate-limit governor "
                "completed its Retry-After backoff. The caller should treat "
                "this batch as failed and try again next loop tick."
            )
        if response.status == 418:
            # Defence-in-depth: the governor MUST have raised by now.
            # If a future caller wires the client without a governor we
            # still refuse loudly.
            raise SafeModeViolation(
                f"binance_public: HTTP 418 from {url}; Binance has IP "
                "banned the gateway. Refusing to continue."
            )
        if response.status != 200:
            raise ExchangeError(
                f"binance_public: HTTP {response.status} from {url}"
            )

        body = response.body
        self._endpoint_call_counts[canonical] = (
            self._endpoint_call_counts.get(canonical, 0) + 1
        )
        return body

    # ------------------------------------------------------------------
    # Read-only API
    # ------------------------------------------------------------------
    def get_symbols(self) -> list[ExchangeSymbol]:
        """Return tradable USDT-perpetual symbols (``/fapi/v1/exchangeInfo``).

        Filters to ``contractType=PERPETUAL`` and ``quoteAsset=USDT``;
        Phase 11C does not consume linear-coin or quarterly contracts.
        """
        self._require_at_least_degraded(surface="get_symbols")
        body = self._request("/fapi/v1/exchangeInfo")
        out: list[ExchangeSymbol] = []
        for sym in body.get("symbols", []) or []:
            if sym.get("contractType") != "PERPETUAL":
                continue
            if sym.get("quoteAsset") != "USDT":
                continue
            price_tick = 0.0
            qty_step = 0.0
            min_notional = 0.0
            for f in sym.get("filters", []) or []:
                ftype = f.get("filterType")
                if ftype == "PRICE_FILTER":
                    price_tick = float(f.get("tickSize") or 0.0)
                elif ftype == "LOT_SIZE":
                    qty_step = float(f.get("stepSize") or 0.0)
                elif ftype == "MIN_NOTIONAL":
                    try:
                        min_notional = float(f.get("notional") or 0.0)
                    except (TypeError, ValueError):
                        min_notional = 0.0
            out.append(
                ExchangeSymbol(
                    symbol=str(sym.get("symbol")),
                    base_asset=str(sym.get("baseAsset", "")),
                    quote_asset="USDT",
                    contract_type="PERPETUAL",
                    status=str(sym.get("status", "TRADING")),
                    price_tick=price_tick,
                    qty_step=qty_step,
                    min_notional=min_notional,
                )
            )
        return out

    def get_top_usdt_perpetual_symbols(
        self,
        *,
        limit: int = 20,
    ) -> list[str]:
        """Return the top-N USDT-perpetual symbols by 24h quote volume.

        Uses ``/fapi/v1/ticker/24hr``. ``limit`` is clamped to a sane
        ceiling so a misconfigured runner cannot accidentally scan
        every contract.
        """
        if limit <= 0:
            return []
        clamped_limit = max(1, min(int(limit), 200))
        body = self._request("/fapi/v1/ticker/24hr")
        rows: list[tuple[str, float]] = []
        for row in body or []:
            sym = str(row.get("symbol", ""))
            if not sym.endswith("USDT"):
                continue
            try:
                quote_vol = float(row.get("quoteVolume") or 0.0)
            except (TypeError, ValueError):
                continue
            rows.append((sym, quote_vol))
        rows.sort(key=lambda r: r[1], reverse=True)
        return [sym for sym, _ in rows[:clamped_limit]]

    def get_orderbook(self, symbol: str, *, depth: int = 20) -> OrderBook:
        """Return a snapshot of the order book (``/fapi/v1/depth``).

        Tagged tier B because the snapshot comes from REST. A future
        WebSocket depth-diff adapter would tag tier A.
        """
        self._require_trustworthy(surface="get_orderbook")
        # Binance accepts: 5, 10, 20, 50, 100, 500, 1000.
        binance_limits = (5, 10, 20, 50, 100, 500, 1000)
        chosen = next((d for d in binance_limits if d >= depth), 1000)
        body = self._request(
            "/fapi/v1/depth", params={"symbol": symbol, "limit": chosen}
        )
        ts = int(body.get("E") or body.get("T") or now_ms())
        bids = tuple(
            OrderBookLevel(price=float(p), qty=float(q))
            for p, q in (body.get("bids") or [])[:depth]
        )
        asks = tuple(
            OrderBookLevel(price=float(p), qty=float(q))
            for p, q in (body.get("asks") or [])[:depth]
        )
        return OrderBook(
            symbol=symbol,
            timestamp=ts,
            bids=bids,
            asks=asks,
            reliability=DataReliability.B,
        )

    def get_recent_trades(
        self, symbol: str, *, limit: int = 100
    ) -> list[RecentTrade]:
        """Return recent aggregated trades (``/fapi/v1/aggTrades``).

        ``aggTrades`` is preferred over ``trades`` because it gives a
        deterministic per-aggressor side flag; the wider Phase 11C
        pipeline relies on ``is_buyer_maker`` to compute CVD and the
        manipulation reason tags.
        """
        self._require_trustworthy(surface="get_recent_trades")
        clamped = max(1, min(int(limit), 1000))
        body = self._request(
            "/fapi/v1/aggTrades", params={"symbol": symbol, "limit": clamped}
        )
        trades: list[RecentTrade] = []
        for row in body or []:
            try:
                ts = int(row.get("T"))
                price = float(row.get("p"))
                qty = float(row.get("q"))
                is_buyer_maker = bool(row.get("m"))
                trade_id = str(row.get("a"))
            except (TypeError, ValueError):
                continue
            # `is_buyer_maker=True` => the aggressor was a SELLER.
            side = TradeSide.SELL if is_buyer_maker else TradeSide.BUY
            trades.append(
                RecentTrade(
                    symbol=symbol,
                    trade_id=trade_id,
                    timestamp=ts,
                    price=price,
                    qty=qty,
                    side=side,
                    is_buyer_maker=is_buyer_maker,
                    reliability=DataReliability.A,
                )
            )
        return trades

    def get_funding_rate(self, symbol: str) -> FundingRate:
        """Return the latest funding-rate row (``/fapi/v1/fundingRate``)."""
        self._require_trustworthy(surface="get_funding_rate")
        body = self._request(
            "/fapi/v1/fundingRate", params={"symbol": symbol, "limit": 1}
        )
        rows = body or []
        if not rows:
            # Fall back to the premiumIndex envelope which always carries
            # a current funding-rate field.
            return self._funding_from_premium_index(symbol)
        row = rows[-1]
        return FundingRate(
            symbol=symbol,
            timestamp=int(row.get("fundingTime") or now_ms()),
            rate=float(row.get("fundingRate") or 0.0),
            next_funding_ts=int(row.get("fundingTime") or now_ms())
            + 8 * 60 * 60 * 1000,
            reliability=DataReliability.B,
        )

    def _funding_from_premium_index(self, symbol: str) -> FundingRate:
        body = self._request(
            "/fapi/v1/premiumIndex", params={"symbol": symbol}
        )
        return FundingRate(
            symbol=symbol,
            timestamp=int(body.get("time") or now_ms()),
            rate=float(body.get("lastFundingRate") or 0.0),
            next_funding_ts=int(body.get("nextFundingTime") or now_ms()),
            reliability=DataReliability.B,
        )

    def get_open_interest(self, symbol: str) -> OpenInterest:
        """Return the latest open-interest row (``/fapi/v1/openInterest``)."""
        self._require_trustworthy(surface="get_open_interest")
        body = self._request(
            "/fapi/v1/openInterest", params={"symbol": symbol}
        )
        return OpenInterest(
            symbol=symbol,
            timestamp=int(body.get("time") or now_ms()),
            open_interest=float(body.get("openInterest") or 0.0),
            open_interest_value=None,
            reliability=DataReliability.B,
        )

    def get_account_snapshot(self) -> AccountSnapshot:
        """Phase 11C never returns a real account snapshot.

        Account / position information lives behind authenticated
        endpoints which Phase 11C is forbidden to call. The override
        is explicit so the failure points at Phase 11C rather than
        at the inherited Phase 3 :class:`NotImplementedError`.
        """
        raise SafeModeViolation(
            "BinancePublicClient.get_account_snapshot is forbidden in "
            "Phase 11C. Account / position data requires authenticated "
            "endpoints which the public-market read-only client never "
            "calls. Use MockExchangeClient for paper account snapshots."
        )

    # ------------------------------------------------------------------
    # Phase 11C-specific public surfaces
    # ------------------------------------------------------------------
    def get_book_ticker(self, symbol: str) -> tuple[float, float, int]:
        """Return ``(bid, ask, timestamp_ms)`` from ``/fapi/v1/ticker/bookTicker``."""
        self._require_trustworthy(surface="get_book_ticker")
        body = self._request(
            "/fapi/v1/ticker/bookTicker", params={"symbol": symbol}
        )
        bid = float(body.get("bidPrice") or 0.0)
        ask = float(body.get("askPrice") or 0.0)
        ts = int(body.get("time") or now_ms())
        return bid, ask, ts

    def get_mark_price(self, symbol: str) -> PublicMarkPrice:
        """Return the latest mark-price + premium-index envelope.

        Endpoint: ``/fapi/v1/premiumIndex``. Carries:

          - ``markPrice``       - the current mark price
          - ``indexPrice``      - the index price
          - ``lastFundingRate`` - last paid funding rate
          - ``nextFundingTime`` - next funding time
        """
        self._require_trustworthy(surface="get_mark_price")
        body = self._request(
            "/fapi/v1/premiumIndex", params={"symbol": symbol}
        )
        return PublicMarkPrice(
            symbol=symbol,
            timestamp=int(body.get("time") or now_ms()),
            mark_price=float(body.get("markPrice") or 0.0),
            index_price=(
                float(body.get("indexPrice"))
                if body.get("indexPrice") is not None
                else None
            ),
            last_funding_rate=(
                float(body.get("lastFundingRate"))
                if body.get("lastFundingRate") is not None
                else None
            ),
            next_funding_ts=(
                int(body.get("nextFundingTime"))
                if body.get("nextFundingTime") is not None
                else None
            ),
            reliability=DataReliability.B,
        )

    def get_klines(
        self,
        symbol: str,
        *,
        interval: str = "1m",
        limit: int = 100,
    ) -> list[tuple[int, float, float, float, float, float]]:
        """Return raw OHLCV klines (``/fapi/v1/klines``).

        Each row is ``(open_ts, open, high, low, close, volume)``. The
        Market Data Buffer's :class:`CandleBuilder` rebuilds bars from
        trades; klines are exposed for the runner banner / daily-report
        diagnostics, NOT as the canonical bar source.
        """
        self._require_at_least_degraded(surface="get_klines")
        clamped = max(1, min(int(limit), 1500))
        body = self._request(
            "/fapi/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": clamped},
        )
        rows: list[tuple[int, float, float, float, float, float]] = []
        for k in body or []:
            try:
                rows.append(
                    (
                        int(k[0]),
                        float(k[1]),
                        float(k[2]),
                        float(k[3]),
                        float(k[4]),
                        float(k[5]),
                    )
                )
            except (IndexError, TypeError, ValueError):
                continue
        return rows

    # ------------------------------------------------------------------
    # Convenience: defensive guard against credential leakage
    # ------------------------------------------------------------------
    def assert_public_only(self) -> None:
        """Defensive runtime self-check.

        Raises :class:`SafeModeViolation` if the client has ever been
        switched into a write mode. Phase 11C never flips
        ``_live_orders_enabled`` and the four write surfaces are
        inherited and refuse unconditionally; this method exists so
        the runner / supervisor can pin the invariant at every loop
        tick.
        """
        if self._live_orders_enabled:
            raise SafeModeViolation(
                "BinancePublicClient is read-only; live_orders_enabled "
                "must remain False in Phase 11C."
            )

    # ------------------------------------------------------------------
    # Lifecycle helpers (delegate to base; documented here for clarity)
    # ------------------------------------------------------------------
    def health_payload(self) -> dict[str, Any]:
        """Return a JSON-safe view of the underlying health state."""
        return {
            "name": self.name,
            "rest_base_url": self._rest_base_url,
            **self.health.to_dict(),
            "endpoint_call_counts": dict(self._endpoint_call_counts),
            "total_calls": self.total_calls,
        }


__all__ = [
    "ALLOWED_PUBLIC_HOSTS",
    "BinancePublicClient",
    "DEFAULT_REST_BASE_URL",
    "FORBIDDEN_PRIVATE_ENDPOINTS",
    "FORBIDDEN_QUERY_PARAMETERS",
    "PublicMarkPrice",
    "PublicRestResponse",
    "PublicTransport",
    "PUBLIC_MARKET_ENDPOINT_ALLOWLIST",
    "assert_public_endpoint_allowed",
]
