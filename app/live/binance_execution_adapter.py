"""Binance USD-M Futures execution adapter (PR113 - Live Execution v0).

This is the FIRST AMA-RT module able to compose + send a real Binance
order / cancel request. It is BLOCKED by default: every order-sending
surface refuses to open a socket unless it is told explicitly that the
order is authorised (``real_order_allowed=True``) AND the config has
``enable_private_trade=True`` AND the runtime mode is ``LIVE_LIMITED``.
That triple is normally only ever true after the
:class:`app.live.execution_gateway.LiveExecutionGateway` has cleared
every gate.

Capabilities:
  - ``normalize_order``                       (tickSize / stepSize / precision)
  - ``validate_order_against_exchange_info``  (tradable / minQty / minNotional)
  - ``build_order_request``                   (exchange-ready request)
  - ``submit_order`` / ``cancel_order``       (compose + send, or refuse)
  - ``get_order`` / ``get_open_orders``       (signed read; safe to retry)
  - ``get_user_trades``                       (fills, with fee)

Hard boundaries (PR113):
  - It NEVER changes leverage. ``set_leverage`` refuses.
  - It NEVER changes margin mode. ``set_margin_mode`` refuses.
  - It NEVER blind-retries an order/cancel (no duplicate orders). Only
    idempotent status reads may retry.
  - Idempotency is enforced via ``newClientOrderId`` = client_order_id.
  - The HMAC signature is computed only inside :meth:`_signed_query`;
    neither the secret nor the full signed URL is ever logged.

Transport
---------
The transport callable is ``(method, url, headers) -> parsed_json`` (the
same shape PR111 uses), so tests inject a deterministic fake and no real
socket is opened. The default transport uses :mod:`urllib.request`.
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
from app.core.enums import LiveRuntimeMode
from app.core.errors import SafeModeViolation
from app.core.events import Event, EventType
from app.live.api_config import BinanceApiConfig
from app.live.binance_models import (
    BinanceExchangeInfoSnapshot,
    BinanceSymbolFilter,
)
from app.live.execution_errors import ExecutionAdapterError
from app.live.execution_models import (
    LiveExecutionStatus,
    LiveFillEvent,
    LiveOrderIntent,
    LiveOrderRequest,
    LiveOrderResult,
    OrderSide,
    OrderType,
    OrderValidationReason,
    OrderValidationResult,
    map_binance_status,
)

BINANCE_EXECUTION_ADAPTER_MODULE = "live.binance_execution_adapter"

DEFAULT_RECV_WINDOW_MS = 5000

# Endpoints PR113 is allowed to compose (order create / cancel / status).
ORDER_ENDPOINT = "/fapi/v1/order"
OPEN_ORDERS_ENDPOINT = "/fapi/v1/openOrders"
USER_TRADES_ENDPOINT = "/fapi/v1/userTrades"

# Sentinel surfaced when the adapter refuses to send because the order is
# not authorised. No socket is opened.
ADAPTER_BLOCKED_NOT_AUTHORISED = "ADAPTER_BLOCKED_ORDER_NOT_AUTHORISED"

#: Transport callable: (method, url, headers) -> parsed JSON value.
BinanceExecutionTransport = Callable[[str, str, Mapping[str, str]], Any]


class BinanceExecutionHttpError(ExecutionAdapterError):
    """A Binance order endpoint returned an error code (e.g. -2019).

    Carries the numeric ``code`` + a sanitised ``msg``. The exchange's
    error body is its own JSON (``{"code":...,"msg":...}``) and does not
    echo our request signature, so the msg is safe to keep.
    """

    def __init__(self, code: int | str | None, msg: str) -> None:
        super().__init__(f"binance order error code={code}: {msg}")
        self.code = code
        self.msg = msg


def _default_execution_transport(timeout_seconds: float = 5.0) -> BinanceExecutionTransport:
    """Return a urllib-based transport that supports GET / POST / DELETE.

    Never logs the URL (it carries a signature). On a Binance error body
    it raises :class:`BinanceExecutionHttpError` with the parsed code /
    msg (the response body is the exchange's own JSON, not our request).
    """

    def _fetch(method: str, url: str, headers: Mapping[str, str]) -> Any:
        path_only = urllib.parse.urlsplit(url).path
        req = urllib.request.Request(url, method=method, headers=dict(headers))
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Try to parse Binance's {"code","msg"} error body. The body is
            # the exchange's JSON and never echoes our query / signature.
            code: int | str | None = getattr(exc, "code", None)
            msg = f"HTTP {code} from {path_only}"
            try:
                body = exc.read().decode("utf-8")
                parsed = json.loads(body)
                if isinstance(parsed, dict) and "code" in parsed:
                    code = parsed.get("code")
                    msg = str(parsed.get("msg", msg))[:200]
            except Exception:  # pragma: no cover - best-effort body parse
                pass
            raise BinanceExecutionHttpError(code, msg) from None
        except urllib.error.URLError as exc:
            raise ExecutionAdapterError(
                f"binance: transport error talking to {path_only}: {exc.reason}"
            ) from None
        except (json.JSONDecodeError, ValueError):
            raise ExecutionAdapterError(
                f"binance: malformed JSON response from {path_only}"
            ) from None

    return _fetch


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
    text = str(exc)
    if "?" in text:
        text = text.split("?", 1)[0]
    return text[:200]


class BinanceExecutionAdapter:
    """Binance USDT-M futures order execution adapter (PR113, blocked by default)."""

    name = "binance_execution"

    def __init__(
        self,
        config: BinanceApiConfig,
        *,
        runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_SHADOW,
        transport: BinanceExecutionTransport | None = None,
        exchange_info: BinanceExchangeInfoSnapshot | None = None,
        request_timeout_seconds: float = 5.0,
        recv_window_ms: int = DEFAULT_RECV_WINDOW_MS,
        event_repo: Any | None = None,
        clock: Callable[[], int] = now_ms,
        status_check_retries: int = 2,
    ) -> None:
        self._config = config
        self._runtime_mode = runtime_mode
        self._transport: BinanceExecutionTransport = transport or _default_execution_transport(
            timeout_seconds=request_timeout_seconds
        )
        self._exchange_info = exchange_info
        self._recv_window_ms = int(recv_window_ms)
        self._event_repo = event_repo
        self._clock = clock
        self._status_check_retries = max(0, int(status_check_retries))

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    @property
    def runtime_mode(self) -> LiveRuntimeMode:
        return self._runtime_mode

    @property
    def private_trade_enabled_by_config(self) -> bool:
        return bool(self._config.enable_private_trade)

    @property
    def fapi_base_url(self) -> str:
        return self._config.resolved_fapi_base_url.rstrip("/")

    def set_exchange_info(self, snapshot: BinanceExchangeInfoSnapshot) -> None:
        self._exchange_info = snapshot

    @property
    def exchange_info(self) -> BinanceExchangeInfoSnapshot | None:
        return self._exchange_info

    def _filter_for(self, symbol: str) -> BinanceSymbolFilter | None:
        if self._exchange_info is None:
            return None
        return self._exchange_info.get(symbol)

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
                    payload={**payload, "exchange_live_orders_default": False},
                )
            )
        except Exception:  # pragma: no cover - audit must never crash a send
            logger.debug("binance_execution: event emit failed (non-fatal)")

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------
    def normalize_order(
        self, intent: LiveOrderIntent
    ) -> tuple[float, float | None, float | None]:
        """Return ``(quantity, price, stop_price)`` normalised to the filters.

        Quantity is floored to the step size; price / stop price are
        rounded to the tick size. Unknown symbol -> raw values.
        """
        f = self._filter_for(intent.symbol)
        if f is None:
            return intent.quantity, intent.price, intent.stop_price
        qty = _round_down_to_step(float(intent.quantity), f.step_size, f.quantity_precision)
        price = (
            _round_to_tick(float(intent.price), f.tick_size, f.price_precision)
            if intent.price is not None
            else None
        )
        stop = (
            _round_to_tick(float(intent.stop_price), f.tick_size, f.price_precision)
            if intent.stop_price is not None
            else None
        )
        return qty, price, stop

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate_order_against_exchange_info(
        self, intent: LiveOrderIntent
    ) -> OrderValidationResult:
        """Validate an order against the symbol's exchangeInfo filters."""
        reasons: list[str] = []
        f = self._filter_for(intent.symbol)
        if f is None:
            return OrderValidationResult(
                ok=False,
                reasons=(OrderValidationReason.SYMBOL_FILTER_MISSING,),
                normalized_symbol=intent.symbol,
                normalized_quantity=float(intent.quantity),
                normalized_price=intent.price,
                normalized_stop_price=intent.stop_price,
                effective_notional_usdt=0.0,
                symbol_tradable=False,
            )

        if not f.is_tradable:
            reasons.append(OrderValidationReason.SYMBOL_NOT_TRADABLE)

        qty, price, stop = self.normalize_order(intent)

        if qty <= 0:
            if intent.reduce_only:
                reasons.append(OrderValidationReason.REDUCE_ONLY_REQUIRES_QUANTITY)
            else:
                reasons.append(OrderValidationReason.QUANTITY_NON_POSITIVE)
        elif f.min_qty > 0 and qty < f.min_qty:
            reasons.append(OrderValidationReason.QUANTITY_BELOW_MIN_QTY)

        if intent.order_type.needs_price and price is None:
            reasons.append(OrderValidationReason.PRICE_REQUIRED_FOR_LIMIT)
        if intent.order_type.needs_stop_price and stop is None:
            reasons.append(OrderValidationReason.STOP_PRICE_REQUIRED)

        # Reference price for the notional check: explicit price, else the
        # planned entry, else the stop price.
        ref_price = price if price is not None else intent.planned_entry_price
        if ref_price is None:
            ref_price = stop
        ref_price = float(ref_price) if ref_price else 0.0
        effective_notional = qty * ref_price if qty > 0 and ref_price > 0 else 0.0

        if f.min_notional > 0 and qty > 0 and ref_price > 0:
            if effective_notional < f.min_notional:
                reasons.append(OrderValidationReason.MIN_NOTIONAL_NOT_MET)

        return OrderValidationResult(
            ok=len(reasons) == 0,
            reasons=tuple(reasons),
            normalized_symbol=intent.symbol,
            normalized_quantity=qty,
            normalized_price=price,
            normalized_stop_price=stop,
            effective_notional_usdt=effective_notional,
            tick_size=f.tick_size,
            step_size=f.step_size,
            min_qty=f.min_qty,
            min_notional=f.min_notional,
            symbol_tradable=f.is_tradable,
        )

    def build_order_request(
        self,
        intent: LiveOrderIntent,
        validation: OrderValidationResult,
        *,
        real_order_allowed: bool = False,
        dry_run: bool = True,
    ) -> LiveOrderRequest:
        """Build a normalised, exchange-ready :class:`LiveOrderRequest`."""
        return LiveOrderRequest(
            normalized_symbol=validation.normalized_symbol,
            normalized_quantity=validation.normalized_quantity,
            normalized_price=validation.normalized_price,
            normalized_stop_price=validation.normalized_stop_price,
            order_type=intent.order_type,
            side=intent.side,
            reduce_only=intent.reduce_only,
            client_order_id=intent.client_order_id or "",
            time_in_force=intent.time_in_force,
            dry_run=bool(dry_run),
            real_order_allowed=bool(real_order_allowed),
        )

    # ------------------------------------------------------------------
    # Authorisation predicate (the adapter's own last line of defence)
    # ------------------------------------------------------------------
    def _send_authorised(self, request: LiveOrderRequest) -> tuple[bool, str | None]:
        """Decide whether the adapter may open a socket for ``request``.

        Even after the gateway clears its gates, the adapter independently
        refuses unless: real_order_allowed AND not dry_run AND private
        trade enabled by config AND runtime is LIVE_LIMITED. This is
        defence-in-depth, NOT the primary gate.
        """
        if not request.real_order_allowed:
            return False, "real_order_allowed_false"
        if request.dry_run:
            return False, "dry_run"
        if not self._config.enable_private_trade:
            return False, "private_trade_disabled_by_config"
        if self._runtime_mode is not LiveRuntimeMode.LIVE_LIMITED:
            return False, "runtime_mode_not_live_limited"
        if not self._config.has_credentials:
            return False, "missing_credentials"
        return True, None

    # ------------------------------------------------------------------
    # Request plumbing (signed)
    # ------------------------------------------------------------------
    def _signed_query(self, params: dict[str, Any]) -> tuple[str, dict[str, str]]:
        """Build a signed query string + auth headers. Secret never logged."""
        params = {k: v for k, v in params.items() if v is not None}
        params["timestamp"] = self._clock()
        params.setdefault("recvWindow", self._recv_window_ms)
        query = urllib.parse.urlencode(params)
        secret = self._config.api_secret.reveal().encode("utf-8")
        signature = hmac.new(secret, query.encode("utf-8"), hashlib.sha256).hexdigest()
        signed = f"{query}&signature={signature}"
        headers = {"X-MBX-APIKEY": self._config.api_key.reveal()}
        return signed, headers

    def _send_signed(
        self, method: str, path: str, params: dict[str, Any], *, retries: int = 0
    ) -> Any:
        signed, headers = self._signed_query(dict(params))
        url = f"{self.fapi_base_url}{path}?{signed}"
        attempt = 0
        while True:
            try:
                return self._transport(method, url, headers)
            except ExecutionAdapterError:
                # Only idempotent reads (retries>0) may be retried; an order
                # / cancel passes retries=0 so it NEVER duplicates.
                if attempt >= retries:
                    raise
                attempt += 1
                # Re-sign so the timestamp / recvWindow stay valid.
                signed, headers = self._signed_query(dict(params))
                url = f"{self.fapi_base_url}{path}?{signed}"

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------
    def submit_order(
        self, request: LiveOrderRequest, *, real_order_allowed: bool | None = None
    ) -> LiveOrderResult:
        """Compose + send a real order, or refuse (no socket) when blocked."""
        if real_order_allowed is not None:
            request = _with_real_order_allowed(request, bool(real_order_allowed))

        authorised, block_reason = self._send_authorised(request)
        if not authorised:
            return self._blocked_result(request, block_reason)

        params = self._compose_order_params(request)
        try:
            body = self._send_signed("POST", ORDER_ENDPOINT, params, retries=0)
        except BinanceExecutionHttpError as exc:
            self._emit(
                EventType.LIVE_ORDER_REJECTED,
                {
                    "client_order_id": request.client_order_id,
                    "symbol": request.normalized_symbol,
                    "error_code": exc.code,
                    "reason": "exchange_rejected",
                },
                symbol=request.normalized_symbol,
            )
            return LiveOrderResult(
                status=LiveExecutionStatus.REJECTED,
                client_order_id=request.client_order_id,
                symbol=request.normalized_symbol,
                side=request.side,
                order_type=request.order_type,
                reduce_only=request.reduce_only,
                error_code=str(exc.code) if exc.code is not None else None,
                error_message_sanitized=exc.msg,
                is_real_order=True,
                audit_event=EventType.LIVE_ORDER_REJECTED.value,
                created_at=self._clock(),
                updated_at=self._clock(),
            )
        except ExecutionAdapterError as exc:
            self._emit(
                EventType.LIVE_ORDER_FAILED,
                {
                    "client_order_id": request.client_order_id,
                    "symbol": request.normalized_symbol,
                    "reason": "transport_error",
                },
                symbol=request.normalized_symbol,
            )
            return LiveOrderResult(
                status=LiveExecutionStatus.FAILED,
                client_order_id=request.client_order_id,
                symbol=request.normalized_symbol,
                side=request.side,
                order_type=request.order_type,
                reduce_only=request.reduce_only,
                error_code="TRANSPORT_ERROR",
                error_message_sanitized=_sanitise(exc),
                is_real_order=False,
                audit_event=EventType.LIVE_ORDER_FAILED.value,
                created_at=self._clock(),
                updated_at=self._clock(),
            )

        result = self.parse_order_response(body, fallback_request=request, is_real_order=True)
        self._emit(
            EventType.LIVE_ORDER_SUBMITTED,
            {
                "client_order_id": result.client_order_id,
                "exchange_order_id": result.exchange_order_id,
                "symbol": result.symbol,
                "status": result.status.value,
                "is_real_order": True,
            },
            symbol=result.symbol,
        )
        return result

    def _blocked_result(self, request: LiveOrderRequest, reason: str | None) -> LiveOrderResult:
        self._emit(
            EventType.LIVE_ORDER_ADAPTER_BLOCKED,
            {
                "client_order_id": request.client_order_id,
                "symbol": request.normalized_symbol,
                "reason": ADAPTER_BLOCKED_NOT_AUTHORISED,
                "detail": reason,
                "runtime_mode": self._runtime_mode.value,
                "private_trade_enabled_by_config": self.private_trade_enabled_by_config,
                "real_order_allowed": request.real_order_allowed,
            },
            symbol=request.normalized_symbol,
        )
        return LiveOrderResult(
            status=LiveExecutionStatus.BLOCKED,
            client_order_id=request.client_order_id,
            symbol=request.normalized_symbol,
            side=request.side,
            order_type=request.order_type,
            reduce_only=request.reduce_only,
            error_code=ADAPTER_BLOCKED_NOT_AUTHORISED,
            error_message_sanitized=f"adapter_blocked:{reason}",
            is_real_order=False,
            audit_event=EventType.LIVE_ORDER_ADAPTER_BLOCKED.value,
            created_at=self._clock(),
            updated_at=self._clock(),
        )

    def _compose_order_params(self, request: LiveOrderRequest) -> dict[str, Any]:
        """Compose the Binance order params (idempotent via newClientOrderId)."""
        params: dict[str, Any] = {
            "symbol": request.normalized_symbol,
            "side": request.side.value,
            "type": request.order_type.value,
            "newClientOrderId": request.client_order_id,
        }
        if request.normalized_quantity and request.normalized_quantity > 0:
            params["quantity"] = request.normalized_quantity
        if request.reduce_only:
            params["reduceOnly"] = "true"
        if request.order_type is OrderType.LIMIT:
            params["price"] = request.normalized_price
            params["timeInForce"] = request.time_in_force.value
        if request.order_type in (OrderType.STOP_MARKET, OrderType.TAKE_PROFIT_MARKET):
            params["stopPrice"] = request.normalized_stop_price
        return params

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------
    def cancel_order(
        self,
        symbol: str,
        *,
        client_order_id: str | None = None,
        order_id: str | None = None,
        real_order_allowed: bool = False,
    ) -> LiveOrderResult:
        """Cancel an order, or refuse (no socket) when not authorised."""
        side = OrderSide.BUY
        otype = OrderType.MARKET
        request = LiveOrderRequest(
            normalized_symbol=symbol,
            normalized_quantity=0.0,
            normalized_price=None,
            normalized_stop_price=None,
            order_type=otype,
            side=side,
            reduce_only=True,
            client_order_id=client_order_id or "",
            dry_run=not real_order_allowed,
            real_order_allowed=real_order_allowed,
        )
        authorised, block_reason = self._send_authorised(request)
        if not authorised:
            return self._blocked_result(request, block_reason)

        params: dict[str, Any] = {"symbol": symbol}
        if order_id is not None:
            params["orderId"] = order_id
        if client_order_id is not None:
            params["origClientOrderId"] = client_order_id
        try:
            body = self._send_signed("DELETE", ORDER_ENDPOINT, params, retries=0)
        except BinanceExecutionHttpError as exc:
            return LiveOrderResult(
                status=LiveExecutionStatus.FAILED,
                client_order_id=client_order_id or "",
                symbol=symbol,
                side=side,
                order_type=otype,
                reduce_only=True,
                error_code=str(exc.code) if exc.code is not None else None,
                error_message_sanitized=exc.msg,
                is_real_order=True,
                audit_event=EventType.LIVE_ORDER_FAILED.value,
            )
        result = self.parse_order_response(body, fallback_request=request, is_real_order=True)
        result = _with_status(result, LiveExecutionStatus.CANCELED)
        self._emit(
            EventType.LIVE_ORDER_CANCELED,
            {"client_order_id": result.client_order_id, "symbol": symbol},
            symbol=symbol,
        )
        return result

    # ------------------------------------------------------------------
    # Read surfaces (signed; safe to retry)
    # ------------------------------------------------------------------
    def get_order(
        self,
        symbol: str,
        *,
        client_order_id: str | None = None,
        order_id: str | None = None,
    ) -> LiveOrderResult:
        """Read an order's status (idempotent; safe to retry)."""
        params: dict[str, Any] = {"symbol": symbol}
        if order_id is not None:
            params["orderId"] = order_id
        if client_order_id is not None:
            params["origClientOrderId"] = client_order_id
        body = self._send_signed(
            "GET", ORDER_ENDPOINT, params, retries=self._status_check_retries
        )
        return self.parse_order_response(body, is_real_order=False)

    def get_open_orders(self, symbol: str | None = None) -> list[LiveOrderResult]:
        """Read open orders (idempotent; safe to retry)."""
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        body = self._send_signed(
            "GET", OPEN_ORDERS_ENDPOINT, params, retries=self._status_check_retries
        )
        return [self.parse_order_response(row, is_real_order=False) for row in (body or [])]

    def get_user_trades(self, symbol: str, *, limit: int = 50) -> list[LiveFillEvent]:
        """Read recent user trades (fills, with fee). Idempotent; safe to retry."""
        params: dict[str, Any] = {"symbol": symbol, "limit": int(limit)}
        body = self._send_signed(
            "GET", USER_TRADES_ENDPOINT, params, retries=self._status_check_retries
        )
        return [LiveFillEvent.from_user_trade(row) for row in (body or [])]

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    def parse_order_response(
        self,
        body: dict[str, Any],
        *,
        fallback_request: LiveOrderRequest | None = None,
        is_real_order: bool = False,
    ) -> LiveOrderResult:
        """Parse a Binance order response into a :class:`LiveOrderResult`."""
        body = body or {}
        raw_status = body.get("status")
        status = map_binance_status(raw_status)
        executed_qty = _to_float(body.get("executedQty"))
        cum_quote = _to_float(body.get("cumQuote") or body.get("cumQuote") or body.get("cummulativeQuoteQty"))
        avg_price = _to_float(body.get("avgPrice"))
        if avg_price <= 0 and executed_qty > 0 and cum_quote > 0:
            avg_price = cum_quote / executed_qty

        side_raw = body.get("side")
        if side_raw is not None:
            side = OrderSide(str(side_raw).strip().upper())
        elif fallback_request is not None:
            side = fallback_request.side
        else:
            side = OrderSide.BUY

        type_raw = body.get("type") or body.get("origType")
        if type_raw is not None:
            try:
                order_type = OrderType(str(type_raw).strip().upper())
            except ValueError:
                order_type = fallback_request.order_type if fallback_request else OrderType.MARKET
        elif fallback_request is not None:
            order_type = fallback_request.order_type
        else:
            order_type = OrderType.MARKET

        client_order_id = (
            str(body.get("clientOrderId"))
            if body.get("clientOrderId")
            else (fallback_request.client_order_id if fallback_request else "")
        )
        exchange_order_id = (
            str(body.get("orderId")) if body.get("orderId") is not None else None
        )
        audit_event = None
        if status is LiveExecutionStatus.FILLED:
            audit_event = EventType.LIVE_ORDER_FILLED.value
        elif status is LiveExecutionStatus.PARTIALLY_FILLED:
            audit_event = EventType.LIVE_ORDER_PARTIALLY_FILLED.value

        return LiveOrderResult(
            status=status,
            exchange_order_id=exchange_order_id,
            client_order_id=client_order_id,
            symbol=str(body.get("symbol", "") or (fallback_request.normalized_symbol if fallback_request else "")),
            side=side,
            order_type=order_type,
            submitted_price=_to_float(body.get("price")) or None,
            avg_fill_price=avg_price or None,
            executed_qty=executed_qty,
            cum_quote=cum_quote,
            fee_usdt=None,  # fees live on userTrades, not the order response
            realized_pnl_usdt=None,
            raw_status=str(raw_status) if raw_status is not None else None,
            reduce_only=bool(body.get("reduceOnly", fallback_request.reduce_only if fallback_request else False)),
            is_real_order=bool(is_real_order),
            audit_event=audit_event,
            created_at=self._clock(),
            updated_at=_to_int_or_now(body.get("updateTime"), self._clock),
        )

    # ------------------------------------------------------------------
    # Forbidden surfaces (PR113 never changes leverage / margin)
    # ------------------------------------------------------------------
    def set_leverage(self, *args: Any, **kwargs: Any) -> Any:
        raise SafeModeViolation(
            "BinanceExecutionAdapter.set_leverage is forbidden in PR113: this "
            "PR never auto-changes leverage. Leverage modification is reserved "
            "for a dedicated future PR behind its own guard."
        )

    def set_margin_mode(self, *args: Any, **kwargs: Any) -> Any:
        raise SafeModeViolation(
            "BinanceExecutionAdapter.set_margin_mode is forbidden in PR113: this "
            "PR never auto-changes margin mode. Margin-mode modification is "
            "reserved for a dedicated future PR behind its own guard."
        )


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _with_real_order_allowed(request: LiveOrderRequest, allowed: bool) -> LiveOrderRequest:
    return LiveOrderRequest(
        normalized_symbol=request.normalized_symbol,
        normalized_quantity=request.normalized_quantity,
        normalized_price=request.normalized_price,
        normalized_stop_price=request.normalized_stop_price,
        order_type=request.order_type,
        side=request.side,
        reduce_only=request.reduce_only,
        client_order_id=request.client_order_id,
        time_in_force=request.time_in_force,
        dry_run=not allowed,
        real_order_allowed=allowed,
    )


def _with_status(result: LiveOrderResult, status: LiveExecutionStatus) -> LiveOrderResult:
    return LiveOrderResult(
        status=status,
        exchange_order_id=result.exchange_order_id,
        client_order_id=result.client_order_id,
        symbol=result.symbol,
        side=result.side,
        order_type=result.order_type,
        submitted_price=result.submitted_price,
        avg_fill_price=result.avg_fill_price,
        executed_qty=result.executed_qty,
        cum_quote=result.cum_quote,
        fee_usdt=result.fee_usdt,
        realized_pnl_usdt=result.realized_pnl_usdt,
        raw_status=result.raw_status,
        error_code=result.error_code,
        error_message_sanitized=result.error_message_sanitized,
        reduce_only=result.reduce_only,
        created_at=result.created_at,
        updated_at=result.updated_at,
        is_real_order=result.is_real_order,
        audit_event=result.audit_event,
    )


def _to_int_or_now(value: Any, clock: Callable[[], int]) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return clock()


__all__ = [
    "BINANCE_EXECUTION_ADAPTER_MODULE",
    "ADAPTER_BLOCKED_NOT_AUTHORISED",
    "BinanceExecutionTransport",
    "BinanceExecutionHttpError",
    "BinanceExecutionAdapter",
]
