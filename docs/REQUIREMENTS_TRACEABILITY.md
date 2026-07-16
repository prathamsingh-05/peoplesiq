# Requirements Traceability Matrix

Every requirement in the Project Brief mapped to where it is implemented. This is
the "do not miss a single line" checklist.

Legend: ✅ implemented · 🔶 implemented with a documented boundary (e.g. requires
external credentials to go fully live).

## The original e-mail asks (Shonalie's note)

| Ask | Status | Where |
|---|---|---|
| Folder where you dump CVs as per JD | ✅ | Batch upload endpoint `POST /api/jobs/{id}/candidates/upload`; Jobs → Upload CVs |
| Agent to screen CV vs JD criteria | ✅ | `services/screening.py`, `POST /api/jobs/{id}/screen` |
| Leaderboard: whom to shortlist / reject | ✅ | `GET /api/jobs/{id}/leaderboard`; JobDetail leaderboard tab |
| Agent to send initial email | ✅ | `services/emailer.py` outreach + `POST /api/emails/{id}/send` (after approval) |
| Agent to suggest screening questions | ✅ | `services/questions.py`, Candidate → Screening questions |
| Recruiter probes for gaps & shortlists | ✅ | Call & decision tab; `POST /api/candidates/{id}/call-outcome` + `/decision` |
| Candidate summary in Excel | ✅ | `services/excel.py` `export_hm_summaries`, `GET /api/jobs/{id}/export/hm-summaries` |
| Update trackers (how many CVs screened) | ✅ | ProcessingLog + `GET /api/tracker` + `GET /api/dashboard` |
| Human updates "training steps" | ✅ | Recruiter corrections/decisions recorded separately; audit trail |
| NICE-TO-HAVE: agent evaluation of Teams interviews | ✅ | `services/interview.py` (post-interview transcript, consent-gated) |
| Human does phone contact / builds interest | ✅ | Stage-7 call-outcome capture; AI never phones candidates |
| Salary negotiation stays with human | ✅ | Compensation captured as call fields; no AI negotiation |
| Back to AI on offer acceptance | ✅ | `POST /api/candidates/{id}/offer-accepted` |
| Email every 3rd day with OculusIT content until T-2 | ✅ | `emailer.build_keepwarm_schedule` (3-day drip up to T-2) |
| Pre-loaded content (YouTube links etc.) | ✅ | Seeded content library, `content_type`/`url` fields |
| "Keep warm protocol" | ✅ | `EngagementSequence` + `scheduler.py` |
| Welcome mail + Day-1 agenda + induction, then hand to client | ✅ | `welcome_day0`/`day1_t1` templates + `POST /api/candidates/{id}/handover` |
| Feasibility answer | ✅ | Delivered as a working system — see FEASIBILITY.md |

## Brief §5 — Clear Project Outcome (11 steps)

| Step | Status | Where |
|---|---|---|
| 1 Upload one JD | ✅ | `POST /api/jobs` |
| 2 Upload a folder of resumes | ✅ | `POST /api/jobs/{id}/candidates/upload` (up to 200/batch) |
| 3 Screen all resumes | ✅ | `POST /api/jobs/{id}/screen` (background batch) |
| 4 Ranked leaderboard | ✅ | `GET /api/jobs/{id}/leaderboard` |
| 5 Open individual assessment | ✅ | `GET /api/candidates/{id}/evaluation` |
| 6 See supporting evidence | ✅ | `criterion_results` with verified quotes |
| 7 Review screening questions | ✅ | `GET /api/candidates/{id}/questions` |
| 8 Approve/change the AI recommendation | ✅ | `POST /api/candidates/{id}/decision` |
| 9 Generate HM summary | ✅ | `POST /api/candidates/{id}/hm-summary` |
| 10 Update tracker automatically | ✅ | tracker derived from live state; every action logs |
| 11 Approve & send email | ✅ | approve → send email endpoints |

## Brief §7 — Workflow stages 1–10

