"""Platform admin dashboard: what workspaces do, never what they contain.

Access: the caller's auth user id must be in PLATFORM_ADMIN_USER_IDS. Every
other caller gets 404, so the admin area does not advertise that it exists.

Scope (deliberate, and enforced here and in the SQL functions of 0014):
account fields (emails of *users*, signup and sign-in times), workspace
names, counts, action labels and security events. Nothing in this router
reads a candidate's name, email, phone, resume, a message body, a job
description or an interview transcript. Opening a workspace is itself
written to the activity log, so admin access is accountable.
"""
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import CurrentUser, get_current_user
from ..config import settings
from ..db import service_client
from ..services import activity

router = APIRouter(tags=["admin"])


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.user_id not in settings.admin_ids:
        raise HTTPException(status_code=404, detail="Not Found")
    return user


# --------------------------------------------------------------------------
# helpers

_users_cache: tuple[float, list[dict]] = (0.0, [])


def _auth_users() -> list[dict]:
    """Account-level fields for every login, via the Auth admin API."""
    global _users_cache
    if _users_cache[0] > time.monotonic():
        return _users_cache[1]
    out, page = [], 1
    headers = {"apikey": settings.supabase_secret_key,
               "Authorization": f"Bearer {settings.supabase_secret_key}"}
    while True:
        r = httpx.get(f"{settings.supabase_url}/auth/v1/admin/users",
                      params={"page": page, "per_page": 1000}, headers=headers, timeout=20)
        r.raise_for_status()
        batch = r.json().get("users", [])
        for u in batch:
            out.append({
                "id": u["id"],
                "email": u.get("email"),
                "created_at": u.get("created_at"),
                "last_sign_in_at": u.get("last_sign_in_at"),
                "providers": sorted({i.get("provider") for i in (u.get("identities") or []) if i.get("provider")}),
            })
        if len(batch) < 1000:
            break
        page += 1
    _users_cache = (time.monotonic() + 60, out)
    return out


def _stats() -> list[dict]:
    return service_client().rpc("admin_workspace_stats", {}).execute().data or []


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _feed(rows: list[dict]) -> list[dict]:
    emails = {u["id"]: u["email"] for u in _auth_users()}
    orgs = {o["id"]: o["name"] for o in service_client().table("organizations").select("id, name").execute().data}
    return [{
        "id": r["id"],
        "at": r["created_at"],
        "action": r["action"],
        "status": r.get("status"),
        "workspace_id": r.get("organization_id"),
        "workspace": orgs.get(r.get("organization_id")),
        "user": emails.get(r.get("user_id")),
        "meta": r.get("meta") or {},
    } for r in rows]


# --------------------------------------------------------------------------
# routes

@router.get("/api/admin/me")
def admin_me(user: CurrentUser = Depends(require_admin)):
    return {"admin": True, "email": user.email}


