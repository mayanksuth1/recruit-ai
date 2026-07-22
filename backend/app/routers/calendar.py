from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from ..auth import CurrentUser, require_org
from ..config import settings
from ..db import service_client
from ..services import google_calendar as gcal

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("/connection")
def connection_status(user: CurrentUser = Depends(require_org)):
    conn = gcal.get_fresh_connection(user.user_id)
    if not conn:
        return {"connected": False}
    return {"connected": True, "google_email": conn.get("google_email")}


@router.get("/oauth/start")
def oauth_start(user: CurrentUser = Depends(require_org)):
    return {"url": gcal.create_consent_url(user.user_id, user.organization_id)}


@router.get("/oauth/callback")
def oauth_callback(state: str = "", code: str = "", error: str = ""):
    """Google redirects the recruiter's browser here. No bearer token —
    identity comes from the one-time state nonce created at /oauth/start."""
    if error or not code:
        return RedirectResponse(f"{settings.frontend_url}/settings?calendar=error&reason={error or 'no_code'}")
    st = gcal.consume_state(state)
    if not st:
        return RedirectResponse(f"{settings.frontend_url}/settings?calendar=error&reason=bad_state")
    tokens = gcal.exchange_code(code)
    gcal.save_connection(st["user_id"], st["organization_id"], tokens)
    return RedirectResponse(f"{settings.frontend_url}/settings?calendar=connected")


@router.delete("/connection")
def disconnect(user: CurrentUser = Depends(require_org)):
    service_client().table("calendar_connections").delete().eq("user_id", user.user_id).execute()
    return {"connected": False}
