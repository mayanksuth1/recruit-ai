"""Outbound email via Resend. Called ONLY from the explicit human-approved
send endpoint — nothing in this codebase may call send_email as a side effect
of another action."""
import httpx
from fastapi import HTTPException

from ..config import settings

RESEND_API = "https://api.resend.com"


def send_email(to: str, subject: str, body: str) -> str:
    """Returns the Resend email id."""
    if not settings.resend_api_key:
        raise HTTPException(status_code=503, detail="RESEND_API_KEY is not configured")
    resp = httpx.post(
        f"{RESEND_API}/emails",
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        json={
            "from": settings.email_from,
            "to": [to],
            "subject": subject,
            "text": body,
        },
        timeout=20,
    )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Resend error: {resp.text}")
    return resp.json()["id"]


def get_email_status(provider_id: str) -> dict:
    resp = httpx.get(
        f"{RESEND_API}/emails/{provider_id}",
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        timeout=20,
    )
    if resp.status_code == 401 and "restricted" in resp.text:
        # Send-only API keys cannot read delivery status back.
        return {"last_event": "unknown_restricted_key"}
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Resend error: {resp.text}")
    return resp.json()
