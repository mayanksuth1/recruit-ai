"""Engagement module: reviewed-before-send email queue.

Human approval gate 1 lives here:
- Outreach can only be DRAFTED for candidates whose shortlist_status is
  'approved' ("Approved for outreach").
- Every message starts as status='draft'. The ONLY path to a candidate's
  inbox is POST /api/messages/{id}/send — an explicit recruiter click.
  Stage changes and follow-up checks create drafts, never send.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUser, require_org
from ..db import service_client
from ..services import ats, drafting
from ..services.email import get_email_status, send_email

router = APIRouter(prefix="/api", tags=["engagement"])

STAGES = ("screening", "outreach", "interview", "offer", "closed")
GATED_STAGES = ("offer", "closed")  # gate 2: require explicit offer approval


def _get_candidate_or_404(candidate_id: str, org_id: str) -> dict:
    res = (
        service_client()
        .table("candidates")
        .select("*")
        .eq("id", candidate_id)
        .eq("organization_id", org_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return res.data[0]


def _org_and_role(org_id: str, role_id: str | None) -> tuple[str, dict]:
    db = service_client()
    org = db.table("organizations").select("name").eq("id", org_id).single().execute().data
    role = {}
    if role_id:
        rows = db.table("roles").select("*").eq("id", role_id).eq("organization_id", org_id).execute().data
        role = rows[0] if rows else {}
    return org["name"], role


def _sender_name(user: CurrentUser) -> str:
    return user.email.split("@")[0].replace(".", " ").title()


@router.post("/candidates/{candidate_id}/draft-outreach", status_code=201)
def create_outreach_draft(candidate_id: str, user: CurrentUser = Depends(require_org)):
    cand = _get_candidate_or_404(candidate_id, user.organization_id)
    # ------- HUMAN APPROVAL GATE 1 -------
    if cand["shortlist_status"] != "approved":
        raise HTTPException(
            status_code=409,
            detail="Candidate is not approved for outreach. Approve them on the shortlist first.",
        )
    if not cand.get("email"):
        raise HTTPException(status_code=400, detail="Candidate has no email address")

    org_name, role = _org_and_role(user.organization_id, cand.get("role_id"))
    draft = drafting.draft_outreach(
        role_title=role.get("title", "a role"),
        jd=role.get("description", ""),
        candidate_name=cand["full_name"],
        profile=cand.get("resume_text") or "",
        sender_name=_sender_name(user),
        org_name=org_name,
    )
    row = (
        service_client()
        .table("messages")
        .insert(
            {
                "organization_id": user.organization_id,
                "candidate_id": candidate_id,
                "role_id": cand.get("role_id"),
                "kind": "outreach",
                "to_email": cand["email"],
                "subject": draft["subject"],
                "body": draft["body"],
                "status": "draft",
                "created_by": user.user_id,
            }
        )
        .execute()
        .data[0]
    )
    return row


class StageUpdate(BaseModel):
    stage: str


@router.post("/candidates/{candidate_id}/approve-offer")
def approve_offer(candidate_id: str, user: CurrentUser = Depends(require_org)):
    """HUMAN APPROVAL GATE 2: an explicit, recorded approval that unlocks
    moving this candidate to the offer/closure stages."""
    _get_candidate_or_404(candidate_id, user.organization_id)
    updated = (
        service_client().table("candidates")
        .update({
            "offer_approved_at": datetime.now(timezone.utc).isoformat(),
            "offer_approved_by": user.user_id,
        })
        .eq("id", candidate_id).eq("organization_id", user.organization_id)
        .execute().data[0]
    )
    ats.send_outbound(user.organization_id, "candidate.offer_approved",
                      {"candidate_id": candidate_id, "email": updated.get("email"),
                       "full_name": updated["full_name"]}, candidate_id)
    return updated


@router.post("/candidates/{candidate_id}/revoke-offer-approval")
def revoke_offer_approval(candidate_id: str, user: CurrentUser = Depends(require_org)):
    _get_candidate_or_404(candidate_id, user.organization_id)
    return (
        service_client().table("candidates")
        .update({"offer_approved_at": None, "offer_approved_by": None})
        .eq("id", candidate_id).eq("organization_id", user.organization_id)
        .execute().data[0]
    )


@router.patch("/candidates/{candidate_id}/stage")
def update_stage(candidate_id: str, body: StageUpdate, background: BackgroundTasks,
                 user: CurrentUser = Depends(require_org)):
    """Move a candidate to a new stage. Automatically DRAFTS (never sends) a
    status-update email for recruiter review. Offer/closure stages sit behind
    gate 2. Stage changes are synced to the org's ATS webhook if configured."""
    if body.stage not in STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage; one of {STAGES}")
    cand = _get_candidate_or_404(candidate_id, user.organization_id)
    if cand["stage"] == body.stage:
        return {"candidate": cand, "status_update_draft": None}

    # ------- HUMAN APPROVAL GATE 2 -------
    if body.stage in GATED_STAGES and not cand.get("offer_approved_at"):
        raise HTTPException(
            status_code=409,
            detail="Offer/closure requires explicit approval first (\"Approve for offer\" on the candidate).",
        )

    db = service_client()
    updated = (
        db.table("candidates")
        .update({"stage": body.stage})
        .eq("id", candidate_id)
        .eq("organization_id", user.organization_id)
        .execute()
        .data[0]
    )

    draft_row = None
    if cand.get("email"):
        org_name, role = _org_and_role(user.organization_id, cand.get("role_id"))
        draft = drafting.draft_status_update(
            role_title=role.get("title", "a role"),
            new_stage=body.stage,
            candidate_name=cand["full_name"],
            sender_name=_sender_name(user),
            org_name=org_name,
        )
        draft_row = (
            db.table("messages")
            .insert(
                {
                    "organization_id": user.organization_id,
                    "candidate_id": candidate_id,
                    "role_id": cand.get("role_id"),
                    "kind": "status_update",
                    "to_email": cand["email"],
                    "subject": draft["subject"],
                    "body": draft["body"],
                    "status": "draft",
                    "created_by": user.user_id,
                }
            )
            .execute()
            .data[0]
        )

    # Sync the stage change to the org's ATS (fire-and-forget, logged).
    background.add_task(
        ats.send_outbound, user.organization_id, "candidate.stage_changed",
        {"candidate_id": candidate_id, "email": cand.get("email"),
         "full_name": cand["full_name"], "from_stage": cand["stage"], "to_stage": body.stage},
        candidate_id,
    )
    return {"candidate": updated, "status_update_draft": draft_row}


