"""Application configuration.

Everything sensitive comes from environment variables (see .env.example).
Secrets are never written to the repository. A per-installation JWT secret
is generated on first boot and persisted with 0600 permissions.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
DATA_DIR = Path(os.environ.get("PEOPLEIQ_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"

for _d in (DATA_DIR, UPLOAD_DIR, EXPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get(
    "PEOPLEIQ_DATABASE_URL", f"sqlite:///{DATA_DIR / 'peopleiq.db'}"
)


def _load_or_create_secret() -> str:
    """JWT signing secret: env var wins; otherwise generate once and persist."""
    env = os.environ.get("PEOPLEIQ_SECRET_KEY")
    if env:
        return env
    secret_file = DATA_DIR / ".secret_key"
    if secret_file.exists():
        return secret_file.read_text().strip()
    secret = secrets.token_urlsafe(64)
    secret_file.write_text(secret)
    try:
        os.chmod(secret_file, 0o600)
    except OSError:
        pass
    return secret


SECRET_KEY = _load_or_create_secret()
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("PEOPLEIQ_TOKEN_MINUTES", "480"))

# --- AI layer -------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("PEOPLEIQ_MODEL", "claude-opus-4-8")
LLM_MAX_TOKENS = int(os.environ.get("PEOPLEIQ_LLM_MAX_TOKENS", "16000"))

# --- Email (SMTP). If unset, the system operates in draft-only mode. ------
SMTP_HOST = os.environ.get("PEOPLEIQ_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("PEOPLEIQ_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("PEOPLEIQ_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("PEOPLEIQ_SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("PEOPLEIQ_SMTP_FROM", "talent@thepeopleiq.com")
SMTP_FROM_NAME = os.environ.get("PEOPLEIQ_SMTP_FROM_NAME", "People IQ Talent Team")
# Hard safety switch: even with SMTP configured, sending is off unless enabled.
EMAIL_SENDING_ENABLED = os.environ.get("PEOPLEIQ_EMAIL_SENDING", "false").lower() == "true"

# --- Upload constraints ----------------------------------------------------
MAX_UPLOAD_BYTES = int(os.environ.get("PEOPLEIQ_MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
ALLOWED_RESUME_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}
MAX_BATCH_FILES = int(os.environ.get("PEOPLEIQ_MAX_BATCH_FILES", "200"))

# --- Data governance --------------------------------------------------------
# Candidate data retention (days) for non-hired candidates; enforced by the
# retention job and documented in docs/RESPONSIBLE_AI_AND_DATA_PRIVACY.md.
CANDIDATE_RETENTION_DAYS = int(os.environ.get("PEOPLEIQ_RETENTION_DAYS", "365"))
# Fraction of AI "do not shortlist" recommendations randomly flagged for
# mandatory human review (fairness control 15).
REJECT_REVIEW_SAMPLE_RATE = float(os.environ.get("PEOPLEIQ_REVIEW_SAMPLE_RATE", "0.15"))

# --- Auth hardening ---------------------------------------------------------
LOGIN_MAX_ATTEMPTS = int(os.environ.get("PEOPLEIQ_LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_SECONDS = int(os.environ.get("PEOPLEIQ_LOGIN_LOCKOUT_SECONDS", "900"))

# --- Web hardening ----------------------------------------------------------
# Interactive API docs expose the full endpoint surface and schema. Useful in
# development, unnecessary attack surface in production — off unless asked for.
ENABLE_API_DOCS = os.environ.get("PEOPLEIQ_ENABLE_API_DOCS", "false").lower() == "true"
# Browser origins allowed to call the API with credentials. Defaults to the
# Vite dev server only; production is single-origin so it needs no entries.
CORS_ORIGINS = [
    o.strip() for o in os.environ.get(
        "PEOPLEIQ_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if o.strip()
]
# Send HSTS (only meaningful over HTTPS; harmless behind Railway's TLS).
ENABLE_HSTS = os.environ.get("PEOPLEIQ_ENABLE_HSTS", "true").lower() == "true"

COMPANY_NAME = os.environ.get("PEOPLEIQ_COMPANY_NAME", "People IQ")
CLIENT_NAME_DEFAULT = os.environ.get("PEOPLEIQ_DEFAULT_CLIENT", "OculusIT")
