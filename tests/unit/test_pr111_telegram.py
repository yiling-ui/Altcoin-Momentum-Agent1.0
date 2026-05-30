"""PR111 - Telegram live client + health tests (fake transport only)."""

from __future__ import annotations

from urllib.parse import urlsplit

from app.core.events import Event, EventType
from app.live.api_config import LiveApiConfig, LiveRuntimeMode
from app.live.status import HealthStatus, TELEGRAM_OUTBOUND_DISABLED
from app.live.telegram_client import TelegramLiveClient, format_operator_message
from app.live.telegram_health import run_telegram_health_check

FAKE_TOKEN = "123456789:ABCDEF_fake_token_value_not_real_000000000"


class FakeEventRepo:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, event: Event) -> None:
        self.events.append(event)

    def types(self):
        return [e.event_type for e in self.events]


class FakeTelegramTransport:
    def __init__(self, *, fail_if_called: bool = False) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self.fail_if_called = fail_if_called

    def __call__(self, method: str, url: str, body):
        if self.fail_if_called:
            raise AssertionError("telegram transport must NOT be called")
        # The URL carries the token; record only the path + method + body.
        self.calls.append((method, urlsplit(url).path, dict(body)))
        return {"ok": True, "result": {"message_id": 1}}


def _cfg(env: dict) -> LiveApiConfig:
    return LiveApiConfig.from_env(env)


# ---- Test 16: token masking works -----------------------------------------
def test_token_masking():
    cfg = _cfg({"AMA_TELEGRAM_BOT_TOKEN": FAKE_TOKEN})
    masked = cfg.telegram.bot_token.masked()
    assert masked != FAKE_TOKEN
    assert masked.startswith("123")
    assert FAKE_TOKEN not in str(cfg.telegram.to_safe_dict())


# ---- Test 17: outbound disabled returns TELEGRAM_OUTBOUND_DISABLED --------
def test_outbound_disabled_does_not_send():
    cfg = _cfg({
        "AMA_TELEGRAM_BOT_TOKEN": FAKE_TOKEN,
        "AMA_TELEGRAM_ALLOWED_CHAT_IDS": "123",
        "AMA_TELEGRAM_OUTBOUND_ENABLED": "false",
    })
    transport = FakeTelegramTransport(fail_if_called=True)
    repo = FakeEventRepo()
    cli = TelegramLiveClient(cfg.telegram, transport=transport, event_repo=repo)
    result = cli.send_test_message("123")
    assert result.sent is False
    assert result.detail == TELEGRAM_OUTBOUND_DISABLED
    assert transport.calls == []
    assert EventType.TELEGRAM_OUTBOUND_DISABLED in repo.types()

    # Health check reports it without crashing.
    health = run_telegram_health_check(cfg.telegram, client=cli)
    assert TELEGRAM_OUTBOUND_DISABLED in health.to_dict()["detail"]
    assert health.test_message_sent is False


# ---- Test 18: explicit test send uses fake transport + emits event --------
def test_explicit_test_send_emits_event():
    cfg = _cfg({
        "AMA_TELEGRAM_BOT_TOKEN": FAKE_TOKEN,
        "AMA_TELEGRAM_ALLOWED_CHAT_IDS": "123",
        "AMA_TELEGRAM_OUTBOUND_ENABLED": "true",
    })
    transport = FakeTelegramTransport()
    repo = FakeEventRepo()
    cli = TelegramLiveClient(cfg.telegram, transport=transport, event_repo=repo)
    result = cli.send_test_message("123", "hello operator")
    assert result.sent is True
    assert result.status == HealthStatus.PASS
    assert len(transport.calls) == 1
    method, path, body = transport.calls[0]
    assert path.endswith("/sendMessage")
    # Token never appears in the message body.
    assert FAKE_TOKEN not in str(body)
    assert EventType.TELEGRAM_TEST_MESSAGE_SENT in repo.types()


def test_chat_id_not_in_allowlist_is_not_sent():
    cfg = _cfg({
        "AMA_TELEGRAM_BOT_TOKEN": FAKE_TOKEN,
        "AMA_TELEGRAM_ALLOWED_CHAT_IDS": "123",
        "AMA_TELEGRAM_OUTBOUND_ENABLED": "true",
    })
    transport = FakeTelegramTransport(fail_if_called=True)
    cli = TelegramLiveClient(cfg.telegram, transport=transport)
    result = cli.send_test_message("999")  # not in allowlist
    assert result.sent is False
    assert result.status == HealthStatus.WARN
    assert transport.calls == []


def test_operator_message_banner_format():
    msg = format_operator_message("system up", runtime_mode=LiveRuntimeMode.LIVE_SHADOW)
    assert msg.startswith("[ama-rt:system_status]")
    assert "mode=LIVE_SHADOW" in msg
    assert "live=off" in msg


def test_health_check_does_not_send_by_default():
    cfg = _cfg({
        "AMA_TELEGRAM_BOT_TOKEN": FAKE_TOKEN,
        "AMA_TELEGRAM_ALLOWED_CHAT_IDS": "123",
        "AMA_TELEGRAM_OUTBOUND_ENABLED": "true",
    })
    transport = FakeTelegramTransport()
    cli = TelegramLiveClient(cfg.telegram, transport=transport)
    # send_test defaults False -> only getMe is called, no sendMessage.
    health = run_telegram_health_check(cfg.telegram, client=cli)
    assert health.test_message_sent is False
    assert all(not path.endswith("/sendMessage") for _, path, _ in transport.calls)
