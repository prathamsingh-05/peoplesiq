"""Tests for demonstrated-scope detection and level alignment
(app.services.seniority_signals) — the title-inflation defence. Pure
functions, no AI, no DB."""
from app.services.seniority_signals import (
    assess_level_alignment, scope_block, scope_signals,
)

_JUNIOR = """
Assisted the senior developer with bug fixes. Supported the team during releases.
Participated in code reviews as part of a team. Internship at a startup.
"""
_EXECUTOR = """
Developed and maintained REST APIs. Implemented new reporting features.
Wrote unit tests and documented the release process. Configured build jobs.
"""
_OWNER = """
Owned the billing service end to end. Led the migration off the legacy stack and
architected the replacement. Designed the retry strategy and independently
delivered it. Scaled the pipeline to handle 3 million requests per day.
"""
_MANAGER = """
Managed a team of 6 engineers and mentored two juniors. Hired and onboarded new
team members, ran performance reviews, and owned a budget of 40 lakh. Set the
roadmap and drove technical direction across the department.
"""


def test_detects_execution_scope():
    assert scope_signals(_EXECUTOR)["demonstrated_scope"] == "executed"


def test_detects_ownership_scope():
    assert scope_signals(_OWNER)["demonstrated_scope"] == "owned"


def test_detects_org_scope():
    assert scope_signals(_MANAGER)["demonstrated_scope"] == "org_scope"


def test_strongest_tier_wins_not_the_most_frequent():
    # Heavy execution language plus a little genuine ownership language should
    # register ownership — frequency must not drown out the stronger signal.
    text = (_EXECUTOR * 5) + " Owned the payments module end to end and architected it."
    assert scope_signals(text)["demonstrated_scope"] == "owned"


def test_counts_quantified_scale_claims():
    signals = scope_signals(
        "Supported 500+ users across 3 regions, processed 12000 transactions."
    )
    assert signals["scale_claim_count"] >= 3


def test_empty_resume_yields_no_scope():
    signals = scope_signals("")
    assert signals["demonstrated_scope"] is None
    assert signals["scale_claim_count"] == 0


def test_alignment_matches_when_scope_fits_the_tier():
    result = assess_level_alignment(_OWNER, "senior")
    assert result["alignment"] == "matches"


def test_alignment_above_is_framed_as_a_conversation_not_a_penalty():
    result = assess_level_alignment(_MANAGER, "entry")
    assert result["alignment"] == "above"
    # Must offer under-titling as an equally likely explanation, and must not
    # read as a mark against the candidate.
    assert "under-titled" in result["note"]
    assert "not treat it as a mark against them" in result["note"]


def test_alignment_below_is_framed_as_verify_not_disqualify():
    result = assess_level_alignment(_EXECUTOR, "lead_plus")
    assert result["alignment"] == "below"
    assert "under-describe real ownership" in result["note"]
    assert "rather than as proof" in result["note"]


def test_no_target_when_job_has_no_seniority_tier():
    result = assess_level_alignment(_OWNER, "")
    assert result["alignment"] == "no_target"


def test_thin_resume_is_not_reported_as_junior():
    result = assess_level_alignment("Name. Email. Skills: Excel.", "senior")
    assert result["demonstrated_scope"] is None
    assert result["alignment"] == "unknown"
    assert "not evidence of a junior candidate" in result["note"]


def test_scope_block_forbids_scoring_the_mismatch():
    block = scope_block(assess_level_alignment(_MANAGER, "entry"))
    assert "must never itself lower the evidence-based score" in block
    assert "not from job titles" in block


def test_scope_block_empty_when_no_scope_detected():
    assert scope_block(assess_level_alignment("", "senior")) == ""
    assert scope_block({}) == ""