@router.get("/api/admin/overview")
def overview(user: CurrentUser = Depends(require_admin)):
    db = service_client()
    stats = _stats()
    users = _auth_users()
    recent = (db.table("activity_log").select("created_at, organization_id, user_id, action")
              .gte("created_at", _since(30)).limit(50000).execute().data)
    week = _since(7)
    today = datetime.now(timezone.utc).date().isoformat()

    # 30-day series: detailed rows where they still exist, daily totals beyond.
    events_by_day = Counter(r["created_at"][:10] for r in recent)
    for d in (db.table("activity_daily").select("day, events").gte("day", _since(30)[:10]).execute().data):
        events_by_day[d["day"]] += d["events"]
    signups_by_day = Counter((u["created_at"] or "")[:10] for u in users)
    days = [(datetime.now(timezone.utc).date() - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]

    return {
        "users": len(users),
        "workspaces": len(stats),
        "signups_7d": sum(1 for u in users if (u["created_at"] or "") >= week),
        "active_workspaces_7d": len({r["organization_id"] for r in recent
                                     if r["organization_id"] and r["created_at"] >= week}),
        "actions_today": sum(1 for r in recent if r["created_at"][:10] == today),
        "ai_calls_this_month": sum(s["ai_calls_this_month"] or 0 for s in stats),
        "own_key_workspaces": sum(1 for s in stats if s["own_ai_provider"]),
        "candidates_total": sum(s["candidates"] or 0 for s in stats),
        "resumes_scored_total": sum(s["resumes_scored"] or 0 for s in stats),
        "emails_sent_total": sum(s["messages_sent"] or 0 for s in stats),
        "free_limit": settings.platform_ai_monthly_limit,
        "series": [{"day": d, "actions": events_by_day.get(d, 0), "signups": signups_by_day.get(d, 0)}
                   for d in days],
    }


@router.get("/api/admin/workspaces")
def workspaces(user: CurrentUser = Depends(require_admin)):
    return _stats()


@router.get("/api/admin/workspaces/{org_id}")
def workspace_detail(org_id: str, user: CurrentUser = Depends(require_admin)):
    row = next((s for s in _stats() if s["organization_id"] == org_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Workspace not found")
    db = service_client()
    members = db.table("organization_members").select("user_id, member_role, created_at") \
        .eq("organization_id", org_id).execute().data
    by_id = {u["id"]: u for u in _auth_users()}
    feed = (db.table("activity_log").select("*").eq("organization_id", org_id)
            .order("created_at", desc=True).limit(200).execute().data)
    history = (db.table("activity_daily").select("day, action, events, users")
               .eq("organization_id", org_id).order("day", desc=True).limit(365).execute().data)
    activity.log("admin.viewed_workspace", user_id=user.user_id, meta={"workspace_id": org_id})
    return {
        "workspace": row,
        "members": [{
            "email": by_id.get(m["user_id"], {}).get("email"),
            "role": m["member_role"],
            "joined": m["created_at"],
            "last_sign_in_at": by_id.get(m["user_id"], {}).get("last_sign_in_at"),
            "providers": by_id.get(m["user_id"], {}).get("providers", []),
        } for m in members],
        "activity": _feed(feed),
        "history": history,
    }


@router.get("/api/admin/activity")
def activity_feed(
    workspace_id: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    user: CurrentUser = Depends(require_admin),
):
    q = service_client().table("activity_log").select("*").order("created_at", desc=True).limit(limit)
    if workspace_id:
        q = q.eq("organization_id", workspace_id)
    return _feed(q.execute().data)


@router.get("/api/admin/users")
def users(user: CurrentUser = Depends(require_admin)):
    db = service_client()
    members = db.table("organization_members").select("user_id, organization_id, member_role").execute().data
    orgs = {o["id"]: o["name"] for o in db.table("organizations").select("id, name").execute().data}
    by_user = {m["user_id"]: m for m in members}
    return [{
        **u,
        "workspace": orgs.get(by_user.get(u["id"], {}).get("organization_id")),
        "workspace_id": by_user.get(u["id"], {}).get("organization_id"),
        "role": by_user.get(u["id"], {}).get("member_role"),
    } for u in sorted(_auth_users(), key=lambda u: u["created_at"] or "", reverse=True)]


@router.get("/api/admin/signins")
def signins(limit: int = Query(default=200, ge=1, le=1000), user: CurrentUser = Depends(require_admin)):
    return service_client().rpc("admin_auth_events", {"p_limit": limit}).execute().data or []


@router.get("/api/admin/alerts")
def alerts(user: CurrentUser = Depends(require_admin)):
    db = service_client()
    stats = _stats()
    day = _since(1)
    security = (db.table("activity_log").select("action, meta, created_at")
                .in_("action", ["auth.failed_login", "security.rate_limited"])
                .gte("created_at", day).limit(10000).execute().data)
    failed = Counter((r["meta"] or {}).get("email") or "(no email)"
                     for r in security if r["action"] == "auth.failed_login")
    blocked = Counter((r["meta"] or {}).get("bucket") or "?"
                      for r in security if r["action"] == "security.rate_limited")
    limit = settings.platform_ai_monthly_limit
    two_days_ago = _since(2)
    return {
        "hit_free_limit": [
            {"workspace_id": s["organization_id"], "workspace": s["name"], "owner_email": s["owner_email"],
             "ai_calls_this_month": s["ai_calls_this_month"]}
            for s in stats if not s["own_ai_provider"] and (s["ai_calls_this_month"] or 0) >= limit
        ],
        "near_free_limit": [
            {"workspace_id": s["organization_id"], "workspace": s["name"], "owner_email": s["owner_email"],
             "ai_calls_this_month": s["ai_calls_this_month"]}
            for s in stats if not s["own_ai_provider"] and limit * 0.8 <= (s["ai_calls_this_month"] or 0) < limit
        ],
        "failed_logins_24h": [{"email": e, "attempts": n} for e, n in failed.most_common() if n >= 3],
        "rate_limited_24h": [{"bucket": b, "times": n} for b, n in blocked.most_common()],
        "dormant_signups": [
            {"workspace_id": s["organization_id"], "workspace": s["name"], "owner_email": s["owner_email"],
             "signed_up": s["created_at"]}
            for s in stats
            if s["created_at"] < two_days_ago and not s["roles_total"] and not s["candidates"]
        ],
    }


@router.get("/api/public/legal")
def legal():
    """Facts the public privacy page states, from the running configuration."""
    return {
        "contact_email": settings.privacy_contact_email or None,
        "activity_retention_days": settings.activity_retention_days,
        "free_ai_calls_per_month": settings.platform_ai_monthly_limit,
    }
