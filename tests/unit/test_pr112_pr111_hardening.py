"""PR112 - PR111 usability hardening tests.

Covers the additional PR111 hardening requirements discovered from the
fresh-server deployment:

  1. Placeholder secret detection (no real HTTP call with a placeholder).
  2. Better health-check operator messages (typed error classification).
  3. .env.live validation (suspicious line + AMA_SECRET_LOGGING_ALLOWED).
  4. Capital profile env compatibility (AMA_LIVE_CAPITAL_PROFILE[_ID]).
  5. Health check remains safe (flags false) even with the fixes.

All tests use fake transports only - no network.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from app.live.api_config import (
    CONFIG_INVALID_CAPITAL_PROFILE,
    LiveApiConfig,
    resolve_capital_profile_id,
)
from app.live.binance_client import BinanceLiveClient
from app.live.capital_profile import CapitalProfileId
from app.live.env_validation import (
    ENV_FILE_SUSPICIOUS_LINE,
    ENV_SECRET_LOGGING_ENABLED,
    ENV_SECRET_LOGGING_KEY_MISSING,
    validate_env_lines,
)
from app.live.health import build_safety_flags, run_unified_health_check
from app.live.secrets import (
    MISSING_REAL_SECRET,
    PLACEHOLDER_SECRET_CONFIGURED,
    SecretValue,
    is_placeholder_secret,
)
from app.live.status import (
    INVALID_SECRET_OR_UNAUTHORIZED,
    NETWORK_ERROR,
    PERMISSION_DENIED,
    RATE_LIMITED,
    classify_api_error,
)
from app.live.telegram_health import run_telegram_health_check


SAMPLE_EXCHANGE_INFO = {
    "serverTime": 1700000000000,
    "symbols": [
        {
            "symbol": "BTCUSDT",
            "status": "TRADING",
            "filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.1"}],
        }
    ],
}


class PublicOnlyTransport:
    """Returns public responses; raises if a PRIVATE path is requested."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.public = {
            "/fapi/v1/ping": {},
            "/fapi/v1/time": {"serverTime": 1700000000000},
            "/fapi/v1/exchangeInfo": SAMPLE_EXCHANGE_INFO,
        }

    def __call__(self, method, url, headers):
        path = urlsplit(url).path
        self.calls.append(path)
        if path in self.public:
            return self.public[path]
        raise AssertionError(f"PRIVATE path must NOT be called: {path}")


class FailIfCalledTransport:
    def __init__(self) -> None:
        self.calls: list = []

    def __call__(self, *args, **kwargs):
        self.calls.append(args)
        raise AssertionError("transport must NOT be called with a placeholder secret")


# ---------------------------------------------------------------------------
# 1. Placeholder secret detection
# ---------------------------------------------------------------------------
def test_is_placeholder_detects_put_your_tokens_but_not_fake_creds():
    assert is_placeholder_secret("PUT_YOUR_KEY_HERE") is True
    assert is_placeholder_secret("PUT_YOUR_SECRET_HERE") is True
    assert is_placeholder_secret("PUT_YOUR_BOT_TOKEN_HERE") is True
    assert is_placeholder_secret("PUT_YOUR_CHAT_ID_HERE") is True
    assert is_placeholder_secret("PUT_YOUR_DEEPSEEK_KEY_HERE") is True
    assert is_placeholder_secret("<your-key>") is True
    assert is_placeholder_secret("changeme") is True
    assert is_placeholder_secret("xxxxxxxx") is True
    # Empty/whitespace are "missing", not placeholder.
    assert is_placeholder_secret("") is False
    assert is_placeholder_secret("   ") is False
    assert is_placeholder_secret(None) is False
    # A fake-but-real-shaped credential must NOT be flagged as placeholder.
    assert is_placeholder_secret("FAKEKEY" + "0" * 57) is False
    assert is_placeholder_secret("123456789:ABCDEF_fake_token_value") is False
    assert is_placeholder_secret("sk-fake-deepseek-key-not-real-00000000") is False


def test_secret_value_health_status():
    assert SecretValue("K", "").health_status() == MISSING_REAL_SECRET
    assert SecretValue("K", "PUT_YOUR_KEY_HERE").health_status() == PLACEHOLDER_SECRET_CONFIGURED
    assert SecretValue("K", "FAKEKEY" + "0" * 57).health_status() == ""


