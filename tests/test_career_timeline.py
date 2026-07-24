"""Unit tests for the deterministic career-timeline engine
(app.services.career_timeline) — pure functions, no AI, no DB."""
from datetime import date

from app.services.career_timeline import build_timeline, is_present, parse_month_year, timeline_block


def test_parse_month_year_formats():
    assert parse_month_year("Mar 2021") == (2021, 3)
    assert parse_month_year("March, 2021") == (2021, 3)
    assert parse_month_year("september 2019") == (2019, 9)
    assert parse_month_year("03/2021") == (2021, 3)
    assert parse_month_year("3-2021") == (2021, 3)
    assert parse_month_year("2021") == (2021, None)
    assert parse_month_year("") is None
    assert parse_month_year("Not a date") is None


def test_is_present():
    assert is_present("Present")
    assert is_present("Current")
    assert is_present("  present ")
    assert not is_present("Mar 2021")
    assert not is_present("")


def test_build_timeline_computes_total_experience_and_gaps():
    employers = [
        {"employer": "Acme", "role": "Engineer", "start": "Jan 2018", "end": "Dec 2019"},
        # ~7-month gap between Dec 2019 and Aug 2020
        {"employer": "Globex", "role": "Senior Engineer", "start": "Aug 2020", "end": "Jun 2022"},
    ]
    tl = build_timeline(employers, today=date(2024, 1, 15))
    assert tl["employer_count"] == 2
    assert tl["entries"][0]["employer"] == "Acme"
    assert tl["entries"][1]["employer"] == "Globex"
    assert tl["gaps"] == [{"months": 7, "from": "Jan 2020", "to": "Jul 2020"}]
    # 24 months (Acme) + 23 months (Globex) = 47 months ≈ 3.9 years
    assert tl["total_experience_years"] == round(47 / 12, 1)


def test_build_timeline_ongoing_role_uses_today():
    employers = [{"employer": "Acme", "role": "Engineer", "start": "Jan 2022", "end": "Present"}]
    tl = build_timeline(employers, today=date(2024, 1, 1))
    entry = tl["entries"][0]
    assert entry["ongoing"] is True
    assert entry["end_label"] == "Present"
    assert entry["duration_months"] == 25  # Jan 2022 -> Jan 2024 inclusive


def test_build_timeline_concurrent_roles_not_double_counted():
    employers = [
        {"employer": "Day job", "role": "Engineer", "start": "Jan 2020", "end": "Dec 2021"},
        {"employer": "Freelance", "role": "Consultant", "start": "Jun 2020", "end": "Jun 2021"},
    ]
    tl = build_timeline(employers, today=date(2024, 1, 1))
    # Overlapping entirely within the day job's span — union is still just
    # the day job's 24 months, not 24+13.
    assert tl["total_experience_years"] == round(24 / 12, 1)
    assert tl["gaps"] == []


def test_build_timeline_skips_unparseable_start():
    employers = [
        {"employer": "Acme", "role": "Engineer", "start": "Sometime long ago", "end": "2020"},
        {"employer": "Globex", "role": "Engineer", "start": "Jan 2021", "end": "Present"},
    ]
    tl = build_timeline(employers, today=date(2022, 1, 1))
    assert tl["employer_count"] == 1
    assert tl["entries"][0]["employer"] == "Globex"


def test_build_timeline_short_stint_detection():
    employers = [
        {"employer": "A", "role": "Eng", "start": "Jan 2019", "end": "May 2019"},   # 5 months
        {"employer": "B", "role": "Eng", "start": "Jun 2019", "end": "Sep 2019"},   # 4 months
        {"employer": "C", "role": "Eng", "start": "Jan 2020", "end": "Present"},    # ongoing, excluded
    ]
    tl = build_timeline(employers, today=date(2024, 1, 1))
    assert tl["short_stint_count"] == 2


def test_build_timeline_most_recent_picks_latest_end_not_last_listed():
    employers = [
        # Listed second but ends earlier — must not be picked as "most recent".
        {"employer": "Older", "role": "Analyst", "start": "Jan 2015", "end": "Dec 2016"},
        {"employer": "Current", "role": "Senior Analyst", "start": "Jan 2020", "end": "Present"},
    ]
    tl = build_timeline(employers, today=date(2024, 1, 1))
    assert tl["most_recent"]["employer"] == "Current"


def test_build_timeline_most_recent_none_when_no_entries():
    assert build_timeline([])["most_recent"] is None


def test_build_timeline_empty_input():
    tl = build_timeline([])
    assert tl["entries"] == []
    assert tl["total_experience_years"] == 0.0
    assert tl["gaps"] == []
    assert tl["employer_count"] == 0
    assert timeline_block(tl) == ""


def test_timeline_block_mentions_ground_truth_and_gaps():
    employers = [
        {"employer": "Acme", "role": "Engineer", "start": "Jan 2018", "end": "Dec 2019"},
        {"employer": "Globex", "role": "Senior Engineer", "start": "Aug 2020", "end": "Jun 2022"},
    ]
    tl = build_timeline(employers, today=date(2024, 1, 1))
    block = timeline_block(tl)
    assert "ground truth" in block
    assert "Acme" in block and "Globex" in block
    assert "gap" in block.lower()
    assert "never scored" in block or "never penalised" in block


def test_timeline_block_names_most_recent_role():
    employers = [
        {"employer": "Older", "role": "Analyst", "start": "Jan 2015", "end": "Dec 2016"},
        {"employer": "Current", "role": "Senior Analyst", "start": "Jan 2020", "end": "Present"},
    ]
    tl = build_timeline(employers, today=date(2024, 1, 1))
    block = timeline_block(tl)
    assert "Most recent" in block
    assert "Current" in block and "Senior Analyst" in block
