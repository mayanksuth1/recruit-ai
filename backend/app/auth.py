"""Supabase JWT verification + tenant resolution.

Tokens are verified by calling Supabase's /auth/v1/user endpoint, which works
regardless of the project's JWT signing configuration (legacy HS256 secret or
new asymmetric keys). Results are cached briefly to avoid a round trip per
request.
"""
import base64
import json
import logging
import secrets
import time
from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .db import service_client

logger = logging.getLogger("uvicorn.error")

_bearer = HTTPBearer(auto_error=False)

# token -> (expires_at_monotonic, user_id, email)
_token_cache: dict[str, tuple[float, str, str]] = {}
_TOKEN_TTL = 60.0

# user_id -> (expires_at_monotonic, org_id)
_org_cache: dict[str, tuple[float, str]] = {}
_ORG_TTL = 300.0


@dataclass
class CurrentUser:
    user_id: str
    email: str
    organization_id: str | None


def _jwt_claims(token: str) -> dict:
    """The token's payload, UNVERIFIED. Only call this on a token that
    /auth/v1/user has just accepted; it reads claims, it does not trust them."""
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return {}


def _auth_admin(method: str, path: str, **kwargs) -> httpx.Response:
    return httpx.request(
        method,
        f"{settings.supabase_url}/auth/v1{path}",
        headers={
            "apikey": settings.supabase_secret_key,
            "Authorization": f"Bearer {settings.supabase_secret_key}",
        },
        timeout=10,
        **kwargs,
    )


def _guard_pre_linked_account(token: str, user: dict) -> None:
    """Close the pre-registration takeover that Google sign-in opens.

    While email verification is off, a password account proves nothing about
    its address: anyone can register victim@gmail.com first. Supabase then
    links the real owner's later "Continue with Google" to that same account,
    because the addresses match, and the squatter still knows the password.

    So an account whose password identity predates its Google identity is
    treated as unproven until its owner arrives through Google. At that
    moment the password is replaced with a random one and every other session
    is revoked, which evicts whoever set it; the owner can set their own again
    through "Forgot password". Until then, password sessions on such an
    account are refused.
    """
    if settings.require_email_verification:
        return  # every password account has proved its inbox
    app_meta = user.get("app_metadata") or {}
    if app_meta.get("password_reclaimed"):
        return
    idents = {i.get("provider"): i for i in (user.get("identities") or [])}
    email_ident, google_ident = idents.get("email"), idents.get("google")
    if not (email_ident and google_ident):
        return
    # ISO-8601 UTC strings from the same server compare correctly as text.
    if (email_ident.get("created_at") or "") > (google_ident.get("created_at") or ""):
        return  # password added after Google had already proved the address

    methods = {a.get("method") for a in (_jwt_claims(token).get("amr") or []) if isinstance(a, dict)}
    if "oauth" in methods:
        reset = _auth_admin(
            "PUT", f"/admin/users/{user['id']}",
            json={
                "password": secrets.token_urlsafe(32),
                "app_metadata": {**app_meta, "password_reclaimed": True},
            },
        )
        if reset.status_code != 200:
            logger.error("could not reclaim pre-linked account %s: %s", user["id"], reset.status_code)
            raise HTTPException(status_code=503, detail="Account check failed — please try again.")
        httpx.post(
            f"{settings.supabase_url}/auth/v1/logout",
            params={"scope": "others"},
            headers={"apikey": settings.supabase_secret_key, "Authorization": f"Bearer {token}"},
            timeout=10,
        )
        logger.warning("reclaimed pre-linked account %s: password reset, other sessions revoked", user["id"])
        return

    # A password session on an account Google has claimed but that has not yet
    # been reclaimed: exactly the squatter's position. End it.
    httpx.post(
        f"{settings.supabase_url}/auth/v1/logout",
        params={"scope": "local"},
        headers={"apikey": settings.supabase_secret_key, "Authorization": f"Bearer {token}"},
        timeout=10,
    )
    raise HTTPException(
        status_code=401,
        detail="This account is linked to Google. Sign in with \"Continue with Google\".",
    )


def _verify_token(token: str) -> tuple[str, str]:
    now = time.monotonic()
    cached = _token_cache.get(token)
    if cached and cached[0] > now:
        return cached[1], cached[2]

    resp = None
    for attempt in range(2):  # GET is idempotent; retry transient upstream blips
        try:
            resp = httpx.get(
                f"{settings.supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": settings.supabase_secret_key,
                },
                timeout=10,
            )
            break
        except httpx.TransportError:
            if attempt:
                raise HTTPException(status_code=503, detail="Auth service unreachable — retry")
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    data = resp.json()
    _guard_pre_linked_account(token, data)
    user_id, email = data["id"], data.get("email", "")
    _token_cache[token] = (now + _TOKEN_TTL, user_id, email)
    if len(_token_cache) > 1000:
        _token_cache.clear()
    return user_id, email


def _resolve_org(user_id: str) -> str | None:
    now = time.monotonic()
    cached = _org_cache.get(user_id)
    if cached and cached[0] > now:
        return cached[1]

    res = (
        service_client()
        .table("organization_members")
        .select("organization_id")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    org_id = res.data[0]["organization_id"] if res.data else None
    if org_id:
        _org_cache[user_id] = (now + _ORG_TTL, org_id)
    return org_id


def invalidate_org_cache(user_id: str) -> None:
    _org_cache.pop(user_id, None)


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    if creds is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    user_id, email = _verify_token(creds.credentials)
    user = CurrentUser(user_id=user_id, email=email, organization_id=_resolve_org(user_id))
    # Read back by the activity-log middleware once the response is ready.
    request.state.actor = user
    return user


def require_org(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Most endpoints require the user to already belong to an organization."""
    if not user.organization_id:
        raise HTTPException(
            status_code=403,
            detail="User has no organization. Call POST /api/organizations/bootstrap first.",
        )
    return user
