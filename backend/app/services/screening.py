"""Stage 3-5 — Evidence-based resume-to-scorecard evaluation engine.

What makes this engine trustworthy (informed by the multi-agent screening
literature and NYC LL144 / EEOC-style controls):

1.  Fairness first: the model only ever sees the *redacted* resume text
    (see fairness.py) and the fairness rules are part of the system prompt.
2.  Evidence, not keywords: every criterion result must quote the resume;
    quotes are verified against the source text and marked
    `evidence_verified` — unverifiable quotes are downgraded, which prunes
    hallucinations.
3.  Five evidence states per criterion: confirmed / partial / no_evidence /
    contradictory / needs_verification.
4.  Deterministic scoring: the LLM judges evidence per criterion; the final
    0-100 score is computed *in code* from criterion states and scorecard
    weights, so identical inputs always produce identical scores and no
    criterion can be silently ignored.
5.  Consistency: results are cached by sha256(redacted_text + scorecard), so
    re-screening the same resume against the same scorecard returns the same
    result (brief §13).
6.  Recall-biased: borderline candidates go to `recruiter_review`, never
    straight to rejection — the most expensive error is losing a strong
    candidate.
7.  Guardrails: a `do_not_shortlist` without an explanation is downgraded to
    review; employment gaps and formatting can never cause rejection.
"""
from __future__ import annotations

import hashlib
import json
import re

from ..models import Evaluation, Scorecard
from . import llm
from .fairness import FAIRNESS_RULES_PROMPT

EVIDENCE_STATES = ["confirmed", "partial", "no_evidence", "contradictory", "needs_verification"]

# Score contribution of each evidence state (fraction of criterion weight).
STATE_SCORES = {
    "confirmed": 1.0,
    "partial": 0.55,
    "needs_verification": 0.35,
    "no_evidence": 0.0,
    "contradictory": 0.0,
}

SHORTLIST_THRESHOLD = 70.0
REVIEW_THRESHOLD = 45.0

EVALUATION_SCHEMA = {
    "type": "object",
    "properties": {
        "criterion_results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion_id": {"type": "integer"},
                    "status": {"type": "string", "enum": EVIDENCE_STATES},
                    "evidence": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["criterion_id", "status", "evidence", "notes"],
                "additionalProperties": False,
            },
        },
        "relevant_experience_years": {"type": "number"},
        "key_strengths": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "relevant_projects": {"type": "array", "items": {"type": "string"}},
        "missing_information": {"type": "array", "items": {"type": "string"}},
        "inconsistencies": {"type": "array", "items": {"type": "string"}},
        "verification_questions": {"type": "array", "items": {"type": "string"}},
        "executive_summary": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": [
        "criterion_results", "relevant_experience_years", "key_strengths", "gaps",
        "risk_flags", "relevant_projects", "missing_information", "inconsistencies",
        "verification_questions", "executive_summary", "confidence",
    ],
    "additionalProperties": False,
}

_SYSTEM = f"""You are the screening engine of the People IQ Recruiter Agent, a
decision-SUPPORT system. You assess one resume against an approved job scorecard.
A human recruiter makes every final decision; your job is rigorous, evidence-linked
analysis.

{FAIRNESS_RULES_PROMPT}

EVIDENCE RULES:
- For each criterion, quote the exact resume text (verbatim, <= 220 characters) that
  supports your status. If no text supports it, evidence must be an empty string.
- Status meanings:
  confirmed          — explicit, dated, contextual evidence in the resume
  partial            — related evidence that does not fully satisfy the criterion
  no_evidence        — nothing in the resume addresses the criterion
  contradictory      — the resume contains statements that conflict with the criterion
                        or with each other
  needs_verification — a claim exists but is vague/unverifiable from the resume alone
                        (also use for location/shift/notice-period items a resume
                        rarely proves)
- A criterion does not require an exact keyword match. If the resume demonstrates the
  underlying capability in different words or via a closely adjacent tool/technology
  (e.g. the criterion asks about "cloud infrastructure" and the resume shows AWS
  work), mark it confirmed or partial on that evidence — do not mark no_evidence on a
  pure terminology technicality when the substance is genuinely present.
- relevant_experience_years = years in roles genuinely relevant to THIS job, computed
  from the dated work history (not the candidate's own total claim).
- missing_information: facts the recruiter must collect (compensation, notice period, etc.).
- inconsistencies: date overlaps, conflicting titles, impossible claims.
- verification_questions: specific things a recruiter should verify on a call.
- executive_summary: 3-5 sentences a busy recruiter can read in 15 seconds.
- confidence: high only when the resume is detailed and evidence is unambiguous."""


