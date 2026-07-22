from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..auth import CurrentUser, require_org
from ..db import service_client
from ..services.pdf import extract_text
from ..services.scoring import score_pool_batch, score_resume

router = APIRouter(prefix="/api", tags=["candidates"])

MAX_PDF_BYTES = 10 * 1024 * 1024


def _get_role_or_404(role_id: str, org_id: str) -> dict:
    res = (
        service_client()
        .table("roles")
        .select("*")
        .eq("id", role_id)
        .eq("organization_id", org_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Role not found")
    return res.data[0]


@router.get("/roles/{role_id}/candidates")
def list_candidates(role_id: str, user: CurrentUser = Depends(require_org)):
    _get_role_or_404(role_id, user.organization_id)
    return (
        service_client()
        .table("candidates")
        .select("*, scores(overall_score, skills_score, experience_score, education_score, rationale, model)")
        .eq("organization_id", user.organization_id)
        .eq("role_id", role_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )


@router.post("/roles/{role_id}/candidates/upload", status_code=201)
async def upload_resume(
    role_id: str,
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_org),
):
    """Upload a resume PDF: extract text, score with Gemini, store candidate + score."""
    role = _get_role_or_404(role_id, user.organization_id)
    if not role["description"].strip():
        raise HTTPException(status_code=400, detail="Role has no job description to score against")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF larger than 10 MB")
    resume_text = extract_text(pdf_bytes)

    result = score_resume(role["description"], resume_text)

    db = service_client()
    full_name = result.get("full_name") or (file.filename or "Unknown")
    email = (result.get("email") or "").lower() or None

    # Upsert the person into the org-wide talent pool so they persist across roles.
    pool_record = {
        "full_name": full_name,
        "email": email,
        "phone": result.get("phone"),
        "profile_text": resume_text,
        "source": "resume_upload",
    }
    pool_id = None
    if email:
        existing = (
            db.table("talent_pool")
            .select("id")
            .eq("organization_id", user.organization_id)
            .eq("email", email)
            .execute()
            .data
        )
        if existing:
            pool_id = existing[0]["id"]
            db.table("talent_pool").update(pool_record).eq("id", pool_id).execute()
    if pool_id is None:
        pool_record["organization_id"] = user.organization_id
        pool_id = db.table("talent_pool").insert(pool_record).execute().data[0]["id"]

    candidate = (
        db.table("candidates")
        .insert(
            {
                "organization_id": user.organization_id,
                "role_id": role_id,
                "talent_pool_id": pool_id,
                "full_name": full_name,
                "email": email,
                "phone": result.get("phone"),
                "resume_text": resume_text,
                "source": "upload",
            }
        )
        .execute()
        .data[0]
    )
    score = (
        db.table("scores")
        .insert(
            {
                "organization_id": user.organization_id,
                "candidate_id": candidate["id"],
                "role_id": role_id,
                "overall_score": result["overall_score"],
                "skills_score": result.get("skills_score"),
                "experience_score": result.get("experience_score"),
                "education_score": result.get("education_score"),
                "rationale": result.get("rationale"),
                "model": result.get("model"),
            }
        )
        .execute()
        .data[0]
    )
    return {"candidate": candidate, "score": score}


class MatchPoolRequest(BaseModel):
    limit: int = 50


@router.post("/roles/{role_id}/match-pool")
def match_pool(
    role_id: str,
    body: MatchPoolRequest | None = None,
    user: CurrentUser = Depends(require_org),
):
    """Score talent-pool entries against this role's JD and add them as
    candidates. Pool entries already attached to the role are skipped."""
    role = _get_role_or_404(role_id, user.organization_id)
    if not role["description"].strip():
        raise HTTPException(status_code=400, detail="Role has no job description to score against")
    limit = min(max((body.limit if body else 50), 1), 100)

    db = service_client()
    already = (
        db.table("candidates")
        .select("talent_pool_id")
        .eq("organization_id", user.organization_id)
        .eq("role_id", role_id)
        .not_.is_("talent_pool_id", "null")
        .execute()
        .data
    )
    already_ids = {r["talent_pool_id"] for r in already}

    pool = (
        db.table("talent_pool")
        .select("*")
        .eq("organization_id", user.organization_id)
        .order("created_at", desc=True)
        .limit(500)
        .execute()
        .data
    )
    entries = [p for p in pool if p["id"] not in already_ids][:limit]
    if not entries:
        return {"matched": 0, "skipped_existing": len(already_ids), "candidates": []}

    profiles = [
        f"Name: {e['full_name']}\n{e.get('profile_text') or ''}" for e in entries
    ]
    results = score_pool_batch(role["description"], profiles)

    created = []
    for entry, result in zip(entries, results):
        if result is None:
            continue
        candidate = (
            db.table("candidates")
            .insert(
                {
                    "organization_id": user.organization_id,
                    "role_id": role_id,
                    "talent_pool_id": entry["id"],
                    "full_name": entry["full_name"],
                    "email": entry.get("email"),
                    "phone": entry.get("phone"),
                    "resume_text": entry.get("profile_text"),
                    "source": "pool_match",
                }
            )
            .execute()
            .data[0]
        )
        db.table("scores").insert(
            {
                "organization_id": user.organization_id,
                "candidate_id": candidate["id"],
                "role_id": role_id,
                "overall_score": result["overall_score"],
                "skills_score": result.get("skills_score"),
                "experience_score": result.get("experience_score"),
                "education_score": result.get("education_score"),
                "rationale": result.get("rationale"),
                "model": result.get("model"),
            }
        ).execute()
        created.append(candidate)

    return {
        "matched": len(created),
        "unscored": len(entries) - len(created),
        "skipped_existing": len(already_ids),
        "candidates": created,
    }


class ShortlistUpdate(BaseModel):
    shortlist_status: str  # 'pending' | 'approved' | 'rejected'


class BulkShortlistUpdate(BaseModel):
    candidate_ids: list[str]
    shortlist_status: str


@router.patch("/candidates/bulk-shortlist")
def bulk_shortlist(body: BulkShortlistUpdate, user: CurrentUser = Depends(require_org)):
    if body.shortlist_status not in ("pending", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid shortlist_status")
    if not body.candidate_ids:
        raise HTTPException(status_code=400, detail="No candidate ids provided")
    if len(body.candidate_ids) > 500:
        raise HTTPException(status_code=400, detail="Too many candidates in one request")
    res = (
        service_client()
        .table("candidates")
        .update({"shortlist_status": body.shortlist_status})
        .eq("organization_id", user.organization_id)
        .in_("id", body.candidate_ids)
        .execute()
    )
    return {"updated": len(res.data)}


@router.patch("/candidates/{candidate_id}/shortlist")
def update_shortlist(
    candidate_id: str,
    body: ShortlistUpdate,
    user: CurrentUser = Depends(require_org),
):
    if body.shortlist_status not in ("pending", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid shortlist_status")
    res = (
        service_client()
        .table("candidates")
        .update({"shortlist_status": body.shortlist_status})
        .eq("id", candidate_id)
        .eq("organization_id", user.organization_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return res.data[0]