class FollowUpRequest(BaseModel):
    days: int = Field(default=4, ge=1, le=60)


@router.post("/engagement/follow-ups")
def generate_follow_ups(body: FollowUpRequest, user: CurrentUser = Depends(require_org)):
    """Draft follow-ups for outreach emails sent >= N days ago with no
    recorded response and no existing follow-up. Drafts only."""
    db = service_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=body.days)).isoformat()
    sent_outreach = (
        db.table("messages")
        .select("*")
        .eq("organization_id", user.organization_id)
        .eq("kind", "outreach")
        .eq("status", "sent")
        .is_("responded_at", "null")
        .lte("sent_at", cutoff)
        .execute()
        .data
    )
    existing_followups = (
        db.table("messages")
        .select("parent_message_id")
        .eq("organization_id", user.organization_id)
        .eq("kind", "follow_up")
        .not_.is_("parent_message_id", "null")
        .execute()
        .data
    )
    already = {f["parent_message_id"] for f in existing_followups}

    created = []
    for msg in sent_outreach:
        if msg["id"] in already:
            continue
        cand_rows = (
            db.table("candidates")
            .select("*")
            .eq("id", msg["candidate_id"])
            .eq("organization_id", user.organization_id)
            .execute()
            .data
        )
        if not cand_rows:
            continue
        cand = cand_rows[0]
        org_name, role = _org_and_role(user.organization_id, msg.get("role_id"))
        sent_at = datetime.fromisoformat(msg["sent_at"].replace("Z", "+00:00"))
        days_ago = max(1, (datetime.now(timezone.utc) - sent_at).days)
        draft = drafting.draft_follow_up(
            role_title=role.get("title", "a role"),
            jd=role.get("description", ""),
            candidate_name=cand["full_name"],
            profile=cand.get("resume_text") or "",
            prev_subject=msg["subject"],
            prev_body=msg["body"],
            days_ago=days_ago,
            sender_name=_sender_name(user),
            org_name=org_name,
        )
        row = (
            db.table("messages")
            .insert(
                {
                    "organization_id": user.organization_id,
                    "candidate_id": cand["id"],
                    "role_id": msg.get("role_id"),
                    "kind": "follow_up",
                    "to_email": msg["to_email"],
                    "subject": draft["subject"],
                    "body": draft["body"],
                    "status": "draft",
                    "parent_message_id": msg["id"],
                    "created_by": user.user_id,
                }
            )
            .execute()
            .data[0]
        )
        created.append(row)
    return {"drafted": len(created), "messages": created}


