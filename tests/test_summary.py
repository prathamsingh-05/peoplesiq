"""Unit tests for the HM-summary formatting (app.services.summary) — pure
function, no AI, no DB."""
from app.services.summary import format_profile


def _content(**overrides):
    base = {
        "candidate_name": "Jane Doe", "candidate_code": "CAND-00001",
        "job_title": "Backend Engineer", "client": "OculusIT",
        "current_role_and_employer": "Engineer @ Acme",
        "total_experience": "5 years", "relevant_experience": "4 years",
        "core_skills": ["Python", "Django"], "industry_client_exposure": "Fintech",
        "key_achievements": ["Shipped payments service"],
        "current_compensation": "18 LPA", "expected_compensation": "24 LPA",
        "notice_period": "30 days", "location_confirmed": True, "shift_confirmed": True,
        "recruiter_observations": "Strong communicator.",
        "areas_to_probe": ["Kubernetes depth"],
        "reason_for_recommendation": "Strong evidence across the board.",
        "ai_score": 82.0, "ai_recommendation": "shortlist",
        "career_pattern": "Steady growth from junior to senior engineer over 5 years.",
        "risk_flags": ["Two short stints under a year — worth asking about."],
    }
    base.update(overrides)
    return base


def test_format_profile_includes_career_pattern_and_risk_flags():
    text = format_profile(_content())
    assert "Career pattern (who this person is, as a professional):" in text
    assert "Steady growth from junior to senior engineer" in text
    assert "Worth a conversation (not marks against the candidate" in text
    assert "Two short stints under a year" in text


def test_format_profile_handles_missing_career_pattern_and_risk_flags():
    text = format_profile(_content(career_pattern="", risk_flags=[]))
    assert "Career pattern (who this person is, as a professional):\n  —" in text
    assert "Worth a conversation" in text  # section header always present
