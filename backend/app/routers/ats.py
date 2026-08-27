"""ATS sync endpoints: org connection config, event log, inbound webhook.

Inbound contract (the ATS POSTs to /api/webhooks/ats/{inbound_token}):
  {"event": "candidate.stage_changed", "candidate_email": "...", "stage": "interview"}
Auth: the unguessable per-org token in the URL, plus HMAC signature
(X-RecruitAI-Signature) when a shared secret is configured.

Approval gate 2 applies to inbound events too: a remote system cannot move a
candidate to 'offer' or 'closed' unless a human approved it here first.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth import CurrentUser, require_org
from ..db import service_client
from ..ratelimit import limiter
from ..services import ats
from ..services.email import send_email  # noqa: F401  (imported for future use)

router = APIRouter(prefix="/api", tags=["ats"])

STAGES = ("screening", "outreach", "interview", "offer", "closed")
GATED_STAGES = ("offer", "closed")


class ConnectionUpdate(BaseModel):
    outbound_url: str | None = None
    secret: str | None = None
    active: bool = True


@router.get("/ats/connection")
def get_connection(user: CurrentUser = Depends(require_org)):
    db = service_client()
    rows = db.table("ats_connections").select("*").eq("organization_id", user.organization_id).execute().data
    if not rows:
        rows = [db.table("ats_connections").insert({"organization_id": user.organization_id}).execute().data[0]]
    conn = rows[0]
    return {
        "outbound_url": conn.get("outbound_url"),
        "has_secret": bool(conn.get("secret")),
        "active": conn["active"],
        "inbound_webhook_path": f"/api/webhooks/ats/{conn['inbound_token']}",
    }


@router.put("/ats/connection")
def update_connection(body: ConnectionUpdate, user: CurrentUser = Depends(require_org)):
    db = service_client()
    rows = db.table("ats_connections").select("id").eq("organization_id", user.organization_id).execute().data
    updates = {"outbound_url": body.outbound_url, "active": body.active}
    if body.secret is not None:
        updates["secret"] = body.secret or None
    if rows:
        db.table("ats_connections").update(updates).eq("id", rows[0]["id"]).execute()
    else:
        db.table("ats_connections").insert({"organization_id": user.organization_id, **updates}).execute()
    return get_connection(user)


@router.get("/ats/events")
def list_events(user: CurrentUser = Depends(require_org)):
    return (
        service_client().table("ats_events").select("*")
        .eq("organization_id", user.organization_id)
        .order("created_at", desc=True).limit(100)
        .execute().data
    )


@router.post("/ats/test-outbound")
def test_outbound(user: CurrentUser = Depends(require_org)):
    conn = ats.get_connection(user.organization_id)
    if not conn or not conn.get("outbound_url"):
        raise HTTPException(status_code=409, detail="Set an outbound URL first")
    ats.send_outbound(user.organization_id, "connection.test", {"message": "hello from Recruit AI"})
    return {"sent": True}


class InboundEvent(BaseModel):
    event: str
    candidate_email: str | None = None
    candidate_id: str | None = None
    stage: str | None = None


# The HMAC check below is the real gate; this only stops an unsigned
# flood from costing us the verification work on every request.
@router.post("/webhooks/ats/{inbound_token}",
             dependencies=[Depends(limiter("ats_inbound", limit=300, window_seconds=60))])
async def inbound_webhook(inbound_token: str, request: Request):
    db = service_client()
    rows = db.table("ats_connections").select("*").eq("inbound_token", inbound_token).eq("active", True).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Unknown webhook token")
    conn = rows[0]
    org_id = conn["organization_id"]

    raw = await request.body()
    if not ats.verify_signature(conn.get("secret") or "", raw, request.headers.get("X-RecruitAI-Signature")):
        ats.log_event(org_id, "inbound", "unknown", {}, "rejected", "bad signature", conn["id"])
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        event = InboundEvent.model_validate_json(raw)
    except Exception as e:
        ats.log_event(org_id, "inbound", "unknown", {}, "rejected", f"bad payload: {e}", conn["id"])
        raise HTTPException(status_code=400, detail="Invalid payload")

    payload = event.model_dump()

    if event.event != "candidate.stage_changed":
        ats.log_event(org_id, "inbound", event.event, payload, "rejected", "unsupported event type", conn["id"])
        raise HTTPException(status_code=400, detail=f"Unsupported event: {event.event}")
    if not event.stage or event.stage not in STAGES:
        ats.log_event(org_id, "inbound", event.event, payload, "rejected", "invalid stage", conn["id"])
        raise HTTPException(status_code=400, detail=f"Invalid stage; one of {STAGES}")

    q = db.table("candidates").select("*").eq("organization_id", org_id)
    if event.candidate_id:
        q = q.eq("id", event.candidate_id)
    elif event.candidate_email:
        q = q.eq("email", event.candidate_email.lower())
    else:
        ats.log_event(org_id, "inbound", event.event, payload, "rejected", "no candidate reference", conn["id"])
        raise HTTPException(status_code=400, detail="Provide candidate_id or candidate_email")
    cands = q.execute().data
    if not cands:
        ats.log_event(org_id, "inbound", event.event, payload, "rejected", "candidate not found", conn["id"])
        raise HTTPException(status_code=404, detail="Candidate not found")
    cand = cands[0]

    # ------- HUMAN APPROVAL GATE 2 (applies to remote systems too) -------
    if event.stage in GATED_STAGES and not cand.get("offer_approved_at"):
        ats.log_event(org_id, "inbound", event.event, payload, "rejected",
                      "offer/closure requires human approval in Recruit AI", conn["id"], cand["id"])
        raise HTTPException(
            status_code=409,
            detail="Stage requires offer approval by a recruiter in Recruit AI first (gate 2)",
        )

    db.table("candidates").update({"stage": event.stage}).eq("id", cand["id"]).execute()
    ats.log_event(org_id, "inbound", event.event, payload, "applied",
                  f"stage -> {event.stage}", conn["id"], cand["id"])
    return {"applied": True, "candidate_id": cand["id"], "stage": event.stage}
