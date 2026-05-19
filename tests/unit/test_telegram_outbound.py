"""Phase 10D - Telegram outbound transport tests (Issue #10 Part 4).

Pin the contract for :class:`TelegramOutboundClient` ABC,
:class:`FakeTelegramClient`, and :class:`TelegramHttpClient`.
"""

from __future__ import annotations

import inspect

import pytest

from app.core.errors import TelegramTransportError
from app.telegram.outbound import (
    FakeTelegramClient,
    OutboundCall,
    OutboundSurface,
    TelegramHttpClient,
    TelegramOutboundClient,
)


# ---------------------------------------------------------------------------
# ABC
# ---------------------------------------------------------------------------
def test_abc_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        TelegramOutboundClient()  # type: ignore[abstract]


def test_abc_only_declares_two_outbound_surfaces():
    """The ABC must declare exactly two abstract surfaces:
    ``send_message`` + ``send_document``. No third surface (eg
    ``send_photo``) without first extending :class:`OutboundSurface`.
    """
    abstract = set(TelegramOutboundClient.__abstractmethods__)
    assert abstract == {"send_message", "send_document"}


def test_outbound_surface_vocabulary_pinned():
    assert {s.value for s in OutboundSurface} == {
        "send_message",
        "send_document",
    }


def test_outbound_call_is_frozen():
    call = OutboundCall(
        surface=OutboundSurface.SEND_MESSAGE,
        chat_id="c",
        text="t",
    )
    with pytest.raises(Exception):
        call.text = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FakeTelegramClient
# ---------------------------------------------------------------------------
def test_fake_records_send_message():
    fake = FakeTelegramClient(outbound_enabled=True)
    fake.send_message("chat-1", "hello")
    assert fake.call_count == 1
    [call] = fake.calls
    assert call.surface is OutboundSurface.SEND_MESSAGE
    assert call.chat_id == "chat-1"
    assert call.text == "hello"


def test_fake_records_send_document():
    fake = FakeTelegramClient(outbound_enabled=True)
    fake.send_document(
        "chat-1",
        document_path="/tmp/x.zip",
        document_bytes=b"PK\x03\x04",
        filename="x.zip",
        caption="phase10d test",
    )
    assert fake.call_count == 1
    [call] = fake.calls
    assert call.surface is OutboundSurface.SEND_DOCUMENT
    assert call.document_filename == "x.zip"
    assert call.document_size_bytes == 4
    assert call.text == "phase10d test"


def test_fake_send_document_rejects_non_bytes():
    fake = FakeTelegramClient(outbound_enabled=True)
    with pytest.raises(TypeError):
        fake.send_document(
            "chat-1",
            document_path="/tmp/x.zip",
            document_bytes="not bytes",  # type: ignore[arg-type]
        )


def test_fake_send_document_rejects_empty_path():
    fake = FakeTelegramClient(outbound_enabled=True)
    with pytest.raises(ValueError):
        fake.send_document("chat-1", document_path="", document_bytes=b"")


def test_fake_failure_injection_records_failed_call_and_raises():
    fake = FakeTelegramClient(outbound_enabled=True)
    fake.set_failure_mode("simulated_drop")
    with pytest.raises(TelegramTransportError):
        fake.send_message("chat-1", "boom")
    assert fake.call_count == 0
    [failed] = fake.failed_calls
    assert failed.text == "boom"


def test_fake_failure_injection_clears_when_set_to_none():
    fake = FakeTelegramClient(outbound_enabled=True)
    fake.set_failure_mode("once")
    with pytest.raises(TelegramTransportError):
        fake.send_message("c", "1")
    fake.set_failure_mode(None)
    fake.send_message("c", "2")
    assert fake.call_count == 1


def test_fake_reset_clears_calls():
    fake = FakeTelegramClient(outbound_enabled=True)
    fake.send_message("c", "1")
    fake.send_message("c", "2")
    assert fake.call_count == 2
    fake.reset()
    assert fake.call_count == 0
    assert fake.failed_calls == ()


def test_fake_is_enabled_reflects_constructor_flag():
    on = FakeTelegramClient(outbound_enabled=True)
    off = FakeTelegramClient(outbound_enabled=False)
    assert on.is_enabled() is True
    assert off.is_enabled() is False


# ---------------------------------------------------------------------------
# TelegramHttpClient (refusal-only skeleton)
# ---------------------------------------------------------------------------
def test_http_send_message_always_refuses():
    client = TelegramHttpClient(outbound_enabled=False, token_provided=False)
    with pytest.raises(TelegramTransportError):
        client.send_message("c", "test")


def test_http_send_document_always_refuses():
    client = TelegramHttpClient(outbound_enabled=False, token_provided=False)
    with pytest.raises(TelegramTransportError):
        client.send_document(
            "c",
            document_path="/tmp/x.zip",
            document_bytes=b"PK",
            filename="x.zip",
            caption="x",
        )


def test_http_refuses_even_when_outbound_enabled_and_token_provided():
    """Phase 10D refuses every call regardless of the configuration
    flags; the real transport ships behind Spec §41 Go/No-Go."""
    client = TelegramHttpClient(outbound_enabled=True, token_provided=True)
    with pytest.raises(TelegramTransportError):
        client.send_message("c", "x")
    with pytest.raises(TelegramTransportError):
        client.send_document(
            "c", document_path="/tmp/x.zip", document_bytes=b"PK"
        )


def test_http_is_enabled_returns_false_in_phase10d():
    client = TelegramHttpClient(outbound_enabled=True, token_provided=True)
    assert client.is_enabled() is False


# ---------------------------------------------------------------------------
# Constructor signature - no credential parameter, no os.environ
# ---------------------------------------------------------------------------
def test_http_constructor_takes_only_boolean_flags():
    """Phase 10D forbids any credential parameter on the HTTP client."""
    sig = inspect.signature(TelegramHttpClient.__init__)
    params = list(sig.parameters)
    assert params[0] == "self"
    allowed = {"outbound_enabled", "token_provided"}
    assert set(params[1:]) <= allowed


def test_fake_constructor_takes_only_boolean_flags():
    sig = inspect.signature(FakeTelegramClient.__init__)
    params = list(sig.parameters)
    assert params[0] == "self"
    allowed = {"outbound_enabled", "failure_mode"}
    assert set(params[1:]) <= allowed


def test_constructor_does_NOT_accept_api_key():
    """Belt-and-braces: passing an api_key parameter must fail."""
    with pytest.raises(TypeError):
        TelegramHttpClient(api_key="x")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        FakeTelegramClient(bot_token="x")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# TelegramTransportError is NOT a SafetyViolation
# ---------------------------------------------------------------------------
def test_transport_error_is_not_a_safety_violation():
    """A transport drop is recoverable; it must NOT be caught as
    a safety violation. Phase 1 SafetyViolation handlers must not
    swallow Phase 10D transport errors."""
    from app.core.errors import SafetyViolation

    assert not issubclass(TelegramTransportError, SafetyViolation)


def test_subclass_inherits_outbound_surface_pin():
    """A future subclass that adds a third surface must extend the
    enum first - we pin the closed list so a quiet maintainer drift
    fails this test."""
    # Phase 10D: only two surfaces.
    assert len(OutboundSurface) == 2
