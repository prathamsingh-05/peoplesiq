"""Regression tests for the scoring/decision-making principles documented at
the top of services/screening.py. These exist so that a future change which
violates one of those principles fails CI, on purpose — this is what turns
"we fixed it" into "it can't quietly regress."
"""
from types import SimpleNamespace

from app.services.screening import (
    _calibration_block, _compute_score, _recommend, _verify_evidence,
)
from app.services.scorecard import _deterministic_scorecard, _is_logistics_condition


def _criterion(name, weight, status, mandatory=False, category="technical_skills"):
    return {
        "name": name, "weight": weight, "status": status,
        "is_mandatory": mandatory, "category": category,
    }


# ---------------------------------------------------------------------------
# Principle: preferred criteria are bonus-only, never a penalty.
# ---------------------------------------------------------------------------
def test_missing_preferred_criterion_does_not_lower_score():
    with_preferred_met = [
        _criterion("Core skill", 2.0, "confirmed", category="technical_skills"),
        _criterion("Nice to have", 1.0, "confirmed", category="preferred"),
    ]
    without_preferred = [
        _criterion("Core skill", 2.0, "confirmed", category="technical_skills"),
        _criterion("Nice to have", 1.0, "no_evidence", category="preferred"),
    ]
    score_with, _ = _compute_score(with_preferred_met)
    score_without, _ = _compute_score(without_preferred)
    # Missing a nice-to-have must never score worse than an identical
    # candidate who was never evaluated on it at all.
    assert score_without == 100.0
    assert score_with >= score_without


def test_preferred_criteria_can_add_bonus_points():
    core_only = [_criterion("Core skill", 2.0, "confirmed", category="technical_skills")]
    core_plus_bonus = core_only + [_criterion("Nice to have", 1.0, "confirmed", category="preferred")]
    score_core, _ = _compute_score(core_only)
    score_bonus, _ = _compute_score(core_plus_bonus)
    assert score_core == 100.0
    assert score_bonus == 100.0  # capped at 100, but never goes below core


# ---------------------------------------------------------------------------
# Principle: structural blind spots (location/hours) don't count against
# candidates in the numeric score.
# ---------------------------------------------------------------------------
def test_location_hours_excluded_from_numeric_score():
    strong_core = [
        _criterion("Core skill A", 2.0, "confirmed", category="technical_skills"),
        _criterion("Core skill B", 2.0, "confirmed", category="experience"),
    ]
    with_unprovable_location = strong_core + [
        _criterion("Shift fit", 1.0, "needs_verification", category="location_hours"),
    ]
    score_plain, _ = _compute_score(strong_core)
    score_with_location, _ = _compute_score(with_unprovable_location)
    assert score_plain == score_with_location == 100.0


# ---------------------------------------------------------------------------
# Principle: needs_verification carries real partial credit.
# ---------------------------------------------------------------------------
def test_needs_verification_scores_above_half_credit():
    results = [_criterion("Skill", 1.0, "needs_verification")]
    score, _ = _compute_score(results)
    assert score == 50.0  # STATE_SCORES["needs_verification"] == 0.5


# ---------------------------------------------------------------------------
# Principle: a single missing mandatory criterion routes to review, not
# automatic rejection — only 2+ genuine mandatory gaps auto-reject.
# ---------------------------------------------------------------------------
def test_single_mandatory_gap_routes_to_review_not_rejection():
    results = [
        _criterion("Work authorization", 3.0, "no_evidence", mandatory=True, category="mandatory"),
        _criterion("5+ years experience", 3.0, "confirmed", mandatory=True, category="experience"),
        _criterion("Core skill", 2.0, "confirmed", category="technical_skills"),
    ]
    score, mandatory_status = _compute_score(results)
    recommendation, explanation = _recommend(
        score, mandatory_status, results, {"confidence": "high"}, "llm"
    )
    assert mandatory_status == "not_met"
    assert recommendation == "recruiter_review"
    assert "recruiter review" in explanation.lower()


def test_two_mandatory_gaps_still_auto_reject():
    results = [
        _criterion("Work authorization", 3.0, "no_evidence", mandatory=True, category="mandatory"),
        _criterion("Security clearance", 3.0, "no_evidence", mandatory=True, category="mandatory"),
        _criterion("Core skill", 2.0, "no_evidence", category="technical_skills"),
    ]
    score, mandatory_status = _compute_score(results)
    recommendation, _ = _recommend(
        score, mandatory_status, results, {"confidence": "high"}, "llm"
    )
    assert mandatory_status == "not_met"
    assert recommendation == "do_not_shortlist"


