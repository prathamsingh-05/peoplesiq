# What Makes the Best AI Recruitment Agent — Research & Design Principles

This system was designed by studying how the leading AI recruitment platforms
work, what the academic literature says about reliable LLM resume screening, and
what regulators require of automated employment decision tools. The principles
below are the ones we deliberately built in — with a note on where each lives in
the code.

## 1. Skills & evidence over keywords (Eightfold-style matching)

The best platforms match on **demonstrated capability and trajectory**, not
keyword overlap. Keyword-count ranking is exactly the failure mode the brief
warns against. → We score **weighted, dated, contextual evidence per criterion**,
and explicitly ignore keyword frequency. (`services/screening.py`)

## 2. Structured, schema-constrained AI output

Off-the-shelf LLMs drift into narrative and hallucinate on varied resume formats.
The research consensus (and our design) is to **force structured output and
validate it**. → Every AI call uses a strict JSON schema
(`output_config.format`) and the result is parsed and reconciled in code.
(`services/llm.py`, all `*_SCHEMA` definitions)

## 3. Hallucination pruning via evidence verification

A leading technique from the resume-parsing literature: **discard any extracted
claim whose supporting text can't be found in the source document.** → Every
evidence quote is verified against the resume (exact or ≥80% shingle match);
unverifiable "confirmed"/"partial" claims are automatically downgraded to
"needs verification." (`screening._verify_evidence`, `_reconcile_criteria`)

## 4. Multi-signal, weighted scoring with a deterministic aggregator

The multi-agent screening frameworks separate **judging evidence** (the model)
from **computing the score** (deterministic code) so results are stable and every
criterion is accounted for. → The LLM judges each criterion; the 0–100 score is
computed in code from evidence states and weights. Identical inputs → identical
scores. (`screening._compute_score`)

## 5. Recall bias — never lose a strong candidate

The brief's most important metric is strong-candidate recall. The best systems
send borderline candidates to human review rather than auto-rejecting. → Low
confidence or offline negatives are routed to `recruiter_review`; only clear
mandatory failures reach `do_not_shortlist`. (`screening._recommend`)

## 6. Human-in-the-loop as a product primitive (Paradox/HireVue lesson)

Successful deployments keep a human accountable and make the AI's role
*assistive*. Over-automation is where these tools get into legal and PR trouble.
→ Eight enforced approval gates; AI recommendations and human decisions stored
separately; the recruiter can override everything.

## 7. Fairness & compliance by construction (EEOC / NYC LL144)

Bias audits hinge on the four-fifths / impact-ratio rule, and regulators expect
protected attributes to be kept out of the decision and every adverse decision to
be explainable. → Protected attributes are redacted before scoring; gaps and
formatting can't cause rejection; every negative decision is explained; a random
sample of rejections gets human review; AI/human decisions are separable for
audit. (`services/fairness.py`, `RESPONSIBLE_AI_AND_DATA_PRIVACY.md`)

## 8. Explainability the recruiter actually reads

The best tools surface *why*, not just a number. → Every candidate has an
executive summary, a plain-language recommendation explanation, and a per-criterion
evidence table with the exact resume quote.

## 9. Conversational candidate engagement & nurture (Paradox-style)

High-volume recruiting wins on **timely, personalised, automated-but-approved
communication** and on **keeping accepted candidates warm** so they actually join.
→ AI-drafted, recruiter-approved outreach; a full offer-to-joining keep-warm
protocol with an approved content library and stop rules. (`services/emailer.py`,
`services/scheduler.py`)

## 10. Resilience & consistency as trust features

Enterprise tools must survive API hiccups and give repeatable answers. → A
deterministic fallback engine keeps screening running during outages, per-file
isolation stops one bad resume sinking a batch, and content-hash caching
guarantees consistent re-evaluation. (`services/screening.py`, `llm.py`)

## 11. Talent rediscovery — mine the base you already have

Consistently cited as the single biggest differentiator among modern platforms:
resurface previously screened candidates for each new requisition, especially
**silver medalists** (people who reached late stages but weren't selected).
Structured rediscovery is associated with ~12-day vs ~42-day time-to-fill. → For
every job, the agent searches the entire historical candidate base against the
approved scorecard, flags silver medalists, and lets the recruiter pull matches
in for full evidence-based screening. (`services/rediscovery.py`)

## 12. Turn audit-readiness into an actual audit

Regulators and recruitment leaders want a report, not a claim. → A generated
responsible-AI report computes selection rates, AI-vs-recruiter agreement, the
recall-risk (AI-missed) count, and fairness-control health checks — with an
honest note that a protected-class impact ratio requires a separate lawful data
source, because protected attributes are deliberately never in the scoring path.
(`services/reporting.py`)

## 13. Interview intelligence done ethically

Analysing interviews is valuable but fraught. The defensible approach is
**post-interview transcript analysis with explicit consent and human review** —
not covert live scoring. → Consent-gated transcript analysis producing an
independent evaluation for the hiring-manager debrief. (`services/interview.py`)

## Sources consulted

- Comparative reviews of leading AI recruiting platforms (Eightfold, HireVue,
  Paradox, hireEZ) — skills-based matching, conversational engagement, and where
  over-automation creates risk.
- Academic work on LLM resume screening: context-aware/explainable multi-agent
  frameworks, layout-aware parsing with hallucination-pruning, and structured-output
  extraction with schema validation.
- Regulatory guidance on automated employment decision tools: EEOC adverse-impact
  principles and NYC Local Law 144 bias-audit / impact-ratio requirements.
- Practitioner guidance on candidate "keep-warm" / drip nurture from offer to joining.
