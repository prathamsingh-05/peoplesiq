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


# A criterion needs to show up in at least this many disagreement cases
# before it's worth surfacing as a pattern — one-off noise isn't a
# calibration signal.
_MIN_PATTERN_COUNT = 2


def _disagreement_criteria(cases: list[Candidate]) -> list[dict]:
    """For a set of AI/recruiter disagreement cases, tally which criteria
    most often show weak evidence (no_evidence/contradictory) in those
    specific evaluations. This turns a vague 'agreement is low' number into
    something actionable: which scorecard criteria are actually driving the
    disagreement, and might be miscalibrated (weighted too harshly for
    candidates recruiters still want, or too leniently for gaps recruiters
    won't accept) — a real recruiter-override learning loop, computed
    entirely from decision data the system already stores."""
    counts: dict[str, int] = {}
    for c in cases:
        if not c.evaluations:
            continue
        for r in (c.evaluations[0].criterion_results or []):
            if r.get("status") in ("no_evidence", "contradictory"):
                counts[r["name"]] = counts.get(r["name"], 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [{"criterion": name, "count": count} for name, count in ranked if count >= _MIN_PATTERN_COUNT][:5]


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
    overselected: list[Candidate] = []   # AI said shortlist, human rejected (over-selection)
    missed: list[Candidate] = []         # AI said reject, human shortlisted (missed by AI)
    for c in decided:
        rec = c.evaluations[0].recommendation
        if c.recruiter_decision == "shortlist" and rec == "shortlist":
            agree += 1
        elif c.recruiter_decision == "reject" and rec == "do_not_shortlist":
            agree += 1
        elif c.recruiter_decision == "reject" and rec == "shortlist":
            overselected.append(c)
        elif c.recruiter_decision == "shortlist" and rec == "do_not_shortlist":
            missed.append(c)
    ai_shortlist_recruiter_reject = len(overselected)
    ai_reject_recruiter_shortlist = len(missed)

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
        # Recruiter-override learning loop: which specific scorecard criteria
        # keep showing up as weak evidence in the cases recruiters overrode,
        # broken out by direction — a concrete "what to recalibrate" signal
        # instead of just an aggregate agreement percentage.
        "ai_missed_common_criteria": _disagreement_criteria(missed),
        "ai_overselected_common_criteria": _disagreement_criteria(overselected),
        "override_pattern_note": (
            "ai_missed_common_criteria lists criteria the AI marked as weak evidence on "
            "candidates recruiters shortlisted anyway — a recurring criterion here is a "
            "candidate for lowering its weight or mandatory status. "
            "ai_overselected_common_criteria lists criteria marked weak on candidates the "
            "AI shortlisted but recruiters rejected — a recurring criterion here suggests "
            "its weight may be too low relative to how much recruiters actually care about it."
        ),
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
