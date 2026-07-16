"""Responsible-AI reporting — turns 'audit readiness' into an actual generated
report (Brief §15: periodic review of AI recommendations vs recruiter decisions,
and the transparency needed for an EEOC / NYC Local Law 144-style bias audit).

Everything here is computed from decision data the system already stores. It does
NOT use protected attributes — those are deliberately kept out of the scoring
path — so a true protected-class impact-ratio analysis requires joining a
separate lawful data source; this report provides the decision-pattern half that
the platform can compute, plus the fairness-control health checks.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Candidate, Evaluation, Job


def _band(score: float) -> str:
    if score >= 70:
        return "70-100"
    if score >= 45:
        return "45-69"
    return "0-44"


def responsible_ai_report(db: Session, job_id: int | None = None) -> dict:
    query = db.query(Candidate)
    if job_id:
        query = query.filter(Candidate.job_id == job_id)
    candidates = query.all()
    evaluated = [c for c in candidates if c.evaluations]
    n = len(evaluated)

    rec_counts = {"shortlist": 0, "recruiter_review": 0, "do_not_shortlist": 0}
    band_counts: dict[str, int] = {"70-100": 0, "45-69": 0, "0-44": 0}
    reports_with_evidence = 0
    negatives = 0
    negatives_without_explanation = 0

    for c in evaluated:
        ev: Evaluation = c.evaluations[0]
        rec_counts[ev.recommendation] = rec_counts.get(ev.recommendation, 0) + 1
        band_counts[_band(ev.overall_score)] += 1
        if any(r.get("evidence") for r in ev.criterion_results):
            reports_with_evidence += 1
        if ev.recommendation == "do_not_shortlist":
            negatives += 1
            if not (ev.explanation or "").strip():
                negatives_without_explanation += 1

    # AI vs recruiter agreement on decided candidates.
    decided = [c for c in evaluated if c.recruiter_decision in ("shortlist", "reject")]
    agree = 0
    ai_shortlist_recruiter_reject = 0   # AI said shortlist, human rejected (over-selection)
    ai_reject_recruiter_shortlist = 0   # AI said reject, human shortlisted (missed by AI)
    for c in decided:
        rec = c.evaluations[0].recommendation
        if c.recruiter_decision == "shortlist" and rec == "shortlist":
            agree += 1
        elif c.recruiter_decision == "reject" and rec == "do_not_shortlist":
            agree += 1
        elif c.recruiter_decision == "reject" and rec == "shortlist":
            ai_shortlist_recruiter_reject += 1
        elif c.recruiter_decision == "shortlist" and rec == "do_not_shortlist":
            ai_reject_recruiter_shortlist += 1

    flagged = [c for c in candidates if c.flagged_for_review]

    def pct(a, b):
        return round(100 * a / b, 1) if b else None

    return {
        "scope": "single job" if job_id else "all jobs",
        "candidates_evaluated": n,
        "recommendation_distribution": rec_counts,
        "selection_rate_shortlist_pct": pct(rec_counts["shortlist"], n),
        "score_band_distribution": band_counts,
        # Fairness-control health checks (targets from the brief)
        "reports_with_evidence_pct": pct(reports_with_evidence, n),        # target 100
        "negatives_without_explanation": negatives_without_explanation,     # target 0
        "negatives_without_explanation_pct": pct(negatives_without_explanation, negatives),
        # AI vs human oversight
        "decided_candidates": len(decided),
        "ai_recruiter_agreement_pct": pct(agree, len(decided)),            # target >=80
        "ai_overselection_count": ai_shortlist_recruiter_reject,
        "ai_missed_count": ai_reject_recruiter_shortlist,                  # recall risk — most important
        # Random fairness review of rejections
        "flagged_for_review": len(flagged),
        "flagged_still_open": sum(1 for c in flagged if c.flagged_for_review),
        # Explicit honesty about the LL144 impact-ratio requirement
        "protected_class_impact_ratio": None,
        "impact_ratio_note": (
            "Protected characteristics are deliberately excluded from the scoring "
            "path, so a protected-class impact ratio (NYC LL144 four-fifths rule) "
            "must be computed by joining decisions to a separate lawful data source. "
            "The decision-pattern and fairness-control metrics above are what the "
            "platform can compute directly and are the ongoing 'periodic review' "
            "control required by the brief."
        ),
        "health": {
            "evidence_coverage_ok": pct(reports_with_evidence, n) == 100.0 if n else True,
            "explanation_coverage_ok": negatives_without_explanation == 0,
            "agreement_ok": (pct(agree, len(decided)) or 0) >= 80 if decided else None,
        },
    }
