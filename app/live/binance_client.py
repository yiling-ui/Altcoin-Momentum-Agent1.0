"""Binance live API client for the Live API Integration Pack (PR111).

Three access layers:

  1. ``PUBLIC_MARKET`` - ping / server time / exchangeInfo / mark price /
     24h ticker / klines. No credential required.
  2. ``PRIVATE_READ`` - account / balances / positions / open orders
     (read) / income history. Signed with HMAC-SHA256; requires
     ``enable_private_read`` in config.
  3. ``PRIVATE_TRADE`` - create_order / cancel_order / set_leverage /
     set_margin_mode. **Interface only.** Every method is BLOCKED in
     PR111: it raises :class:`app.core.errors.LiveTradeNotEnabled` (or
     returns the ``TRADE_API_BLOCKED_BY_PR111`` sentinel via
     :meth:`trade_blocked_reason`) and NEVER builds or sends an HTTP
     order request.

Transport
---------

The default transport uses :mod:`urllib.request` from the standard
library (no third-party HTTP dependency). Tests inject a deterministic
``transport`` callable so no real socket is opened. The transport
signature is ``(method, url, headers) -> parsed_json``.

Secret handling
---------------

The API key / secret are held as :class:`app.live.secrets.SecretValue`.
The secret is revealed only inside :meth:`_signed_query` for HMAC
signing; the resulting signature and the signed URL are NEVER logged.
Audit events carry only masked / non-sensitive fields.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Mapping

from loguru import logger

from app.core.clock import now_ms
from app.core.errors import LiveApiError, LiveTradeNotEnabled
from app.core.events import Event, EventType
from app.live.api_config import BinanceApiConfig, LiveRuntimeMode
from app.live.binance_models import (
    BinanceAccountSnapshot,
    BinanceApiHealthResult,
    BinanceExchangeInfoSnapshot,
    BinanceIncomeEvent,
    BinancePositionSnapshot,
    BinanceSymbolFilter,
    parse_account,
    parse_exchange_info,
)
from app.live.binance_permissions import inspect_permissions
from app.live.secrets import API_HEALTH_MISSING_SECRET
from app.live.status import HealthStatus, TRADE_API_BLOCKED_BY_PR111, worst_of

#: Transport callable: (method, url, headers) -> parsed JSON value.
BinanceTransport = Callable[[str, str, Mapping[str, str]], Any]

DEFAULT_RECV_WINDOW_MS = 5000

# Forbidden trade / leverage / margin endpoints. Listed so a reviewer can
# pin that PR111 never composes one of these into a request. The client
# refuses to build them.
FORBIDDEN_TRADE_ENDPOINTS: frozenset[str] = frozenset(
    {
        "/fapi/v1/order",
        "/fapi/v1/batchOrders",
        "/fapi/v1/allOpenOrders",
        "/fapi/v1/leverage",
        "/fapi/v1/marginType",
        "/fapi/v1/positionMargin",
        "/fapi/v1/positionSide/dual",
        "/fapi/v1/listenKey",
    }
)


def _default_transport(timeout_seconds: float = 5.0) -> BinanceTransport:
    """Return a default urllib-based transport.

    Issues a single request, parses JSON. Does NOT log the URL (it may
    carry a signature). Non-2xx bodies are converted into
    :class:`LiveApiError` with a sanitised message (path only, no query).
    """

    def _fetch(method: str, url: str, headers: Mapping[str, str]) -> Any:
        path_only = urllib.parse.urlsplit(url).path
        req = urllib.request.Request(url, method=method, headers=dict(headers))
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                raw = resp.read()
                if resp.status != 200:
                    raise LiveApiError(f"binance: HTTP {resp.status} from {path_only}")
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Do NOT include the response body / URL query: it can echo
            # request parameters. Only the status + path are surfaced.
            raise LiveApiError(
                f"binance: HTTP error {getattr(exc, 'code', '?')} from {path_only}"
            ) from None
        except urllib.error.URLError as exc:
            raise LiveApiError(
                f"binance: transport error talking to {path_only}: {exc.reason}"
            ) from None
        except (json.JSONDecodeError, ValueError):
            raise LiveApiError(
                f"binance: malformed JSON response from {path_only}"
            ) from None

    return _fetch


class BinanceLiveClient:
    """Layered Binance USDT-M futures live client (PR111)."""

    name = "binance_live"

    def __init__(
        self,
        config: BinanceApiConfig,
        *,
        runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_SHADOW,
        transport: BinanceTransport | None = None,
        request_timeout_seconds: float = 5.0,
        recv_window_ms: int = DEFAULT_RECV_WINDOW_MS,
        event_repo: Any | None = None,
        clock: Callable[[], int] = now_ms,
    ) -> None:
        self._config = config
        self._runtime_mode = runtime_mode
        self._transport: BinanceTransport = transport or _default_transport(
            timeout_seconds=request_timeout_seconds
        )
        self._recv_window_ms = int(recv_window_ms)
        self._event_repo = event_repo
        self._clock = clock
        self._exchange_info: BinanceExchangeInfoSnapshot | None = None

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    @property
    def runtime_mode(self) -> LiveRuntimeMode:
        return self._runtime_mode

    @property
    def fapi_base_url(self) -> str:
        return self._config.resolved_fapi_base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Event emission (always secret-safe payloads)
    # ------------------------------------------------------------------
    def _emit(self, event_type: EventType, payload: dict[str, Any], *, symbol: str | None = None) -> None:
        if self._event_repo is None:
            return
        try:
            self._event_repo.append(
                Event(
                    event_type=event_type,
                    source_module=self.name,
                    symbol=symbol,
                    payload=payload,
                )
            )
        except Exception:  # pragma: no cover - audit must never crash a read
            logger.debug("binance_live: event emit failed (non-fatal)")

    # ------------------------------------------------------------------
    # Request plumbing
    # ------------------------------------------------------------------
    def _public_request(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        url = self.fapi_base_url + path
        query = _encode_params(params)
        if query:
            url = f"{url}?{query}"
        return self._transport("GET", url, {})

    def _signed_query(self, params: dict[str, Any]) -> tuple[str, dict[str, str]]:
        """Build a signed query string + auth headers for a PRIVATE_READ call.

        The HMAC signature is computed from the api_secret and never
        logged. The returned headers carry the api key.
        """
        params = dict(params)
        params["timestamp"] = self._clock()
        params.setdefault("recvWindow", self._recv_window_ms)
        query = urllib.parse.urlencode(params)
        secret = self._config.api_secret.reveal().encode("utf-8")
        signature = hmac.new(secret, query.encode("utf-8"), hashlib.sha256).hexdigest()
        signed = f"{query}&signature={signature}"
        headers = {"X-MBX-APIKEY": self._config.api_key.reveal()}
        return signed, headers

    def _private_read_request(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        if not self._config.enable_private_read:
            raise LiveApiError(
                "binance: private read is disabled (AMA_BINANCE_ENABLE_PRIVATE_READ=false)"
            )
        if not self._config.has_credentials:
            raise LiveApiError(f"binance: {API_HEALTH_MISSING_SECRET}")
        signed, headers = self._signed_query(dict(params or {}))
        url = f"{self.fapi_base_url}{path}?{signed}"
        return self._transport("GET", url, headers)

    # ==================================================================
    # 1. PUBLIC_MARKET
    # ==================================================================
    def ping(self) -> bool:
        self._public_request("/fapi/v1/ping")
        return True

    def server_time(self) -> int:
        body = self._public_request("/fapi/v1/time")
        try:
            return int(body.get("serverTime"))
        except (AttributeError, TypeError, ValueError):
            return 0

    def get_exchange_info(self, *, force: bool = False) -> BinanceExchangeInfoSnapshot:
        if self._exchange_info is not None and not force:
            return self._exchange_info
        body = self._public_request("/fapi/v1/exchangeInfo")
        snapshot = parse_exchange_info(body)
        self._exchange_info = snapshot
        return snapshot

    def get_mark_price(self, symbol: str) -> dict[str, Any]:
        return self._public_request("/fapi/v1/premiumIndex", {"symbol": symbol})

    def get_ticker_24hr(self, symbol: str | None = None) -> Any:
        params = {"symbol": symbol} if symbol else None
        return self._public_request("/fapi/v1/ticker/24hr", params)

    def get_klines(self, symbol: str, interval: str = "1m", limit: int = 100) -> Any:
        return self._public_request(
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": interval, "limit": int(limit)},
        )

    # ==================================================================
    # 2. PRIVATE_READ
    # ==================================================================
    def get_account(self) -> BinanceAccountSnapshot:
        body = self._private_read_request("/fapi/v2/account")
        snapshot = parse_account(body, timestamp_ms=self._clock())
        self._emit(
            EventType.BINANCE_ACCOUNT_SNAPSHOT_READ,
            {
                "balance_count": len(snapshot.balances),
                "open_position_count": snapshot.open_position_count,
                "can_trade": snapshot.can_trade,
                "can_withdraw": snapshot.can_withdraw,
                "fee_tier": snapshot.fee_tier,
            },
        )
        return snapshot

    def get_balances(self) -> list[dict[str, Any]]:
        body = self._private_read_request("/fapi/v2/balance")
        return list(body or [])

    def get_positions(self) -> list[BinancePositionSnapshot]:
        body = self._private_read_request("/fapi/v2/positionRisk")
        positions: list[BinancePositionSnapshot] = []
        for p in body or []:
            positions.append(
                BinancePositionSnapshot(
                    symbol=str(p.get("symbol", "") or ""),
                    position_amt=_to_float(p.get("positionAmt")),
                    entry_price=_to_float(p.get("entryPrice")),
                    unrealized_pnl=_to_float(p.get("unRealizedProfit")),
                    leverage=_to_float(p.get("leverage")),
                    margin_type=str(p.get("marginType", "") or ""),
                    position_side=str(p.get("positionSide", "BOTH") or "BOTH"),
                )
            )
        return positions

    def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Read-only open orders. (Reading orders is NOT placing them.)"""
        params = {"symbol": symbol} if symbol else {}
        body = self._private_read_request("/fapi/v1/openOrders", params)
        return list(body or [])

    def get_income_history(
        self,
        *,
        symbol: str | None = None,
        income_type: str | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        limit: int = 100,
    ) -> list[BinanceIncomeEvent]:
        """Read + classify income rows (funding / commission / realized PnL / transfer)."""
        params: dict[str, Any] = {"limit": int(limit)}
        if symbol:
            params["symbol"] = symbol
        if income_type:
            params["incomeType"] = income_type
        if start_time_ms is not None:
            params["startTime"] = int(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)
        body = self._private_read_request("/fapi/v1/income", params)
        events = [BinanceIncomeEvent.from_row(row) for row in (body or [])]
        funding_count = sum(1 for e in events if e.is_funding)
        commission_count = sum(1 for e in events if e.is_fee)
        self._emit(
            EventType.BINANCE_INCOME_HISTORY_READ,
            {"row_count": len(events), "funding_count": funding_count, "commission_count": commission_count},
        )
        if funding_count:
            self._emit(EventType.FUNDING_EVENT_DETECTED, {"count": funding_count})
        if commission_count:
            self._emit(EventType.COMMISSION_EVENT_DETECTED, {"count": commission_count})
        return events

    # ==================================================================
    # 3. PRIVATE_TRADE - interface only, BLOCKED in PR111
    # ==================================================================
    def trade_blocked_reason(self) -> str:
        """Non-raising contract: returns the PR111 trade-block sentinel."""
        self._emit(
            EventType.BINANCE_PRIVATE_TRADE_BLOCKED,
            {"reason": TRADE_API_BLOCKED_BY_PR111, "runtime_mode": self._runtime_mode.value},
        )
        return TRADE_API_BLOCKED_BY_PR111

    def _refuse_trade(self, surface: str) -> None:
        """Emit the block event and raise. NEVER builds an HTTP request."""
        self._emit(
            EventType.BINANCE_PRIVATE_TRADE_BLOCKED,
            {"surface": surface, "reason": TRADE_API_BLOCKED_BY_PR111, "runtime_mode": self._runtime_mode.value},
        )
        raise LiveTradeNotEnabled(
            f"binance.{surface} is blocked by PR111 ({TRADE_API_BLOCKED_BY_PR111}). "
            f"runtime_mode={self._runtime_mode.value}. PR111 builds the live trade "
            "interface but never sends a real order / cancel / leverage / margin "
            "request. Real execution lands in a later live-capital PR behind the "
            "Risk Engine + Execution FSM."
        )

    def create_order(self, *args: Any, **kwargs: Any) -> Any:
        self._refuse_trade("create_order")

    def cancel_order(self, *args: Any, **kwargs: Any) -> Any:
        self._refuse_trade("cancel_order")

    def cancel_all_orders(self, *args: Any, **kwargs: Any) -> Any:
        self._refuse_trade("cancel_all_orders")

    def set_leverage(self, *args: Any, **kwargs: Any) -> Any:
        self._refuse_trade("set_leverage")

    def set_margin_mode(self, *args: Any, **kwargs: Any) -> Any:
        self._refuse_trade("set_margin_mode")

    # ------------------------------------------------------------------
    # Precision / rule helpers (PR111: validation only, no submission)
    # ------------------------------------------------------------------
    def _filter_for(self, symbol: str) -> BinanceSymbolFilter | None:
        info = self.get_exchange_info()
        return info.get(symbol)

    def normalize_order_quantity(self, symbol: str, raw_qty: float) -> float:
        """Floor ``raw_qty`` to the symbol's step size + quantity precision."""
        f = self._filter_for(symbol)
        if f is None:
            return float(raw_qty)
        return _round_down_to_step(float(raw_qty), f.step_size, f.quantity_precision)

    def normalize_order_price(self, symbol: str, raw_price: float) -> float:
        """Round ``raw_price`` to the symbol's tick size + price precision."""
        f = self._filter_for(symbol)
        if f is None:
            return float(raw_price)
        return _round_to_tick(float(raw_price), f.tick_size, f.price_precision)

    def validate_min_notional(self, symbol: str, price: float, qty: float) -> bool:
        """True if ``price * qty`` meets the symbol's min notional."""
        f = self._filter_for(symbol)
        if f is None:
            return False
        if f.min_notional <= 0:
            return True
        return float(price) * float(qty) >= f.min_notional

    def validate_symbol_tradable(self, symbol: str) -> bool:
        """True if the symbol exists in exchangeInfo and is TRADING."""
        f = self._filter_for(symbol)
        return bool(f and f.is_tradable)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    def health_check(self) -> BinanceApiHealthResult:
        """Run a non-mutating Binance health check.

        Never places orders, never changes mode/leverage/margin. The
        private-read section runs only when ``enable_private_read`` is on
        AND credentials are present.
        """

        warnings: list[str] = []
        errors: list[str] = []
        public_ok = False
        private_read_ok = False
        can_read_account = False
        can_read_positions = False
        can_read_income = False
        can_trade_flag = False
        high_risk = False
        server_time_ms: int | None = None
        symbol_count = 0
        open_positions = 0

        private_trade_configured = self._config.has_credentials
        private_trade_enabled_by_config = self._config.enable_private_trade
        # PR111: order path is blocked while runtime mode does not allow
        # live orders (LIVE_SHADOW is the default). PR111 keeps it blocked
        # regardless, but we report the mode-based predicate honestly.
        private_trade_blocked_by_mode = not self._runtime_mode.real_orders_possible

        # --- PUBLIC_MARKET ---
        try:
            self.ping()
            server_time_ms = self.server_time()
            info = self.get_exchange_info()
            symbol_count = info.symbol_count
            public_ok = True
            self._emit(EventType.BINANCE_PUBLIC_HEALTH_OK, {"symbol_count": symbol_count})
        except Exception as exc:
            errors.append(f"public_market: {_sanitise(exc)}")

        # --- PRIVATE_READ ---
        if not self._config.enable_private_read:
            warnings.append("private_read_disabled_by_config")
        elif not self._config.has_credentials:
            warnings.append(API_HEALTH_MISSING_SECRET)
        else:
            try:
                account = self.get_account()
                can_read_account = True
                can_trade_flag = account.can_trade
                open_positions = account.open_position_count
                can_read_positions = True
                perms = inspect_permissions(account)
                high_risk = perms.high_risk_permission_warning
                if perms.warnings:
                    warnings.extend(perms.warnings)
                    self._emit(
                        EventType.BINANCE_PERMISSION_WARNING,
                        {"warnings": list(perms.warnings), "high_risk": high_risk},
                    )
                try:
                    self.get_income_history(limit=10)
                    can_read_income = True
                except Exception as exc:
                    warnings.append(f"income_read: {_sanitise(exc)}")
                private_read_ok = can_read_account
                if private_read_ok:
                    self._emit(EventType.BINANCE_PRIVATE_READ_OK, {"can_read_income": can_read_income})
            except Exception as exc:
                errors.append(f"private_read: {_sanitise(exc)}")

        # --- PRIVATE_TRADE (always reported as blocked) ---
        self._emit(
            EventType.BINANCE_PRIVATE_TRADE_BLOCKED,
            {
                "reason": TRADE_API_BLOCKED_BY_PR111,
                "configured": private_trade_configured,
                "enabled_by_config": private_trade_enabled_by_config,
                "blocked_by_mode": private_trade_blocked_by_mode,
            },
        )

        # --- Overall status ---
        statuses: list[HealthStatus] = []
        if public_ok:
            statuses.append(HealthStatus.PASS)
        else:
            statuses.append(HealthStatus.FAIL)
        if self._config.enable_private_read:
            statuses.append(HealthStatus.PASS if private_read_ok else HealthStatus.FAIL)
        if high_risk:
            statuses.append(HealthStatus.WARN)
        status = worst_of(statuses)

        return BinanceApiHealthResult(
            status=status,
            public_market_ok=public_ok,
            private_read_ok=private_read_ok,
            private_trade_configured=private_trade_configured,
            private_trade_enabled_by_config=private_trade_enabled_by_config,
            private_trade_blocked_by_mode=private_trade_blocked_by_mode,
            can_read_account=can_read_account,
            can_read_positions=can_read_positions,
            can_read_income=can_read_income,
            can_trade_if_account_reports_it=can_trade_flag,
            high_risk_permission_warning=high_risk,
            server_time_ms=server_time_ms,
            symbol_count=symbol_count,
            open_position_count=open_positions,
            warnings=tuple(warnings),
            errors=tuple(errors),
            masked_api_key=self._config.api_key.masked(),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _encode_params(params: Mapping[str, Any] | None) -> str:
    if not params:
        return ""
    pairs = [(k, v) for k, v in params.items() if v is not None]
    return urllib.parse.urlencode(pairs)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _round_down_to_step(value: float, step: float, precision: int) -> float:
    if step and step > 0:
        steps = math.floor(value / step + 1e-9)
        value = steps * step
    digits = precision if precision and precision > 0 else 8
    return round(value, digits)


def _round_to_tick(value: float, tick: float, precision: int) -> float:
    if tick and tick > 0:
        ticks = round(value / tick)
        value = ticks * tick
    digits = precision if precision and precision > 0 else 8
    return round(value, digits)


def _sanitise(exc: Exception) -> str:
    """Return a short, secret-free description of an exception.

    The Binance transport already strips query strings from its error
    text, so this is defence-in-depth: we only keep the type + message
    and never re-include the original request.
    """
    text = str(exc)
    # Belt-and-braces: drop anything after a '?' that could echo a query.
    if "?" in text:
        text = text.split("?", 1)[0]
    return text[:200]


__all__ = [
    "BinanceLiveClient",
    "BinanceTransport",
    "FORBIDDEN_TRADE_ENDPOINTS",
]
