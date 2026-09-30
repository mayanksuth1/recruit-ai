import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .routers import (
    ai_interviews, ai_provider, ats, calendar, candidates, company_profile, dashboard,
    engagement, interviews, organizations, reports, roles, signup, talent_pool,
)
from .services import scheduler

logger = logging.getLogger("uvicorn.error")


async def _scheduler_loop():
    """In-process reminder/nudge loop. An n8n workflow could replace this
    later by hitting POST /api/scheduler/run-checks on its own cadence."""
    while True:
        try:
            result = await asyncio.to_thread(scheduler.run_checks)
            if result["reminders_drafted"] or result["nudges_sent"]:
                logger.info("scheduler: %s", result)
        except Exception:
            logger.exception("scheduler check failed")
        await asyncio.sleep(settings.scheduler_interval_seconds)


async def _keepalive_loop():
    """Ping Supabase every minute so pooled connections never go idle long
    enough for the server to drop them (Windows surfaces that as a
    'connection forcibly closed' 500 on the next real request)."""
    from .db import service_client

    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(
                lambda: service_client().table("organizations").select("id").limit(1).execute()
            )
        except Exception:
            pass  # a failed ping just means the next real request reconnects


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [asyncio.create_task(_scheduler_loop()), asyncio.create_task(_keepalive_loop())]
    yield
    for t in tasks:
        t.cancel()


# The interactive docs list every route, parameter and schema: a free map for
# anyone probing the public URL. Off unless explicitly enabled for development.
_docs = settings.expose_api_docs
app = FastAPI(
    title="Recruit AI", version="0.4.0", lifespan=lifespan,
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)

# Largest legitimate body is a 10 MB resume PDF plus multipart overhead.
MAX_BODY_BYTES = 12 * 1024 * 1024

# Only what the built frontend actually loads: its own bundle, Google Fonts,
# and XHR to this origin (API and the /supabase auth proxy) or to a Supabase
# URL baked in at build time. No inline script, no framing.
_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    f"connect-src 'self' {settings.supabase_url.rstrip('/')}",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


class _BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """Cap request bodies by counting the bytes actually received.

    Checking Content-Length alone is not enough: a chunked upload carries no
    length header, and Starlette would spool the whole thing to disk before a
    route ever sees it. Counting in receive() stops it at the limit.
    """

    def __init__(self, app, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        for name, value in scope.get("headers", []):
            if name == b"content-length" and value.isdigit() and int(value) > self.max_bytes:
                return await JSONResponse({"detail": "Request body too large"}, status_code=413)(scope, receive, send)

        seen = 0
        started = False

        async def counted_receive():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    raise _BodyTooLarge
            return message

        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted_receive, tracked_send)
        except _BodyTooLarge:
            if not started:
                await JSONResponse({"detail": "Request body too large"}, status_code=413)(scope, receive, send)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    # Candidate links carry their credential in the path (/schedule/<token>,
    # /ai-interview/<token>); never hand that URL to another site as a Referer.
    h.setdefault("Referrer-Policy", "no-referrer")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    h.setdefault("Content-Security-Policy", _CSP)
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path.startswith("/api/"):
        # Candidate data must not linger in shared or browser caches.
        h.setdefault("Cache-Control", "no-store")
    # Do not advertise the server stack.
    if "server" in h:
        del h["server"]
    return response


app.add_middleware(BodyLimitMiddleware, max_bytes=MAX_BODY_BYTES)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(organizations.router)
app.include_router(dashboard.router)
app.include_router(company_profile.router)
app.include_router(roles.router)
app.include_router(candidates.router)
app.include_router(talent_pool.router)
app.include_router(engagement.router)
app.include_router(calendar.router)
app.include_router(interviews.router)
app.include_router(ai_interviews.router)
app.include_router(ai_provider.router)
app.include_router(ats.router)
app.include_router(reports.router)
app.include_router(signup.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}

# Self-host mode: serve the built frontend and proxy Supabase from this same
# origin. Registered AFTER every router so the SPA catch-all cannot shadow an
# API route. No-ops when frontend/dist has not been built.
from . import selfhost  # noqa: E402  (import here: it must load after routers)

selfhost.mount(app)