def test_binance_placeholder_secret_skips_real_http_call():
    cfg = LiveApiConfig.from_env(
        {
            "AMA_BINANCE_API_KEY": "PUT_YOUR_KEY_HERE",
            "AMA_BINANCE_API_SECRET": "PUT_YOUR_SECRET_HERE",
            "AMA_BINANCE_ENABLE_PRIVATE_READ": "true",
        }
    )
    transport = PublicOnlyTransport()
    cli = BinanceLiveClient(cfg.binance, transport=transport, clock=lambda: 1700000000000)
    result = cli.health_check()
    # No private endpoint was contacted (would have raised).
    assert "/fapi/v2/account" not in transport.calls
    assert "/fapi/v1/income" not in transport.calls
    # The placeholder is surfaced as a clear operator action, not an HTTP 401.
    assert PLACEHOLDER_SECRET_CONFIGURED in result.warnings
    assert result.private_read_ok is False


def test_telegram_placeholder_token_does_not_call_getme():
    cfg = LiveApiConfig.from_env(
        {
            "AMA_TELEGRAM_BOT_TOKEN": "PUT_YOUR_BOT_TOKEN_HERE",
            "AMA_TELEGRAM_OUTBOUND_ENABLED": "true",
        }
    )
    from app.live.telegram_client import TelegramLiveClient

    transport = FailIfCalledTransport()
    cli = TelegramLiveClient(cfg.telegram, transport=transport)
    health = run_telegram_health_check(cfg.telegram, client=cli)
    assert transport.calls == []  # getMe never called
    assert PLACEHOLDER_SECRET_CONFIGURED in health.to_dict()["detail"]


def test_deepseek_placeholder_key_does_not_call_api():
    cfg = LiveApiConfig.from_env(
        {
            "AMA_DEEPSEEK_API_KEY": "PUT_YOUR_DEEPSEEK_KEY_HERE",
            "AMA_DEEPSEEK_ENABLED": "true",
        }
    )
    from app.live.deepseek_client import DeepSeekLiveClient
    from app.live.deepseek_health import run_deepseek_health_check

    transport = FailIfCalledTransport()
    cli = DeepSeekLiveClient(cfg.deepseek, transport=transport)
    health = run_deepseek_health_check(cfg.deepseek, client=cli, call_api=True)
    assert transport.calls == []
    assert PLACEHOLDER_SECRET_CONFIGURED in health.to_dict()["detail"]
    assert health.briefing_generated is False


# ---------------------------------------------------------------------------
# 2. Better health-check operator messages
# ---------------------------------------------------------------------------
def test_classify_api_error_distinguishes_causes():
    assert classify_api_error("binance: HTTP error 401 from /fapi/v2/account") == INVALID_SECRET_OR_UNAUTHORIZED
    assert classify_api_error("binance: HTTP error 403 from /fapi/v2/account") == PERMISSION_DENIED
    assert classify_api_error("binance: HTTP error 429 from /fapi/v1/income") == RATE_LIMITED
    assert classify_api_error("binance: transport error talking to /fapi/v1/ping: timed out") == NETWORK_ERROR


def test_binance_401_classified_not_generic():
    cfg = LiveApiConfig.from_env(
        {
            "AMA_BINANCE_API_KEY": "FAKEKEY" + "0" * 57,
            "AMA_BINANCE_API_SECRET": "FAKESECRET" + "0" * 54,
            "AMA_BINANCE_ENABLE_PRIVATE_READ": "true",
        }
    )

    def transport(method, url, headers):
        from app.core.errors import LiveApiError

        path = urlsplit(url).path
        if path in ("/fapi/v1/ping", "/fapi/v1/time", "/fapi/v1/exchangeInfo"):
            return {"serverTime": 1} if path == "/fapi/v1/time" else (
                SAMPLE_EXCHANGE_INFO if path == "/fapi/v1/exchangeInfo" else {}
            )
        raise LiveApiError("binance: HTTP error 401 from /fapi/v2/account")

    cli = BinanceLiveClient(cfg.binance, transport=transport, clock=lambda: 1)
    result = cli.health_check()
    assert any(INVALID_SECRET_OR_UNAUTHORIZED in e for e in result.errors)


# ---------------------------------------------------------------------------
# 3. .env.live validation
# ---------------------------------------------------------------------------
def test_env_validation_flags_suspicious_shell_line():
    lines = [
        "AMA_BINANCE_API_KEY=abc",
        "chmod 600 .env.liveALLOWED=false",
        "AMA_SECRET_LOGGING_ALLOWED=false",
    ]
    result = validate_env_lines(lines)
    assert ENV_FILE_SUSPICIOUS_LINE in result.warnings
    assert any(f.reason == ENV_FILE_SUSPICIOUS_LINE for f in result.findings)


def test_env_validation_warns_when_secret_logging_key_missing():
    result = validate_env_lines(["AMA_BINANCE_API_KEY=abc"])
    assert ENV_SECRET_LOGGING_KEY_MISSING in result.warnings


