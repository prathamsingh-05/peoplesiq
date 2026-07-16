# Business Requirements Document — People IQ Recruiter Agent

## 1. Purpose

Deliver an AI-assisted recruitment platform that reduces the time recruiters
spend on initial resume screening and repetitive administration, while keeping
every hiring judgement with a human. The system is a **decision-support tool**,
never an autonomous hiring authority.

## 2. Business problem

Recruiters at People IQ manage several open roles at once and receive large
volumes of resumes per role. Manual screening is slow, inconsistent, and prone
to losing good candidates to workload, formatting, or incomplete review. The
downstream admin — summaries, trackers, repetitive candidate emails, and
follow-up until joining — compounds the load.

## 3. Primary user & needs

**Recruitment Specialist.** Needs the system to answer, per candidate, quickly:
does this candidate meet the essentials; what evidence supports it; what is
missing; what to verify on the call; and whether to prioritise, hold, or reject.

Secondary users: **Admin** (user management, content approval, governance) and
**Hiring Manager** (read-only access to approved candidate summaries and interview
evaluations).

## 4. Objectives

- Cut initial screening time by ≥50% without removing human judgement.
- Produce an evidence-linked, explainable recommendation for every candidate.
- Maximise strong-candidate recall (the costliest error is losing a good fit).
- Maintain a single source of truth (tracker + dashboard) with an audit trail.

## 5. Scope

**In scope (delivered):** JD intake & structured scorecard; batch resume upload,
parsing, de-duplication, unreadable handling; evidence-based screening; ranked
leaderboard; individual assessments; screening-question generation; recruiter
decision capture and correction; hiring-manager summaries; master tracker and
dashboard; candidate email drafting/approval/sending; offer-accepted keep-warm
protocol and Day-1 handover; post-interview transcript intelligence; audit logs;
role-based access; Excel exports.

**Boundaries (documented, not gaps):** live Microsoft Graph/Outlook/Teams/SharePoint
and ATS integrations are the enterprise path (SMTP is the working email channel;
transcripts are uploaded/pasted). The agent never phones candidates or negotiates
salary — those stay with the recruiter.

## 6. Functional requirements

See `docs/REQUIREMENTS_TRACEABILITY.md` for the complete, itemised map of every
brief requirement to its implementation. In summary the platform supports: JD
upload; PDF/Word resume upload and structured extraction; scorecard creation and
approval; batch screening (≥50/batch); candidate ranking; evidence-linked
recommendations; candidate-level reports; screening-question generation; recruiter
approval and correction; email draft generation and approved sending; Excel tracker
updates; candidate-status management; communication scheduling; audit logs;
role-based access; and result export.

## 7. Non-functional requirements

Usable by non-technical recruiters; ≥50 resumes per batch; transparent per-criterion
scoring; secure handling of personal data; access restriction by recruiter/project;
duplicate-processing resistance; graceful recovery from unreadable files and API
failures; deterministic re-evaluation; correctable outputs; and a full audit trail.

## 8. Success metrics (targets)

| Metric | Target |
|---|---|
| Resume processing success | ≥95% |
| Mandatory-criteria extraction accuracy | ≥90% |
| Strong-candidate recall (most important) | ≥90% |
| AI ↔ recruiter shortlist agreement | ≥80% |
| Candidates rejected without explanation | 0% |
| Candidate reports containing resume evidence | 100% |
| Reduction in initial screening time | ≥50% |
| Tracker-update accuracy | ≥95% |

Measured by `scripts/run_evaluation.py` against the sample dataset with recruiter
ground-truth labels.

## 9. Constraints & assumptions

- LLM outputs must be **structured fields**, not free narrative (enforced via JSON
  schema on every call).
- The system must remain demonstrable and functional without an LLM key
  (deterministic fallback).
- Candidate personal data is subject to retention rules and correction/erasure
  processes (see the responsible-AI note).

## 10. Definition of Done (Brief §20)

A recruiter can upload a JD; the system generates an editable scorecard; the
recruiter can upload ≥25 resumes; all readable resumes are evaluated; every score
is supported by resume evidence; a leaderboard is produced; the recruiter can
override the AI; screening questions are produced for shortlisted/borderline
candidates; a structured candidate summary is generated; results export to Excel;
AI and human decisions are recorded separately; and the product has been tested
against recruiter-reviewed resumes. **All verified by the automated pipeline test.**
