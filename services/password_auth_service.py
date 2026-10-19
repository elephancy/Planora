from __future__ import annotations

import hashlib
import hmac
import importlib.util
import re
import secrets
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

from services.env_service import env_bool, env_bool_strict, env_value


_PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


_NOTIFICATIONS_MODULE = Path("/run/ops/shared-notifications/python/ops_notifications.py")


@lru_cache(maxsize=1)
def _notifier():
    """Load the Ops-owned runtime bundle lazily; never fall back to local policy."""
    try:
        spec = importlib.util.spec_from_file_location("planora_ops_notifications", _NOTIFICATIONS_MODULE)
        if spec is None or spec.loader is None:
            raise RuntimeError("Ops notifications are unavailable.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.Notifier()
    except (ImportError, OSError):
        raise RuntimeError("Ops notifications are unavailable.") from None


@dataclass(frozen=True)
class OutboundEmail:
    """Auth semantics only. Ops supplies presentation, identity and transport."""

    to_email: str
    kind: str
    action_path: str
    code: str

    def event(self) -> dict[str, str]:
        notifier = _notifier()
        return {
            "kind": self.kind,
            "to": self.to_email,
            "actionUrl": notifier.action_url(self.action_path),
            "code": self.code,
        }


def normalize_email(email: str) -> str:
    normalized = str(email or "").strip().lower()
    if not _EMAIL_RE.match(normalized):
        raise ValueError("A valid email address is required.")
    return normalized


def validate_password(password: str) -> None:
    if len(str(password or "")) < 10:
        raise ValueError("Password must be at least 10 characters.")


def hash_password(password: str) -> str:
    validate_password(password)
    return _PASSWORD_HASHER.hash(str(password))


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return bool(_PASSWORD_HASHER.verify(password_hash, str(password or "")))
    except (VerifyMismatchError, VerificationError, TypeError):
        return False


def should_rehash_password(password_hash: str) -> bool:
    try:
        return bool(_PASSWORD_HASHER.check_needs_rehash(password_hash))
    except Exception:
        return True


def new_plain_token(prefix: str = "") -> str:
    return f"{prefix}{secrets.token_urlsafe(24)}"


def new_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def secret_pepper() -> str:
    pepper = env_value("PLANORA_TOKEN_PEPPER", "")
    auth_secret = env_value("PLANORA_AUTH_SECRET", "")
    if env_bool_strict("PLANORA_PRODUCTION", False):
        if not pepper:
            raise RuntimeError(
                "PLANORA_TOKEN_PEPPER or PLANORA_TOKEN_PEPPER_FILE is required in production."
            )
        if len(pepper.encode("utf-8")) < 32:
            raise RuntimeError(
                "PLANORA_TOKEN_PEPPER must contain at least 32 UTF-8 bytes in production."
            )
        if auth_secret and hmac.compare_digest(
            pepper.encode("utf-8"), auth_secret.encode("utf-8")
        ):
            raise RuntimeError(
                "PLANORA_TOKEN_PEPPER must be independent from PLANORA_AUTH_SECRET in production."
            )
    return pepper or auth_secret or "planora-local-token-pepper"


def hash_token(token: str) -> str:
    digest = hmac.new(secret_pepper().encode("utf-8"), str(token).encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def email_verification_required() -> bool:
    return env_bool("PLANORA_EMAIL_VERIFICATION_REQUIRED", True)


def registration_enabled() -> bool:
    return env_bool("PLANORA_REGISTRATION_ENABLED", True)


def smtp_configured() -> bool:
    try:
        status = _notifier().status()
        return bool(status.get("configured") and status.get("mode") == "smtp")
    except RuntimeError:
        return False


def _validated_public_base_url(value: str, *, require_https: bool) -> str:
    base_url = str(value or "").strip().rstrip("/")
    parsed = urlparse(base_url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("PLANORA_PUBLIC_BASE_URL has an invalid port.") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port is not None and not 1 <= port <= 65535
    ):
        raise RuntimeError("PLANORA_PUBLIC_BASE_URL must be an absolute http(s) URL without credentials, query, or fragment.")
    if require_https and parsed.scheme != "https":
        raise RuntimeError("PLANORA_PUBLIC_BASE_URL must use https in production.")
    return base_url


def verification_base_url(default_base_url: str) -> str:
    production = env_bool_strict("PLANORA_PRODUCTION", False)
    configured = env_value("PLANORA_PUBLIC_BASE_URL", "").strip()
    if not configured:
        domain = env_value("PLANORA_DOMAIN", "").strip().rstrip("/")
        if domain:
            parsed_domain = urlparse(f"//{domain}")
            if (
                not parsed_domain.hostname
                or parsed_domain.username is not None
                or parsed_domain.password is not None
                or parsed_domain.path
                or parsed_domain.query
                or parsed_domain.fragment
            ):
                raise RuntimeError("PLANORA_DOMAIN must contain only a hostname and optional port.")
            configured = f"https://{domain}"
    if configured:
        return _validated_public_base_url(configured, require_https=production)
    if production:
        raise RuntimeError(
            "PLANORA_PUBLIC_BASE_URL or PLANORA_DOMAIN is required in production."
        )
    return str(default_base_url or "").rstrip("/")


def build_verification_email(base_url: str, to_email: str, token: str, code: str) -> OutboundEmail:
    # Keep the call signature for auth callers. Ops owns the destination origin;
    # the auth flow alone supplies its path, token and actual confirmation code.
    return OutboundEmail(to_email, "verify-email", f"/auth/verify?token={token}", code)


def build_password_reset_email(base_url: str, to_email: str, token: str, code: str) -> OutboundEmail:
    return OutboundEmail(to_email, "reset-password", f"/login?reset_token={token}", code)


def send_email(message: OutboundEmail) -> None:
    _notifier().send_account(message.event())


def email_auth_public_config() -> dict[str, Any]:
    return {
        "mode": "email_password",
        "registration_enabled": registration_enabled(),
        "email_verification_required": email_verification_required(),
        "smtp_configured": smtp_configured(),
    }


def expires_at(seconds: int) -> float:
    return time.time() + int(seconds)