def test_env_validation_warns_when_secret_logging_enabled():
    result = validate_env_lines(["AMA_SECRET_LOGGING_ALLOWED=true"])
    assert ENV_SECRET_LOGGING_ENABLED in result.warnings


def test_env_validation_clean_file_ok():
    result = validate_env_lines(
        [
            "# comment",
            "AMA_BINANCE_API_KEY=abc",
            "AMA_SECRET_LOGGING_ALLOWED=false",
            "export AMA_LIVE_CAPITAL_PROFILE=L1_10U_PROBE",
        ]
    )
    assert result.ok is True
    assert result.findings == ()
    # No secret VALUE is ever surfaced - only key names.
    assert "abc" not in str(result.to_dict())


# ---------------------------------------------------------------------------
# 4. Capital profile env compatibility
# ---------------------------------------------------------------------------
def test_capital_profile_alias_loads_l1_10u():
    r = resolve_capital_profile_id({"AMA_LIVE_CAPITAL_PROFILE": "L1_10U_PROBE"})
    assert r.profile_id is CapitalProfileId.L1_10U_PROBE
    assert r.error == ""
    cfg = LiveApiConfig.from_env({"AMA_LIVE_CAPITAL_PROFILE": "L1_10U_PROBE"})
    assert cfg.capital_profile_id is CapitalProfileId.L1_10U_PROBE


def test_capital_profile_id_takes_priority_over_alias():
    r = resolve_capital_profile_id(
        {
            "AMA_LIVE_CAPITAL_PROFILE_ID": "L2_25U_50U_SCOUT",
            "AMA_LIVE_CAPITAL_PROFILE": "L1_10U_PROBE",
        }
    )
    assert r.profile_id is CapitalProfileId.L2_25U_50U_SCOUT
    assert r.source_env == "AMA_LIVE_CAPITAL_PROFILE_ID"


def test_capital_profile_default_is_l0_shadow():
    r = resolve_capital_profile_id({})
    assert r.profile_id is CapitalProfileId.L0_SHADOW
    assert r.error == ""
    assert r.warning == ""


def test_capital_profile_invalid_is_explicit_not_silent():
    r = resolve_capital_profile_id({"AMA_LIVE_CAPITAL_PROFILE": "NOT_A_PROFILE"})
    # Stays on the safe default BUT surfaces the explicit error/warning.
    assert r.profile_id is CapitalProfileId.L0_SHADOW
    assert r.error == CONFIG_INVALID_CAPITAL_PROFILE
    assert CONFIG_INVALID_CAPITAL_PROFILE in r.warning


def test_health_report_reflects_capital_profile_from_env():
    # The PR111 bug: AMA_LIVE_CAPITAL_PROFILE=L1_10U_PROBE was ignored and
    # the health report still showed L0_SHADOW. It must now show L1_10U_PROBE.
    cfg = LiveApiConfig.from_env({"AMA_LIVE_CAPITAL_PROFILE": "L1_10U_PROBE"})
    report = run_unified_health_check(cfg, check_binance=False, check_telegram=True)
    assert report.to_dict()["capital_profile_id"] == "L1_10U_PROBE"


def test_health_report_surfaces_invalid_profile_warning():
    cfg = LiveApiConfig.from_env({"AMA_LIVE_CAPITAL_PROFILE": "BOGUS"})
    report = run_unified_health_check(cfg, check_binance=False, check_telegram=True)
    d = report.to_dict()
    assert d["safety_flags"]["capital_profile_config_error"] == CONFIG_INVALID_CAPITAL_PROFILE
    assert any("CONFIG_INVALID_CAPITAL_PROFILE" in w for w in d["warnings"])


# ---------------------------------------------------------------------------
# 5. Health check remains safe even with the hardening fixes
# ---------------------------------------------------------------------------
def test_health_check_safe_flags_with_placeholders():
    cfg = LiveApiConfig.from_env(
        {
            "AMA_BINANCE_API_KEY": "PUT_YOUR_KEY_HERE",
            "AMA_BINANCE_API_SECRET": "PUT_YOUR_SECRET_HERE",
            "AMA_BINANCE_ENABLE_PRIVATE_READ": "true",
            "AMA_LIVE_CAPITAL_PROFILE": "L1_10U_PROBE",
        }
    )
    flags = build_safety_flags(cfg)
    assert flags["exchange_live_orders"] is False
    assert flags["live_trading"] is False
    assert flags["trade_authority"] is False
    assert flags["ai_trade_authority"] is False
    assert flags["binance_private_trade_blocked"] is True
    assert flags["phase_12_forbidden"] is True
    # Capital profile is surfaced (the fix) but no flag is loosened.
    assert flags["capital_profile_id"] == "L1_10U_PROBE"
