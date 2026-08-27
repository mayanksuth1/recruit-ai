"""Fixed-window rate limiting for the unauthenticated surface.

Every other endpoint is behind a verified Supabase JWT, so abuse there is
attributable and bounded by the account. These are not: they are reachable by
anyone holding a link, or by anyone at all. Two of them cost real money per
call because they run a model, and one of them creates accounts.

Deliberately in-process and dependency-free. The counters live in this
worker's memory, which means:

  * A multi-instance or multi-worker deployment gets one bucket PER worker, so
    the effective limit is (limit x workers). That is fine for the single
    free-plan instance this ships on, and still a useful ceiling if it grows —
    but if you scale out and need exact limits, move the counters to Postgres
    or Redis. Do not silently assume these numbers hold across replicas.
  * Counters reset on deploy. Acceptable: the window is minutes.

Not a security boundary — it is a cost and nuisance ceiling. The real
authorisation checks are the unguessable token and the HMAC signature.
"""
import time
from collections import defaultdict

from fastapi import HTTPException, Request

# (bucket, key) -> (window_started_at, count)
_hits: dict[tuple[str, str], tuple[float, int]] = defaultdict(lambda: (0.0, 0))
_last_sweep = 0.0


def client_ip(request: Request) -> str:
    """The caller's address as seen past the platform proxy.

    Render and Netlify both terminate TLS and forward, so request.client.host
    is the proxy, not the caller — every request would share one bucket. The
    left-most X-Forwarded-For entry is the original client. It is spoofable by
    the caller, which is precisely why this is a cost ceiling and not an
    authorisation check.
    """
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        first = fwd.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def _sweep(now: float) -> None:
    """Drop windows that have long expired so the dict cannot grow forever.

    Without this, one bucket entry per attacker IP is a slow memory leak on a
    public endpoint.
    """
    global _last_sweep
    if now - _last_sweep < 300:
        return
    _last_sweep = now
    stale = [k for k, (started, _) in _hits.items() if now - started > 3600]
    for k in stale:
        del _hits[k]


def hit(bucket: str, key: str, *, limit: int, window_seconds: int) -> None:
    """Count one call. Raises 429 once `limit` is exceeded inside the window."""
    now = time.monotonic()
    _sweep(now)
    started, count = _hits[(bucket, key)]

    if now - started >= window_seconds:
        _hits[(bucket, key)] = (now, 1)
        return

    if count >= limit:
        retry_after = max(1, int(window_seconds - (now - started)))
        raise HTTPException(
            status_code=429,
            detail="Too many requests — slow down and try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )

    _hits[(bucket, key)] = (started, count + 1)


def limiter(bucket: str, *, limit: int, window_seconds: int):
    """FastAPI dependency that rate-limits a route by caller IP."""

    def _dep(request: Request) -> None:
        hit(bucket, client_ip(request), limit=limit, window_seconds=window_seconds)

    return _dep