def input_hash(redacted_text: str, scorecard: Scorecard) -> str:
    payload = redacted_text + "||" + json.dumps(
        [
            {
                "id": c.id, "cat": c.category, "name": c.name,
                "w": c.weight, "m": c.is_mandatory,
            }
            for c in scorecard.criteria
        ],
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def evaluate(redacted_text: str, scorecard: Scorecard, job_title: str) -> dict:
    """Run the evaluation. Returns a dict ready to persist on Evaluation."""
    try:
        raw = _llm_evaluate(redacted_text, scorecard, job_title)
        engine = "llm"
    except llm.LLMUnavailable:
        raw = _deterministic_evaluate(redacted_text, scorecard)
        engine = "deterministic"

    results = _reconcile_criteria(raw.get("criterion_results", []), scorecard, redacted_text)
    score, mandatory_status = _compute_score(results)
    recommendation, explanation = _recommend(
        score, mandatory_status, results, raw, engine
    )

    return {
        "overall_score": round(score, 1),
        "mandatory_status": mandatory_status,
        "relevant_experience_years": float(raw.get("relevant_experience_years") or 0),
        "key_strengths": raw.get("key_strengths", [])[:8],
        "gaps": raw.get("gaps", [])[:8],
        "risk_flags": raw.get("risk_flags", [])[:8],
        "recommendation": recommendation,
        "confidence": raw.get("confidence", "low"),
        "executive_summary": raw.get("executive_summary", ""),
        "explanation": explanation,
        "criterion_results": results,
        "relevant_projects": raw.get("relevant_projects", [])[:8],
        "missing_information": raw.get("missing_information", [])[:10],
        "inconsistencies": raw.get("inconsistencies", [])[:8],
        "verification_questions": raw.get("verification_questions", [])[:10],
        "engine": engine,
    }


def _llm_evaluate(redacted_text: str, scorecard: Scorecard, job_title: str) -> dict:
    criteria_block = "\n".join(
        f"- criterion_id={c.id} | category={c.category} | mandatory={c.is_mandatory} | "
        f"weight={c.weight} | {c.name}: {c.description}"
        for c in scorecard.criteria
    )
    user = f"""Job title: {job_title}

Approved scorecard criteria:
{criteria_block}

Resume (protected attributes redacted):
<resume>
{redacted_text[:30000]}
</resume>

Assess every criterion_id exactly once."""
    return llm.structured_call(
        system=_SYSTEM, user_content=user, schema=EVALUATION_SCHEMA, max_tokens=8000
    )


# ---------------------------------------------------------------------------
# Post-processing: verification, scoring, recommendation
# ---------------------------------------------------------------------------
def _normalise_for_match(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _verify_evidence(evidence: str, source: str) -> bool:
    """A quote counts as verified when it (or 80% of its 5-word shingles)
    appears in the source text — tolerant of whitespace/punctuation drift."""
    if not evidence:
        return False
    ev, src = _normalise_for_match(evidence), _normalise_for_match(source)
    if ev in src:
        return True
    words = ev.split()
    if len(words) < 5:
        return False
    shingles = [" ".join(words[i:i + 5]) for i in range(len(words) - 4)]
    hits = sum(1 for s in shingles if s in src)
    return hits / len(shingles) >= 0.8


def _reconcile_criteria(raw_results: list, scorecard: Scorecard, source_text: str) -> list:
    """Ensure every scorecard criterion has exactly one result; verify quotes;
    downgrade unverifiable 'confirmed' claims (hallucination pruning)."""
    by_id = {c.id: c for c in scorecard.criteria}
    seen: dict[int, dict] = {}
    for item in raw_results:
        cid = item.get("criterion_id")
        if cid not in by_id or cid in seen:
            continue
        criterion = by_id[cid]
        status = item.get("status", "no_evidence")
        if status not in STATE_SCORES:
            status = "no_evidence"
        evidence = (item.get("evidence") or "")[:400]
        verified = _verify_evidence(evidence, source_text)
        notes = item.get("notes", "")
        if status in ("confirmed", "partial") and evidence and not verified:
            status = "needs_verification"
            notes = (notes + " | Evidence quote could not be verified against the "
                             "resume text; downgraded for recruiter verification.").strip(" |")
        seen[cid] = {
            "criterion_id": cid,
            "name": criterion.name,
            "category": criterion.category,
            "is_mandatory": criterion.is_mandatory,
            "weight": criterion.weight,
            "status": status,
            "evidence": evidence,
            "evidence_verified": verified,
            "notes": notes,
        }
    # Any criterion the model skipped defaults to needs_verification (never
    # silently pass or fail).
    for cid, criterion in by_id.items():
        if cid not in seen:
            seen[cid] = {
                "criterion_id": cid,
                "name": criterion.name,
                "category": criterion.category,
                "is_mandatory": criterion.is_mandatory,
                "weight": criterion.weight,
                "status": "needs_verification",
                "evidence": "",
                "evidence_verified": False,
                "notes": "Not assessed by the engine; requires recruiter verification.",
            }
    return [seen[c.id] for c in scorecard.criteria]


# Categories the engine itself documents as "a resume rarely proves" (see the
# needs_verification definition in _SYSTEM below) — these belong in the call-
# verification list, not the numeric score. A candidate isn't a worse fit
# because their resume doesn't restate the office location or shift pattern.
SCORE_EXCLUDED_CATEGORIES = {"location_hours"}


def _compute_score(results: list) -> tuple[float, str]:
    scored = [r for r in results if r["category"] not in SCORE_EXCLUDED_CATEGORIES]
    if not scored:
        scored = results
    total_weight = sum(r["weight"] for r in scored) or 1.0
    earned = sum(r["weight"] * STATE_SCORES[r["status"]] for r in scored)
    score = 100.0 * earned / total_weight

    mandatory = [r for r in results if r["is_mandatory"]]
    if not mandatory:
        mandatory_status = "met"
    else:
        states = {r["status"] for r in mandatory}
        if states <= {"confirmed"}:
            mandatory_status = "met"
        elif states & {"no_evidence", "contradictory"}:
            mandatory_status = "not_met"
        else:
            mandatory_status = "partially_met"
    return score, mandatory_status


def _recommend(score: float, mandatory_status: str, results: list, raw: dict,
               engine: str) -> tuple[str, str]:
    reasons: list[str] = []
    if mandatory_status == "not_met":
        failed = [r["name"] for r in results
                  if r["is_mandatory"] and r["status"] in ("no_evidence", "contradictory")]
        recommendation = "do_not_shortlist"
        reasons.append(
            "Mandatory criteria without supporting evidence: " + "; ".join(failed) + "."
        )
    elif score >= SHORTLIST_THRESHOLD and mandatory_status == "met":
        recommendation = "shortlist"
        confirmed = [r["name"] for r in results if r["status"] == "confirmed"][:5]
        reasons.append(
            f"Weighted evidence score {score:.0f}/100 with all mandatory criteria met. "
            + ("Confirmed: " + "; ".join(confirmed) + "." if confirmed else "")
        )
    elif score >= REVIEW_THRESHOLD or mandatory_status == "partially_met":
        recommendation = "recruiter_review"
        pending = [r["name"] for r in results if r["status"] == "needs_verification"][:5]
        reasons.append(
            f"Weighted evidence score {score:.0f}/100; "
            f"mandatory criteria {mandatory_status.replace('_', ' ')}. "
            + ("Verify on the screening call: " + "; ".join(pending) + "."
               if pending else "")
        )
    else:
        recommendation = "do_not_shortlist"
        missing = [r["name"] for r in results
                   if r["status"] in ("no_evidence", "contradictory")][:6]
        reasons.append(
            f"Weighted evidence score {score:.0f}/100 — the resume shows no evidence for "
            "most weighted criteria: " + "; ".join(missing) + "."
        )

    # Recall bias: a low-confidence or offline-engine negative goes to human
    # review instead — the system must not silently discard a possible fit.
    if recommendation == "do_not_shortlist":
        if raw.get("confidence") == "low" and mandatory_status != "not_met":
            recommendation = "recruiter_review"
            reasons.append("Engine confidence is low, so the candidate is routed to "
                           "recruiter review rather than rejection.")
        elif engine == "deterministic" and mandatory_status != "not_met":
            recommendation = "recruiter_review"
            reasons.append("Deterministic (offline) engine cannot reject on nuance; "
                           "routed to recruiter review.")

    explanation = " ".join(reasons)
    # Absolute guardrail: no negative recommendation without an explanation.
    if recommendation == "do_not_shortlist" and not explanation.strip():
        recommendation = "recruiter_review"
        explanation = ("Downgraded to recruiter review: a negative recommendation "
                       "without explanation is not permitted.")
    return recommendation, explanation


# ---------------------------------------------------------------------------
# Deterministic fallback engine (no API key / API outage)
# ---------------------------------------------------------------------------
def _deterministic_evaluate(text: str, scorecard: Scorecard) -> dict:
    lowered = text.lower()
    results = []
    for criterion in scorecard.criteria:
        tokens = [t for t in re.split(r"[^a-z0-9+#.]+", criterion.name.lower()) if len(t) > 2]
        hits = [t for t in tokens if t in lowered]
        if tokens and len(hits) == len(tokens):
            status, evidence = "partial", _find_snippet(text, hits[0])
        elif hits:
            status, evidence = "needs_verification", _find_snippet(text, hits[0])
        else:
            status, evidence = "no_evidence", ""
        results.append({
            "criterion_id": criterion.id, "status": status,
            "evidence": evidence,
            "notes": "Deterministic engine (keyword-presence heuristic only; treat as a "
                     "screening aid, not a judgement).",
        })
    years_match = re.search(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*years?", lowered)
    return {
        "criterion_results": results,
        "relevant_experience_years": float(years_match.group(1)) if years_match else 0.0,
        "key_strengths": [],
        "gaps": [],
        "risk_flags": ["Evaluated by the offline deterministic engine — "
                       "recruiter review required."],
        "relevant_projects": [],
        "missing_information": ["Full AI evaluation pending (offline mode)."],
        "inconsistencies": [],
        "verification_questions": [],
        "executive_summary": "Screened by the deterministic offline engine. Statuses reflect "
                             "keyword presence only and every result requires recruiter review.",
        "confidence": "low",
    }


def _find_snippet(text: str, token: str, width: int = 90) -> str:
    idx = text.lower().find(token.lower())
    if idx < 0:
        return ""
    start = max(0, idx - width // 2)
    return text[start:start + width].replace("\n", " ").strip()


def leaderboard_row(evaluation: Evaluation, rank: int, candidate) -> dict:
    """Stage 4 leaderboard columns exactly as specified in the brief."""
    return {
        "rank": rank,
        "candidate_id": candidate.id,
        "candidate_code": candidate.candidate_code,
        "candidate": candidate.full_name or candidate.resume_filename,
        "overall_match": evaluation.overall_score,
        "mandatory_criteria": evaluation.mandatory_status,
        "relevant_experience_years": evaluation.relevant_experience_years,
        "key_strengths": evaluation.key_strengths,
        "gaps": evaluation.gaps,
        "risk_flags": evaluation.risk_flags,
        "recommendation": evaluation.recommendation,
        "confidence": evaluation.confidence,
        "evidence": [
            {"criterion": r["name"], "status": r["status"], "evidence": r["evidence"]}
            for r in evaluation.criterion_results
            if r.get("evidence")
        ][:6],
        "recruiter_decision": candidate.recruiter_decision,
        "status": candidate.status,
        "flagged_for_review": candidate.flagged_for_review,
    }
