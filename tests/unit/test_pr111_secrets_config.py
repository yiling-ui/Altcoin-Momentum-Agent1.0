"""PR111 - secret loading + config tests (no real API calls)."""

from __future__ import annotations

import json

from app.live.api_config import (
    DEFAULT_LIVE_RUNTIME_MODE,
    LiveApiConfig,
    LiveRuntimeMode,
)
from app.live.secrets import (
    API_HEALTH_MISSING_SECRET,
    SecretValue,
    load_secret,
    mask_secret,
)

# A fake-but-realistic-looking secret. NOT a real credential.
FAKE_SECRET = "ABCDEFGH1234567890ZYXWVUTSRQ0987654321abcdefghij"


# ---- Test 1: missing secret returns MISSING_SECRET, does not crash --------
def test_missing_secret_does_not_crash_and_reports_missing():
    sv = load_secret("AMA_BINANCE_API_KEY", environ={})
    assert sv.is_present is False
    assert sv.masked() == "<absent>"
    # Building the full config with an empty env must not raise.
    cfg = LiveApiConfig.from_env({})
    assert cfg.binance.has_credentials is False
    # The health-status string the rest of the pack maps to.
    assert API_HEALTH_MISSING_SECRET == "API_HEALTH_MISSING_SECRET"


# ---- Test 2: secret masking works -----------------------------------------
def test_mask_secret_formats():
    assert mask_secret("abcdefghijklmnopqrstuvwxyz") == "abc***xyz"
    assert mask_secret("short") == "*" * len("short")
    assert mask_secret("") == "<absent>"
    assert mask_secret(None) == "<absent>"


# ---- Test 3: secret does not appear in repr / json / safe dict ------------
def test_secret_never_appears_in_repr_or_serialisation():
    sv = SecretValue(name="AMA_BINANCE_API_SECRET", _raw=FAKE_SECRET)
    # repr / str only ever show masked form.
    assert FAKE_SECRET not in repr(sv)
    assert FAKE_SECRET not in str(sv)
    assert sv.masked() in repr(sv)
    # to_safe_dict never carries the raw value.
    assert FAKE_SECRET not in json.dumps(sv.to_safe_dict())
    # reveal() is the only way to get the raw value.
    assert sv.reveal() == FAKE_SECRET


def test_config_safe_dict_has_no_raw_secret():
    env = {
        "AMA_BINANCE_API_KEY": FAKE_SECRET,
        "AMA_BINANCE_API_SECRET": FAKE_SECRET + "SECRET",
        "AMA_TELEGRAM_BOT_TOKEN": "123456789:" + FAKE_SECRET,
        "AMA_DEEPSEEK_API_KEY": "sk-" + FAKE_SECRET,
    }
    cfg = LiveApiConfig.from_env(env)
    blob = json.dumps(cfg.to_safe_dict())
    assert FAKE_SECRET not in blob
    assert "sk-" + FAKE_SECRET not in blob
    # masked forms are present instead.
    assert cfg.binance.api_key.masked() in blob


# ---- runtime mode default + no auto-escalation ----------------------------
def test_default_runtime_mode_is_live_shadow():
    cfg = LiveApiConfig.from_env({})
    assert cfg.live_runtime_mode == LiveRuntimeMode.LIVE_SHADOW
    assert DEFAULT_LIVE_RUNTIME_MODE == LiveRuntimeMode.LIVE_SHADOW


def test_runtime_mode_never_auto_escalates_to_live_orders():
    # Even if the operator asks for LIVE_LIMITED / LIVE_FULL, PR111 keeps
    # the runtime at LIVE_SHADOW so the order path stays blocked.
    for asked in ("LIVE_LIMITED", "LIVE_FULL"):
        cfg = LiveApiConfig.from_env({"AMA_LIVE_RUNTIME_MODE": asked})
        assert cfg.live_runtime_mode == LiveRuntimeMode.LIVE_SHADOW
        assert cfg.live_runtime_mode.allows_live_orders is False


def test_unknown_runtime_mode_falls_back_safely():
    cfg = LiveApiConfig.from_env({"AMA_LIVE_RUNTIME_MODE": "garbage"})
    assert cfg.live_runtime_mode == LiveRuntimeMode.LIVE_SHADOW


def test_secret_logging_allowed_defaults_false():
    cfg = LiveApiConfig.from_env({})
    assert cfg.general.secret_logging_allowed is False


def test_asdict_on_config_does_not_leak_raw_secret():
    # Defence-in-depth: even dataclasses.asdict() on a config holding a
    # SecretValue must NOT surface the raw value, because SecretValue is
    # intentionally not a dataclass.
    import dataclasses

    from app.live.api_config import BinanceApiConfig

    cfg = BinanceApiConfig.from_env({
        "AMA_BINANCE_API_KEY": FAKE_SECRET,
        "AMA_BINANCE_API_SECRET": FAKE_SECRET + "S",
    })
    blob = repr(dataclasses.asdict(cfg))
    assert FAKE_SECRET not in blob
    # The SecretValue object survives asdict but only ever reprs masked.
    assert cfg.api_key.reveal() == FAKE_SECRET  # reveal still works for signing


def test_secretvalue_has_no_exposed_raw_attribute_dict():
    sv = SecretValue(name="AMA_BINANCE_API_SECRET", _raw=FAKE_SECRET)
    # __slots__ means there is no __dict__ to scrape.
    assert not hasattr(sv, "__dict__")
    assert FAKE_SECRET not in repr(vars(type(sv)))
