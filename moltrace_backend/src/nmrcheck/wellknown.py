"""RFC 9116 ``security.txt`` generation (Security Prompt 17).

A pure, settings-driven builder for the ``/.well-known/security.txt`` machine-
and human-readable disclosure file. Kept out of ``api.py`` so the body can be
unit-tested without standing up the app, and so the route handler stays a
one-liner.

Two deliberate design choices:

* **``Expires`` is computed at call time, never a hardcoded literal.** RFC 9116
  requires an ``Expires`` field and recommends it be less than a year out; a
  static date silently goes stale. We emit ``now + N days`` (clamped into the
  one-year window) so a served file is always valid. The trade-off — the body
  is not byte-stable over time — is fine because the file is *not* signed; if a
  deployment chooses to sign it, it must pin a fixed ``Expires`` instead.

* **Optional fields are omitted unless configured.** We never advertise a
  ``Policy``/``Encryption``/``Acknowledgments`` URL that might 404, nor a paid
  bug-bounty the program does not run. The default file carries only the
  mandatory ``Contact`` + ``Expires`` (plus ``Preferred-Languages``), which are
  always real. A deployment points the optional URLs at pages that exist.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .settings import Settings

# RFC 9116 caps the validity window at one year. Publish well inside it and clamp
# defensively so a misconfigured ``security_txt_expires_days`` can never emit a
# stale or out-of-window file. The floor is a generous week so even a fat-fingered
# tiny value still yields a comfortably-valid window.
_MIN_EXPIRES_DAYS = 7
_MAX_EXPIRES_DAYS = 364

# Conservative fallback if a deployment blanks the contact: the address published
# in the repo SECURITY.md. ``Contact`` is mandatory, so we never emit zero of them.
_DEFAULT_CONTACT = "mailto:security@moltrace.co"


def _expires_value(now: datetime, days: int) -> str:
    """RFC 3339 / ISO 8601 UTC timestamp ``now + days`` (clamped, day-truncated)."""
    days = max(_MIN_EXPIRES_DAYS, min(int(days), _MAX_EXPIRES_DAYS))
    when = (now + timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(value: str) -> str:
    """Collapse CR/LF (and surrounding whitespace) so an operator-set value can never
    inject a forged field line into the file. Values come from env vars, not end
    users, but this closes the misconfigured-/compromised-env footgun and keeps the
    output a strictly one-field-per-line RFC 9116 file.
    """
    return value.replace("\r", " ").replace("\n", " ").strip()


def _contacts(raw: str | None) -> list[str]:
    # Split on comma first, then strip CR/LF from each part so neither the
    # comma-separated nor a comma-less embedded-newline value can inject a line.
    contacts = [c for c in (_clean(part) for part in (raw or "").split(",")) if c]
    return contacts or [_DEFAULT_CONTACT]


def build_security_txt(settings: Settings, *, now: datetime | None = None) -> str:
    """Render the ``security.txt`` body for ``settings`` as an RFC 9116 string.

    ``now`` is injected for deterministic testing; production passes ``None`` and
    we read the wall clock. Lines are CRLF-terminated per RFC 9116 (clients also
    tolerate LF). The returned string is meant to be served as
    ``Content-Type: text/plain; charset=utf-8``.
    """
    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    lines: list[str] = [
        "# MolTrace security.txt (RFC 9116)",
        "# Report vulnerabilities privately. Do NOT open public GitHub issues,",
        "# discussions, or pull requests for security bugs.",
        "",
    ]
    # Contact (mandatory, >=1, highest priority first).
    for contact in _contacts(settings.security_txt_contacts):
        lines.append(f"Contact: {contact}")
    # Expires (mandatory, exactly one, <1yr out).
    lines.append(f"Expires: {_expires_value(now, settings.security_txt_expires_days)}")

    # Optional fields — emitted only when configured to a non-empty value so the
    # file never points at a page/key that does not exist.
    optional = (
        ("Policy", settings.security_txt_policy_url),
        ("Canonical", settings.security_txt_canonical_url),
        ("Encryption", settings.security_txt_encryption_url),
        ("Acknowledgments", settings.security_txt_acknowledgments_url),
    )
    for name, value in optional:
        value = _clean(value or "")
        if value:
            lines.append(f"{name}: {value}")

    langs = _clean(settings.security_txt_preferred_languages or "")
    if langs:
        lines.append(f"Preferred-Languages: {langs}")

    return "\r\n".join(lines) + "\r\n"
