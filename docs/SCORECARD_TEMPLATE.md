# JD Evaluation Scorecard Template

The scorecard is the single source of truth for screening. The agent generates a
draft from the job description; the recruiter reviews, edits, and **approves** it
before any resume is scored.

## Structure

Each criterion has:

| Field | Meaning |
|---|---|
| **Category** | One of: `mandatory`, `experience`, `technical_skills`, `domain`, `qualifications`, `seniority`, `location_hours`, `stability`, `preferred` |
| **Name** | Short, verifiable criterion (e.g. "Ellucian Banner 9 production support") |
| **Description** | What evidence in a resume satisfies it |
| **Weight** | 0.25–5.0 — importance to this role (preferred items 0.5–1.0; critical items up to 3.0) |
| **Mandatory** | True only for genuine knock-outs |

## Scoring model (deterministic, in code)

Per criterion the engine assigns an evidence status; the status maps to a fraction
of the criterion's weight:

| Status | Meaning | Score fraction |
|---|---|---|
| `confirmed` | Explicit, dated, contextual evidence | 1.00 |
| `partial` | Related but incomplete evidence | 0.55 |
| `needs_verification` | Claim present but unverifiable from the resume | 0.35 |
| `no_evidence` | Nothing addresses it | 0.00 |
| `contradictory` | Conflicting statements | 0.00 |

**Overall score** = 100 × (Σ weight·fraction) / (Σ weight). Because scoring is
computed in code from the model's per-criterion evidence judgement, identical
inputs always yield identical scores, and no criterion can be silently skipped.

**Mandatory status** = `met` (all mandatory confirmed) / `partially_met` /
`not_met` (any mandatory has no evidence or is contradictory).

**Recommendation:**
- `shortlist` — score ≥ 70 **and** all mandatory met
- `recruiter_review` — score ≥ 45, or mandatory partially met, or low confidence
- `do_not_shortlist` — mandatory not met, or very low weighted evidence **with an explanation**

The engine is recall-biased: low-confidence or offline negatives are routed to
recruiter review rather than rejection.

## Worked example — ERP Application Administrator (Ellucian Banner)

| Category | Criterion | Weight | Mandatory |
|---|---|---|---|
| mandatory | Willingness to work night shift (US EST overlap) | 3.0 | ✓ |
| mandatory | Hands-on Banner **production support** (not implementation-only) | 3.0 | ✓ |
| experience | ≥5 years administering Ellucian Banner in production | 3.0 | ✓ |
| technical_skills | Oracle PL/SQL development & tuning | 2.0 | |
| technical_skills | Banner 9 self-service & admin pages | 2.0 | |
| domain | Support for US higher-education clients | 1.5 | |
| technical_skills | WebLogic / Oracle 19c troubleshooting | 1.5 | |
| qualifications | Bachelor's in Computer Science or equivalent | 1.0 | |
| location_hours | Suitability for Gurugram (hybrid) + EST shift | 1.0 | |
| stability | Career progression (gaps never penalised) | 1.0 | |
| preferred | Ellucian Ethos / Banner APIs | 0.75 | |
| preferred | Jenkins / deployment automation | 0.5 | |
| preferred | Argos / Cognos / Degree Works | 0.5 | |

## Fairness rules baked into scorecard generation

The generator will **never** create criteria based on age, gender, marital/family
status, religion, caste, health, nationality/ethnicity, photographs, or
school/employer prestige. Employment gaps are never a criterion. Location/hours
criteria are created only when the JD states an explicit requirement, and are
scored `needs_verification` when the resume can't prove them (to be confirmed on
the call).
