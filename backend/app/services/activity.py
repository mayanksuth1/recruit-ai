"""The platform activity log behind the admin dashboard.

What is recorded, and why it is safe to record:

  * WHICH action happened (the route template, e.g.
    "POST /api/roles/{role_id}/linkedin-post"), WHO did it (user id), in
    WHICH workspace, WHEN, and whether it succeeded.
  * Never a request or response body, never a candidate's name, email or
    resume, never an IP address. The route template carries ids only as
    placeholders, so even a candidate id does not end up in the log.

That keeps the log to what running the service needs (support, abuse
detection, product analytics) and nothing a workspace's candidates would
have to worry about. Entries older than settings.activity_retention_days are
folded into permanent daily totals (activity_daily, no user ids) and then
deleted, in one transaction, by the scheduler loop (storage limitation).
"""
import logging
from datetime import datetime, timedelta, timezone

from ..config import settings
from ..db import service_client

logger = logging.getLogger("uvicorn.error")

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def log(action: str, *, org_id: str | None = None, user_id: str | None = None,
        status: int | None = None, meta: dict | None = None) -> None:
    """Record one entry. Never raises: losing a log line must not fail the
    request that caused it."""
    try:
        service_client().table("activity_log").insert({
            "action": action[:300],
            "organization_id": org_id,
            "user_id": user_id,
            "status": status,
            "meta": meta or {},
        }).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("activity log write failed for %s: %s", action, exc)


def log_request(method: str, route_path: str | None, status: int, actor) -> None:
    """Called by the HTTP middleware for every successful state change."""
    if method not in _MUTATING or not route_path or not route_path.startswith("/api/"):
        return
    if route_path.startswith("/api/admin"):
        return  # admin views are logged explicitly, with what was viewed
    if not (200 <= status < 400):
        return
    org_id, user_id = (actor.organization_id, actor.user_id) if actor else (None, None)
    log(f"{method} {route_path}", org_id=org_id, user_id=user_id, status=status)


def purge_expired() -> int:
    """Fold expired entries into activity_daily, then delete them (0015)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.activity_retention_days)
    try:
        return service_client().rpc(
            "activity_rollup_and_purge", {"p_before": cutoff.isoformat()}
        ).execute().data or 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("activity log purge failed: %s", exc)
        return 0
