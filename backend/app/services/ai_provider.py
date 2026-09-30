"""Which model provider a given organization's AI calls go to.

Every organization can connect its own provider (OpenAI, Anthropic, Gemini,
Groq, OpenRouter, ... or any OpenAI-compatible endpoint). All of them are
reached through the OpenAI SDK, because each one exposes an OpenAI-compatible
chat-completions API; only the base URL, key and model differ.

Without its own provider, an organization runs on the platform key (NVIDIA
NIM, settings.nvidia_*) for settings.platform_ai_monthly_limit calls per
calendar month, counted atomically in ai_usage.
"""
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from ..config import settings
from ..db import service_client
from . import ats

# Preset endpoints. `key_url` is where an owner creates a key; shown in the UI.
PROVIDERS: dict[str, dict] = {
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1",
               "key_url": "https://platform.openai.com/api-keys"},
    "anthropic": {"label": "Anthropic (Claude)", "base_url": "https://api.anthropic.com/v1/",
                  "key_url": "https://console.anthropic.com/settings/keys"},
    "gemini": {"label": "Google Gemini",
               "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
               "key_url": "https://aistudio.google.com/apikey"},
    "groq": {"label": "Groq", "base_url": "https://api.groq.com/openai/v1",
             "key_url": "https://console.groq.com/keys"},
    "openrouter": {"label": "OpenRouter (hundreds of models)", "base_url": "https://openrouter.ai/api/v1",
                   "key_url": "https://openrouter.ai/keys"},
    "mistral": {"label": "Mistral", "base_url": "https://api.mistral.ai/v1",
                "key_url": "https://console.mistral.ai/api-keys"},
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com/v1",
                 "key_url": "https://platform.deepseek.com/api_keys"},
    "together": {"label": "Together AI", "base_url": "https://api.together.xyz/v1",
                 "key_url": "https://api.together.xyz/settings/api-keys"},
    "xai": {"label": "xAI (Grok)", "base_url": "https://api.x.ai/v1",
            "key_url": "https://console.x.ai"},
    "nvidia": {"label": "NVIDIA NIM", "base_url": "https://integrate.api.nvidia.com/v1",
               "key_url": "https://build.nvidia.com"},
    "custom": {"label": "Other (OpenAI-compatible URL)", "base_url": "", "key_url": ""},
}


@dataclass(frozen=True)
class Target:
    """Everything needed to make one call. `own` is False on the platform key."""
    own: bool
    provider: str
    label: str
    base_url: str
    api_key: str
    model: str
    quality_model: str
    fallback_model: str


# --------------------------------------------------------------------------
# Encryption

def _fernet() -> Fernet:
    if not settings.ai_keys_encryption_key:
        raise HTTPException(
            status_code=503,
            detail="This server cannot store API keys yet (AI_KEYS_ENCRYPTION_KEY is not set).",
        )
    return Fernet(settings.ai_keys_encryption_key.encode())


def encrypt_key(raw: str) -> str:
    return _fernet().encrypt(raw.encode()).decode()


def decrypt_key(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise HTTPException(
            status_code=400,
            detail="The saved AI provider key can no longer be read. Re-enter it in Settings → AI provider.",
        )


# --------------------------------------------------------------------------
# Validation

def normalise_base_url(provider: str, base_url: str | None) -> str:
    """The preset URL for a known provider; a checked public HTTPS URL for custom.

    A custom URL is fetched by this server with the org's key, so it gets the
    same SSRF treatment as ATS webhooks: public internet addresses only.
    Otherwise any workspace could aim it at the local database gateway.
    """
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Unknown AI provider")
    if provider != "custom":
        return PROVIDERS[provider]["base_url"]
    url = (base_url or "").strip()
    if not url.lower().startswith("https://"):
        raise HTTPException(status_code=400, detail="A custom provider URL must start with https://")
    try:
        return ats.check_outbound_url(url)
    except ats.UnsafeURL as e:
        raise HTTPException(status_code=400, detail=str(e).replace("Webhook", "Provider"))


# --------------------------------------------------------------------------
# Resolution

_cache: dict[str, tuple[float, dict | None]] = {}
_CACHE_TTL = 30.0


def load_row(org_id: str) -> dict | None:
    now = time.monotonic()
    hit = _cache.get(org_id)
    if hit and hit[0] > now:
        return hit[1]
    rows = (
        service_client().table("org_ai_providers").select("*")
        .eq("organization_id", org_id).execute().data
    )
    row = rows[0] if rows else None
    _cache[org_id] = (now + _CACHE_TTL, row)
    return row


def invalidate(org_id: str) -> None:
    _cache.pop(org_id, None)


def platform_target() -> Target:
    if not settings.nvidia_api_key:
        raise HTTPException(
            status_code=402,
            detail="No AI provider is connected. Add your own API key in Settings → AI provider.",
        )
    return Target(
        own=False, provider="platform", label="Recruit AI free allowance",
        base_url=settings.nvidia_base_url, api_key=settings.nvidia_api_key,
        model=settings.nvidia_model, quality_model=settings.nvidia_quality_model,
        fallback_model=settings.nvidia_fallback_model,
    )


def target_from_row(row: dict) -> Target:
    base_url = row["base_url"]
    if row["provider"] == "custom":
        # Re-checked at use, not just at save: DNS can change in between.
        base_url = normalise_base_url("custom", base_url)
    return Target(
        own=True, provider=row["provider"],
        label=PROVIDERS.get(row["provider"], {}).get("label", row["provider"]),
        base_url=base_url, api_key=decrypt_key(row["api_key_ciphertext"]),
        model=row["model"], quality_model=row.get("quality_model") or row["model"],
        fallback_model=row["model"],
    )


def resolve(org_id: str | None) -> Target:
    """The target for this organization's next call (no metering here)."""
    row = load_row(org_id) if org_id else None
    return target_from_row(row) if row else platform_target()


# --------------------------------------------------------------------------
# Free allowance

def _month_start() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1).date().isoformat()


def usage_this_month(org_id: str) -> int:
    rows = (
        service_client().table("ai_usage").select("platform_calls")
        .eq("organization_id", org_id).eq("month", _month_start()).execute().data
    )
    return rows[0]["platform_calls"] if rows else 0


def meter_platform_call(org_id: str | None, *, candidate_facing: bool) -> None:
    """Count one platform-key call and refuse it once the allowance is spent.

    Candidate-facing calls (the AI interview a candidate is sitting in) are
    counted but never refused: a candidate should not hit an error halfway
    through because the recruiter's workspace ran out of free calls.
    """
    if not org_id:
        return
    used = service_client().rpc(
        "ai_usage_bump", {"p_org": org_id, "p_month": _month_start()}
    ).execute().data
    limit = settings.platform_ai_monthly_limit
    if not candidate_facing and isinstance(used, int) and used > limit:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Your workspace has used its {limit} free AI calls this month. "
                "Add your own AI provider key in Settings → AI provider to keep going "
                "(OpenAI, Claude, Gemini, Groq and others are supported)."
            ),
        )