@router.get("/messages")
def list_messages(
    status: str | None = None,
    role_id: str | None = None,
    user: CurrentUser = Depends(require_org),
):
    q = (
        service_client()
        .table("messages")
        .select("*, candidates(full_name), roles(title)")
        .eq("organization_id", user.organization_id)
        .order("created_at", desc=True)
        .limit(200)
    )
    if status:
        q = q.eq("status", status)
    if role_id:
        q = q.eq("role_id", role_id)
    return q.execute().data


class MessageEdit(BaseModel):
    subject: str | None = None
    body: str | None = None


def _get_message_or_404(message_id: str, org_id: str) -> dict:
    res = (
        service_client()
        .table("messages")
        .select("*")
        .eq("id", message_id)
        .eq("organization_id", org_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Message not found")
    return res.data[0]


@router.patch("/messages/{message_id}")
def edit_message(message_id: str, body: MessageEdit, user: CurrentUser = Depends(require_org)):
    msg = _get_message_or_404(message_id, user.organization_id)
    if msg["status"] != "draft":
        raise HTTPException(status_code=409, detail="Only drafts can be edited")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    return (
        service_client()
        .table("messages")
        .update(updates)
        .eq("id", message_id)
        .eq("organization_id", user.organization_id)
        .execute()
        .data[0]
    )


@router.post("/messages/{message_id}/send")
def send_message(message_id: str, user: CurrentUser = Depends(require_org)):
    """THE human approval action: an explicit recruiter click sends exactly
    this reviewed draft. There is no other code path that emails candidates."""
    msg = _get_message_or_404(message_id, user.organization_id)
    if msg["status"] == "sent":
        raise HTTPException(status_code=409, detail="Message already sent")
    if msg["status"] != "draft":
        raise HTTPException(status_code=409, detail=f"Cannot send a {msg['status']} message")

    provider_id = send_email(msg["to_email"], msg["subject"], msg["body"])
    return (
        service_client()
        .table("messages")
        .update(
            {
                "status": "sent",
                "provider_id": provider_id,
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "sent_by": user.user_id,
            }
        )
        .eq("id", message_id)
        .eq("organization_id", user.organization_id)
        .execute()
        .data[0]
    )


@router.post("/messages/{message_id}/discard")
def discard_message(message_id: str, user: CurrentUser = Depends(require_org)):
    msg = _get_message_or_404(message_id, user.organization_id)
    if msg["status"] != "draft":
        raise HTTPException(status_code=409, detail="Only drafts can be discarded")
    return (
        service_client()
        .table("messages")
        .update({"status": "discarded"})
        .eq("id", message_id)
        .eq("organization_id", user.organization_id)
        .execute()
        .data[0]
    )


@router.post("/messages/{message_id}/mark-responded")
def mark_responded(message_id: str, user: CurrentUser = Depends(require_org)):
    _get_message_or_404(message_id, user.organization_id)
    return (
        service_client()
        .table("messages")
        .update({"responded_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", message_id)
        .eq("organization_id", user.organization_id)
        .execute()
        .data[0]
    )


@router.get("/messages/{message_id}/delivery")
def delivery_status(message_id: str, user: CurrentUser = Depends(require_org)):
    msg = _get_message_or_404(message_id, user.organization_id)
    if not msg.get("provider_id"):
        raise HTTPException(status_code=400, detail="Message has not been sent")
    data = get_email_status(msg["provider_id"])
    return {"provider_status": data.get("last_event"), "provider": data}
