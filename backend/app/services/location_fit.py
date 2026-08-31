"""Location / work-model fit — a separate operational view, never a score.

Whether a candidate is in the right city (or will move, or can work the
required model) is a logistics question, not a measure of how good they are at
the job. The screening engine therefore excludes it from scoring entirely
(screening.py principles 8 and 12) and always has.

But a recruiter still has to answer it, and burying it inside per-criterion
evidence makes it tedious to answer across a whole pile of candidates. So this
module produces a plain, deterministic roster: for this job's location and work
model, where does each candidate stand, and what still needs confirming on the
call.

Nothing here feeds back into any score, ranking or recommendation. It reads
already-stored data (the candidate's parsed location and anything the recruiter
recorded on the call) and reports it.
"""
from __future__ import annotations

import re

# Remote roles are location-independent by definition, so a candidate's city
# simply doesn't constrain them.
_REMOTE_MODELS = {"remote"}

# Common Indian metro spellings/aliases, so "Bangalore" and "Bengaluru" (or
# "Gurgaon" and "Gurugram") aren't reported as different places. Purely a
# matching aid — an unrecognised city is reported as unclear, never as a
# mismatch, since this module must not manufacture a negative it can't support.
_CITY_ALIASES: list[set[str]] = [
    {"bangalore", "bengaluru", "blr"},
    {"gurgaon", "gurugram"},
    {"bombay", "mumbai"},
    {"madras", "chennai"},
    {"calcutta", "kolkata"},
    {"delhi", "new delhi", "ncr", "national capital region"},
    {"hyderabad", "hyd", "secunderabad"},
    {"pune", "poona"},
    {"trivandrum", "thiruvananthapuram"},
    {"cochin", "kochi"},
]

_ALIAS_LOOKUP: dict[str, set[str]] = {}
for _group in _CITY_ALIASES:
    for _name in _group:
        _ALIAS_LOOKUP[_name] = _group

_STOPWORDS = {
    "india", "remote", "hybrid", "onsite", "on", "site", "office", "work",
    "from", "home", "and", "or", "the", "area", "region", "city", "state",
}


def _tokens(text: str) -> set[str]:
    words = re.split(r"[^a-z]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _expand(tokens: set[str]) -> set[str]:
    """Adds known aliases so equivalent city names compare equal."""
    expanded = set(tokens)
    for token in tokens:
        expanded |= _ALIAS_LOOKUP.get(token, set())
    return expanded


def candidate_location_fit(job, candidate) -> dict:
    """Where one candidate stands on location/work-model for one job.

    status is deliberately coarse and honest:
      remote_role        — location doesn't constrain this role at all
      confirmed          — the recruiter confirmed it on the call
      likely_match       — the candidate's stated location matches the job's
      needs_confirmation — no contradiction found, but nothing confirms it
                           either; a resume often doesn't say
      different_location — stated locations genuinely differ (still not a
                           rejection: people relocate, and the JD's own
                           applicants self-selected by applying)
    """
    job_location = (getattr(job, "location", "") or "").strip()
    work_model = (getattr(job, "work_model", "") or "").strip().lower()
    candidate_location = (candidate.location or "").strip()

    confirmed = candidate.location_confirmed is True
    shift_confirmed = candidate.shift_confirmed is True

    if work_model in _REMOTE_MODELS:
        status, detail = "remote_role", (
            "This role is remote, so the candidate's location doesn't constrain them."
        )
    elif confirmed:
        status, detail = "confirmed", (
            "Confirmed with the candidate on the screening call."
        )
    elif not job_location:
        status, detail = "needs_confirmation", (
            "No location is set on this job, so there's nothing to compare against — "
            "add one to the job, or confirm directly with the candidate."
        )
    elif not candidate_location:
        status, detail = "needs_confirmation", (
            "The resume doesn't state a location. Resumes frequently omit it, so this "
            "says nothing about the candidate — just ask on the call."
        )
    else:
        job_tokens = _expand(_tokens(job_location))
        candidate_tokens = _expand(_tokens(candidate_location))
        if job_tokens & candidate_tokens:
            status, detail = "likely_match", (
                f"Resume location ({candidate_location}) matches the role's "
                f"location ({job_location}). Worth a quick confirmation on the call."
            )
        else:
            status, detail = "different_location", (
                f"Resume says {candidate_location}; the role is in {job_location}. "
                "Not a reason to pass on its own — they applied knowing the location, "
                "and people relocate. Ask about relocation or hybrid arrangements."
            )

    return {
        "candidate_id": candidate.id,
        "candidate_code": candidate.candidate_code,
        "candidate": candidate.full_name or candidate.resume_filename,
        "candidate_location": candidate_location,
        "job_location": job_location,
        "work_model": work_model,
        "working_hours": getattr(job, "working_hours", "") or "",
        "status": status,
        "detail": detail,
        "location_confirmed": candidate.location_confirmed,
        "shift_confirmed": candidate.shift_confirmed,
        "needs_shift_confirmation": bool(getattr(job, "working_hours", "")) and not shift_confirmed,
        "candidate_status": candidate.status,
        "recruiter_decision": candidate.recruiter_decision,
    }


def job_location_roster(job) -> dict:
    """The whole roster for a job, plus counts for an at-a-glance read."""
    rows = [candidate_location_fit(job, c) for c in job.candidates]
    order = {"confirmed": 0, "likely_match": 1, "remote_role": 2,
             "needs_confirmation": 3, "different_location": 4}
    rows.sort(key=lambda r: (order.get(r["status"], 9), r["candidate"].lower()))

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    return {
        "job_location": (getattr(job, "location", "") or ""),
        "work_model": (getattr(job, "work_model", "") or ""),
        "working_hours": (getattr(job, "working_hours", "") or ""),
        "counts": counts,
        "total": len(rows),
        "candidates": rows,
        "note": (
            "Location and shift fit are logistics, not ability — they are excluded "
            "from every score, ranking and recommendation in this system, and nothing "
            "on this tab changes a candidate's rating. It exists so you can answer "
            "'who can actually take this role' in one place."
        ),
    }
