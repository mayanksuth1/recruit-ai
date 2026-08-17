import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import (
    ai_interviews, ats, calendar, candidates, company_profile, dashboard,
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


app = FastAPI(title="Recruit AI", version="0.4.0", lifespan=lifespan)

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
app.include_router(ats.router)
app.include_router(reports.router)
app.include_router(signup.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
