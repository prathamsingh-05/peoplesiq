# People IQ Recruiter Agent

An AI-assisted recruitment platform that helps recruiters **screen resumes,
prioritise candidates, prepare screening conversations, maintain recruitment
trackers, and manage candidate communication — while every final hiring
decision stays with a human recruiter.**

Built for **People IQ** (talent partner for **OculusIT**) as a
**decision-support system, not an autonomous hiring authority.**

> This repository implements the full Project Brief end-to-end: Phase 1 (screening
> MVP), Phase 2 (recruiter workflow), Phase 3 (candidate engagement / keep-warm),
> and Phase 4 (interview intelligence). See [`docs/REQUIREMENTS_TRACEABILITY.md`](docs/REQUIREMENTS_TRACEABILITY.md)
> for a line-by-line map of every brief requirement to where it lives in the code.

---

## What it does (the recruiter's five questions, answered fast)

For every candidate, the agent answers:

1. **Does this candidate meet the essential requirements?** → mandatory-criteria status
2. **What evidence supports the match?** → verbatim resume quotes per criterion, verified against the source
3. **What is missing or unclear?** → gaps, missing information, items needing verification
4. **What should the recruiter verify on the call?** → a 5–7 question screening pack
5. **Prioritise, hold, or reject?** → shortlist / recruiter-review / do-not-shortlist, with an explanation

## The eleven-step recruiter outcome (Brief §5)

Upload a JD → approve the AI scorecard → drop a folder of CVs → screen all →
ranked leaderboard → open any candidate's evidence-linked assessment →
review screening questions → **approve or override** the AI → generate the
hiring-manager summary → the tracker updates itself → approve & send the
right candidate email. All of it is in the running app.

---

## Architecture

```
frontend/  React (Vite) recruiter portal — login, dashboard, jobs, scorecard,
           upload, leaderboard, candidate workspace (8 tabs), tracker, outbox,
           content library, governance.
backend/   FastAPI + SQLAlchemy (SQLite) application.
   app/services/   AI + domain logic:
     llm.py            Anthropic Claude, strict JSON structured outputs, retries
     fairness.py       protected-attribute redaction + responsible-AI guardrails
     resume_parser.py  PDF/DOCX/TXT extraction, contact + structured profile
     scorecard.py      JD → weighted evaluation scorecard
     screening.py      evidence-based, deterministic-scored evaluation engine
     questions.py      screening-question generator (4 categories)
     summary.py        hiring-manager summary (structured + formatted profile)
     emailer.py        outreach / rejection / keep-warm templates + SMTP send
     interview.py      §11 transcript intelligence (consent-gated)
     scheduler.py      keep-warm dispatch, stop rules, retention pass
     excel.py          leaderboard / tracker / HM-summary Excel exports
   app/routers/    REST API (auth, jobs, candidates, screening, emails,
                   engagement, interviews, tracker, admin)
scripts/   generate_sample_data.py (3 JDs + 32 resumes), run_evaluation.py
tests/     pytest suite incl. full end-to-end pipeline through the real API
docs/      BRD, user journey, scorecard template, responsible-AI note,
           evaluation plan, research, security, roadmap, requirements traceability
```

The AI layer **degrades gracefully**: with no `ANTHROPIC_API_KEY` the whole
product still runs on a deterministic keyword engine (screening quality is
basic and everything routes to recruiter review) — so the app is always
demonstrable, and API outages never break a batch.

---

