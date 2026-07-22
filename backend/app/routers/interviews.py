"""Interview scheduling.

Flow: recruiter proposes slots (computed from their real Google free/busy) →
a scheduling-link email is DRAFTED for review (approval flow from Phase 3) →
the candidate opens the public link and picks a slot → the calendar event is
created on the recruiter's calendar with Meet link, and Google invites the
attendees the candidate chose to meet.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUser, require_org
from ..config import settings
from ..db import service_client
from ..services import google_calendar as gcal
from ..services import scheduler

router = APIRouter(prefix="/api", tags=["interviews"])


class ProposeRequest(BaseModel):
    duration_minutes: int = Field(default=45, ge=15, le=240)
    days_ahead: int = Field(default=5, ge=1, le=20)
    slots_wanted: int = Field(default=5, ge=2, le=12)
    attendee_emails: list[str] = []  # e.g. hiring manager


@router.post("/candidates/{candidate_id}/interviews/propose", status_code=201)
def propose_interview(candidate_id: str, body: ProposeRequest, user: CurrentUser = Depends(require_org)):
    db = service_client()
    cand_rows = (
        db.table("candidates").select("*")
        .eq("id", candidate_id).eq("organization_id", user.organization_id)
        .execute().data
    )
    if not cand_rows:
        raise HTTPException(status_code=404, detail="Candidate not found")
    cand = cand_rows[0]
    if not cand.get("email"):
        raise HTTPException(status_code=400, detail="Candidate has no email address")

    conn = gcal.get_fresh_connection(user.user_id)
    if not conn:
        raise HTTPException(status_code=409, detail="Connect your Google Calendar first (Settings page)")

    now = datetime.now(timezone.utc)
    busy = gcal.fetch_busy(
        conn["access_token"], body.attendee_emails,
        now, now + timedelta(days=body.days_ahead * 2 + 2),
    )
    slots = gcal.compute_free_slots(busy, body.duration_minutes, body.days_ahead, body.slots_wanted)
    if not slots:
        raise HTTPException(status_code=409, detail="No free slots found in the window")

    role_title, org_name = "the role", ""
    if cand.get("role_id"):
        rows = db.table("roles").select("title").eq("id", cand["role_id"]).execute().data
        if rows:
            role_title = rows[0]["title"]
    org = db.table("organizations").select("name").eq("id", user.organization_id).single().execute().data
    org_name = org["name"]

    interview = (
        db.table("interviews").insert({
            "organization_id": user.organization_id,
            "candidate_id": candidate_id,
            "role_id": cand.get("role_id"),
            "interviewer_user_id": user.user_id,
            "interviewer_email": user.email,
            "attendee_emails": body.attendee_emails,
            "duration_minutes": body.duration_minutes,
            "proposed_slots": slots,
            "status": "proposed",
        }).execute().data[0]
    )

    link = f"{settings.frontend_url}/schedule/{interview['public_token']}"
    first_name = cand["full_name"].split()[0]
    body_text = (
        f"Hi {first_name},\n\n"
        f"Great news — we'd like to schedule your interview for {role_title} at {org_name}.\n\n"
        f"Please pick a time that works for you here:\n{link}\n\n"
        f"The interview is {body.duration_minutes} minutes over Google Meet. "
        f"If none of the times work, just reply to this email.\n\n"
        f"Best regards,\n{org_name}"
    )
    draft = (
        db.table("messages").insert({
            "organization_id": user.organization_id,
            "candidate_id": candidate_id,
            "role_id": cand.get("role_id"),
            "kind": "scheduling_link",
            "to_email": cand["email"],
            "subject": f"Schedule your interview — {role_title} at {org_name}",
            "body": body_text,
            "status": "draft",
            "created_by": user.user_id,
        }).execute().data[0]
    )
    return {"interview": interview, "draft": draft, "slots": slots, "link": link}


@router.get("/interviews")
def list_interviews(user: CurrentUser = Depends(require_org)):
    return (
        service_client()
        .table("interviews")
        .select("*, candidates(full_name, email), roles(title)")
        .eq("organization_id", user.organization_id)
        .order("created_at", desc=True)
        .limit(200)
        .execute().data
    )


class FeedbackBody(BaseModel):
    feedback: str = Field(min_length=1)


@router.patch("/interviews/{interview_id}/feedback")
def log_feedback(interview_id: str, body: FeedbackBody, user: CurrentUser = Depends(require_org)):
    db = service_client()
    rows = (
        db.table("interviews").select("id, scheduled_end")
        .eq("id", interview_id).eq("organization_id", user.organization_id)
        .execute().data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Interview not found")
    updates = {
        "feedback": body.feedback,
        "feedback_logged_at": datetime.now(timezone.utc).isoformat(),
    }
    end = rows[0].get("scheduled_end")
    if end and datetime.fromisoformat(end.replace("Z", "+00:00")) < datetime.now(timezone.utc):
        updates["status"] = "completed"
    return db.table("interviews").update(updates).eq("id", interview_id).execute().data[0]


@router.post("/interviews/{interview_id}/cancel")
def cancel_interview(interview_id: str, user: CurrentUser = Depends(require_org)):
    db = service_client()
    rows = (
        db.table("interviews").select("*")
        .eq("id", interview_id).eq("organization_id", user.organization_id)
        .execute().data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Interview not found")
    iv = rows[0]
    if iv["status"] == "cancelled":
        return iv
    if iv.get("google_event_id") and iv.get("interviewer_user_id"):
        conn = gcal.get_fresh_connection(iv["interviewer_user_id"])
        if conn:
            gcal.delete_event(conn["access_token"], iv["google_event_id"])
    return db.table("interviews").update({"status": "cancelled"}).eq("id", interview_id).execute().data[0]


@router.post("/scheduler/run-checks")
def run_scheduler_checks(user: CurrentUser = Depends(require_org)):
    """Manually trigger the reminder/nudge pass (it also runs on an interval)."""
    return scheduler.run_checks()


# ---------------------------------------------------------------------------
# Public, unauthenticated endpoints for the candidate's scheduling link.
# Keyed by unguessable public_token; expose only what the candidate needs.
# ---------------------------------------------------------------------------

def _interview_by_token(token: str) -> dict:
    rows = service_client().table("interviews").select("*").eq("public_token", token).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Scheduling link not found or expired")
    return rows[0]


@router.get("/public/schedule/{token}")
def public_get_schedule(token: str):
    iv = _interview_by_token(token)
    db = service_client()
    org = db.table("organizations").select("name").eq("id", iv["organization_id"]).single().execute().data
    role_title = None
    if iv.get("role_id"):
        rows = db.table("roles").select("title").eq("id", iv["role_id"]).execute().data
        role_title = rows[0]["title"] if rows else None
    now = datetime.now(timezone.utc)
    future_slots = [
        s for s in (iv.get("proposed_slots") or [])
        if datetime.fromisoformat(s["start"]) > now
    ]
    return {
        "status": iv["status"],
        "org_name": org["name"],
        "role_title": role_title,
        "duration_minutes": iv["duration_minutes"],
        "slots": future_slots if iv["status"] == "proposed" else [],
        "scheduled_start": iv.get("scheduled_start"),
        "meet_link": iv.get("meet_link") if iv["status"] == "scheduled" else None,
    }


class SlotChoice(BaseModel):
    start: str  # must match one of the proposed slots


@router.post("/public/schedule/{token}")
def public_select_slot(token: str, body: SlotChoice):
    iv = _interview_by_token(token)
    if iv["status"] != "proposed":
        raise HTTPException(status_code=409, detail="This interview is already scheduled or cancelled")
    slot = next((s for s in (iv.get("proposed_slots") or []) if s["start"] == body.start), None)
    if not slot:
        raise HTTPException(status_code=400, detail="Slot not in the proposed list")
    if datetime.fromisoformat(slot["start"]) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="That slot is in the past — ask for new times")

    conn = gcal.get_fresh_connection(iv["interviewer_user_id"])
    if not conn:
        raise HTTPException(status_code=502, detail="Recruiter calendar is no longer connected")

    db = service_client()
    cand = db.table("candidates").select("full_name, email").eq("id", iv["candidate_id"]).execute().data[0]
    role_title = "Interview"
    if iv.get("role_id"):
        rows = db.table("roles").select("title").eq("id", iv["role_id"]).execute().data
        if rows:
            role_title = rows[0]["title"]

    attendees = [cand["email"], iv["interviewer_email"], *(iv.get("attendee_emails") or [])]
    attendees = [a for i, a in enumerate(attendees) if a and a not in attendees[:i]]
    event = gcal.create_event(
        conn["access_token"],
        summary=f"Interview: {cand['full_name']} — {role_title}",
        description="Scheduled via Recruit AI scheduling link.",
        start_iso=slot["start"],
        end_iso=slot["end"],
        attendee_emails=attendees,
    )
    meet = event.get("hangoutLink") or next(
        (ep.get("uri") for ep in event.get("conferenceData", {}).get("entryPoints", []) if ep.get("uri")),
        None,
    )
    updated = (
        db.table("interviews").update({
            "status": "scheduled",
            "scheduled_start": slot["start"],
            "scheduled_end": slot["end"],
            "google_event_id": event["id"],
            "meet_link": meet,
        }).eq("id", iv["id"]).execute().data[0]
    )
    return {
        "status": "scheduled",
        "scheduled_start": updated["scheduled_start"],
        "meet_link": meet,
    }
