"""PR111 - DeepSeek live client + health tests (fake transport only)."""

from __future__ import annotations

import json

import pytest

from app.core.errors import LiveApiError
from app.core.events import Event, EventType
from app.live.api_config import LiveApiConfig
from app.live.deepseek_client import (
    DeepSeekLiveClient,
    validate_ai_market_intelligence,
)
from app.live.deepseek_health import run_deepseek_health_check
from app.live.status import HealthStatus

FAKE_KEY = "sk-fake-deepseek-key-not-real-00000000000000000000"


class FakeEventRepo:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, event: Event) -> None:
        self.events.append(event)

    def types(self):
        return [e.event_type for e in self.events]


def _chat_response(content: dict) -> dict:
    return {
        "model": "deepseek-chat",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        "choices": [{"message": {"role": "assistant", "content": json.dumps(content)}}],
    }


class FakeDeepSeekTransport:
    def __init__(self, response, *, fail_if_called: bool = False) -> None:
        self.response = response
        self.calls: list[tuple[str, dict]] = []
        self.fail_if_called = fail_if_called

    def __call__(self, url: str, headers, body):
        if self.fail_if_called:
            raise AssertionError("deepseek transport must NOT be called")
        # The key travels in the Authorization header; record it so we can
        # assert it is a Bearer header but never leak it elsewhere.
        self.calls.append((url, dict(body)))
        return self.response


def _cfg(env: dict) -> LiveApiConfig:
    return LiveApiConfig.from_env(env)


def _enabled_env():
    return {"AMA_DEEPSEEK_API_KEY": FAKE_KEY, "AMA_DEEPSEEK_ENABLED": "true"}


# ---- Test 19: missing api key returns disabled/missing secret -------------
def test_missing_api_key_raises_missing_secret_and_health_warns():
    cfg = _cfg({"AMA_DEEPSEEK_ENABLED": "true"})  # enabled but no key
    transport = FakeDeepSeekTransport(None, fail_if_called=True)
    cli = DeepSeekLiveClient(cfg.deepseek, transport=transport)
    with pytest.raises(LiveApiError) as exc:
        cli.chat_completion([{"role": "user", "content": "hi"}])
    assert "MISSING_SECRET" in str(exc.value)
    # Health check (call_api True) does not crash and warns.
    health = run_deepseek_health_check(cfg.deepseek, client=cli, call_api=True)
    assert "MISSING_SECRET" in health.to_dict()["detail"]
    assert health.briefing_generated is False


def test_disabled_client_does_not_call():
    cfg = _cfg({"AMA_DEEPSEEK_API_KEY": FAKE_KEY, "AMA_DEEPSEEK_ENABLED": "false"})
    transport = FakeDeepSeekTransport(None, fail_if_called=True)
    cli = DeepSeekLiveClient(cfg.deepseek, transport=transport)
    with pytest.raises(LiveApiError):
        cli.chat_completion([{"role": "user", "content": "hi"}])
    assert transport.calls == []


# ---- Test 20: valid fake response produces operator briefing --------------
def test_valid_response_produces_briefing():
    response = _chat_response({
        "market_summary": "BTC chops sideways; alt liquidity contracting.",
        "risk_notes": "Funding neutral; avoid late chase.",
        "operator_briefing": "Observe only; no clear right-tail setup.",
    })
    transport = FakeDeepSeekTransport(response)
    cfg = _cfg(_enabled_env())
    cli = DeepSeekLiveClient(cfg.deepseek, transport=transport)
    briefing = cli.generate_test_briefing()
    assert "BTC" in briefing.market_summary
    assert briefing.operator_briefing
    assert briefing.usage["total_tokens"] == 30
    # The key only appears in the Authorization header, never in body.
    assert all(FAKE_KEY not in str(body) for _, body in transport.calls)


# ---- Test 21: forbidden AI fields are rejected ----------------------------
def test_forbidden_fields_rejected_and_event_emitted():
    response = _chat_response({
        "market_summary": "Looks bullish.",
        "should_buy": True,
        "direction": "long",
        "leverage": 20,
        "stop_price": 59000,
        "take_profit": 65000,
        "runtime_config_patch": {"symbol_limit": 50},
    })
    transport = FakeDeepSeekTransport(response)
    repo = FakeEventRepo()
    cfg = _cfg(_enabled_env())
    cli = DeepSeekLiveClient(cfg.deepseek, transport=transport, event_repo=repo)
    briefing = cli.generate_test_briefing()
    # Market summary survives; trade-authority fields are stripped.
    assert briefing.market_summary == "Looks bullish."
    rejected = set(briefing.rejected_fields)
    for forbidden in ("should_buy", "direction", "leverage", "stop_price", "take_profit", "runtime_config_patch"):
        assert forbidden in rejected
    assert EventType.DEEPSEEK_OUTPUT_REJECTED_FOR_TRADE_AUTHORITY in repo.types()
    # The briefing schema never carries a forbidden field as a data key
    # (forbidden names only appear in the rejected_fields audit list).
    briefing_keys = set(briefing.to_dict().keys())
    assert briefing_keys.isdisjoint(
        {"should_buy", "direction", "leverage", "stop_price", "take_profit", "runtime_config_patch"}
    )


def test_validator_strips_nested_forbidden_fields():
    payload = {
        "market_summary": "ok",
        "nested": {"execution_decision": "enter", "note": "keep"},
    }
    result = validate_ai_market_intelligence(payload)
    assert "nested.execution_decision" in result.rejected_fields
    assert result.clean_payload["nested"] == {"note": "keep"}
    assert result.ai_trade_authority is False


# ---- Test 22: ai_trade_authority remains false ----------------------------
def test_ai_trade_authority_always_false():
    response = _chat_response({"market_summary": "neutral"})
    transport = FakeDeepSeekTransport(response)
    cfg = _cfg(_enabled_env())
    cli = DeepSeekLiveClient(cfg.deepseek, transport=transport)
    briefing = cli.generate_test_briefing()
    assert briefing.ai_trade_authority is False
    assert briefing.to_dict()["ai_trade_authority"] is False
    assert briefing.to_dict()["authority"] == "MARKET_INTELLIGENCE_ONLY"

    health = run_deepseek_health_check(cfg.deepseek, client=cli, call_api=True)
    assert health.to_dict()["ai_trade_authority"] is False
    assert health.status == HealthStatus.PASS


def test_chat_completion_retries_then_succeeds():
    # First call fails, second succeeds. Use injectable no-op sleep.
    calls = {"n": 0}
    good = _chat_response({"market_summary": "ok"})

    def flaky(url, headers, body):
        calls["n"] += 1
        if calls["n"] == 1:
            raise LiveApiError("deepseek: transient")
        return good

    cfg = _cfg(_enabled_env())
    cli = DeepSeekLiveClient(
        cfg.deepseek, transport=flaky, max_retries=2, sleep=lambda s: None
    )
    out = cli.chat_completion([{"role": "user", "content": "hi"}])
    assert out["model"] == "deepseek-chat"
    assert calls["n"] == 2
