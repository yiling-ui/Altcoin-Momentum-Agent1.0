"""Phase 10C - LLM prompt tests (Issue #10 Part 3 / Spec §22)."""

from __future__ import annotations

from app.llm.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT_TEMPLATE,
    build_messages,
    build_user_prompt,
)


def test_prompt_version_is_versioned_string():
    assert isinstance(PROMPT_VERSION, str)
    assert PROMPT_VERSION.startswith("v")


def test_system_prompt_enumerates_forbidden_fields():
    """The fixed system prompt MUST itself list every forbidden field
    so even if the downstream guardrail ever drifted, the model has
    been told not to emit them. Tests pin this to fail loudly when a
    future maintainer dilutes the prompt."""
    text = SYSTEM_PROMPT_TEMPLATE
    for needle in (
        "direction",
        "leverage",
        "position size",
        "target price",
        "order type",
        "stop price",
        "take profit",
        "should_buy",
        "should_short",
        "trade_decision",
        "entry",
        "exit",
        "liquidation price",
        "margin mode",
        "risk budget",
        "signal_to_trade",
    ):
        assert needle in text, (
            f"system prompt does not mention {needle!r}; the guardrail "
            "must be enumerated in writing"
        )


def test_system_prompt_mentions_schema_constraints():
    text = SYSTEM_PROMPT_TEMPLATE
    for fragment in (
        "single JSON object",
        "AMA-RT",
        "Output schema",
        "discarded",
        "Risk Engine",
    ):
        assert fragment in text, (
            f"system prompt missing required fragment {fragment!r}"
        )


def test_system_prompt_mentions_prompt_injection_handling():
    text = SYSTEM_PROMPT_TEMPLATE
    assert "ignore previous instructions" in text.lower()
    assert "prompt_injection_detected" in text


def test_build_user_prompt_includes_signal_context():
    text = build_user_prompt(
        source_text="ALPHA token had 3x volume spike",
        symbol="ALPHAUSDT",
        anomaly_score=82.0,
        price_change_pct=0.05,
        oi_change_pct=0.03,
        funding_change_pct=0.0001,
        sources=("twitter:internal", "tg:cmc-news"),
    )
    assert "symbol: ALPHAUSDT" in text
    assert "anomaly_score: 82" in text
    assert "ALPHA token" in text
    assert "twitter:internal" in text
    assert "tg:cmc-news" in text
    assert "SOURCE TEXT BEGIN" in text
    assert "SOURCE TEXT END" in text


def test_build_user_prompt_handles_missing_optional_fields():
    text = build_user_prompt(
        source_text="hi",
        symbol=None,
        anomaly_score=None,
        price_change_pct=None,
        oi_change_pct=None,
        funding_change_pct=None,
        sources=(),
    )
    assert "symbol:" not in text
    assert "anomaly_score:" not in text
    assert "SOURCE TEXT BEGIN" in text


def test_build_messages_returns_system_then_user():
    messages = build_messages(source_text="hello world")
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "AMA-RT" in messages[0]["content"]
    assert "hello world" in messages[1]["content"]


def test_system_prompt_does_not_contain_credentials():
    """Defence in depth: the system prompt MUST NOT bake a credential."""
    text = SYSTEM_PROMPT_TEMPLATE.lower()
    for needle in (
        "api_key",
        "api-key",
        "api key=",
        "secret_key",
        "bot_token",
        "deepseek_api",
        "openai_api",
        "anthropic_api",
        "binance_api",
    ):
        assert needle not in text, (
            f"system prompt unexpectedly mentions {needle!r}"
        )
