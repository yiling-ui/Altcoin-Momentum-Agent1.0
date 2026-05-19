"""Phase 11B - environment-variable pre-flight guard tests."""

from __future__ import annotations

import pytest

from app.core.errors import SafetyViolation
from app.paper_run.config import (
    DEFAULT_FORBIDDEN_CRED_ENV_VARS,
    DEFAULT_INSPECTED_ENV_VARS,
    EnvGuardConfig,
)
from app.paper_run.env_guard import EnvGuard, EnvGuardReport


def _strict_config(**kwargs) -> EnvGuardConfig:
    base = {
        "enabled": True,
        "refuse_on_dangerous_value": True,
        "inspected_env_vars": DEFAULT_INSPECTED_ENV_VARS,
        "forbidden_credential_env_vars": DEFAULT_FORBIDDEN_CRED_ENV_VARS,
    }
    base.update(kwargs)
    return EnvGuardConfig(**base)


def test_clean_environment_passes():
    guard = EnvGuard(config=_strict_config(), environ={})
    report = guard.evaluate()
    assert report.passed is True
    assert report.forbidden_credentials_present == ()
    assert report.dangerous_runtime_values == ()
    assert "clean_env" in report.notes


def test_assert_safe_returns_report_on_clean_env():
    guard = EnvGuard(config=_strict_config(), environ={})
    report = guard.assert_safe()
    assert report.passed is True


def test_disabled_guard_short_circuits():
    """When the guard is disabled, evaluate() returns a passed report
    even with a forbidden credential present."""
    guard = EnvGuard(
        config=_strict_config(enabled=False),
        environ={"BINANCE_API_KEY": "danger"},
    )
    report = guard.evaluate()
    assert report.passed is True
    assert "env_guard_disabled" in report.notes


def test_forbidden_credential_present_fails():
    guard = EnvGuard(
        config=_strict_config(),
        environ={"BINANCE_API_KEY": "leaked-secret-value"},
    )
    report = guard.evaluate()
    assert report.passed is False
    assert "BINANCE_API_KEY" in report.forbidden_credentials_present


def test_assert_safe_raises_on_forbidden_credential():
    guard = EnvGuard(
        config=_strict_config(),
        environ={"TELEGRAM_BOT_TOKEN": "xxx"},
    )
    with pytest.raises(SafetyViolation):
        guard.assert_safe()


def test_empty_credential_value_is_treated_as_absent():
    """The .env.example ships every credential as an empty placeholder
    so an operator who copies it verbatim must not trip the guard."""
    guard = EnvGuard(
        config=_strict_config(),
        environ={"BINANCE_API_KEY": ""},
    )
    report = guard.evaluate()
    assert report.passed is True


def test_whitespace_credential_value_is_treated_as_absent():
    guard = EnvGuard(
        config=_strict_config(),
        environ={"BINANCE_API_KEY": "   "},
    )
    report = guard.evaluate()
    assert report.passed is True


@pytest.mark.parametrize(
    "name, value",
    [
        ("AMA_LIVE_TRADING_ENABLED", "true"),
        ("AMA_RIGHT_TAIL_ENABLED", "1"),
        ("AMA_LLM_ENABLED", "yes"),
        ("AMA_EXCHANGE_LIVE_ORDER_ENABLED", "ON"),
    ],
)
def test_dangerous_runtime_truthy_fails(name: str, value: str):
    guard = EnvGuard(config=_strict_config(), environ={name: value})
    report = guard.evaluate()
    assert report.passed is False
    flagged = {n for n, _ in report.dangerous_runtime_values}
    assert name in flagged


@pytest.mark.parametrize(
    "value",
    ["false", "0", "no", "off", "", "FALSE", "False"],
)
def test_dangerous_runtime_safe_values_pass(value: str):
    guard = EnvGuard(
        config=_strict_config(),
        environ={"AMA_LIVE_TRADING_ENABLED": value},
    )
    report = guard.evaluate()
    assert report.passed is True


def test_ama_trading_mode_must_be_paper():
    guard = EnvGuard(
        config=_strict_config(),
        environ={"AMA_TRADING_MODE": "live_limited"},
    )
    report = guard.evaluate()
    assert report.passed is False
    flagged = {n for n, _ in report.dangerous_runtime_values}
    assert "AMA_TRADING_MODE" in flagged


def test_ama_trading_mode_paper_passes():
    guard = EnvGuard(
        config=_strict_config(),
        environ={"AMA_TRADING_MODE": "paper"},
    )
    report = guard.evaluate()
    assert report.passed is True


def test_payload_does_not_leak_credential_env_var_names():
    """to_payload() must NEVER carry the literal credential env-var
    names (e.g. ``BINANCE_API_KEY``). The Phase 8.5 redaction gate
    considers those literals forbidden in any rendered artifact."""
    guard = EnvGuard(
        config=_strict_config(),
        environ={"BINANCE_API_KEY": "x", "TELEGRAM_BOT_TOKEN": "y"},
    )
    report = guard.evaluate()
    payload = report.to_payload()
    import json

    serialised = json.dumps(payload, default=str)
    for literal in (
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "TELEGRAM_BOT_TOKEN",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        assert literal not in serialised, (
            f"EnvGuardReport.to_payload() leaked {literal}"
        )
    # The payload must still expose the count so the supervisor can
    # surface "N credential vars present" in the deploy log.
    assert payload["forbidden_credentials_present_count"] == 2
    assert "forbidden_credentials_present_labels" in payload


def test_safety_violation_message_does_not_leak_value():
    guard = EnvGuard(
        config=_strict_config(),
        environ={"BINANCE_API_KEY": "highly-secret-value"},
    )
    with pytest.raises(SafetyViolation) as exc:
        guard.assert_safe()
    assert "highly-secret-value" not in str(exc.value)


def test_environ_snapshot_isolates_from_later_mutation():
    """Mutating the environment after construction must not change
    the guard's behaviour."""
    env = {"BINANCE_API_KEY": "x"}
    guard = EnvGuard(config=_strict_config(), environ=env)
    env["AMA_LIVE_TRADING_ENABLED"] = "true"
    report = guard.evaluate()
    assert report.passed is False
    assert "BINANCE_API_KEY" in report.forbidden_credentials_present
    # The post-construction mutation must NOT have leaked.
    flagged_runtime = {n for n, _ in report.dangerous_runtime_values}
    assert "AMA_LIVE_TRADING_ENABLED" not in flagged_runtime


def test_evaluate_does_not_raise_on_forbidden():
    """evaluate() never raises - it only reports. Only assert_safe()
    raises."""
    guard = EnvGuard(
        config=_strict_config(),
        environ={"BINANCE_API_KEY": "x"},
    )
    report = guard.evaluate()
    assert isinstance(report, EnvGuardReport)
    assert report.passed is False


def test_assert_safe_does_not_raise_when_refuse_disabled():
    """If ``refuse_on_dangerous_value=False``, the guard reports the
    failure but does NOT raise."""
    guard = EnvGuard(
        config=_strict_config(refuse_on_dangerous_value=False),
        environ={"BINANCE_API_KEY": "x"},
    )
    report = guard.assert_safe()
    assert report.passed is False
