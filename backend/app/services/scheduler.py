"""Periodic checks: 24h-before interview reminder DRAFTS (reviewed before
send, per the approval rule) and 48h-after feedback nudges to the interviewer
(internal staff — the one email that sends automatically, and it never goes
to a candidate or client).

Runs in-process on an interval (see main.py). This is the piece an n8n
workflow could later replace so a non-technical admin can edit cadences —
the endpoints it calls are already API-shaped.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..config import settings
from ..db import service_client
from .email import send_email


def _fmt(iso: str) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ZoneInfo(settings.scheduler_timezone))
    return dt.strftime("%A %d %b %Y, %I:%M %p (%Z)")


def _candidate_and_role(db, interview) -> tuple[dict, dict]:
    cand = db.table("candidates").select("*").eq("id", interview["candidate_id"]).execute().data
    role = {}
    if interview.get("role_id"):
        rows = db.table("roles").select("title").eq("id", interview["role_id"]).execute().data
        role = rows[0] if rows else {}
    return (cand[0] if cand else {}), role


def draft_due_reminders() -> int:
    """Interviews starting within 24h with no reminder draft yet →
    create a DRAFT reminder in the outbox."""
    db = service_client()
    now = datetime.now(timezone.utc)
    due = (
        db.table("interviews").select("*")
        .eq("status", "scheduled")
        .gte("scheduled_start", now.isoformat())
        .lte("scheduled_start", (now + timedelta(hours=24)).isoformat())
        .is_("reminder_drafted_at", "null")
        .execute().data
    )
    drafted = 0
    for iv in due:
        cand, role = _candidate_and_role(db, iv)
        if not cand.get("email"):
            continue
        body = (
            f"Hi {cand['full_name'].split()[0]},\n\n"
            f"A quick reminder about your interview for {role.get('title', 'the role')} "
            f"on {_fmt(iv['scheduled_start'])}."
            + (f"\n\nJoin link: {iv['meet_link']}" if iv.get("meet_link") else "")
            + "\n\nIf anything has changed, just reply to this email.\n\nBest regards"
        )
        db.table("messages").insert({
            "organization_id": iv["organization_id"],
            "candidate_id": iv["candidate_id"],
            "role_id": iv.get("role_id"),
            "kind": "interview_reminder",
            "to_email": cand["email"],
            "subject": f"Reminder: interview on {_fmt(iv['scheduled_start'])}",
            "body": body,
            "status": "draft",
        }).execute()
        db.table("interviews").update(
            {"reminder_drafted_at": now.isoformat()}
        ).eq("id", iv["id"]).execute()
        drafted += 1
    return drafted


def send_due_feedback_nudges() -> int:
    """Interviews that ended >48h ago with no feedback logged → email the
    interviewer (internal). Marks nudge_sent_at even on provider failure so
    a broken address doesn't retry forever; the failure is recorded."""
    db = service_client()
    now = datetime.now(timezone.utc)
    due = (
        db.table("interviews").select("*")
        .eq("status", "scheduled")
        .lte("scheduled_end", (now - timedelta(hours=48)).isoformat())
        .is_("feedback", "null")
        .is_("nudge_sent_at", "null")
        .execute().data
    )
    nudged = 0
    for iv in due:
        to = iv.get("interviewer_email")
        if not to:
            continue
        cand, role = _candidate_and_role(db, iv)
        subject = f"Feedback pending: {cand.get('full_name', 'candidate')} — {role.get('title', 'role')}"
        body = (
            f"You interviewed {cand.get('full_name', 'a candidate')} for "
            f"{role.get('title', 'a role')} on {_fmt(iv['scheduled_end'])} and no feedback "
            f"has been logged yet.\n\nPlease add your feedback on the Interviews page."
        )
        status, error = "sent", None
        try:
            send_email(to, subject, body)
        except Exception as e:  # keep the loop alive; record what happened
            status, error = "failed", str(e)[:500]
        db.table("messages").insert({
            "organization_id": iv["organization_id"],
            "candidate_id": iv["candidate_id"],
            "role_id": iv.get("role_id"),
            "kind": "feedback_nudge",
            "to_email": to,
            "subject": subject,
            "body": body,
            "status": status,
            "error": error,
            "sent_at": now.isoformat() if status == "sent" else None,
        }).execute()
        db.table("interviews").update({"nudge_sent_at": now.isoformat()}).eq("id", iv["id"]).execute()
        nudged += 1
    return nudged


def run_checks() -> dict:
    from .reporting import generate_weekly_reports

    return {
        "reminders_drafted": draft_due_reminders(),
        "nudges_sent": send_due_feedback_nudges(),
        "weekly_reports": generate_weekly_reports(),
    }
