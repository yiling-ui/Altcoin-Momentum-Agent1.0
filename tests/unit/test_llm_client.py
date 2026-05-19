"""Phase 10C - LLM client (transport) tests (Issue #10 Part 3)."""

from __future__ import annotations

import pytest

from app.llm.client import (
    DeepSeekClient,
    FakeLLMClient,
    LLMClientBase,
    LLMTimeoutError,
    SchemaRejection,
    TransportError,
)


# ---------------------------------------------------------------------------
# ABC
# ---------------------------------------------------------------------------
def test_cannot_instantiate_base():
    with pytest.raises(TypeError):
        LLMClientBase()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# FakeLLMClient
# ---------------------------------------------------------------------------
def test_fake_client_returns_fixed_payload():
    payload = {"narrative": "x", "confidence": 0.5}
    client = FakeLLMClient(payload=payload, model_name="fake")
    out = client.generate(messages=[{"role": "user", "content": "hi"}], timeout_ms=1000)
    assert out == payload
    assert client.calls == 1
    assert client.model_name == "fake"


def test_fake_client_iterates_payloads():
    p1 = {"a": 1}
    p2 = {"a": 2}
    client = FakeLLMClient(payloads=[p1, p2])
    assert client.generate(messages=[], timeout_ms=10) == p1
    assert client.generate(messages=[], timeout_ms=10) == p2
    # Sticks on last entry after exhaustion.
    assert client.generate(messages=[], timeout_ms=10) == p2


def test_fake_client_response_fn_inspects_input():
    seen: list[str] = []

    def fn(inp):
        seen.append(inp.source_text)
        return {"narrative": inp.source_text}

    client = FakeLLMClient(response_fn=fn)
    from app.llm.models import LLMInterpretationInput

    client.stage_input(LLMInterpretationInput(source_text="hello"))
    out = client.generate(messages=[], timeout_ms=10)
    assert out == {"narrative": "hello"}
    assert seen == ["hello"]


def test_fake_client_raise_after_triggers_timeout():
    client = FakeLLMClient(payload={"x": 1}, raise_after=1)
    # First call succeeds.
    client.generate(messages=[], timeout_ms=10)
    # Second call raises.
    with pytest.raises(LLMTimeoutError):
        client.generate(messages=[], timeout_ms=10)


def test_fake_client_constructor_requires_a_mode():
    with pytest.raises(ValueError):
        FakeLLMClient()


def test_fake_client_records_messages():
    client = FakeLLMClient(payload={"a": 1})
    client.generate(messages=[{"role": "user", "content": "abc"}], timeout_ms=10)
    assert client.last_messages == [{"role": "user", "content": "abc"}]


# ---------------------------------------------------------------------------
# DeepSeekClient skeleton
# ---------------------------------------------------------------------------
def test_deepseek_skeleton_refuses_when_disabled():
    client = DeepSeekClient(llm_enabled=False, credentials_provided=False)
    with pytest.raises(TransportError):
        client.generate(messages=[], timeout_ms=10)


def test_deepseek_skeleton_refuses_when_no_api_key():
    client = DeepSeekClient(llm_enabled=True, credentials_provided=False)
    with pytest.raises(TransportError):
        client.generate(messages=[], timeout_ms=10)


def test_deepseek_skeleton_refuses_even_with_both_flags():
    """Phase 10C ships NO real adapter. Even when both flags pass the
    skeleton MUST refuse with a TransportError so a future PR cannot
    accidentally trip the live path before Spec §41 Go/No-Go."""
    client = DeepSeekClient(llm_enabled=True, credentials_provided=True)
    with pytest.raises(TransportError):
        client.generate(messages=[], timeout_ms=10)


def test_deepseek_skeleton_constructor_validates_types():
    with pytest.raises(TypeError):
        DeepSeekClient(llm_enabled="yes", credentials_provided=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        DeepSeekClient(llm_enabled=True, credentials_provided=1)  # type: ignore[arg-type]


def test_deepseek_skeleton_exposes_state():
    client = DeepSeekClient(llm_enabled=True, credentials_provided=True)
    assert client.llm_enabled is True
    assert client.credentials_provided is True
    assert client.name == "deepseek_skeleton"


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------
def test_transport_error_hierarchy():
    assert issubclass(LLMTimeoutError, TransportError)
    assert issubclass(SchemaRejection, TransportError)
    # TransportError is NOT a SafetyViolation (Phase 10C contract).
    from app.core.errors import SafetyViolation

    assert not issubclass(TransportError, SafetyViolation)
