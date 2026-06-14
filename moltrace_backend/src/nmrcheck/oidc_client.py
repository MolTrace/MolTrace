"""Minimal, testable OpenID Connect (Authorization Code + PKCE) client (Prompt 1, SSO).

Three network-touching functions — :func:`discover`, :func:`exchange_code`,
:func:`validate_id_token` — are module-level so tests can monkeypatch them with a fake IdP
without real HTTP. The store calls only these plus the pure helpers :func:`new_pkce` /
:func:`build_authorization_url`.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

DEFAULT_SCOPE = "openid email profile"
_TIMEOUT = httpx.Timeout(10.0)


class OIDCError(ValueError):
    """OIDC discovery/exchange/validation failure (mapped to a 400/401 at the route)."""


@dataclass(frozen=True)
class OIDCMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str


def discover(issuer: str) -> OIDCMetadata:
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    try:
        resp = httpx.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        doc = resp.json()
        return OIDCMetadata(
            issuer=doc.get("issuer", issuer),
            authorization_endpoint=doc["authorization_endpoint"],
            token_endpoint=doc["token_endpoint"],
            jwks_uri=doc["jwks_uri"],
        )
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise OIDCError(f"OIDC discovery failed for {issuer!r}: {exc}") from exc


def new_pkce() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` for PKCE S256."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_authorization_url(
    meta: OIDCMetadata,
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    nonce: str,
    code_challenge: str,
    scope: str = DEFAULT_SCOPE,
) -> str:
    query = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return meta.authorization_endpoint + "?" + urlencode(query)


def exchange_code(
    meta: OIDCMetadata,
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict[str, Any]:
    try:
        resp = httpx.post(
            meta.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
                "code_verifier": code_verifier,
            },
            headers={"Accept": "application/json"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OIDCError(f"OIDC token exchange failed: {exc}") from exc


def validate_id_token(
    id_token: str, *, meta: OIDCMetadata, client_id: str, nonce: str
) -> dict[str, Any]:
    """Verify signature (via the IdP JWKS), issuer, audience, expiry, and nonce."""
    try:
        signing_key = PyJWKClient(meta.jwks_uri).get_signing_key_from_jwt(id_token).key
        claims = jwt.decode(
            id_token,
            signing_key,
            algorithms=["RS256", "RS384", "RS512", "ES256"],
            audience=client_id,
            issuer=meta.issuer,
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        )
    except (jwt.PyJWTError, Exception) as exc:  # noqa: BLE001 - any verification failure is a hard fail
        raise OIDCError(f"OIDC id_token validation failed: {exc}") from exc
    if nonce and claims.get("nonce") != nonce:
        raise OIDCError("OIDC id_token nonce mismatch")
    return claims
