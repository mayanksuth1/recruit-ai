"""Self-serve signup that never depends on confirmation emails.

The account is created via the Supabase admin API with the email already
confirmed, and the organization is bootstrapped in the same call — so the
user can sign in with their password immediately after signing up.
"""
import httpx
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from ..config import settings
from ..db import service_client
from ..ratelimit import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    organization_name: str = Field(min_length=1, max_length=200)


# Open registration: anyone on the internet can call this, and each call
# creates a Supabase user plus an organization. Six per hour per address
# leaves room for genuine retries and typo-fixes without letting a script
# fill the project with junk tenants.
@router.post("/signup", status_code=201,
             dependencies=[Depends(limiter("signup", limit=6, window_seconds=3600))])
def signup(body: SignupRequest, request: Request):
    resp = httpx.post(
        f"{settings.supabase_url}/auth/v1/admin/users",
        headers={
            "apikey": settings.supabase_secret_key,
            "Authorization": f"Bearer {settings.supabase_secret_key}",
        },
        # email_confirm=True marks the address confirmed WITHOUT sending
        # anything, which is what lets signup work with no mail server.
        # Inverting it hands verification back to Supabase Auth.
        json={
            "email": body.email,
            "password": body.password,
            "email_confirm": not settings.require_email_verification,
        },
        timeout=20,
    )
    if resp.status_code == 422 or (resp.status_code == 400 and "already" in resp.text.lower()):
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists — sign in instead.",
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=502,
            detail="Could not create the account right now — please try again in a moment.",
        )
    user_id = resp.json()["id"]

    db = service_client()
    org = db.table("organizations").insert({"name": body.organization_name}).execute().data[0]
    db.table("organization_members").insert(
        {"organization_id": org["id"], "user_id": user_id, "member_role": "owner"}
    ).execute()
    # No signed-in user on this route; attribute the activity-log entry
    # to the workspace (the middleware reads request.state.actor).
    request.state.actor = SimpleNamespace(organization_id=org["id"], user_id=user_id)
    return {
        "ok": True,
        # The frontend needs to know whether to say "you're in" or "check
        # your inbox", and only the server knows which mode this is.
        "verification_required": settings.require_email_verification,
    }
