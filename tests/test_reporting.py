"""Unit tests for the recruiter-override learning-loop signal in
app.services.reporting — pure function, no DB, using duck-typed fakes for
Candidate/Evaluation the same way test_scoring_principles.py fakes
Evaluation for pool_insight/top_differentiators."""
from types import SimpleNamespace

from app.services.reporting import _disagreement_criteria


def _fake_candidate(criterion_results):
    evaluation = SimpleNamespace(criterion_results=criterion_results)
    return SimpleNamespace(evaluations=[evaluation])


def test_disagreement_criteria_needs_at_least_two_occurrences():
    cases = [_fake_candidate([{"name": "Kubernetes experience", "status": "no_evidence"}])]
    assert _disagreement_criteria(cases) == []


def test_disagreement_criteria_surfaces_recurring_weak_evidence():
    cases = [
        _fake_candidate([{"name": "Kubernetes experience", "status": "no_evidence"},
                        {"name": "Python", "status": "confirmed"}]),
        _fake_candidate([{"name": "Kubernetes experience", "status": "no_evidence"},
                        {"name": "Python", "status": "confirmed"}]),
        _fake_candidate([{"name": "Kubernetes experience", "status": "contradictory"}]),
    ]
    result = _disagreement_criteria(cases)
    assert result[0] == {"criterion": "Kubernetes experience", "count": 3}
    # Python was confirmed every time — never counted as weak evidence.
    assert not any(r["criterion"] == "Python" for r in result)


def test_disagreement_criteria_empty_for_no_cases():
    assert _disagreement_criteria([]) == []


def test_disagreement_criteria_ignores_candidates_without_evaluations():
    cases = [SimpleNamespace(evaluations=[]), SimpleNamespace(evaluations=[])]
    assert _disagreement_criteria(cases) == []
