"""DeepSeek live API client for the Live API Integration Pack (PR111).

PR111 contract:

  - API key held as :class:`app.live.secrets.SecretValue`; never logged
    / never in repr / never in exceptions (masked only).
  - Chat-completion wrapper with timeout + minimal retry/backoff.
  - Output is MARKET_INTELLIGENCE_ONLY. It may carry: market_summary,
    evidence_summary, risk_notes, operator_briefing, contradiction_notes,
    confidence commentary. It MUST NOT carry any trade-authority field
    (should_buy / should_sell / direction / position_size / leverage /
    stop_price / take_profit / order_type / execution_decision /
    runtime_config_patch, ...).
  - :func:`validate_ai_market_intelligence` strips + flags any forbidden
    field. Every result pins ``ai_trade_authority = False``.

The default transport uses :mod:`urllib.request` (no third-party
dependency). Tests inject a fake transport callable.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from loguru import logger

from app.core.errors import LiveApiError
from app.core.events import Event, EventType
from app.live.api_config import DeepSeekApiConfig
from app.live.secrets import API_HEALTH_MISSING_SECRET

#: Transport callable: (url, headers, json_body) -> parsed JSON value.
DeepSeekTransport = Callable[[str, Mapping[str, str], Mapping[str, Any]], Any]


# ---------------------------------------------------------------------------
# AI trade-authority guard
# ---------------------------------------------------------------------------
#: Fields a market-intelligence output is allowed to carry.
ALLOWED_INTELLIGENCE_FIELDS: frozenset[str] = frozenset(
    {
        "market_summary",
        "evidence_summary",
        "risk_notes",
        "operator_briefing",
        "contradiction_notes",
        "confidence_commentary",
        "confidence",
    }
)

#: Forbidden trade-authority fields. PR111 rejects/strips these at any
#: nesting depth, matched case-insensitively. The brief's explicit list
#: is included verbatim plus a defence-in-depth superset.
FORBIDDEN_TRADE_AUTHORITY_FIELDS: frozenset[str] = frozenset(
    {
        "should_buy",
        "should_sell",
        "should_short",
        "should_long",
        "direction",
        "position_size",
        "size",
        "leverage",
        "stop_price",
        "stop_loss",
        "take_profit",
        "target_price",
        "target",
        "order_type",
        "order",
        "execution_decision",
        "execution_command",
        "runtime_config_patch",
        "runtime_config",
        "buy",
        "sell",
        "long",
        "short",
        "entry",
        "entry_price",
        "exit",
        "exit_price",
        "signal_to_trade",
        "trade_signal",
        "risk_budget",
    }
)

#: Lower-cased view used for case-insensitive matching.
_FORBIDDEN_TRADE_AUTHORITY_LOWER: frozenset[str] = frozenset(
    f.lower() for f in FORBIDDEN_TRADE_AUTHORITY_FIELDS
)


@dataclass(frozen=True)
class AIIntelligenceValidationResult:
    """Result of validating a raw AI payload for trade-authority leakage."""

    clean_payload: dict[str, Any]
    rejected_fields: tuple[str, ...]
    ai_trade_authority: bool = False  # always False by construction

    @property
    def had_forbidden_fields(self) -> bool:
        return len(self.rejected_fields) > 0


def _strip_forbidden_case_insensitive(
    payload: Any, forbidden_lower: frozenset[str]
) -> tuple[Any, list[str]]:
    """Recursively strip forbidden keys, matching case-insensitively.

    Returns ``(clean_payload, stripped_dotted_paths)``. A key matches if
    its lower-cased form is in ``forbidden_lower``. This closes the gap
    where a model returns ``Direction`` / ``LEVERAGE`` / ``Should_Buy``
    instead of the lower-case spelling.
    """

    stripped: list[str] = []

    def _walk(node: Any, path: str) -> Any:
        if isinstance(node, Mapping):
            out: dict[str, Any] = {}
            for raw_key, value in node.items():
                key = str(raw_key)
                here = f"{path}.{key}" if path else key
                if key.strip().lower() in forbidden_lower:
                    stripped.append(here)
                    continue
                out[key] = _walk(value, here)
            return out
        if isinstance(node, (list, tuple)):
            return [_walk(item, f"{path}[{idx}]") for idx, item in enumerate(node)]
        return node

    cleaned = _walk(payload, "")
    return cleaned, sorted(set(stripped))


def validate_ai_market_intelligence(payload: Mapping[str, Any]) -> AIIntelligenceValidationResult:
    """Strip every forbidden trade-authority field from ``payload``.

    Returns a clean payload (forbidden keys removed at every nesting
    depth, matched case-insensitively) plus the sorted list of stripped
    dotted paths. The result always reports
    ``ai_trade_authority == False``.
    """

    cleaned, stripped = _strip_forbidden_case_insensitive(
        dict(payload), _FORBIDDEN_TRADE_AUTHORITY_LOWER
    )
    if not isinstance(cleaned, dict):
        cleaned = {}
    return AIIntelligenceValidationResult(
        clean_payload=cleaned,
        rejected_fields=tuple(stripped),
        ai_trade_authority=False,
    )


@dataclass(frozen=True)
class DeepSeekBriefing:
    """A validated, trade-authority-free market intelligence briefing."""

    market_summary: str = ""
    evidence_summary: str = ""
    risk_notes: str = ""
    operator_briefing: str = ""
    contradiction_notes: str = ""
    confidence_commentary: str = ""
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    rejected_fields: tuple[str, ...] = ()
    ai_trade_authority: bool = False  # pinned False

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_summary": self.market_summary,
            "evidence_summary": self.evidence_summary,
            "risk_notes": self.risk_notes,
            "operator_briefing": self.operator_briefing,
            "contradiction_notes": self.contradiction_notes,
            "confidence_commentary": self.confidence_commentary,
            "model": self.model,
            "usage": dict(self.usage),
            "rejected_fields": list(self.rejected_fields),
            # Hard-pinned: AI never has trade authority in PR111.
            "ai_trade_authority": False,
            "authority": "MARKET_INTELLIGENCE_ONLY",
        }


def _default_transport(timeout_seconds: float = 30.0) -> DeepSeekTransport:
    """Return a default urllib-based DeepSeek transport (POST + JSON)."""

    def _post(url: str, headers: Mapping[str, str], body: Mapping[str, Any]) -> Any:
        data = json.dumps(dict(body)).encode("utf-8")
        req = urllib.request.Request(url, method="POST", data=data, headers=dict(headers))
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                raw = resp.read()
                if resp.status != 200:
                    raise LiveApiError(f"deepseek: HTTP {resp.status}")
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise LiveApiError(f"deepseek: HTTP error {getattr(exc, 'code', '?')}") from None
        except urllib.error.URLError as exc:
            raise LiveApiError(f"deepseek: transport error: {exc.reason}") from None
        except (json.JSONDecodeError, ValueError):
            raise LiveApiError("deepseek: malformed JSON response") from None

    return _post


class DeepSeekLiveClient:
    """DeepSeek live client (PR111)."""

    name = "deepseek_live"

    def __init__(
        self,
        config: DeepSeekApiConfig,
        *,
        transport: DeepSeekTransport | None = None,
        request_timeout_seconds: float = 30.0,
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
        event_repo: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._transport: DeepSeekTransport = transport or _default_transport(
            timeout_seconds=request_timeout_seconds
        )
        self._max_retries = max(0, int(max_retries))
        self._backoff_seconds = float(backoff_seconds)
        self._event_repo = event_repo
        self._sleep = sleep

    @property
    def config(self) -> DeepSeekApiConfig:
        return self._config

    def _emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_repo is None:
            return
        try:
            self._event_repo.append(
                Event(event_type=event_type, source_module=self.name, payload=payload)
            )
        except Exception:  # pragma: no cover
            logger.debug("deepseek_live: event emit failed (non-fatal)")

    def _chat_url(self) -> str:
        return f"{self._config.base_url.rstrip('/')}/chat/completions"

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = True,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Call DeepSeek chat-completions with minimal retry/backoff.

        Requires the key to be present and the client to be enabled. The
        API key only ever travels in the Authorization header handed to
        the transport; it is never logged.
        """

        if not self._config.enabled:
            raise LiveApiError("deepseek: disabled (AMA_DEEPSEEK_ENABLED=false)")
        if not self._config.has_key:
            raise LiveApiError(f"deepseek: {API_HEALTH_MISSING_SECRET}")

        body: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": int(max_tokens),
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._config.api_key.reveal()}",
        }

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return self._transport(self._chat_url(), headers, body)
            except LiveApiError as exc:
                last_error = exc
                if attempt < self._max_retries:
                    self._sleep(self._backoff_seconds * (2 ** attempt))
                    continue
                raise
        # Unreachable, but keep type-checkers happy.
        raise last_error or LiveApiError("deepseek: unknown error")

    def generate_test_briefing(
        self,
        prompt: str = (
            "Produce a SHORT market-intelligence test briefing as JSON with keys "
            "market_summary, risk_notes, operator_briefing. This is a connectivity "
            "test only. Do NOT include any trading instruction, direction, size, "
            "leverage, stop, target, or execution decision."
        ),
    ) -> DeepSeekBriefing:
        """Generate a safe test briefing and validate it for trade authority.

        Any forbidden trade-authority field in the model output is
        stripped + flagged (and a
        ``DEEPSEEK_OUTPUT_REJECTED_FOR_TRADE_AUTHORITY`` event is
        emitted). The returned briefing always has
        ``ai_trade_authority == False``.
        """

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a MARKET_INTELLIGENCE_ONLY assistant for AMA-RT. You "
                    "never decide direction, size, leverage, stops, targets, or "
                    "execution. You only summarise evidence and risk."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        raw = self.chat_completion(messages)
        return self._parse_briefing(raw)

    def _parse_briefing(self, raw: Mapping[str, Any]) -> DeepSeekBriefing:
        usage = dict(raw.get("usage", {}) or {})
        model = str(raw.get("model", self._config.model) or self._config.model)

        content_obj: dict[str, Any] = {}
        try:
            choices = raw.get("choices") or []
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                if isinstance(content, str) and content.strip():
                    content_obj = json.loads(content)
                elif isinstance(content, Mapping):
                    content_obj = dict(content)
        except (json.JSONDecodeError, ValueError, AttributeError, IndexError, TypeError):
            content_obj = {}

        validation = validate_ai_market_intelligence(content_obj)
        if validation.had_forbidden_fields:
            self._emit(
                EventType.DEEPSEEK_OUTPUT_REJECTED_FOR_TRADE_AUTHORITY,
                {"rejected_fields": list(validation.rejected_fields)},
            )

        clean = validation.clean_payload
        return DeepSeekBriefing(
            market_summary=str(clean.get("market_summary", "") or ""),
            evidence_summary=str(clean.get("evidence_summary", "") or ""),
            risk_notes=str(clean.get("risk_notes", "") or ""),
            operator_briefing=str(clean.get("operator_briefing", "") or ""),
            contradiction_notes=str(clean.get("contradiction_notes", "") or ""),
            confidence_commentary=str(clean.get("confidence_commentary", "") or ""),
            model=model,
            usage=usage,
            rejected_fields=validation.rejected_fields,
            ai_trade_authority=False,
        )


__all__ = [
    "DeepSeekLiveClient",
    "DeepSeekTransport",
    "DeepSeekBriefing",
    "AIIntelligenceValidationResult",
    "validate_ai_market_intelligence",
    "ALLOWED_INTELLIGENCE_FIELDS",
    "FORBIDDEN_TRADE_AUTHORITY_FIELDS",
]
