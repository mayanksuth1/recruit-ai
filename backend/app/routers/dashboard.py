"""Operational overview: what is happening, and what is waiting on a human.

Deliberately NOT a second reporting surface. /api/reports/funnel answers "how is
the pipeline converting" and produces the PDF a client reads; this answers "what
should I do next", which is a different question with a different shelf life —
these numbers are only interesting until you act on them.

Everything is one request. The counts are small and the frontend showing half a
dashboard while four spinners resolve is worse than waiting for one payload.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from ..auth import CurrentUser, require_org
from ..db import service_client

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_ACTIVITY_LIMIT = 12
_STAGES = ("screening", "outreach", "interview", "offer", "closed")


def _count(query) -> int:
    """PostgREST exact count without transferring the rows."""
    return query.execute().count or 0


@router.get("")
def dashboard(user: CurrentUser = Depends(require_org)):
    db = service_client()
    org = user.organization_id
    now = datetime.now(timezone.utc)

    roles = (
        db.table("roles").select("id, title, status, created_at, linkedin_post_draft")
        .eq("organization_id", org).order("created_at", desc=True).execute().data
    )
    candidates = (
        db.table("candidates")
        .select("id, full_name, stage, shortlist_status, created_at, role_id")
        .eq("organization_id", org).order("created_at", desc=True).execute().data
    )
    messages = (
        db.table("messages").select("id, status, kind, subject, created_at, sent_at, candidate_id")
        .eq("organization_id", org).order("created_at", desc=True).limit(100).execute().data
    )
    interviews = (
        db.table("interviews")
        .select("id, status, scheduled_start, feedback_logged_at, created_at, candidate_id, role_id")
        .eq("organization_id", org).order("created_at", desc=True).execute().data
    )
    sessions = (
        db.table("ai_interview_sessions")
        .select("id, status, issued_at, expires_at, completed_at, created_at, candidate_id")
        .eq("organization_id", org).order("created_at", desc=True).execute().data
    )
    pool_count = _count(
        db.table("talent_pool").select("id", count="exact").eq("organization_id", org)
    )
    backlog = (
        db.table("ai_embedding_backlog").select("source_kind")
        .eq("organization_id", org).execute().data
    )

    names = {c["id"]: c["full_name"] for c in candidates}
    titles = {r["id"]: r["title"] for r in roles}

    # ---- headline counts -------------------------------------------------
    upcoming = [
        i for i in interviews
        if i["status"] == "scheduled" and i.get("scheduled_start")
        and i["scheduled_start"] > now.isoformat()
    ]
    tiles = {
        "open_roles": sum(1 for r in roles if r["status"] == "open"),
        "candidates": len(candidates),
        "talent_pool": pool_count,
        "draft_emails": sum(1 for m in messages if m["status"] == "draft"),
        "upcoming_interviews": len(upcoming),
        "embed_backlog": len(backlog),
    }

    # ---- what is waiting on a human -------------------------------------
    # Each item is something only a person can clear, phrased as the action.
    # An empty list here is the app telling you there is nothing to do, which
    # is worth as much as a long one.
    attention = []

    pending = [c for c in candidates if c["shortlist_status"] == "pending"]
    if pending:
        attention.append({
            "kind": "shortlist",
            "count": len(pending),
            "label": f"{len(pending)} candidate{'s' if len(pending) != 1 else ''} awaiting an approve/reject decision",
            "href": "/",
        })

    drafts = [m for m in messages if m["status"] == "draft"]
    if drafts:
        attention.append({
            "kind": "drafts",
            "count": len(drafts),
            "label": f"{len(drafts)} email draft{'s' if len(drafts) != 1 else ''} waiting for review — nothing sends until you do",
            "href": "/outbox",
        })

    # Interviews that have happened but nobody wrote down what came of them.
    missing_feedback = [
        i for i in interviews
        if i.get("scheduled_start") and i["scheduled_start"] < now.isoformat()
        and i["status"] != "cancelled" and not i.get("feedback_logged_at")
    ]
    if missing_feedback:
        attention.append({
            "kind": "feedback",
            "count": len(missing_feedback),
            "label": f"{len(missing_feedback)} past interview{'s' if len(missing_feedback) != 1 else ''} with no feedback logged",
            "href": "/interviews",
        })

    # Issued links that will lapse unread. 72h window, so "soon" is 24h.
    expiring = [
        s for s in sessions
        if s["status"] in ("issued", "in_progress")
        and s.get("expires_at") and now.isoformat() < s["expires_at"] < (now + timedelta(hours=24)).isoformat()
    ]
    if expiring:
        attention.append({
            "kind": "expiring",
            "count": len(expiring),
            "label": f"{len(expiring)} AI interview link{'s' if len(expiring) != 1 else ''} expiring within 24 hours",
            "href": "/ai-interviews",
        })

    unscored = [s for s in sessions if s["status"] == "completed"]
    if unscored:
        attention.append({
            "kind": "unscored",
            "count": len(unscored),
            "label": f"{len(unscored)} completed AI interview{'s' if len(unscored) != 1 else ''} not scored yet",
            "href": "/ai-interviews",
        })

    if backlog:
        attention.append({
            "kind": "backlog",
            "count": len(backlog),
            "label": f"{len(backlog)} item{'s' if len(backlog) != 1 else ''} not embedded — they will not appear in search",
            "href": "/ai-interviews",
        })

    roles_without_post = [r for r in roles if r["status"] == "open" and not (r.get("linkedin_post_draft") or "").strip()]
    if roles_without_post:
        attention.append({
            "kind": "no_post",
            "count": len(roles_without_post),
            "label": f"{len(roles_without_post)} open role{'s' if len(roles_without_post) != 1 else ''} with no LinkedIn post drafted",
            "href": "/",
        })

    # ---- pipeline spread -------------------------------------------------
    by_stage = [
        {"stage": s, "count": sum(1 for c in candidates if c["stage"] == s)}
        for s in _STAGES
    ]

    # ---- recent activity -------------------------------------------------
    # Merged from every table that records a timestamp, then sorted once. The
    # per-table limits above keep this bounded without a union query.
    events: list[dict] = []
    for r in roles[:_ACTIVITY_LIMIT]:
        events.append({"at": r["created_at"], "kind": "role", "text": f"Role opened — {r['title']}"})
    for c in candidates[:_ACTIVITY_LIMIT]:
        events.append({"at": c["created_at"], "kind": "candidate",
                       "text": f"Candidate added — {c['full_name']}"})
    for m in messages[:_ACTIVITY_LIMIT]:
        who = names.get(m["candidate_id"], "a candidate")
        if m["status"] == "sent" and m.get("sent_at"):
            events.append({"at": m["sent_at"], "kind": "sent", "text": f"Email sent to {who}"})
        else:
            events.append({"at": m["created_at"], "kind": "draft",
                           "text": f"{m['kind'].replace('_', ' ').title()} draft written for {who}"})
    for i in interviews[:_ACTIVITY_LIMIT]:
        events.append({"at": i["created_at"], "kind": "interview",
                       "text": f"Interview {i['status']} — {names.get(i['candidate_id'], 'candidate')}"
                               + (f" · {titles.get(i['role_id'])}" if titles.get(i.get("role_id")) else "")})
    for s in sessions[:_ACTIVITY_LIMIT]:
        events.append({"at": s["created_at"], "kind": "ai_interview",
                       "text": f"AI interview {s['status'].replace('_', ' ')} — {names.get(s['candidate_id'], 'candidate')}"})

    events = [e for e in events if e.get("at")]
    events.sort(key=lambda e: e["at"], reverse=True)

    return {
        "generated_at": now.isoformat(),
        "tiles": tiles,
        "attention": attention,
        "by_stage": by_stage,
        "activity": events[:_ACTIVITY_LIMIT],
    }
