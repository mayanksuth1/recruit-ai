"""Self-serve signup that never depends on confirmation emails.

The account is created via the Supabase admin API with the email already
confirmed, and the organization is bootstrapped in the same call — so the
user can sign in with their password immediately after signing up.
"""
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

from ..config import settings
from ..db import service_client

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    organization_name: str = Field(min_length=1, max_length=200)


@router.post("/signup", status_code=201)
def signup(body: SignupRequest):
    resp = httpx.post(
        f"{settings.supabase_url}/auth/v1/admin/users",
        headers={
            "apikey": settings.supabase_secret_key,
            "Authorization": f"Bearer {settings.supabase_secret_key}",
        },
        json={"email": body.email, "password": body.password, "email_confirm": True},
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
    return {"ok": True}
