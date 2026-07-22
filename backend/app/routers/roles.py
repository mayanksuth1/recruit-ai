from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUser, require_org
from ..db import service_client
from ..services.scoring import generate_boolean_search

router = APIRouter(prefix="/api/roles", tags=["roles"])


class RoleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""


class RoleUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None


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
