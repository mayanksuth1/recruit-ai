"""Google Calendar integration: OAuth per recruiter, free/busy slot
computation, event create/delete. Plain REST via httpx — no SDK needed."""
import secrets
import uuid
from datetime import datetime, time as dtime, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException

from ..config import settings
from ..db import service_client

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
CAL_API = "https://www.googleapis.com/calendar/v3"
SCOPES = "openid email https://www.googleapis.com/auth/calendar"

WORK_START = dtime(10, 0)
WORK_END = dtime(18, 0)
GRID_MINUTES = 30


def _require_google_config():
    if not (settings.google_client_id and settings.google_client_secret):
        raise HTTPException(status_code=503, detail="Google OAuth credentials not configured")


def create_consent_url(user_id: str, org_id: str) -> str:
    _require_google_config()
    state = secrets.token_urlsafe(32)
    service_client().table("oauth_states").insert(
        {"state": state, "user_id": user_id, "organization_id": org_id}
    ).execute()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def consume_state(state: str) -> dict | None:
    db = service_client()
    rows = db.table("oauth_states").select("*").eq("state", state).execute().data
    if not rows:
        return None
    db.table("oauth_states").delete().eq("state", state).execute()
    created = datetime.fromisoformat(rows[0]["created_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) - created > timedelta(minutes=15):
        return None
    return rows[0]


def exchange_code(code: str) -> dict:
    resp = httpx.post(TOKEN_URL, data={
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.google_redirect_uri,
    }, timeout=20)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Google token exchange failed: {resp.text[:300]}")
    return resp.json()


def fetch_google_email(access_token: str) -> str | None:
    resp = httpx.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=20)
    return resp.json().get("email") if resp.status_code == 200 else None


def save_connection(user_id: str, org_id: str, tokens: dict) -> dict:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600) - 60)
    record = {
        "user_id": user_id,
        "organization_id": org_id,
        "google_email": fetch_google_email(tokens["access_token"]),
        "access_token": tokens["access_token"],
        "token_expires_at": expires_at.isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if tokens.get("refresh_token"):
        record["refresh_token"] = tokens["refresh_token"]
    db = service_client()
    existing = db.table("calendar_connections").select("user_id").eq("user_id", user_id).execute().data
    if existing:
        return db.table("calendar_connections").update(record).eq("user_id", user_id).execute().data[0]
    return db.table("calendar_connections").insert(record).execute().data[0]


def get_fresh_connection(user_id: str) -> dict | None:
    """Load the user's connection, refreshing the access token if expired."""
    db = service_client()
    rows = db.table("calendar_connections").select("*").eq("user_id", user_id).execute().data
    if not rows:
        return None
    conn = rows[0]
    expires = conn.get("token_expires_at")
    if expires and datetime.fromisoformat(expires.replace("Z", "+00:00")) > datetime.now(timezone.utc):
        return conn
    if not conn.get("refresh_token"):
        return conn  # let the API call fail loudly if truly expired
    resp = httpx.post(TOKEN_URL, data={
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "refresh_token": conn["refresh_token"],
        "grant_type": "refresh_token",
    }, timeout=20)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Google token refresh failed: {resp.text[:300]}")
    tokens = resp.json()
    new_expires = datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600) - 60)
    conn["access_token"] = tokens["access_token"]
    conn["token_expires_at"] = new_expires.isoformat()
    db.table("calendar_connections").update(
        {"access_token": conn["access_token"], "token_expires_at": conn["token_expires_at"],
         "updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("user_id", user_id).execute()
    return conn


def fetch_busy(access_token: str, emails: list[str], time_min: datetime, time_max: datetime) -> list[tuple[datetime, datetime]]:
    """Free/busy across the recruiter's primary calendar plus any attendee
    calendars Google will disclose (external calendars often won't be)."""
    resp = httpx.post(
        f"{CAL_API}/freeBusy",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "items": [{"id": "primary"}] + [{"id": e} for e in emails],
        },
        timeout=20,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Google freeBusy failed: {resp.text[:300]}")
    busy = []
    for cal in resp.json().get("calendars", {}).values():
        for block in cal.get("busy", []):
            busy.append((
                datetime.fromisoformat(block["start"].replace("Z", "+00:00")),
                datetime.fromisoformat(block["end"].replace("Z", "+00:00")),
            ))
    return busy


def compute_free_slots(busy: list[tuple[datetime, datetime]], duration_minutes: int,
                       days_ahead: int, count: int) -> list[dict]:
    """Weekday slots on a 30-min grid within working hours, skipping busy
    blocks. Times are in the org's scheduler timezone."""
    tz = ZoneInfo(settings.scheduler_timezone)
    duration = timedelta(minutes=duration_minutes)
    now = datetime.now(tz)
    slots: list[dict] = []
    day = now.date() + timedelta(days=1)
    end_day = now.date() + timedelta(days=days_ahead * 2 + 2)  # headroom for weekends
    business_days_seen = 0
    while day <= end_day and len(slots) < count and business_days_seen < days_ahead:
        if day.weekday() < 5:
            business_days_seen += 1
            cursor = datetime.combine(day, WORK_START, tz)
            day_end = datetime.combine(day, WORK_END, tz)
            while cursor + duration <= day_end and len(slots) < count:
                slot_end = cursor + duration
                if not any(cursor < b_end and slot_end > b_start for b_start, b_end in busy):
                    slots.append({"start": cursor.isoformat(), "end": slot_end.isoformat()})
                    cursor += timedelta(minutes=max(GRID_MINUTES * 2, duration_minutes))
                else:
                    cursor += timedelta(minutes=GRID_MINUTES)
        day += timedelta(days=1)
    return slots


def create_event(access_token: str, summary: str, description: str,
                 start_iso: str, end_iso: str, attendee_emails: list[str]) -> dict:
    resp = httpx.post(
        f"{CAL_API}/calendars/primary/events",
        params={"conferenceDataVersion": 1, "sendUpdates": "all"},
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_iso},
            "end": {"dateTime": end_iso},
            "attendees": [{"email": e} for e in attendee_emails],
            "conferenceData": {"createRequest": {
                "requestId": uuid.uuid4().hex,
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }},
            "reminders": {"useDefault": True},
        },
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Google event creation failed: {resp.text[:300]}")
    return resp.json()


def get_event(access_token: str, event_id: str) -> dict | None:
    resp = httpx.get(f"{CAL_API}/calendars/primary/events/{event_id}",
                     headers={"Authorization": f"Bearer {access_token}"}, timeout=20)
    return resp.json() if resp.status_code == 200 else None


def delete_event(access_token: str, event_id: str) -> None:
    httpx.delete(f"{CAL_API}/calendars/primary/events/{event_id}",
                 params={"sendUpdates": "all"},
                 headers={"Authorization": f"Bearer {access_token}"}, timeout=20)
