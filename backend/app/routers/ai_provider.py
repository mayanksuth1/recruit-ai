"""Settings → AI provider: connect the workspace's own model provider.

Only the workspace owner may view the connection details or change them; any
member can see which provider is in use and how much of the free allowance is
left. The API key is write-only: it is never returned, only its last four
characters.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUser, require_org
from ..config import settings
from ..db import service_client
from ..ratelimit import limiter
from ..services import ai_provider
from ..services.ai_provider import PROVIDERS, Target
from ..services.scoring import list_models, test_target

router = APIRouter(prefix="/api/ai-provider", tags=["ai-provider"])

# Test and model-list calls go out to third parties with a key the caller
# typed, so they are the part worth limiting.
_outbound_limit = Depends(limiter("ai_provider_outbound", limit=20, window_seconds=300))


def _is_owner(user: CurrentUser) -> bool:
    rows = (
        service_client().table("organization_members").select("member_role")
        .eq("organization_id", user.organization_id).eq("user_id", user.user_id)
        .execute().data
    )
    return bool(rows) and rows[0]["member_role"] == "owner"


def _require_owner(user: CurrentUser) -> None:
    if not _is_owner(user):
        raise HTTPException(status_code=403, detail="Only the workspace owner can change the AI provider.")


def _state(user: CurrentUser) -> dict:
    row = ai_provider.load_row(user.organization_id)
    owner = _is_owner(user)
    config = None
    if row:
        config = {
            "provider": row["provider"],
            "label": PROVIDERS.get(row["provider"], {}).get("label", row["provider"]),
            "model": row["model"],
            "quality_model": row.get("quality_model"),
            "updated_at": row["updated_at"],
        }
        if owner:
            config["base_url"] = row["base_url"]
            config["key_last4"] = row["key_last4"]
    return {
        "can_edit": owner,
        "providers": [{"id": k, **v} for k, v in PROVIDERS.items()],
        "config": config,
        "usage": {
            "using_free_allowance": row is None,
            "used": ai_provider.usage_this_month(user.organization_id),
            "limit": settings.platform_ai_monthly_limit,
        },
    }


@router.get("")
def get_provider(user: CurrentUser = Depends(require_org)):
    return _state(user)


class ProviderBody(BaseModel):
    provider: str = Field(max_length=40)
    base_url: str | None = Field(default=None, max_length=500)
    # Omitted = keep the saved key (only allowed when the endpoint is unchanged).
    api_key: str | None = Field(default=None, max_length=1000)
    model: str = Field(min_length=1, max_length=200)
    quality_model: str | None = Field(default=None, max_length=200)


class ModelsBody(BaseModel):
    provider: str = Field(max_length=40)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=1000)


def _key_for(user: CurrentUser, base_url: str, typed: str | None) -> str:
    """The typed key, or the saved one when it is for this same endpoint.

    Reusing the saved key for a DIFFERENT endpoint is refused: otherwise
    changing only the URL would send the stored secret to a new host.
    """
    if typed and typed.strip():
        return typed.strip()
    row = ai_provider.load_row(user.organization_id)
    if row and row["base_url"] == base_url:
        return ai_provider.decrypt_key(row["api_key_ciphertext"])
    raise HTTPException(status_code=400, detail="Enter the API key for this provider.")


@router.post("/models", dependencies=[_outbound_limit])
def provider_models(body: ModelsBody, user: CurrentUser = Depends(require_org)):
    _require_owner(user)
    base_url = ai_provider.normalise_base_url(body.provider, body.base_url)
    key = _key_for(user, base_url, body.api_key)
    t = Target(own=True, provider=body.provider,
               label=PROVIDERS[body.provider]["label"], base_url=base_url, api_key=key,
               model="", quality_model="", fallback_model="")
    return {"models": list_models(t)}


@router.put("", dependencies=[_outbound_limit])
def save_provider(body: ProviderBody, user: CurrentUser = Depends(require_org)):
    _require_owner(user)
    base_url = ai_provider.normalise_base_url(body.provider, body.base_url)
    key = _key_for(user, base_url, body.api_key)
    model = body.model.strip()
    quality = (body.quality_model or "").strip() or None
    t = Target(own=True, provider=body.provider, label=PROVIDERS[body.provider]["label"],
               base_url=base_url, api_key=key, model=model,
               quality_model=quality or model, fallback_model=model)

    # Prove it works BEFORE saving: a broken key saved here would break every
    # AI feature in the workspace until someone noticed.
    result = test_target(t)

    service_client().table("org_ai_providers").upsert({
        "organization_id": user.organization_id,
        "provider": body.provider,
        "base_url": base_url,
        "model": model,
        "quality_model": quality,
        "api_key_ciphertext": ai_provider.encrypt_key(key),
        "key_last4": key[-4:],
        "updated_by": user.user_id,
        "updated_at": "now()",
    }).execute()
    ai_provider.invalidate(user.organization_id)
    return {**_state(user), "test": result}


@router.post("/test", dependencies=[_outbound_limit])
def test_saved(user: CurrentUser = Depends(require_org)):
    _require_owner(user)
    row = ai_provider.load_row(user.organization_id)
    if not row:
        raise HTTPException(status_code=404, detail="No AI provider is connected.")
    return test_target(ai_provider.target_from_row(row))


@router.delete("")
def remove_provider(user: CurrentUser = Depends(require_org)):
    _require_owner(user)
    service_client().table("org_ai_providers").delete().eq("organization_id", user.organization_id).execute()
    ai_provider.invalidate(user.organization_id)
    return _state(user)
