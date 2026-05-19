"""Phase 11B - paper_cloud.yaml config loader tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.paper_run.config import (
    DEFAULT_FORBIDDEN_CRED_ENV_VARS,
    DEFAULT_INCIDENT_DRILLS,
    DEFAULT_INSPECTED_ENV_VARS,
    DEFAULT_PAPER_CLOUD_PATH,
    EnvGuardConfig,
    PaperCloudConfig,
    PaperCloudConfigError,
)


def _safe_section() -> dict:
    """A baseline safe paper_cloud section that the tests mutate."""
    return {
        "trading_mode": "paper",
        "live_trading_enabled": False,
        "right_tail_enabled": False,
        "exchange_live_order_enabled": False,
        "llm_enabled": False,
        "real_order_enabled": False,
        "paper_test_duration_days": 7,
        "acceptance_dry_run_minutes": 1,
        "daily_report_enabled": True,
        "daily_report_subdir": "reports/daily",
        "daily_report_filename_template": "{date}-paper-report.md",
        "export_enabled": True,
        "export_interval_hours": 24,
        "export_subdir": "reports/exports",
        "export_range_label": "24h",
        "export_type_filter": "all",
        "export_on_boot": True,
        "telegram_report_enabled": True,
        "telegram_outbound_enabled": False,
        "telegram_token_loaded": False,
        "telegram_chat_id": "phase11b_cloud",
        "health_check_interval_seconds": 60,
        "incident_drill_enabled": True,
        "incident_drills": list(DEFAULT_INCIDENT_DRILLS),
        "env_guard": {
            "enabled": True,
            "refuse_on_dangerous_value": True,
            "inspected_env_vars": list(DEFAULT_INSPECTED_ENV_VARS),
            "forbidden_credential_env_vars": list(
                DEFAULT_FORBIDDEN_CRED_ENV_VARS
            ),
        },
    }


def test_default_paper_cloud_yaml_loads_cleanly():
    """The shipped paper_cloud.yaml must load without raising."""
    cfg = PaperCloudConfig.load(DEFAULT_PAPER_CLOUD_PATH)
    assert cfg.trading_mode == "paper"
    assert cfg.live_trading_enabled is False
    assert cfg.right_tail_enabled is False
    assert cfg.exchange_live_order_enabled is False
    assert cfg.llm_enabled is False
    assert cfg.real_order_enabled is False
    # Phase 11B brief explicitly requires 7 or 15 days; the shipped
    # yaml ships 7. The acceptance dry-run cap is 1 minute (CI-friendly).
    assert cfg.paper_test_duration_days in (7, 15)
    assert cfg.acceptance_dry_run_minutes >= 1
    assert cfg.export_interval_hours == 24
    assert cfg.export_range_label == "24h"
    assert cfg.export_type_filter == "all"
    assert cfg.incident_drill_enabled is True
    assert tuple(cfg.incident_drills) == DEFAULT_INCIDENT_DRILLS
    assert cfg.env_guard.enabled is True
    assert cfg.env_guard.refuse_on_dangerous_value is True


def test_from_mapping_round_trip_safe_section():
    cfg = PaperCloudConfig.from_mapping(_safe_section())
    assert isinstance(cfg, PaperCloudConfig)
    assert cfg.trading_mode == "paper"
    assert cfg.env_guard.inspected_env_vars == DEFAULT_INSPECTED_ENV_VARS
    assert (
        cfg.env_guard.forbidden_credential_env_vars
        == DEFAULT_FORBIDDEN_CRED_ENV_VARS
    )


@pytest.mark.parametrize(
    "field, value",
    [
        ("trading_mode", "live"),
        ("trading_mode", "live_limited"),
        ("live_trading_enabled", True),
        ("right_tail_enabled", True),
        ("exchange_live_order_enabled", True),
        ("llm_enabled", True),
        ("real_order_enabled", True),
        ("paper_test_duration_days", 0),
        ("paper_test_duration_days", -3),
        ("acceptance_dry_run_minutes", 0),
        ("export_interval_hours", 0),
        ("health_check_interval_seconds", 0),
    ],
)
def test_from_mapping_refuses_unsafe_value(field: str, value):
    section = _safe_section()
    section[field] = value
    with pytest.raises(PaperCloudConfigError):
        PaperCloudConfig.from_mapping(section)


def test_load_raises_when_file_missing(tmp_path: Path):
    with pytest.raises(PaperCloudConfigError):
        PaperCloudConfig.load(tmp_path / "missing.yaml")


def test_load_raises_when_yaml_root_is_not_mapping(tmp_path: Path):
    target = tmp_path / "bad_root.yaml"
    target.write_text("- not_a_mapping\n", encoding="utf-8")
    with pytest.raises(PaperCloudConfigError):
        PaperCloudConfig.load(target)


def test_load_raises_when_paper_cloud_section_missing(tmp_path: Path):
    target = tmp_path / "missing_section.yaml"
    target.write_text("other_section: 1\n", encoding="utf-8")
    with pytest.raises(PaperCloudConfigError):
        PaperCloudConfig.load(target)


def test_load_raises_when_env_guard_is_not_mapping(tmp_path: Path):
    target = tmp_path / "bad_env_guard.yaml"
    target.write_text(
        "paper_cloud:\n  trading_mode: paper\n  env_guard: not_a_mapping\n",
        encoding="utf-8",
    )
    with pytest.raises(PaperCloudConfigError):
        PaperCloudConfig.load(target)


def test_to_payload_does_not_leak_credential_env_var_names():
    """The serialised payload must only carry COUNTS - never the
    literal env-var names like ``BINANCE_API_KEY``. The Phase 8.5
    redaction gate refuses any output that contains those literals."""
    cfg = PaperCloudConfig.load(DEFAULT_PAPER_CLOUD_PATH)
    payload = cfg.to_payload()
    forbidden_literals = (
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "TELEGRAM_BOT_TOKEN",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    )
    serialised = yaml.safe_dump(payload, default_flow_style=False)
    for literal in forbidden_literals:
        assert literal not in serialised, (
            f"PaperCloudConfig.to_payload() leaked {literal} into serialised form"
        )


def test_default_drill_list_matches_phase11b_brief():
    """The eight drills in the brief must be exactly the eight
    incident drills the supervisor will run."""
    expected = {
        "stop_unconfirmed",
        "unknown_position",
        "data_degraded",
        "p0_ghost_position",
        "p0_unattached_stop",
        "rebase_in_progress",
        "telegram_export_failure",
        "llm_degraded",
    }
    assert set(DEFAULT_INCIDENT_DRILLS) == expected


def test_env_guard_config_has_phase1_runtime_flags_in_inspected_list():
    """The env-guard MUST inspect every Phase 1 ``AMA_*_ENABLED`` flag
    so a dangerous truthy value surfaces in the deploy log."""
    cfg = PaperCloudConfig.load(DEFAULT_PAPER_CLOUD_PATH)
    inspected = set(cfg.env_guard.inspected_env_vars)
    required = {
        "AMA_TRADING_MODE",
        "AMA_LIVE_TRADING_ENABLED",
        "AMA_RIGHT_TAIL_ENABLED",
        "AMA_LLM_ENABLED",
        "AMA_EXCHANGE_LIVE_ORDER_ENABLED",
    }
    missing = required - inspected
    assert not missing, f"env_guard inspected list missing {missing}"


def test_env_guard_config_lists_canonical_credential_env_vars():
    """The forbidden credential env-var list must include every
    canonical name the supervisor refuses to start under."""
    cfg = PaperCloudConfig.load(DEFAULT_PAPER_CLOUD_PATH)
    forbidden = set(cfg.env_guard.forbidden_credential_env_vars)
    required = {
        "AMA_EXCHANGE_API_KEY",
        "AMA_EXCHANGE_API_SECRET",
        "AMA_TELEGRAM_BOT_TOKEN",
        "AMA_DEEPSEEK_API_KEY",
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "TELEGRAM_BOT_TOKEN",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    }
    missing = required - forbidden
    assert not missing, (
        f"env_guard.forbidden_credential_env_vars missing {missing}"
    )


def test_env_guard_config_default_values():
    """EnvGuardConfig defaults match the brief."""
    cfg = EnvGuardConfig()
    assert cfg.enabled is True
    assert cfg.refuse_on_dangerous_value is True
    assert cfg.inspected_env_vars == DEFAULT_INSPECTED_ENV_VARS
    assert cfg.forbidden_credential_env_vars == DEFAULT_FORBIDDEN_CRED_ENV_VARS
