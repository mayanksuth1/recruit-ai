from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUser, get_current_user, invalidate_org_cache, require_org
from ..db import service_client

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


class BootstrapRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=200)


@router.post("/bootstrap")
def bootstrap(body: BootstrapRequest, user: CurrentUser = Depends(get_current_user)):
    """Called once after signup: creates the org and makes the caller its owner."""
    if user.organization_id:
        raise HTTPException(status_code=409, detail="User already belongs to an organization")
    db = service_client()
    org = (
        db.table("organizations")
        .insert({"name": body.organization_name})
        .execute()
        .data[0]
    )
    db.table("organization_members").insert(
        {"organization_id": org["id"], "user_id": user.user_id, "member_role": "owner"}
    ).execute()
    invalidate_org_cache(user.user_id)
    return org


@router.get("/me")
def my_org(user: CurrentUser = Depends(require_org)):
    db = service_client()
    org = (
        db.table("organizations")
        .select("*")
        .eq("id", user.organization_id)
        .single()
        .execute()
        .data
    )
    return org
