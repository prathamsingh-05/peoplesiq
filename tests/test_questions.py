"""Unit tests for the deterministic screening-question fallback
(app.services.questions._fallback_questions) — no AI, no DB."""
from types import SimpleNamespace

from app.services.questions import _fallback_questions


def _job(**overrides):
    base = dict(title="Backend Engineer", client_name="OculusIT", location="Gurugram",
                work_model="hybrid", working_hours="10am-7pm IST",
                notice_period_preference="30 days")
    base.update(overrides)
    return SimpleNamespace(**base)


def _evaluation(**overrides):
    base = dict(executive_summary="", gaps=[], risk_flags=[], criterion_results=[])
    base.update(overrides)
    return SimpleNamespace(**base)


def test_fallback_questions_includes_risk_flag_follow_up():
    evaluation = _evaluation(
        risk_flags=["Two short stints under a year — worth asking about."],
    )
    questions = _fallback_questions(SimpleNamespace(), evaluation, _job())
    risk_questions = [q for q in questions if "short stints" in q["question"]]
    assert len(risk_questions) == 1
    assert risk_questions[0]["category"] == "motivation"


def test_fallback_questions_no_risk_flag_question_when_none_present():
    evaluation = _evaluation()
    questions = _fallback_questions(SimpleNamespace(), evaluation, _job())
    assert not any("worth asking you about directly" in q["question"] for q in questions)


def test_fallback_questions_still_includes_eligibility_and_motivation_baseline():
    evaluation = _evaluation()
    questions = _fallback_questions(SimpleNamespace(), evaluation, _job())
    categories = {q["category"] for q in questions}
    assert "eligibility" in categories
    assert "motivation" in categories
