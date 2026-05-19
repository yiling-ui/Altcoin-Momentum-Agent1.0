"""Phase 10C - LLM cache tests (Issue #10 Part 3)."""

from __future__ import annotations

import pytest

from app.llm.cache import LLMCache, LLMCacheEntry


def test_cache_make_key_deterministic():
    k1 = LLMCache.make_key(
        input_text="hello",
        prompt_version="v1",
        schema_version="v1",
        model_name="fake",
        throttle_tier="standard",
    )
    k2 = LLMCache.make_key(
        input_text="hello",
        prompt_version="v1",
        schema_version="v1",
        model_name="fake",
        throttle_tier="standard",
    )
    assert k1 == k2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"input_text": "different"},
        {"prompt_version": "v2"},
        {"schema_version": "v2"},
        {"model_name": "other"},
        {"throttle_tier": "light"},
        {"symbol": "BTCUSDT"},
    ],
)
def test_cache_make_key_changes_when_inputs_change(kwargs):
    base = dict(
        input_text="hello",
        prompt_version="v1",
        schema_version="v1",
        model_name="fake",
        throttle_tier="standard",
    )
    altered = dict(base, **kwargs)
    assert LLMCache.make_key(**base) != LLMCache.make_key(**altered)


def test_cache_get_miss_returns_none():
    cache = LLMCache()
    assert cache.get("nope") is None


def test_cache_put_then_get_returns_payload():
    cache = LLMCache(max_entries=4)
    payload = {"narrative": "hi", "confidence": 0.5}
    cache.put("k", payload)
    entry = cache.get("k")
    assert isinstance(entry, LLMCacheEntry)
    assert entry.payload == payload
    assert entry.hits == 1


def test_cache_lru_eviction():
    cache = LLMCache(max_entries=2)
    cache.put("a", {"x": 1})
    cache.put("b", {"x": 2})
    cache.put("c", {"x": 3})
    assert cache.get("a") is None
    assert cache.get("b") is not None
    assert cache.get("c") is not None


def test_cache_refuses_credential_keys():
    cache = LLMCache()
    for forbidden in (
        "api_key",
        "API_KEY",
        "deepseek_api_key",
        "openai_api_secret",
        "telegram_bot_token",
        "private_key",
        "session_id",
        "password",
    ):
        with pytest.raises(ValueError):
            cache.put("k", {forbidden: "secret"})


def test_cache_clear_resets_size():
    cache = LLMCache()
    cache.put("k", {"x": 1})
    assert cache.size == 1
    cache.clear()
    assert cache.size == 0


def test_cache_max_entries_validated():
    with pytest.raises(ValueError):
        LLMCache(max_entries=0)
