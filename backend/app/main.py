"""People IQ Recruiter Agent — FastAPI application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .database import Base, engine
from .routers import (
    admin, auth_routes, candidates, emails, engagement, interviews, jobs,
    rediscovery, screening, tracker,
)
from .seed import seed_initial_data
from .services import scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_initial_data()
    await scheduler.start()
    yield
    await scheduler.stop()


app = FastAPI(
    title="People IQ Recruiter Agent",
    description="AI-assisted recruitment screening & candidate engagement — "
                "a decision-support system where every final decision stays human.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


for router in (auth_routes.router, jobs.router, candidates.router, screening.router,
               emails.router, engagement.router, interviews.router, tracker.router,
               rediscovery.router, admin.router):
    app.include_router(router)


@app.get("/api/health")
def health():
    from .services.llm import llm_available
    from .services.emailer import sending_configured
    return {
        "status": "ok",
        "ai_engine": "claude" if llm_available() else "deterministic-fallback",
        "model": config.ANTHROPIC_MODEL if llm_available() else None,
        "email_mode": "live" if sending_configured() else "draft-only",
    }


# --- Serve the built frontend (single-origin deployment) ---------------------
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():  # pragma: no cover
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        target = _frontend_dist / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(_frontend_dist / "index.html")