| Stage | Status | Where |
|---|---|---|
| 1 Create requirement + fields | ✅ | `Job` model, `JobCreate` schema (title, location, hours, model, min exp, essential/preferred skills, quals, comp, notice, mandatory conditions) |
| 1 JD → scorecard, recruiter approves | ✅ | `services/scorecard.py`; approve gate in `routers/jobs.py` |
| 2 Extract name/contact | ✅ | `resume_parser.extract_contact` |
| 2 Identify employers/roles/dates/skills/quals/projects | ✅ | `resume_parser.extract_profile` (`PROFILE_SCHEMA`) |
| 2 Detect duplicates | ✅ | file-hash + email/phone content dedupe |
| 2 Flag unreadable/incomplete | ✅ | `MIN_READABLE_CHARS`, `unreadable` status |
| 2 Unique candidate ID | ✅ | `candidate_code` = CAND-##### |
| 2 Record processing date/time | ✅ | `received_at` / `processed_at` + ProcessingLog |
| 3 Evaluate against all criteria dims | ✅ | scorecard categories: mandatory, experience, technical, domain, quals, seniority, location/hours, stability, preferred |
| 3 Five evidence states | ✅ | confirmed / partial / no_evidence / contradictory / needs_verification |
| 4 Leaderboard columns | ✅ | rank, candidate, overall match, mandatory, rel-exp, strengths, gaps, risk flags, recommendation, confidence, evidence |
| 4 No keyword-count ranking | ✅ | weighted evidence scoring; shingled quote verification; no keyword frequency signal |
| 5 Individual assessment (11 fields) | ✅ | executive summary, mandatory/preferred match, projects, missing info, inconsistencies, verification questions, AI recommendation + explanation, recruiter decision + comments |
| 6 5–7 questions, 4 categories | ✅ | eligibility / skill_evidence / gap_probing / motivation |
| 7 Human screening capture | ✅ | call-outcome fields: interest, comms, gaps, comp, availability, notice, corrections |
| 8 HM summary (14 fields) | ✅ | `services/summary.py` + Excel + formatted profile |
| 9 Master tracker (20 fields) | ✅ | `TRACKER_HEADERS` in `excel.py`; `/api/tracker` |
| 9 Dashboard metrics (11) | ✅ | `/api/dashboard` incl. AI-vs-recruiter agreement rate |
| 10 Day-1 handover items | ✅ | `day1_t1` template (reporting time, induction link, manager, docs, tech, agenda, contact) |
| 10 Ownership transfers to client | ✅ | handover endpoint; further automation stops |

## Brief §8 — Communication

| Item | Status | Where |
|---|---|---|
| Initial email fields | ✅ | `initial_outreach` template (role, opportunity, company, location/model, hours, interest & info request, apply instructions) |
| Approve before send | ✅ | draft → approve → send; extracted address alone never sends |
| Rejection/hold templates (5 kinds) | ✅ | reject_not_suitable, hold_future, more_info_needed, unreachable, position_on_hold |
| Rejections draft-only in early version | ✅ | send endpoint refuses rejection templates (403) |

## Brief §9–10 — Keep-warm & Day-1

| Item | Status | Where |
|---|---|---|
| Offer-accepted starts sequence | ✅ | `offer-accepted` endpoint |
| Confirmation + every-3rd-day + T-7/5/3/2/1/0 | ✅ | `build_keepwarm_schedule` |
| Content library (10 content types) | ✅ | seeded `ContentItem`s; leadership, video, stories, photos, learning, team, benefits, FAQ, shift, docs |
| Stop rules (declined/date-change/withdrawn/paused/joined) | ✅ | `scheduler.py` + engagement endpoints |
| Two-days-before Day-1 details | ✅ | `day1_t1` at T-1 with full details |
| Handover to client HR | ✅ | handover endpoint |

## Brief §11 — Interview intelligence

| Item | Status | Where |
|---|---|---|
| Read transcript, competencies, summaries | ✅ | `interview.analyse_transcript` (`ANALYSIS_SCHEMA`) |
| Compare answers vs resume | ✅ | `resume_consistency` |
| Flag vague/unsupported claims, unanswered Qs | ✅ | schema fields |
| Independent evaluation + competency scores | ✅ | `overall_score`, `competencies_covered` |
| Compare interviewer feedback vs AI | ✅ | `GET /api/interviews/{id}/compare` |
| Debrief suggestions | ✅ | `debrief_suggestions` |
| No covert recording; 4 consents required | ✅ | `interview.check_consent` blocks analysis |
| Human review before added/shared | ✅ | review gate; analysis hidden until approved |
| Post-interview (not live) | ✅ | transcript uploaded after the interview |