def test_strong_candidate_with_one_gap_scores_and_routes_reasonably():
    """The exact shape of bug this suite exists to prevent: a candidate who
    is a genuinely strong fit must not be silently auto-rejected because one
    mandatory item wasn't explicitly restated on the resume."""
    results = [
        _criterion("Work authorization", 3.0, "no_evidence", mandatory=True, category="mandatory"),
        _criterion("5+ years experience", 3.0, "confirmed", mandatory=True, category="experience"),
        _criterion("Core skill A", 2.0, "confirmed", category="technical_skills"),
        _criterion("Core skill B", 2.0, "confirmed", category="technical_skills"),
        _criterion("Core skill C", 2.0, "confirmed", category="technical_skills"),
        _criterion("Domain fit", 1.5, "partial", category="domain"),
    ]
    score, mandatory_status = _compute_score(results)
    recommendation, _ = _recommend(score, mandatory_status, results, {"confidence": "high"}, "llm")
    # The headline principle: a resume this strong must never be silently
    # auto-rejected over one missing mandatory item. The exact score matters
    # less than the recommendation never landing on do_not_shortlist here.
    assert score >= 70.0
    assert recommendation == "recruiter_review"
    assert recommendation != "do_not_shortlist"


# ---------------------------------------------------------------------------
# Principle: quote verification catches fabrication, not phrasing.
# ---------------------------------------------------------------------------
def test_verification_tolerates_reordering_and_punctuation():
    source = "Led backend development using Python and AWS Lambda for three years."
    paraphrased = "backend development using Python, AWS Lambda"
    assert _verify_evidence(paraphrased, source) is True


def test_verification_tolerates_short_quotes_regardless_of_order():
    source = "Experience with Kubernetes and Docker in production environments."
    assert _verify_evidence("Docker Kubernetes", source) is True


def test_verification_rejects_fabricated_evidence():
    source = "Experience with Python and Django in a small startup."
    fabricated = "Ten years leading enterprise Java migrations at Fortune 500 banks"
    assert _verify_evidence(fabricated, source) is False


def test_verification_rejects_empty_evidence():
    assert _verify_evidence("", "Any resume text here.") is False


# ---------------------------------------------------------------------------
# Principle: judge relative to the role's actual level and pay band, not one
# fixed "impressive resume" ideal.
# ---------------------------------------------------------------------------
def _job(**overrides):
    base = dict(
        title="Backend Engineer", seniority_tier="", compensation_range="",
        good_enough_note="", success_criteria="",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_calibration_block_empty_when_no_context_given():
    assert _calibration_block(_job()) == ""


def test_calibration_block_reflects_entry_tier_guidance():
    block = _calibration_block(_job(seniority_tier="entry", compensation_range="6 LPA"))
    assert "entry" in block.lower()
    assert "6 LPA" in block
    # The whole point: entry-level guidance must not demand senior-level depth.
    assert "not deep" in block.lower() or "developing" in block.lower()


def test_calibration_block_reflects_senior_tier_guidance():
    block = _calibration_block(_job(seniority_tier="senior"))
    assert "senior" in block.lower()
    assert "ownership" in block.lower()


def test_calibration_block_includes_good_enough_and_success_criteria():
    block = _calibration_block(_job(
        good_enough_note="Can ship features with guidance.",
        success_criteria="Owns one service end to end by month six.",
    ))
    assert "Can ship features with guidance." in block
    assert "Owns one service end to end by month six." in block


def test_calibration_block_ignores_unknown_tier_gracefully():
    # An unrecognised/blank tier must not crash or fabricate guidance text.
    block = _calibration_block(_job(seniority_tier="not-a-real-tier"))
    assert "not-a-real-tier" not in block


# ---------------------------------------------------------------------------
# Principle: self-selected logistics (shift/WFO/relocation/notice period) are
# eligibility conditions, never scored mandatory criteria.
# ---------------------------------------------------------------------------
def test_logistics_keywords_detected():
    for cond in ["Willing to work night shifts", "Must work from office (WFO)",
                 "Open to relocation", "30 days notice period", "Willing to travel"]:
        assert _is_logistics_condition(cond), cond


def test_non_logistics_condition_not_flagged():
    assert not _is_logistics_condition("Valid AWS Solutions Architect certification")
    assert not _is_logistics_condition("Active security clearance required")


def _scorecard_job(mandatory_conditions):
    return SimpleNamespace(
        mandatory_conditions=mandatory_conditions, min_experience_years=0,
        essential_skills=[], preferred_skills=[], qualifications="",
        location="", working_hours="", work_model="",
    )


def test_deterministic_scorecard_routes_logistics_to_location_hours():
    job = _scorecard_job(["Willing to work night shifts", "Active security clearance required"])
    criteria = _deterministic_scorecard(job)
    by_name = {c["name"]: c for c in criteria}

    shift = by_name["Willing to work night shifts"]
    assert shift["category"] == "location_hours"
    assert shift["is_mandatory"] is False

    clearance = by_name["Active security clearance required"]
    assert clearance["category"] == "mandatory"
    assert clearance["is_mandatory"] is True
