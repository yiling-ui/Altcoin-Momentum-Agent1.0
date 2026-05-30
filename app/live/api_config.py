"""Live API configuration models for the Live API Integration Pack (PR111).

All configuration is loaded from the process environment. Nothing here
is hard-coded, and no secret value ever appears in ``repr`` / ``dict`` /
``json`` output - secrets are held as :class:`app.live.secrets.SecretValue`.

Environment variables (all optional; sensible safe defaults apply)
------------------------------------------------------------------

Binance:
  - ``AMA_BINANCE_API_KEY``
  - ``AMA_BINANCE_API_SECRET``
  - ``AMA_BINANCE_BASE_URL``            (spot/base REST; default api.binance.com)
  - ``AMA_BINANCE_FAPI_BASE_URL``       (USDT-M futures REST; default fapi.binance.com)
  - ``AMA_BINANCE_ENABLE_PRIVATE_READ`` (default false)
  - ``AMA_BINANCE_ENABLE_PRIVATE_TRADE``(default false; PR111 keeps order path blocked regardless)
  - ``AMA_BINANCE_USE_TESTNET``         (default false)

Telegram:
  - ``AMA_TELEGRAM_BOT_TOKEN``
  - ``AMA_TELEGRAM_ALLOWED_CHAT_IDS``   (comma-separated)
  - ``AMA_TELEGRAM_OUTBOUND_ENABLED``   (default false)

DeepSeek:
  - ``AMA_DEEPSEEK_API_KEY``
  - ``AMA_DEEPSEEK_BASE_URL``           (default api.deepseek.com)
  - ``AMA_DEEPSEEK_MODEL``              (default deepseek-chat)
  - ``AMA_DEEPSEEK_ENABLED``            (default false)

General:
  - ``AMA_LIVE_RUNTIME_MODE``           (default LIVE_SHADOW)
  - ``AMA_LIVE_API_HEALTHCHECK_ENABLED``(default true)
  - ``AMA_SECRET_LOGGING_ALLOWED``      (default false; MUST stay false in normal use)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Final

from app.live.secrets import SecretValue, load_secret


# ---------------------------------------------------------------------------
# Live runtime mode
# ---------------------------------------------------------------------------
class LiveRuntimeMode(str, Enum):
    """Live runtime mode for the real-capital road map.

    HANDOFF(PR110): this enum is intentionally shaped to be unified with
    the PR110 "Live Path Isolation" runtime modes. Until PR110 lands,
    PR111 ships this self-contained enum and defaults to
    :attr:`LIVE_SHADOW`.

    Ladder semantics (strict):

      - ``LIVE_SHADOW``  - connect real read APIs, observe real market /
        balances, push operator messages, but the order path is HARD
        blocked. This is the PR111 default and the only mode PR111
        supports for real connectivity.
      - ``LIVE_LIMITED`` - small-capital real trading (a later PR). PR111
        NEVER auto-selects this mode.
      - ``LIVE_FULL``    - full real trading (a much later PR).
      - ``PAPER``        - no real API; pure paper. Kept so the mode set
        is a superset of the paper road map.
    """

    PAPER = "PAPER"
    LIVE_SHADOW = "LIVE_SHADOW"
    LIVE_LIMITED = "LIVE_LIMITED"
    LIVE_FULL = "LIVE_FULL"

    @property
    def allows_live_orders(self) -> bool:
        """Only LIVE_LIMITED / LIVE_FULL conceptually allow orders.

        PR111 still refuses to *send* orders in every mode; this property
        only describes the mode's intent so the order-path gate can read a
        single predicate. ``LIVE_SHADOW`` and ``PAPER`` never allow orders.
        """
        return self in (LiveRuntimeMode.LIVE_LIMITED, LiveRuntimeMode.LIVE_FULL)


# Default mode: never auto-escalate above LIVE_SHADOW in PR111.
DEFAULT_LIVE_RUNTIME_MODE: Final[LiveRuntimeMode] = LiveRuntimeMode.LIVE_SHADOW

# Public Binance USDT-M futures + spot hosts (production + testnet).
DEFAULT_BINANCE_BASE_URL: Final[str] = "https://api.binance.com"
DEFAULT_BINANCE_FAPI_BASE_URL: Final[str] = "https://fapi.binance.com"
TESTNET_BINANCE_BASE_URL: Final[str] = "https://testnet.binance.vision"
TESTNET_BINANCE_FAPI_BASE_URL: Final[str] = "https://testnet.binancefuture.com"

DEFAULT_DEEPSEEK_BASE_URL: Final[str] = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL: Final[str] = "deepseek-chat"


def _env(name: str, default: str = "", *, environ: dict[str, str] | None = None) -> str:
    source = environ if environ is not None else os.environ
    raw = source.get(name, default)
    return ("" if raw is None else str(raw)).strip()


def _env_bool(name: str, default: bool, *, environ: dict[str, str] | None = None) -> bool:
    raw = _env(name, "", environ=environ)
    if raw == "":
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _parse_chat_ids(raw: str) -> tuple[str, ...]:
    if not raw:
        return ()
    out: list[str] = []
    for chunk in raw.replace(";", ",").split(","):
        token = chunk.strip()
        if token:
            out.append(token)
    return tuple(out)


# ---------------------------------------------------------------------------
# Per-provider config
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BinanceApiConfig:
    """Binance live API configuration.

    ``api_key`` / ``api_secret`` are :class:`SecretValue`; they never
    serialise their raw value. ``enable_private_trade`` describes the
    operator's *intent*, but PR111 keeps the order path blocked
    regardless of its value (see :mod:`app.live.binance_client`).
    """

    api_key: SecretValue
    api_secret: SecretValue
    base_url: str = DEFAULT_BINANCE_BASE_URL
    fapi_base_url: str = DEFAULT_BINANCE_FAPI_BASE_URL
    enable_private_read: bool = False
    enable_private_trade: bool = False
    use_testnet: bool = False

    @property
    def has_credentials(self) -> bool:
        return self.api_key.is_present and self.api_secret.is_present

    @property
    def resolved_fapi_base_url(self) -> str:
        if self.use_testnet:
            return TESTNET_BINANCE_FAPI_BASE_URL
        return self.fapi_base_url

    @property
    def resolved_base_url(self) -> str:
        if self.use_testnet:
            return TESTNET_BINANCE_BASE_URL
        return self.base_url

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "api_key": self.api_key.to_safe_dict(),
            "api_secret": self.api_secret.to_safe_dict(),
            "base_url": self.resolved_base_url,
            "fapi_base_url": self.resolved_fapi_base_url,
            "enable_private_read": self.enable_private_read,
            "enable_private_trade": self.enable_private_trade,
            "use_testnet": self.use_testnet,
            "has_credentials": self.has_credentials,
        }

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "BinanceApiConfig":
        return cls(
            api_key=load_secret("AMA_BINANCE_API_KEY", environ=environ),
            api_secret=load_secret("AMA_BINANCE_API_SECRET", environ=environ),
            base_url=_env("AMA_BINANCE_BASE_URL", DEFAULT_BINANCE_BASE_URL, environ=environ),
            fapi_base_url=_env(
                "AMA_BINANCE_FAPI_BASE_URL", DEFAULT_BINANCE_FAPI_BASE_URL, environ=environ
            ),
            enable_private_read=_env_bool(
                "AMA_BINANCE_ENABLE_PRIVATE_READ", False, environ=environ
            ),
            enable_private_trade=_env_bool(
                "AMA_BINANCE_ENABLE_PRIVATE_TRADE", False, environ=environ
            ),
            use_testnet=_env_bool("AMA_BINANCE_USE_TESTNET", False, environ=environ),
        )


@dataclass(frozen=True)
class TelegramApiConfig:
    """Telegram bot live API configuration."""

    bot_token: SecretValue
    allowed_chat_ids: tuple[str, ...] = ()
    outbound_enabled: bool = False

    @property
    def has_token(self) -> bool:
        return self.bot_token.is_present

    def is_chat_allowed(self, chat_id: str | int) -> bool:
        return str(chat_id) in self.allowed_chat_ids

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "bot_token": self.bot_token.to_safe_dict(),
            "allowed_chat_ids": list(self.allowed_chat_ids),
            "outbound_enabled": self.outbound_enabled,
            "has_token": self.has_token,
        }

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "TelegramApiConfig":
        return cls(
            bot_token=load_secret("AMA_TELEGRAM_BOT_TOKEN", environ=environ),
            allowed_chat_ids=_parse_chat_ids(
                _env("AMA_TELEGRAM_ALLOWED_CHAT_IDS", "", environ=environ)
            ),
            outbound_enabled=_env_bool(
                "AMA_TELEGRAM_OUTBOUND_ENABLED", False, environ=environ
            ),
        )


@dataclass(frozen=True)
class DeepSeekApiConfig:
    """DeepSeek live API configuration."""

    api_key: SecretValue
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    model: str = DEFAULT_DEEPSEEK_MODEL
    enabled: bool = False

    @property
    def has_key(self) -> bool:
        return self.api_key.is_present

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "api_key": self.api_key.to_safe_dict(),
            "base_url": self.base_url,
            "model": self.model,
            "enabled": self.enabled,
            "has_key": self.has_key,
        }

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "DeepSeekApiConfig":
        return cls(
            api_key=load_secret("AMA_DEEPSEEK_API_KEY", environ=environ),
            base_url=_env("AMA_DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL, environ=environ),
            model=_env("AMA_DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL, environ=environ),
            enabled=_env_bool("AMA_DEEPSEEK_ENABLED", False, environ=environ),
        )


@dataclass(frozen=True)
class GeneralLiveConfig:
    """Cross-cutting live API configuration."""

    runtime_mode: LiveRuntimeMode = DEFAULT_LIVE_RUNTIME_MODE
    healthcheck_enabled: bool = True
    # MUST default False and should never be True in normal use. Even if
    # a misconfigured operator sets it True, the pack only ever displays
    # masked secrets; this flag does NOT unlock raw-secret logging in
    # PR111 (there is no code path that logs a revealed secret).
    secret_logging_allowed: bool = False

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "runtime_mode": self.runtime_mode.value,
            "healthcheck_enabled": self.healthcheck_enabled,
            "secret_logging_allowed": self.secret_logging_allowed,
        }

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "GeneralLiveConfig":
        raw_mode = _env("AMA_LIVE_RUNTIME_MODE", "", environ=environ).upper()
        try:
            mode = LiveRuntimeMode(raw_mode) if raw_mode else DEFAULT_LIVE_RUNTIME_MODE
        except ValueError:
            # Unknown mode: fall back to the safe default rather than crash.
            mode = DEFAULT_LIVE_RUNTIME_MODE
        # PR111 never escalates above LIVE_SHADOW for real connectivity.
        if mode.allows_live_orders:
            mode = LiveRuntimeMode.LIVE_SHADOW
        return cls(
            runtime_mode=mode,
            healthcheck_enabled=_env_bool(
                "AMA_LIVE_API_HEALTHCHECK_ENABLED", True, environ=environ
            ),
            secret_logging_allowed=_env_bool(
                "AMA_SECRET_LOGGING_ALLOWED", False, environ=environ
            ),
        )


@dataclass(frozen=True)
class LiveApiConfig:
    """Top-level live API config bundle."""

    binance: BinanceApiConfig
    telegram: TelegramApiConfig
    deepseek: DeepSeekApiConfig
    general: GeneralLiveConfig = field(default_factory=GeneralLiveConfig)

    @property
    def live_runtime_mode(self) -> LiveRuntimeMode:
        return self.general.runtime_mode

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "binance": self.binance.to_safe_dict(),
            "telegram": self.telegram.to_safe_dict(),
            "deepseek": self.deepseek.to_safe_dict(),
            "general": self.general.to_safe_dict(),
        }

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "LiveApiConfig":
        return cls(
            binance=BinanceApiConfig.from_env(environ),
            telegram=TelegramApiConfig.from_env(environ),
            deepseek=DeepSeekApiConfig.from_env(environ),
            general=GeneralLiveConfig.from_env(environ),
        )


__all__ = [
    "LiveRuntimeMode",
    "DEFAULT_LIVE_RUNTIME_MODE",
    "BinanceApiConfig",
    "TelegramApiConfig",
    "DeepSeekApiConfig",
    "GeneralLiveConfig",
    "LiveApiConfig",
    "DEFAULT_BINANCE_BASE_URL",
    "DEFAULT_BINANCE_FAPI_BASE_URL",
    "TESTNET_BINANCE_BASE_URL",
    "TESTNET_BINANCE_FAPI_BASE_URL",
    "DEFAULT_DEEPSEEK_BASE_URL",
    "DEFAULT_DEEPSEEK_MODEL",
]
