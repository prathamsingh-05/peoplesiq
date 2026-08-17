"""People IQ Recruiter Agent — FastAPI application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .database import Base, engine, run_lightweight_migrations
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
    run_lightweight_migrations()
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
    # Interactive docs publish the whole endpoint surface; off unless explicitly
    # enabled (config.ENABLE_API_DOCS), so production doesn't advertise it.
    docs_url="/api/docs" if config.ENABLE_API_DOCS else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if config.ENABLE_API_DOCS else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Content-Security-Policy is what actually stops injected/tampered code from
# executing in the page: scripts may only come from this origin, so an attacker
# who manages to get markup into the DOM still cannot run inline JS, load a
# remote script, or eval anything. (A user editing their own browser's copy of
# the page is always possible and is not a server-side threat — what matters is
# that the API trusts nothing from the client, which it doesn't: every mutating
# endpoint re-authorises server-side.)
# style-src allows 'unsafe-inline' because the UI uses React inline style props;
# script-src deliberately does NOT — that's the directive that matters here.
_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = _CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
    )
    if config.ENABLE_HSTS:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
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

    _dist_root = _frontend_dist.resolve()

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        """Serve the SPA. Any path that isn't a real file inside the build
        directory falls through to index.html (client-side routing).

        The containment check is load-bearing, not decorative: joining a
        user-supplied path onto a directory lets `..` segments escape it, so
        without resolving and verifying the result stays under the build root,
        a request like `/../backend/app/config.py` would happily serve backend
        source — and anything else readable by the process, including .env
        files. Symlinks are covered too, since resolve() follows them before
        the check.
        """
        # An unmatched /api/ path is a client error, not a page: falling through
        # to index.html would answer a bad or removed API call with HTML and a
        # 200, hiding the mistake from any caller that checks status codes.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        if full_path:
            try:
                target = (_dist_root / full_path).resolve()
            except (OSError, RuntimeError, ValueError):
                target = None
            if (target is not None
                    and target.is_relative_to(_dist_root)
                    and target.is_file()):
                return FileResponse(target)
        return FileResponse(_dist_root / "index.html")
