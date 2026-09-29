"""Serve the whole product from one origin, for self-hosted deployments.

On the managed path the three pieces live apart: Netlify serves the frontend,
Render serves this API, and Supabase serves auth and data, each on its own
domain. Self-hosting has no such luxury — there is one machine and, realistically,
one public URL — so this module folds all three behind this process:

    /                -> the built frontend (SPA, client-side routing)
    /api/*           -> this app's routers, untouched
    /supabase/*      -> reverse proxy to the local Supabase stack

The proxy is the load-bearing part. The frontend's Supabase calls run in the
VISITOR's browser, and the local stack answers on 127.0.0.1, which in their
browser means their own machine. Proxying through here gives them a reachable
address without exposing the stack's port directly.

Serving everything from one origin also removes CORS from the picture entirely:
same-origin requests never preflight.

Only /supabase/auth/v1/* is forwarded (see _allowed): the gateway behind it
also serves unauthenticated superuser SQL endpoints that must never be
public. Only plain HTTP is proxied. Supabase Realtime needs WebSockets and is NOT
forwarded — the frontend uses onAuthStateChange (a local event) rather than
Postgres subscriptions, so nothing needs it today. If Realtime is ever used,
this needs a WebSocket path too.

Deliberately NOT proxied: Studio (54423) and the Postgres port. Those stay
bound to localhost, reachable only from the machine itself.
"""
import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings

logger = logging.getLogger("uvicorn.error")

# backend/app/selfhost.py -> repo root -> frontend/dist
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

# Hop-by-hop headers are per-connection and must not be forwarded: passing
# them along corrupts the response for the real client.
_STRIP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
}


def _proxy_client() -> httpx.Client:
    if not hasattr(_proxy_client, "_c"):
        _proxy_client._c = httpx.Client(base_url=settings.supabase_url.rstrip("/"), timeout=30)
    return _proxy_client._c


# supabase-js endpoints behind signInWithPassword + session refresh (token),
# signInWithOAuth (authorize, callback), resetPasswordForEmail (recover), the
# emailed link (verify), getUser/updateUser (user), signOut (logout), and the
# client's startup probes (settings, health).
_AUTH_ENDPOINTS = {
    "token", "authorize", "callback", "recover", "verify",
    "user", "logout", "settings", "health",
}


def _allowed(path: str) -> bool:
    """Allow-list, never a deny-list, for what the public may reach upstream.

    The local API gateway serves far more than auth: /pg is postgres-meta and
    /mcp is the Supabase MCP server, and on the CLI stack both run arbitrary
    SQL as the superuser with NO key at all. Forwarding every path made the
    whole database writable by anyone holding the tunnel URL.

    The browser only ever talks to Supabase Auth (every data call goes
    through this backend's /api routes), and only to the endpoints the
    frontend's supabase.auth calls use. Everything else in auth is refused,
    notably:
      * /signup — GoTrue's own signup is auto-confirmed and bypasses the
        backend's rate limit, so anyone could squat an address they do not
        own. Accounts are created through POST /api/auth/signup instead.
        (It cannot be switched off in config.toml without also disabling
        password sign-in.)
      * /otp, /magiclink, /resend, /invite — unused, and each sends mail.
      * /admin — would need the service key anyway.
    """
    parts = path.split("/")
    return len(parts) >= 3 and parts[:2] == ["auth", "v1"] and parts[2] in _AUTH_ENDPOINTS


async def _supabase_proxy(request: Request, path: str) -> Response:
    # Normalise before checking so /supabase/auth/v1/../../pg/query and
    # percent-encoded variants cannot walk out of the allowed prefix.
    path = path.lstrip("/")
    if ".." in path or "%" in path or "\\" in path or not _allowed(path):
        raise HTTPException(status_code=404, detail="Not found")
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _STRIP}
    try:
        upstream = _proxy_client().request(
            request.method,
            "/" + path,
            params=dict(request.query_params),
            content=body or None,
            headers=headers,
        )
    except httpx.HTTPError as exc:
        # The stack is down or still starting. Say so plainly rather than
        # surfacing a bare 500 the browser cannot explain.
        logger.warning("supabase proxy failed for /%s: %s", path, exc)
        return Response(
            content='{"message":"The database is not reachable. Is the local Supabase stack running?"}',
            status_code=502,
            media_type="application/json",
        )
    out = {k: v for k, v in upstream.headers.items() if k.lower() not in _STRIP}
    return Response(content=upstream.content, status_code=upstream.status_code, headers=out)


def mount(app: FastAPI) -> None:
    """Attach the self-host routes. Safe to call when no build exists."""
    app.add_api_route(
        "/supabase/{path:path}",
        _supabase_proxy,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        include_in_schema=False,
    )

    if not DIST.is_dir():
        logger.info("selfhost: %s not built — serving API only. Run `npm run build` in frontend/.", DIST)
        return

    # Hashed asset filenames are safe to cache hard; index.html must never be,
    # or a deploy leaves visitors on a stale bundle pointing at dead assets.
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    index = DIST / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        """Serve real files when they exist, otherwise index.html.

        The SPA owns routes like /roles/:id and /schedule/:token, so a refresh
        or a shared deep link must return the app rather than a 404.
        """
        # ...but never for the API namespaces. Falling through to index.html
        # there turns a mistyped or removed endpoint into 200 text/html, which
        # every client will try to parse as JSON, and which hides the real
        # error behind a page that looks like it worked.
        if full_path.startswith(("api/", "supabase/")):
            raise HTTPException(status_code=404, detail="Not found")

        candidate = (DIST / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(DIST.resolve()):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-store"})

    logger.info("selfhost: serving frontend from %s", DIST)
