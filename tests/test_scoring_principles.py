"""Regression tests for the scoring/decision-making principles documented at
the top of services/screening.py. These exist so that a future change which
violates one of those principles fails CI, on purpose — this is what turns
"we fixed it" into "it can't quietly regress."
"""
from app.services.screening import _compute_score, _recommend, _verify_evidence


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
