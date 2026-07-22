"""Supabase JWT verification + tenant resolution.

Tokens are verified by calling Supabase's /auth/v1/user endpoint, which works
regardless of the project's JWT signing configuration (legacy HS256 secret or
new asymmetric keys). Results are cached briefly to avoid a round trip per
request.
"""
import time
from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .db import service_client

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
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    if creds is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    user_id, email = _verify_token(creds.credentials)
    return CurrentUser(user_id=user_id, email=email, organization_id=_resolve_org(user_id))


def require_org(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Most endpoints require the user to already belong to an organization."""
    if not user.organization_id:
        raise HTTPException(
            status_code=403,
            detail="User has no organization. Call POST /api/organizations/bootstrap first.",
        )
    return user
