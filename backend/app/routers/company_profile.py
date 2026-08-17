"""Company profile: the org-level context the LinkedIn post generator writes from.

One row per organization (see 0010). GET creates the empty row on first read so
the frontend always has a shape to bind a form to, matching how
/api/ats/connection behaves.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth import CurrentUser, require_org
from ..db import service_client

router = APIRouter(prefix="/api/company-profile", tags=["company-profile"])

FIELDS = ("company_name", "what_we_do", "culture_benefits", "location", "extra_notes")


class CompanyProfileUpdate(BaseModel):
    company_name: str = Field(default="", max_length=300)
    what_we_do: str = Field(default="", max_length=5000)
    culture_benefits: str = Field(default="", max_length=5000)
    location: str = Field(default="", max_length=300)
    extra_notes: str = Field(default="", max_length=5000)


def get_or_create(organization_id: str) -> dict:
    """Used by the post generator too — a role can be posted about before the
    profile has ever been opened in Settings."""
    db = service_client()
    rows = (
        db.table("company_profile")
        .select("*")
        .eq("organization_id", organization_id)
        .execute()
        .data
    )
    if rows:
        return rows[0]
    return (
        db.table("company_profile")
        .insert({"organization_id": organization_id})
        .execute()
        .data[0]
    )


def _public(row: dict) -> dict:
    return {f: row.get(f) or "" for f in FIELDS} | {"updated_at": row.get("updated_at")}


@router.get("")
def get_company_profile(user: CurrentUser = Depends(require_org)):
    return _public(get_or_create(user.organization_id))


@router.put("")
def update_company_profile(
    body: CompanyProfileUpdate, user: CurrentUser = Depends(require_org)
):
    existing = get_or_create(user.organization_id)
    updates = body.model_dump() | {"updated_at": "now()"}
    row = (
        service_client()
        .table("company_profile")
        .update(updates)
        .eq("id", existing["id"])
        .eq("organization_id", user.organization_id)
        .execute()
        .data[0]
    )
    return _public(row)
