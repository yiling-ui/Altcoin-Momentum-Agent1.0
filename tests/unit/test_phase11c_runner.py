"""Phase 11C - Runner script tests.

Covers:

  - test_public_market_runner_does_not_require_credentials
  - basic argument parsing / duration parsing / dry-run smoke
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

from scripts.run_public_market_paper import (  # noqa: E402
    PHASE_11C_FORBIDDEN_CRED_ENV_VARS,
    _build_arg_parser,
    _parse_duration,
    main,
)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [
        ("30s", 30.0),
        ("2min", 120.0),
        ("1h", 3600.0),
        ("6h", 21600.0),
        ("24h", 86400.0),
        ("90", 90.0),
    ],
)
def test_parse_duration_accepts_canonical_forms(value: str, expected: float):
    assert _parse_duration(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "abc",
        "0s",
        "-5h",
        "1y",
    ],
)
def test_parse_duration_rejects_malformed(value: str):
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        _parse_duration(value)


def test_arg_parser_default_symbol_limit_is_5():
    """Phase 11C.1A lowered the default symbol limit from 20 to 5 to
    keep the gateway well below Binance's public-data weight budget
    after the first 24h test triggered HTTP 429 / 418."""
    parser = _build_arg_parser()
    args = parser.parse_args([])
    assert args.symbol_limit == 5


def test_phase_11c_forbidden_env_vars_includes_binance_and_telegram():
    assert "BINANCE_API_KEY" in PHASE_11C_FORBIDDEN_CRED_ENV_VARS
    assert "BINANCE_API_SECRET" in PHASE_11C_FORBIDDEN_CRED_ENV_VARS
    assert "TELEGRAM_BOT_TOKEN" in PHASE_11C_FORBIDDEN_CRED_ENV_VARS
    assert "DEEPSEEK_API_KEY" in PHASE_11C_FORBIDDEN_CRED_ENV_VARS


# ---------------------------------------------------------------------------
# Runner: dry-run smoke
# ---------------------------------------------------------------------------
def test_public_market_runner_does_not_require_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The runner starts and finishes cleanly without any
    BINANCE_API_KEY / BINANCE_API_SECRET env-var present.

    We monkeypatch the data dir so test artefacts go into ``tmp_path``,
    clear every forbidden credential env-var, and run the runner in
    ``--dry-run`` mode for 1 second on 2 symbols.
    """
    # Make sure the env is clean of every forbidden credential.
    for name in PHASE_11C_FORBIDDEN_CRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    # Force the data dir to a sandbox so the test does not touch the
    # repo's data/.
    monkeypatch.setenv("AMA_DATA_DIR", str(tmp_path))
    # Reset the lru_cache.
    from app.config.settings import get_settings

    get_settings.cache_clear()

    rc = main(
        [
            "--duration",
            "1s",
            "--symbol-limit",
            "2",
            "--dry-run",
            "--poll-interval-seconds",
            "0.5",
            "--no-banner",
        ]
    )
    assert rc == 0, "runner returned non-zero exit"

    # The runner wrote events.db inside tmp_path.
    events_db = tmp_path / "sqlite" / "events.db"
    assert events_db.exists(), "events.db not created by runner"


def test_runner_refuses_to_start_with_a_credential_env_var_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """If a forbidden credential env-var is set the runner refuses
    to boot via the env-guard."""
    monkeypatch.setenv("AMA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BINANCE_API_KEY", "x")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    from app.core.errors import SafetyViolation

    with pytest.raises(SafetyViolation):
        main(
            [
                "--duration",
                "1s",
                "--symbol-limit",
                "2",
                "--dry-run",
                "--poll-interval-seconds",
                "0.5",
                "--no-banner",
            ]
        )


def test_runner_refuses_unknown_provider_via_explicit_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Forcing the rest_base_url to a non-allowed host fails fast,
    before the loop starts.

    The BinancePublicClient constructor probes ``assert_public_endpoint_allowed``
    against the configured base URL; we use ``--rest-base-url`` to drive
    that path."""
    monkeypatch.setenv("AMA_DATA_DIR", str(tmp_path))
    for name in PHASE_11C_FORBIDDEN_CRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    from app.config.settings import get_settings

    get_settings.cache_clear()

    rc = main(
        [
            "--duration",
            "1s",
            "--symbol-limit",
            "2",
            "--dry-run",
            "--poll-interval-seconds",
            "0.5",
            "--no-banner",
            "--rest-base-url",
            "https://example.com",
        ]
    )
    # Either a non-zero exit OR a SafeModeViolation propagated; the
    # runner converts the violation into rc=2.
    assert rc != 0
