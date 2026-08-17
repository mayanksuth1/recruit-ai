from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUser, require_org
from ..db import service_client
from ..services.linkedin_post import generate_linkedin_post
from ..services.scoring import generate_boolean_search
from .company_profile import get_or_create as get_company_profile_row

router = APIRouter(prefix="/api/roles", tags=["roles"])


class RoleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""


class RoleUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None


class LinkedInDraftUpdate(BaseModel):
    linkedin_post_draft: str = Field(default="", max_length=20000)


@router.get("")
def list_roles(user: CurrentUser = Depends(require_org)):
    return (
        service_client()
        .table("roles")
        .select("*")
        .eq("organization_id", user.organization_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )


@router.post("", status_code=201)
def create_role(body: RoleCreate, user: CurrentUser = Depends(require_org)):
    return (
        service_client()
        .table("roles")
        .insert(
            {
                "organization_id": user.organization_id,
                "title": body.title,
                "description": body.description,
                "created_by": user.user_id,
            }
        )
        .execute()
        .data[0]
    )


@router.get("/{role_id}")
def get_role(role_id: str, user: CurrentUser = Depends(require_org)):
    res = (
        service_client()
        .table("roles")
        .select("*")
        .eq("id", role_id)
        .eq("organization_id", user.organization_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Role not found")
    return res.data[0]


@router.post("/{role_id}/boolean-search")
def boolean_search(role_id: str, user: CurrentUser = Depends(require_org)):
    """Generate LinkedIn / Google X-ray Boolean search strings from the JD."""
    role = get_role(role_id, user)
    if not role["description"].strip():
        raise HTTPException(status_code=400, detail="Role has no job description")
    return generate_boolean_search(role["description"])


@router.post("/{role_id}/linkedin-post")
def generate_post(role_id: str, user: CurrentUser = Depends(require_org)):
    """Generate (or regenerate) the LinkedIn post draft for this role.

    Draft only — the text is stored and returned for the user to copy. Nothing
    is published anywhere.
    """
    role = get_role(role_id, user)
    if not role["description"].strip():
        raise HTTPException(status_code=400, detail="Role has no job description")

    profile = get_company_profile_row(user.organization_id)
    if not any((profile.get(f) or "").strip() for f in ("company_name", "what_we_do")):
        raise HTTPException(
            status_code=400,
            detail="Fill in the company profile in Settings first — the post is written from it.",
        )

    post, model = generate_linkedin_post(profile, role["title"], role["description"])
    return _save_draft(role_id, user, post, model=model)


@router.put("/{role_id}/linkedin-post")
def save_post(
    role_id: str, body: LinkedInDraftUpdate, user: CurrentUser = Depends(require_org)
):
    """Persist the user's edits to the draft. Editing does not re-run the model,
    so the recorded model/timestamp stay pointed at the generation that produced it."""
    get_role(role_id, user)  # 404s if the role is not the caller's
    return _save_draft(role_id, user, body.linkedin_post_draft)


def _save_draft(role_id: str, user: CurrentUser, draft: str, model: str | None = None):
    updates: dict = {"linkedin_post_draft": draft}
    if model is not None:
        updates["linkedin_post_model"] = model
        updates["linkedin_post_generated_at"] = "now()"
    row = (
        service_client()
        .table("roles")
        .update(updates)
        .eq("id", role_id)
        .eq("organization_id", user.organization_id)
        .execute()
        .data[0]
    )
    return {
        "linkedin_post_draft": row.get("linkedin_post_draft") or "",
        "linkedin_post_model": row.get("linkedin_post_model"),
        "linkedin_post_generated_at": row.get("linkedin_post_generated_at"),
    }


@router.patch("/{role_id}")
def update_role(role_id: str, body: RoleUpdate, user: CurrentUser = Depends(require_org)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    res = (
        service_client()
        .table("roles")
        .update(updates)
        .eq("id", role_id)
        .eq("organization_id", user.organization_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Role not found")
    return res.data[0]