## Quick start

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
# optional but recommended — enables full AI screening:
export ANTHROPIC_API_KEY=sk-ant-...          # uses claude-opus-4-8 by default
export PEOPLEIQ_ADMIN_PASSWORD=choose-a-strong-password
uvicorn app.main:app --port 8000
```

On first boot the app creates the SQLite database, seeds a bootstrap **admin**
account (password from `PEOPLEIQ_ADMIN_PASSWORD`, or a random one printed to
the log), and loads the approved keep-warm content library. API docs are at
`http://localhost:8000/api/docs`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev            # dev server on http://localhost:5173 (proxies /api → :8000)
# or, for a single-origin deployment:
npm run build          # backend then serves the built SPA from / automatically
```

### 3. Try it with the sample dataset

```bash
pip install reportlab                         # only needed to generate sample PDFs
python scripts/generate_sample_data.py        # 3 JDs + 32 resumes + recruiter labels
python scripts/run_evaluation.py --password "$PEOPLEIQ_ADMIN_PASSWORD"
```

`run_evaluation.py` drives the whole API (create JD → approve scorecard →
upload 32 resumes → batch-screen → compare to recruiter ground truth) and
prints the Brief §18 success-metric scorecard.

---

## Configuration

All configuration is via environment variables — see [`.env.example`](.env.example).
Highlights:

| Variable | Purpose | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Enables full AI screening | *(unset → deterministic fallback)* |
| `PEOPLEIQ_MODEL` | Claude model id | `claude-opus-4-8` |
| `PEOPLEIQ_ADMIN_PASSWORD` | Bootstrap admin password | *(random, logged once)* |
| `PEOPLEIQ_EMAIL_SENDING` + `PEOPLEIQ_SMTP_*` | Enable real email sending | *(off → draft-only)* |
| `PEOPLEIQ_RETENTION_DAYS` | Candidate data-retention window | `365` |
| `PEOPLEIQ_REVIEW_SAMPLE_RATE` | Fraction of AI rejections flagged for human review | `0.15` |
| `PEOPLEIQ_SECRET_KEY` | JWT signing secret | *(auto-generated, persisted 0600)* |

**Secrets are never committed.** The `.gitignore` excludes `.env`, the SQLite
database, uploads and the auto-generated JWT secret.

---

## Human-in-the-loop decision gates (Brief §14)

The product enforces all eight mandatory human gates:

1. **Scorecard approval** — screening is blocked (HTTP 409) until a recruiter approves the scorecard.
2. **Shortlist / rejection decisions** — recorded separately from the AI; a rejection with no reason is refused.
3. **First candidate email** — no email sends without an explicit approval step.
4. **Post screening-call confirmation** — the recruiter records the outcome before HM submission.
5. **HM summary approval** — required before a summary is marked shareable.
6. **Engagement-sequence approval** — the keep-warm sequence stays inert until approved.
7. **Interview-evaluation review** — AI interview analysis is hidden until a human approves it.
8. **Day-1 handover confirmation** — an explicit act transfers the candidate out of People IQ.

## Responsible-AI & fairness (Brief §15)

- Protected/sensitive attributes are **redacted before the model ever sees the resume**
  (age, gender, marital/family status, religion, caste, health, nationality/ethnicity,
  photos, street address; lawful work-authorisation phrases are preserved).
- **Employment gaps and poor formatting can never cause an automatic rejection.**
- **Every negative recommendation carries an explanation** (enforced in code).
- A **random sample of AI rejections is flagged for mandatory human review.**
- **Consistency:** the same resume + scorecard always yields the same score
  (evidence quotes are verified against the source; unverifiable "confirmed"
  claims are downgraded — pruning hallucinations).
- Full detail: [`docs/RESPONSIBLE_AI_AND_DATA_PRIVACY.md`](docs/RESPONSIBLE_AI_AND_DATA_PRIVACY.md).

## Security (internal-tool hardening)

JWT bearer auth · PBKDF2-SHA256 password hashing (310k iterations) ·
role-based access (admin / recruiter / hiring-manager) · login lockout ·
security headers · full audit trail of every AI action and human decision ·
admin-only data purge for erasure requests. See [`docs/SECURITY.md`](docs/SECURITY.md).

---

## Testing

```bash
python -m pytest tests/ -q
```

The suite covers fairness redaction, resume parsing, the deterministic
fallback, RBAC, and a **complete end-to-end pipeline** (scorecard gate →
upload with duplicates/unreadable → batch screening → leaderboard → decisions
→ questions → call → HM summary → email gates → offer-accepted → keep-warm →
stop rules → handover → tracker/dashboard/audit → Excel exports).

## Deliverables map (Brief §19)

| Deliverable | Location |
|---|---|
| Business-requirements document | [`docs/BUSINESS_REQUIREMENTS.md`](docs/BUSINESS_REQUIREMENTS.md) |
| Recruiter user journey | [`docs/RECRUITER_USER_JOURNEY.md`](docs/RECRUITER_USER_JOURNEY.md) |
| JD evaluation-scorecard template | [`docs/SCORECARD_TEMPLATE.md`](docs/SCORECARD_TEMPLATE.md) |
| Working web application | `frontend/` + `backend/` |
| Resume-upload facility | Jobs → Upload CVs tab |
| Candidate-screening engine | `backend/app/services/screening.py` |
| Candidate leaderboard | Jobs → Screen & Leaderboard tab |
| Individual candidate report | Candidate → Assessment tab |
| Screening-question generator | `backend/app/services/questions.py` |
| Excel candidate tracker | Dashboard / Tracker → Export |
| Test dataset | `scripts/generate_sample_data.py` → `data/sample/` |
| Evaluation report (AI vs recruiter) | `scripts/run_evaluation.py` |
| Data-privacy & responsible-AI note | [`docs/RESPONSIBLE_AI_AND_DATA_PRIVACY.md`](docs/RESPONSIBLE_AI_AND_DATA_PRIVACY.md) |
| Recommendations for future development | [`docs/FUTURE_ROADMAP.md`](docs/FUTURE_ROADMAP.md) |
| Research summary (best AI recruiters) | [`docs/RESEARCH_BEST_PRACTICES.md`](docs/RESEARCH_BEST_PRACTICES.md) |