## Brief §12 — Functional requirements

All ✅: JD upload, PDF/Word resumes, structured extraction, scorecard create+approve,
batch screening, ranking, evidence-linked recommendations, candidate reports,
question generation, recruiter approval/correction, email drafting, approved sending,
Excel tracker updates, candidate-status management, communication scheduling, audit
logs, role-based access, exporting results.

## Brief §13 — Non-functional requirements

| Requirement | Status | Notes |
|---|---|---|
| Easy for a non-technical recruiter | ✅ | Guided tabbed portal, plain language, one action per step |
| ≥50 resumes per batch | ✅ | `MAX_BATCH_FILES=200`; background screening |
| Transparent scoring | ✅ | per-criterion evidence + explanation on every score |
| Secure candidate data | ✅ | see SECURITY.md |
| Restrict access by recruiter/project | ✅ | RBAC + audit; per-job scoping |
| Resistant to duplicate processing | ✅ | hash + content dedupe; idempotent re-screen |
| Recover from unreadable files / API failures | ✅ | per-file isolation; deterministic fallback engine |
| Consistent re-evaluation | ✅ | `input_hash` cache; deterministic scoring |
| Correctable AI outputs | ✅ | recruiter correction + override endpoints |
| Audit trail of AI + human decisions | ✅ | `AuditLog` on every action |

## Brief §14 — Eight human gates: all ✅ (see README).

## Brief §15 — Fairness controls: all ✅ (see RESPONSIBLE_AI_AND_DATA_PRIVACY.md).

## Brief §16 — Phases 1–4: all delivered.

## Brief §17 — Technology architecture

React portal ✅ · FastAPI application layer ✅ · LLM for JD structuring / extraction /
evidence / comparison / questions / summaries / email / transcript analysis ✅ ·
structured (non-narrative) AI outputs ✅ · SQLite storage ✅ · secure file storage ✅ ·
Excel export ✅. Microsoft Graph/Outlook/Teams/SharePoint and ATS integrations are
documented as the enterprise path in FUTURE_ROADMAP.md (SMTP is the working email path).

## Brief §18 — Evaluation plan: `scripts/run_evaluation.py` (3 JDs, 32 resumes, metric scorecard).

## Brief §19 — Deliverables: mapped in README "Deliverables map".

## Brief §20 — Definition of Done: all criteria met — verified by `tests/test_pipeline.py`.

## Beyond the brief — research-driven additions

Informed by research into the best AI recruitment agents (see
`RESEARCH_BEST_PRACTICES.md`), these capabilities were added on top of the brief:

| Addition | Status | Where |
|---|---|---|
| **Talent rediscovery / silver medalists** — resurface prior candidates from other roles for a new requisition; the most-cited differentiator (12- vs 42-day time-to-fill) | ✅ | `services/rediscovery.py`, `GET /api/jobs/{id}/rediscover`, `POST …/pull`; JobDetail "Rediscover talent" tab |
| **Generated responsible-AI / bias-audit report** — turns audit-readiness into an actual report (selection rates, AI-vs-recruiter agreement, recall-risk count, fairness-control health checks, honest LL144 impact-ratio note) | ✅ | `services/reporting.py`, `GET /api/responsible-ai-report`; Governance "Responsible-AI report" tab |
| **Bulk leaderboard decisions** — shortlist/hold/reject many at once (bulk reject still needs a reason) | ✅ | `POST /api/jobs/{id}/decisions/bulk`; leaderboard multi-select |
| **Candidate search & filter** on the tracker | ✅ | `GET /api/tracker?q=&status=&decision=`; Tracker search bar |
| **CI pipeline** — pytest + frontend build on every push/PR | ✅ | `.github/workflows/ci.yml` |
| **Two §18 metrics automated** — mandatory-criteria extraction alignment + tracker-update accuracy | ✅ | `scripts/run_evaluation.py` (both compute 100% on the sample set) |
| **Turnkey private deployment** — one-command Docker/Compose serving API + UI on one origin | ✅ | `Dockerfile`, `docker-compose.yml`, `docs/DEPLOYMENT.md` |
