"""Tests for the location/work-model roster (app.services.location_fit).

The load-bearing property: this view is operational only and must never feed
a score, rank or recommendation — location is excluded from scoring by design
(screening.py principles 8 and 12).
"""
from types import SimpleNamespace

from app.services.location_fit import candidate_location_fit, job_location_roster


def _job(**overrides):
    base = dict(location="Gurugram, India", work_model="hybrid",
                working_hours="10am-7pm IST", candidates=[])
    base.update(overrides)
    return SimpleNamespace(**base)


def _candidate(cid=1, location="", **overrides):
    base = dict(id=cid, candidate_code=f"CAND-{cid:05d}", full_name=f"Person {cid}",
                resume_filename="cv.pdf", location=location, status="screened",
                recruiter_decision="", location_confirmed=None, shift_confirmed=None)
    base.update(overrides)
    return SimpleNamespace(**base)


def test_matching_city_is_a_likely_match():
    fit = candidate_location_fit(_job(), _candidate(location="Gurugram"))
    assert fit["status"] == "likely_match"


def test_city_aliases_are_treated_as_the_same_place():
    # Gurgaon/Gurugram and Bangalore/Bengaluru are the same city.
    assert candidate_location_fit(_job(), _candidate(location="Gurgaon"))["status"] == "likely_match"
    blr = _job(location="Bengaluru")
    assert candidate_location_fit(blr, _candidate(location="Bangalore"))["status"] == "likely_match"


def test_different_city_is_reported_without_being_a_rejection():
    fit = candidate_location_fit(_job(), _candidate(location="Chennai"))
    assert fit["status"] == "different_location"
    # Must read as something to ask about, never as grounds to pass.
    assert "not a reason to pass" in fit["detail"].lower()
    assert "relocat" in fit["detail"].lower()


def test_missing_resume_location_is_a_question_not_a_mark_against():
    fit = candidate_location_fit(_job(), _candidate(location=""))
    assert fit["status"] == "needs_confirmation"
    assert "says nothing about the candidate" in fit["detail"]


def test_remote_role_makes_location_irrelevant():
    fit = candidate_location_fit(_job(work_model="remote"), _candidate(location="Kochi"))
    assert fit["status"] == "remote_role"


def test_call_confirmation_wins_over_resume_text():
    fit = candidate_location_fit(
        _job(), _candidate(location="Chennai", location_confirmed=True))
    assert fit["status"] == "confirmed"


def test_job_without_a_location_asks_rather_than_guessing():
    fit = candidate_location_fit(_job(location=""), _candidate(location="Pune"))
    assert fit["status"] == "needs_confirmation"


def test_shift_confirmation_is_tracked_separately_from_location():
    job = _job(working_hours="6pm-3am IST")
    unconfirmed = candidate_location_fit(job, _candidate(location="Gurugram"))
    confirmed = candidate_location_fit(job, _candidate(location="Gurugram", shift_confirmed=True))
    assert unconfirmed["needs_shift_confirmation"] is True
    assert confirmed["needs_shift_confirmation"] is False


def test_roster_counts_and_orders_by_actionability():
    job = _job()
    job.candidates = [
        _candidate(1, "Chennai"),                              # different_location
        _candidate(2, "Gurugram"),                             # likely_match
        _candidate(3, "", ),                                   # needs_confirmation
        _candidate(4, "Chennai", location_confirmed=True),     # confirmed
    ]
    roster = job_location_roster(job)
    assert roster["total"] == 4
    assert roster["counts"]["confirmed"] == 1
    assert roster["counts"]["likely_match"] == 1
    assert roster["counts"]["different_location"] == 1
    # Settled candidates first, unresolved ones last.
    assert [r["status"] for r in roster["candidates"]] == [
        "confirmed", "likely_match", "needs_confirmation", "different_location",
    ]


def test_roster_states_plainly_that_it_never_affects_rating():
    roster = job_location_roster(_job())
    assert "excluded from every score" in roster["note"]
    assert "nothing on this tab changes a candidate's rating" in roster["note"].lower()


def test_roster_handles_a_job_with_no_candidates():
    roster = job_location_roster(_job())
    assert roster["total"] == 0
    assert roster["candidates"] == []
