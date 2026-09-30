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


_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def client_ip(request: Request) -> str:
    """The caller's address as seen past whichever proxy delivered the request.

    Only a header written by a proxy WE run is believed; anything the caller
    could have typed themselves is not, or one script rotating a fake header
    would get a fresh bucket per request and walk straight past every limit
    (signup included).

      * Self-hosted: cloudflared connects from this machine, and Cloudflare's
        edge overwrites CF-Connecting-IP with the real client. Trusted only
        when the socket peer is loopback, i.e. the request came through the
        tunnel rather than from someone setting the header directly.
      * Tailscale Funnel: tailscaled also connects from loopback. It marks
        funnel traffic with Tailscale-Funnel-Request and writes the client
        address into X-Forwarded-For, so the right-most entry is the one it
        vouches for. Checked FIRST: a funnel caller can send their own
        CF-Connecting-IP, and nothing on that path would overwrite it.
      * Render: its proxy APPENDS the connecting address to X-Forwarded-For,
        so the right-most entry is the one it vouches for. The left-most entry
        is whatever the caller sent — the old code trusted exactly that one.
      * Otherwise: the socket peer.
    """
    peer = request.client.host if request.client else "unknown"
    if peer in _LOOPBACK:
        if request.headers.get("tailscale-funnel-request"):
            last = (request.headers.get("x-forwarded-for") or "").split(",")[-1].strip()
            return last or peer
        cf = request.headers.get("cf-connecting-ip", "").strip()
        if cf:
            return cf
    fwd = request.headers.get("x-forwarded-for")
    if fwd and peer not in _LOOPBACK:
        last = fwd.split(",")[-1].strip()
        if last:
            return last
    return peer


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
        if count == limit:
            # First refusal in this window: one alert for the admin view,
            # not one per blocked request. The caller's IP is not stored.
            from .services import activity
            activity.log("security.rate_limited", meta={"bucket": bucket})
            _hits[(bucket, key)] = (started, count + 1)
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
