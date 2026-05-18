"""Phase 3 (Issue #3) - repository-wide network sanity checks.

These tests ensure that Phase 3 has not accidentally introduced an
outbound network surface anywhere in the repository:

  - `requirements.txt` and `pyproject.toml` must not contain any
    exchange SDK or HTTP client.
  - No source file under `app/` may import an outbound HTTP / WS
    library at module load time.

If a future PR ever needs to introduce a real exchange SDK (Phase 4 or
later), it must update these tests *and* the Phase 1 safety lock - both
together. That's the whole point: the test failure forces the safety
lock change to be reviewed.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_PACKAGES = (
    "ccxt",
    "binance-connector",
    "python-binance",
    "binance.client",
    "aiohttp",
    "websockets",
    "websocket-client",
    "requests",
    "httpx",
)


def test_requirements_does_not_include_exchange_sdk():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for token in FORBIDDEN_PACKAGES:
        assert token.lower() not in requirements.lower(), (
            f"requirements.txt must not depend on {token} in Phase 3"
        )


def test_pyproject_does_not_include_exchange_sdk():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for token in FORBIDDEN_PACKAGES:
        assert token.lower() not in pyproject.lower(), (
            f"pyproject.toml must not depend on {token} in Phase 3"
        )


def test_no_app_module_imports_a_network_library():
    # Walk every .py file under app/ and confirm no `import <forbidden>`
    # / `from <forbidden> import` lines exist. This is a textual scan,
    # which is intentionally conservative; the price is that comments
    # and docstrings cannot mention these tokens either at the start of
    # an import line.
    forbidden_imports = tuple(
        f.replace("-", "_").split(".")[0] for f in FORBIDDEN_PACKAGES
    )
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            for token in forbidden_imports:
                assert not stripped.startswith(f"import {token}"), (
                    f"{path} imports {token}; forbidden in Phase 3"
                )
                assert not stripped.startswith(f"from {token}"), (
                    f"{path} imports from {token}; forbidden in Phase 3"
                )
