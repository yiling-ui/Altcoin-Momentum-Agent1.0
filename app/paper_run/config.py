"""Phase 11B paper-cloud config loader.

Reads ``app/config/paper_cloud.yaml`` into a frozen dataclass. The
loader does NOT touch :class:`app.config.settings.Settings`; the
Phase 1 safety lock is the single source of truth for the five
trading flags. This module only carries the Phase 11B-specific
operational knobs (durations, cadences, drill list).

Phase 11B boundary
------------------

  - reads NO ``os.environ`` for credentials
  - imports NO exchange / LLM / Telegram SDK
  - opens NO socket
  - defines NO write surface
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_PAPER_CLOUD_PATH = CONFIG_DIR / "paper_cloud.yaml"


# ---------------------------------------------------------------------------
# The default drill list mirrors the Phase 11B brief verbatim.
# ---------------------------------------------------------------------------
DEFAULT_INCIDENT_DRILLS: tuple[str, ...] = (
    "stop_unconfirmed",
    "unknown_position",
    "data_degraded",
    "p0_ghost_position",
    "p0_unattached_stop",
    "rebase_in_progress",
    "telegram_export_failure",
    "llm_degraded",
)


# Forbidden credential env-vars the env-guard refuses to see in the
# process environment. The supervisor refuses to start if any of these
# is present and non-empty. Phase 11B does NOT read the values; only
# checks presence so a cloud operator cannot accidentally attach a
# real transport.
DEFAULT_FORBIDDEN_CRED_ENV_VARS: tuple[str, ...] = (
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
)

DEFAULT_INSPECTED_ENV_VARS: tuple[str, ...] = (
    "AMA_TRADING_MODE",
    "AMA_LIVE_TRADING_ENABLED",
    "AMA_RIGHT_TAIL_ENABLED",
    "AMA_LLM_ENABLED",
    "AMA_EXCHANGE_LIVE_ORDER_ENABLED",
)


class PaperCloudConfigError(ValueError):
    """Raised when ``paper_cloud.yaml`` is malformed or asserts an
    unsafe value."""


@dataclass(frozen=True)
class EnvGuardConfig:
    enabled: bool = True
    refuse_on_dangerous_value: bool = True
    inspected_env_vars: tuple[str, ...] = DEFAULT_INSPECTED_ENV_VARS
    forbidden_credential_env_vars: tuple[str, ...] = DEFAULT_FORBIDDEN_CRED_ENV_VARS


@dataclass(frozen=True)
class PaperCloudConfig:
    """Phase 11B operational knobs.

    Hard expectations are encoded as fields so a future maintainer who
    sets one of them to an unsafe value gets a typed
    :class:`PaperCloudConfigError` at load time.
    """

    # Hard expectations (the loader refuses anything else).
    trading_mode: str = "paper"
    live_trading_enabled: bool = False
    right_tail_enabled: bool = False
    exchange_live_order_enabled: bool = False
    llm_enabled: bool = False
    real_order_enabled: bool = False

    # Acceptance run.
    paper_test_duration_days: int = 7
    acceptance_dry_run_minutes: int = 1

    # Daily report.
    daily_report_enabled: bool = True
    daily_report_subdir: str = "reports/daily"
    daily_report_filename_template: str = "{date}-paper-report.md"

    # Export.
    export_enabled: bool = True
    export_interval_hours: int = 24
    export_subdir: str = "reports/exports"
    export_range_label: str = "24h"
    export_type_filter: str = "all"
    export_on_boot: bool = True

    # Telegram.
    telegram_report_enabled: bool = True
    telegram_outbound_enabled: bool = False
    telegram_token_loaded: bool = False
    telegram_chat_id: str = "phase11b_cloud"

    # Health-check cadence.
    health_check_interval_seconds: int = 60

    # Incident drill.
    incident_drill_enabled: bool = True
    incident_drills: tuple[str, ...] = DEFAULT_INCIDENT_DRILLS

    # Env guard.
    env_guard: EnvGuardConfig = field(default_factory=EnvGuardConfig)

    # ------------------------------------------------------------------
    @classmethod
    def load(
        cls,
        path: Path | str | None = None,
    ) -> "PaperCloudConfig":
        """Load + validate ``paper_cloud.yaml``.

        Always returns a fully validated :class:`PaperCloudConfig` or
        raises :class:`PaperCloudConfigError`. Missing optional keys
        default to the safe value defined on this dataclass.
        """
        config_path = Path(path) if path is not None else DEFAULT_PAPER_CLOUD_PATH
        if not config_path.exists():
            raise PaperCloudConfigError(
                f"paper_cloud config not found: {config_path}. Phase 11B "
                "requires app/config/paper_cloud.yaml to exist."
            )
        with config_path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        if not isinstance(raw, dict):
            raise PaperCloudConfigError(
                f"paper_cloud config root must be a mapping; got {type(raw).__name__}"
            )
        section = raw.get("paper_cloud")
        if not isinstance(section, dict):
            raise PaperCloudConfigError(
                "paper_cloud.yaml must contain a top-level 'paper_cloud' mapping"
            )
        return cls.from_mapping(section)

    @classmethod
    def from_mapping(cls, section: dict[str, Any]) -> "PaperCloudConfig":
        """Build a :class:`PaperCloudConfig` from an already-parsed mapping.

        Tests use this entry point to avoid touching the filesystem.
        """
        env_guard_raw = section.get("env_guard") or {}
        if not isinstance(env_guard_raw, dict):
            raise PaperCloudConfigError(
                "paper_cloud.env_guard must be a mapping"
            )
        # Build env guard.
        inspected = tuple(
            str(s)
            for s in (
                env_guard_raw.get(
                    "inspected_env_vars", DEFAULT_INSPECTED_ENV_VARS
                )
                or ()
            )
        )
        forbidden = tuple(
            str(s)
            for s in (
                env_guard_raw.get(
                    "forbidden_credential_env_vars",
                    DEFAULT_FORBIDDEN_CRED_ENV_VARS,
                )
                or ()
            )
        )
        env_guard = EnvGuardConfig(
            enabled=bool(env_guard_raw.get("enabled", True)),
            refuse_on_dangerous_value=bool(
                env_guard_raw.get("refuse_on_dangerous_value", True)
            ),
            inspected_env_vars=inspected,
            forbidden_credential_env_vars=forbidden,
        )

        drills = tuple(
            str(d).strip()
            for d in (section.get("incident_drills") or DEFAULT_INCIDENT_DRILLS)
        )

        cfg = cls(
            trading_mode=str(section.get("trading_mode", "paper")),
            live_trading_enabled=bool(section.get("live_trading_enabled", False)),
            right_tail_enabled=bool(section.get("right_tail_enabled", False)),
            exchange_live_order_enabled=bool(
                section.get("exchange_live_order_enabled", False)
            ),
            llm_enabled=bool(section.get("llm_enabled", False)),
            real_order_enabled=bool(section.get("real_order_enabled", False)),
            paper_test_duration_days=int(
                section.get("paper_test_duration_days", 7)
            ),
            acceptance_dry_run_minutes=int(
                section.get("acceptance_dry_run_minutes", 1)
            ),
            daily_report_enabled=bool(section.get("daily_report_enabled", True)),
            daily_report_subdir=str(
                section.get("daily_report_subdir", "reports/daily")
            ),
            daily_report_filename_template=str(
                section.get(
                    "daily_report_filename_template",
                    "{date}-paper-report.md",
                )
            ),
            export_enabled=bool(section.get("export_enabled", True)),
            export_interval_hours=int(section.get("export_interval_hours", 24)),
            export_subdir=str(section.get("export_subdir", "reports/exports")),
            export_range_label=str(section.get("export_range_label", "24h")),
            export_type_filter=str(section.get("export_type_filter", "all")),
            export_on_boot=bool(section.get("export_on_boot", True)),
            telegram_report_enabled=bool(
                section.get("telegram_report_enabled", True)
            ),
            telegram_outbound_enabled=bool(
                section.get("telegram_outbound_enabled", False)
            ),
            telegram_token_loaded=bool(
                section.get("telegram_token_loaded", False)
            ),
            telegram_chat_id=str(
                section.get("telegram_chat_id", "phase11b_cloud")
            ),
            health_check_interval_seconds=int(
                section.get("health_check_interval_seconds", 60)
            ),
            incident_drill_enabled=bool(
                section.get("incident_drill_enabled", True)
            ),
            incident_drills=drills,
            env_guard=env_guard,
        )
        cfg._assert_safe_values()
        return cfg

    # ------------------------------------------------------------------
    def _assert_safe_values(self) -> None:
        """Refuse a config that asserts an unsafe value.

        These checks duplicate the runtime safety assertions in
        :func:`assert_paper_cloud_safety`; the redundancy is deliberate
        so a malformed YAML never reaches the supervisor at all.
        """
        if self.trading_mode != "paper":
            raise PaperCloudConfigError(
                "paper_cloud.trading_mode must be 'paper'; "
                f"got {self.trading_mode!r}"
            )
        if self.live_trading_enabled:
            raise PaperCloudConfigError(
                "paper_cloud.live_trading_enabled must be false"
            )
        if self.right_tail_enabled:
            raise PaperCloudConfigError(
                "paper_cloud.right_tail_enabled must be false"
            )
        if self.exchange_live_order_enabled:
            raise PaperCloudConfigError(
                "paper_cloud.exchange_live_order_enabled must be false"
            )
        if self.llm_enabled:
            # Phase 1 safety lock will coerce this to False anyway, but
            # we refuse to even load such a config so cloud deploy logs
            # show the failure.
            raise PaperCloudConfigError(
                "paper_cloud.llm_enabled must be false (Phase 1 lock); "
                "use the boot drill's FakeLLMClient for testing"
            )
        if self.real_order_enabled:
            raise PaperCloudConfigError(
                "paper_cloud.real_order_enabled must be false"
            )
        if self.paper_test_duration_days <= 0:
            raise PaperCloudConfigError(
                "paper_test_duration_days must be > 0; "
                f"got {self.paper_test_duration_days}"
            )
        if self.acceptance_dry_run_minutes <= 0:
            raise PaperCloudConfigError(
                "acceptance_dry_run_minutes must be > 0; "
                f"got {self.acceptance_dry_run_minutes}"
            )
        if self.export_interval_hours <= 0:
            raise PaperCloudConfigError(
                "export_interval_hours must be > 0; "
                f"got {self.export_interval_hours}"
            )
        if self.health_check_interval_seconds <= 0:
            raise PaperCloudConfigError(
                "health_check_interval_seconds must be > 0; "
                f"got {self.health_check_interval_seconds}"
            )

    # ------------------------------------------------------------------
    def to_payload(self) -> dict[str, Any]:
        """JSON-safe view used by the daily report + acceptance report.

        Note: the ``env_guard`` block intentionally exposes COUNTS only;
        the full env-var name list is in-process detail. Embedding the
        literal credential names (e.g. ``BINANCE_API_KEY``) into a
        rendered Markdown or events.db row would trip the Phase 8.5
        :func:`assert_no_forbidden_substrings` gate. The operator can
        always grep ``app/config/paper_cloud.yaml`` for the canonical
        list."""
        return {
            "trading_mode": self.trading_mode,
            "live_trading_enabled": bool(self.live_trading_enabled),
            "right_tail_enabled": bool(self.right_tail_enabled),
            "exchange_live_order_enabled": bool(self.exchange_live_order_enabled),
            "llm_enabled": bool(self.llm_enabled),
            "real_order_enabled": bool(self.real_order_enabled),
            "paper_test_duration_days": int(self.paper_test_duration_days),
            "acceptance_dry_run_minutes": int(self.acceptance_dry_run_minutes),
            "daily_report_enabled": bool(self.daily_report_enabled),
            "daily_report_subdir": self.daily_report_subdir,
            "export_enabled": bool(self.export_enabled),
            "export_interval_hours": int(self.export_interval_hours),
            "export_subdir": self.export_subdir,
            "export_range_label": self.export_range_label,
            "export_type_filter": self.export_type_filter,
            "export_on_boot": bool(self.export_on_boot),
            "telegram_report_enabled": bool(self.telegram_report_enabled),
            "telegram_outbound_enabled": bool(self.telegram_outbound_enabled),
            "telegram_token_loaded": bool(self.telegram_token_loaded),
            "telegram_chat_id": self.telegram_chat_id,
            "health_check_interval_seconds": int(
                self.health_check_interval_seconds
            ),
            "incident_drill_enabled": bool(self.incident_drill_enabled),
            "incident_drills": list(self.incident_drills),
            "env_guard": {
                "enabled": bool(self.env_guard.enabled),
                "refuse_on_dangerous_value": bool(
                    self.env_guard.refuse_on_dangerous_value
                ),
                "inspected_env_var_count": len(
                    self.env_guard.inspected_env_vars
                ),
                "forbidden_credential_env_var_count": len(
                    self.env_guard.forbidden_credential_env_vars
                ),
            },
        }


__all__ = [
    "PaperCloudConfig",
    "PaperCloudConfigError",
    "EnvGuardConfig",
    "DEFAULT_INCIDENT_DRILLS",
    "DEFAULT_FORBIDDEN_CRED_ENV_VARS",
    "DEFAULT_INSPECTED_ENV_VARS",
    "DEFAULT_PAPER_CLOUD_PATH",
]
