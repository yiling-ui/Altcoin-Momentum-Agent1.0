"""Phase 10C - LLM transport (Issue #10 Part 3).

This module ships:

  - :class:`LLMClientBase` ABC: the interface every transport
    implements.
  - :class:`FakeLLMClient`: a deterministic in-memory transport used
    by tests AND the boot self-check. The fake client is the only
    transport actually invoked anywhere in Phase 10C.
  - :class:`DeepSeekClient`: a refusal-only skeleton for the future
    real DeepSeek adapter. Phase 10C ships NO real network code.
    The skeleton refuses to be invoked unless ``llm_enabled=True``
    AND ``credentials_provided=True`` is passed in by the caller
    (the package never reads the process environment). Calling it
    under those conditions still raises :class:`TransportError`;
    the actual adapter lands behind a Go/No-Go checklist in a
    separate PR.

Typed errors:

  - :class:`TransportError`           - transport-level failure
  - :class:`LLMTimeoutError`          - explicit timeout sentinel
  - :class:`SchemaRejection`          - the model returned a payload
                                        the schema validator rejects
                                        (re-raised by the orchestrator
                                        as a degraded result)

Phase 10C boundary
------------------

This module:

  - imports nothing that opens a socket (no ``aiohttp`` / ``httpx`` /
    ``requests`` / ``websockets`` / ``ccxt`` / ``binance`` /
    ``openai`` / ``anthropic`` / ``deepseek``)
  - reads NO process-environment variable for credentials - the
    caller passes them as a boolean flag through the constructor
  - defines no write surface (``create_order`` / ``cancel_order`` /
    ``set_leverage`` / ``set_margin_mode``)
  - defines no Telegram outbound surface reference
  - never raises a SafeModeViolation - that is the Phase 1 / 3
    contract; LLM faults degrade the result, they do not abort the
    process

The Phase 10C interpreter wraps every transport call in a try/except
and converts any error - even unexpected ones - into a degraded
:class:`LLMInterpretationResult`. The transport is therefore allowed
to raise.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Callable

from app.llm.models import LLMInterpretationInput
from app.llm.prompts import PROMPT_VERSION


# ===========================================================================
# Typed errors
# ===========================================================================
class TransportError(Exception):
    """A transport-layer failure (connection / serialisation / etc.).

    Phase 10C deliberately does NOT subclass ``AMARTError``: a
    transport drop is recoverable. The orchestrator wraps it into a
    degraded result. Tests assert this distinction.
    """


class LLMTimeoutError(TransportError):
    """Sentinel indicating the transport hit its timeout budget."""


class SchemaRejection(TransportError):
    """The model returned a payload the schema validator rejects."""


# ===========================================================================
# Base ABC
# ===========================================================================
class LLMClientBase(ABC):
    """Abstract LLM transport.

    A transport is a thin wrapper that returns *one* JSON-safe dict
    given a list of chat messages. It is NOT the orchestrator; it
    must not validate the schema, must not enforce the whitelist, and
    must not strip forbidden fields. Those guardrails live in
    :class:`app.llm.interpreter.LLMGuardedInterpreter`.

    Concrete subclasses:

      - :class:`FakeLLMClient`  - in-memory deterministic test double
      - :class:`DeepSeekClient` - refusal-only skeleton for now
    """

    name: str = "llm_client_base"
    model_name: str = "unknown"

    @abstractmethod
    def generate(
        self,
        *,
        messages: list[dict[str, str]],
        timeout_ms: int,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """Return one JSON-safe dict.

        On any failure the method MUST raise an
        :class:`TransportError` (or subclass). The orchestrator
        converts that into a degraded result.
        """
        raise NotImplementedError


# ===========================================================================
# FakeLLMClient
# ===========================================================================
ResponseFn = Callable[[LLMInterpretationInput], dict[str, Any]]


class FakeLLMClient(LLMClientBase):
    """Deterministic in-memory transport.

    Three construction modes:

      1. ``FakeLLMClient(payload=...)`` - return ``payload`` for every
         call.
      2. ``FakeLLMClient(payloads=[p1, p2, ...])`` - return one
         payload per call, then repeat the last entry.
      3. ``FakeLLMClient(response_fn=fn)`` - call ``fn(input)`` per
         call. Useful for tests that derive a response from the
         input.

    Plus failure injection knobs:

      - ``raise_after=N`` - raise :class:`LLMTimeoutError` after N
        successful calls. The orchestrator must wrap this into a
        degraded result.
      - ``raise_exc=`` - the exception instance to raise (default
        ``LLMTimeoutError``).
    """

    name = "fake_llm_client"

    def __init__(
        self,
        *,
        payload: dict[str, Any] | None = None,
        payloads: list[dict[str, Any]] | None = None,
        response_fn: ResponseFn | None = None,
        model_name: str = "fake-llm",
        raise_after: int | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        if (
            payload is None
            and payloads is None
            and response_fn is None
        ):
            raise ValueError(
                "FakeLLMClient requires payload= / payloads= / response_fn="
            )
        self._payload = payload
        self._payloads = list(payloads) if payloads is not None else None
        self._response_fn = response_fn
        self.model_name = str(model_name)
        self._raise_after = raise_after
        self._raise_exc = raise_exc or LLMTimeoutError("fake timeout")
        self._calls = 0
        self._last_input: LLMInterpretationInput | None = None
        self._last_messages: list[dict[str, str]] | None = None

    @property
    def calls(self) -> int:
        return self._calls

    @property
    def last_messages(self) -> list[dict[str, str]] | None:
        return self._last_messages

    def stage_input(self, value: LLMInterpretationInput) -> None:
        """Stage the upstream input so ``response_fn`` can inspect it.

        The orchestrator calls this before invoking :meth:`generate`
        when ``response_fn`` is wired. Tests can also call it directly
        for unit-level verification.
        """
        self._last_input = value

    def generate(
        self,
        *,
        messages: list[dict[str, str]],
        timeout_ms: int,
        seed: int | None = None,
    ) -> dict[str, Any]:
        self._calls += 1
        self._last_messages = list(messages)
        if (
            self._raise_after is not None
            and self._calls > int(self._raise_after)
        ):
            raise self._raise_exc
        if self._response_fn is not None:
            inp = self._last_input
            if inp is None:
                inp = LLMInterpretationInput(source_text="")
            return dict(self._response_fn(inp))
        if self._payloads is not None:
            index = min(self._calls - 1, len(self._payloads) - 1)
            return dict(self._payloads[index])
        assert self._payload is not None  # validated in __init__
        return dict(self._payload)


# ===========================================================================
# DeepSeekClient skeleton
# ===========================================================================
class DeepSeekClient(LLMClientBase):
    """Refusal-only skeleton for a future DeepSeek transport.

    Phase 10C ships NO real DeepSeek code. The skeleton exists for
    static-typing and documentation purposes. Even when
    ``llm_enabled=True`` and an explicit ``api_key`` is provided, the
    skeleton raises :class:`TransportError` on every call so the
    orchestrator degrades. The actual adapter lands behind the
    Spec §41 Go/No-Go checklist.

    The skeleton intentionally:

      - imports nothing from ``deepseek`` / ``openai`` / ``aiohttp``
      - reads NO process-environment for credentials - the caller MUST
        pass credentials explicitly via the constructor flag
      - has no Telegram outbound surface reference anywhere
      - has NO ``create_order`` / ``cancel_order`` /
        ``set_leverage`` / ``set_margin_mode`` definition
    """

    name = "deepseek_skeleton"

    def __init__(
        self,
        *,
        model_name: str = "deepseek-chat",
        llm_enabled: bool,
        credentials_provided: bool,
    ) -> None:
        if not isinstance(llm_enabled, bool):
            raise TypeError("llm_enabled must be bool")
        if not isinstance(credentials_provided, bool):
            raise TypeError("credentials_provided must be bool")
        self._llm_enabled = bool(llm_enabled)
        self._credentials_provided = bool(credentials_provided)
        self.model_name = str(model_name)

    @property
    def llm_enabled(self) -> bool:
        return self._llm_enabled

    @property
    def credentials_provided(self) -> bool:
        return self._credentials_provided

    def generate(
        self,
        *,
        messages: list[dict[str, str]],
        timeout_ms: int,
        seed: int | None = None,
    ) -> dict[str, Any]:
        # Defence in depth: refuse twice.
        if not self._llm_enabled:
            raise TransportError(
                "DeepSeekClient: llm_enabled=False; refusing to call. "
                "Phase 1 safety lock keeps llm_enabled=False; the real "
                "adapter lands behind a Go/No-Go checklist (Spec §41)."
            )
        if not self._credentials_provided:
            raise TransportError(
                "DeepSeekClient: no credentials supplied; refusing to "
                "call. Phase 10C requires the caller to pass credentials "
                "explicitly; the package never reads process environment."
            )
        # Phase 10C ships NO real adapter. Any call past the two
        # guards above still refuses so a future PR cannot accidentally
        # trip the live path before passing the Go/No-Go checklist.
        raise TransportError(
            "DeepSeekClient is a Phase 10C skeleton. The real adapter "
            "ships behind Spec §41 Go/No-Go; this build is paper-only "
            "and does not execute network calls. Use FakeLLMClient for "
            "tests + the boot self-check."
        )


__all__ = [
    "LLMClientBase",
    "FakeLLMClient",
    "DeepSeekClient",
    "TransportError",
    "LLMTimeoutError",
    "SchemaRejection",
]


# Light helper kept module-private; tests access via the orchestrator.
def _ensure_json_safe(value: Any) -> dict[str, Any]:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
        json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise TransportError(f"non-JSON-safe payload: {exc}") from exc
    if not isinstance(value, dict):
        raise TransportError("payload must be a JSON object")
    return value


# Pin the prompt-version constant so a future maintainer cannot drift
# the prompt without bumping the version.
assert isinstance(PROMPT_VERSION, str) and PROMPT_VERSION.startswith("v"), (
    "PROMPT_VERSION must be a versioned string"
)
