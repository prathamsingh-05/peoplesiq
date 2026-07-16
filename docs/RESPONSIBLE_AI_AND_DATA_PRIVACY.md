# Responsible-AI & Data-Privacy Note

This note documents how the People IQ Recruiter Agent meets the fairness,
transparency, and data-protection requirements of the brief (§6, §13, §15) and
aligns with recognised standards for automated employment decision tools
(EEOC guidance, NYC Local Law 144 / the four-fifths rule, GDPR/DPDP principles).

## 1. Core principle: decision-support, not decision-maker

The AI **recommends** (shortlist / recruiter-review / do-not-shortlist). A human
**decides**. Eight mandatory approval gates (scorecard, decisions, first email,
post-call, HM summary, engagement sequence, interview evaluation, handover)
ensure a person is accountable at every consequential step. AI recommendations
and human decisions are stored **separately**, so the two can always be compared
and audited.

## 2. What the model is not allowed to see or use

Before any resume text reaches the scoring model it passes through
`services/fairness.py`, which redacts:

- Age / date of birth
- Gender and gendered honorifics
- Marital and family status (spouse, children, parents' names)
- Religion and caste
- Disability / health information (incl. blood group)
- Nationality / ethnicity — **except** explicit, lawful work-authorisation
  statements, which are preserved because a role may legitimately require them
- Photographs (references)
- Residential street address (city/state, which may be a legitimate location
  requirement, is preserved)

The scoring engine works on the **redacted** text only. The candidate's
identity/contact block is extracted separately for communication and is **not**
provided to the ranking model.

## 3. Scoring fairness guardrails (enforced in code)

- **Employment gaps never lower a score or trigger rejection.** Gaps may only be
  flagged neutrally for the recruiter to discuss.
- **Poor formatting never lowers a score.**
- **Non-native English is not penalised** unless written communication is an
  explicitly listed essential requirement.
- **Keyword frequency is not evidence.** Scores reflect demonstrated, dated,
  contextual experience — evidence quotes are verified against the source text,
  and unverifiable "confirmed" claims are automatically downgraded.
- **School/employer prestige is not a criterion** and cannot be generated as one.
- **Every negative recommendation carries an explanation.** A `do_not_shortlist`
  with no explanation is programmatically downgraded to recruiter-review.

## 4. Human oversight of the AI

- **Random rejection review:** a configurable fraction (default 15%) of AI
  "do not shortlist" recommendations is flagged for **mandatory human review** in
  the Governance → Fairness queue.
- **Agreement monitoring:** the dashboard reports the AI-vs-recruiter decision
  agreement rate, so systematic divergence is visible and can trigger a scorecard
  or prompt review (the ongoing "periodic review" control).
- **Correction process:** recruiters can correct any extracted candidate
  information; every correction is logged with who, when, and why.

## 5. Consistency, transparency & explainability

- The **same resume + scorecard always produces the same score** (results are
  cached by a content hash; scoring is deterministic given the evidence
  judgement). Reproducibility is a fairness property, not just an engineering one.
- Every score is **traceable to per-criterion evidence** — a recruiter can see
  the exact resume quote behind each judgement and whether it was verified.
- 100% of candidate reports contain resume evidence (verified in the evaluation
  script).

## 6. Interview intelligence — consent by design (§11)

Post-interview transcript analysis is **refused** unless all four are true:
candidate notified & consented, interviewer aware, transcription enabled in the
meeting platform, and client tenant/administrator permission. The agent never
records or analyses an interview covertly, and any resulting evaluation requires
**human review before it is added to the record or shared.**

## 7. Data protection & retention

- **Minimisation:** only role-relevant data is used for scoring; protected
  attributes are stripped.
- **Retention:** non-hired candidate records past the configured window (default
  365 days) are automatically **flagged for deletion review** — the system never
  silently deletes personal data, and an admin can **hard-purge** a candidate
  (resume file included) on an erasure request, leaving a non-personal audit
  record.
- **Security:** JWT auth, PBKDF2 password hashing, role-based access, login
  lockout, security headers, and a complete audit trail. See `docs/SECURITY.md`.
- **Correction & access:** recruiters can correct records; role-based access
  limits who sees what (hiring managers see only approved summaries/evaluations).

## 8. Bias-audit readiness

The system is structured so a Local-Law-144-style bias audit is straightforward:
AI recommendations and human decisions are stored separately and time-stamped,
the agreement rate and per-decision reasons are queryable, and because scoring is
deterministic and evidence-linked, selection-rate/impact-ratio analysis can be run
over historical records at any time. Protected attributes are not stored in the
scoring path, so they must be joined from a separate lawful source for any such
audit — by design.

## 9. Limitations & responsible-use notes

- The AI can misread a resume; that is exactly why the recruiter verifies gaps on
  the call and can correct or override every output.
- The deterministic fallback engine (no API key / API outage) is a **screening
  aid only** — it routes everything to recruiter review and must not be treated
  as a judgement.
- The tool assists screening; it does not, and must not, make the final hiring
  decision.
