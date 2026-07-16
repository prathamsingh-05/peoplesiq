# Backend Tasks — from "runs today" to "100% production functional"

The application is **functionally complete** for the prototype: every workflow in
the brief works end-to-end through the API, verified by the test suite and the
evaluation script. This document lists what remains to reach full production
functionality, grouped by effort. Items marked ✅ are already implemented; the
rest are the concrete backend tasks to take care of.

---

## A. Config-only (no code — provide a value and it activates)

These are already wired in the backend; they just need the input.

| # | Task | What flips it on | Effect until then |
|---|---|---|---|
| A1 | **Enable full Claude screening** | set `ANTHROPIC_API_KEY` (model defaults to `claude-opus-4-8`) | deterministic fallback engine (basic, review-only) |
| A2 | **Enable real email sending** (SMTP) | set `PEOPLEIQ_SMTP_*` + `PEOPLEIQ_EMAIL_SENDING=true` | safe draft-only mode |
| A3 | **Set the admin password / JWT secret** | `PEOPLEIQ_ADMIN_PASSWORD`, `PEOPLEIQ_SECRET_KEY` | random password logged once; secret auto-generated |
| A4 | **Point at PostgreSQL** | set `PEOPLEIQ_DATABASE_URL=postgresql://…` | SQLite (single-instance only) |
| A5 | **Private deployment** | `docker compose up -d --build` behind your TLS | runs locally only |

---

## B. Backend engineering tasks (for scale, HA & robustness)

The prototype is built for a single instance. These make it production-grade for
concurrent users and multiple app replicas.

- [ ] **B1 · Alembic migrations.** Replace `Base.metadata.create_all` with Alembic
      so the schema can evolve safely in production. *(Small.)*
- [ ] **B2 · PostgreSQL hardening.** Run against Postgres (SQLAlchemy already
      supports it via `PEOPLEIQ_DATABASE_URL`); add connection pooling config and
      verify the JSON columns map to `JSONB`. *(Small.)*
- [ ] **B3 · Externalize the keep-warm scheduler.** Today it's an in-process
      asyncio loop (`services/scheduler.py`) — correct for one instance, but two
      replicas would double-send. Move to a single scheduled worker
      (APScheduler+Redis lock, Celery beat, or a platform cron hitting
      `POST /api/admin/scheduler/run`). *(Medium.)*
- [ ] **B4 · Move batch screening to a task queue.** Screening runs in a
      background thread with in-memory progress (`_screen_progress`). For
      multi-instance and durability, move to Celery/RQ/Arq and persist progress
      in the DB. *(Medium.)*
- [ ] **B5 · Object storage for uploads.** Resumes are written to a local volume
      (`UPLOAD_DIR`). For cloud/multi-instance, store to S3 / Azure Blob and keep
      only the key in the DB. *(Medium.)*
- [ ] **B6 · Shared login-lockout store.** The failed-login tracker is an
      in-memory dict (`auth._failed_logins`) — per-process. Move to Redis so
      lockout holds across replicas. *(Small.)*
- [ ] **B7 · Rate limiting.** Add per-IP/user rate limits on `/api/auth/login`
      and write endpoints (SlowAPI middleware, or at the reverse proxy/WAF).
      *(Small.)*
- [ ] **B8 · Secrets manager.** Load `PEOPLEIQ_SECRET_KEY`, `ANTHROPIC_API_KEY`
      and SMTP creds from Azure Key Vault / AWS Secrets Manager instead of env
      files in production. *(Small.)*
- [ ] **B9 · Structured logging + tracing.** Add request IDs, JSON logs and
      OpenTelemetry spans; ship to your log store. *(Small–Medium.)*

---

## C. Integration tasks (need external credentials + adapter code)

Each needs the corresponding tenant/app registration from your side, plus a
backend adapter. The seams for these already exist (e.g. `services/emailer.py`
isolates sending).

- [ ] **C1 · Microsoft Graph email provider.** Add a Graph-based sender
      alongside SMTP (send + optional reply/thread tracking). *Needs:* Entra ID
      app registration with `Mail.Send`. *(Medium.)*
- [ ] **C2 · Microsoft Teams transcript retrieval.** Pull interview transcripts
      via Graph instead of paste/upload; the consent gates and analysis are
      already built. *Needs:* Graph `OnlineMeetingTranscript.Read.All` + tenant
      admin consent. *(Medium.)*
- [ ] **C3 · Entra ID (Azure AD) SSO.** Replace/augment the local user store with
      OIDC login + MFA. *Needs:* app registration. *(Medium.)*
- [ ] **C4 · SharePoint / OneDrive storage.** Store resumes and Excel exports in
      the client's tenant. *Needs:* Graph `Files.ReadWrite.All`. *(Medium.)*
- [ ] **C5 · ATS (Keka) two-way sync.** Pull requisitions/candidates, push
      decisions/statuses/summaries. *Needs:* Keka API credentials. *(Large.)*
- [ ] **C6 · Inbound email / reply capture.** Ingest candidate replies (Graph
      webhook or IMAP) to track responses in the tracker. *Needs:* mailbox
      subscription. *(Medium.)*

---

## D. Screening-quality backend tasks (optional, model-side)

- [ ] **D1 · Prompt-cache the scorecard** on large batches to cut LLM cost/latency.
- [ ] **D2 · Configurable score thresholds per role family** (currently global
      constants `SHORTLIST_THRESHOLD` / `REVIEW_THRESHOLD` in `services/screening.py`).
- [ ] **D3 · Semantic skill matching** (embeddings) to catch synonymous skills in
      rediscovery and screening pre-filters.
- [ ] **D4 · Scheduled bias-audit export** — persist the responsible-AI report on
      a cadence and alert on agreement-rate/decision-distribution drift.

---

## Priority to reach "100% functional & private"

1. **A1–A5** (config) → a private, logged-in instance with full AI + email. *Same day.*
2. **B1, B2, B6, B7, B8** → safe for real users and a proper DB. *A few days.*
3. **B3, B4, B5** → horizontal scale / HA. *When traffic warrants.*
4. **C1–C6** → deep Microsoft/ATS integration. *Phase 2, per your tenant.*

Nothing in section A is a code gap — it's inputs. Sections B–D are the standard
production-hardening backlog; the prototype runs correctly without them for a
single-instance private deployment.
