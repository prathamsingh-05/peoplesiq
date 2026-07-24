"""Deterministic career-timeline reconstruction from parsed resume employment
history — the same mental model a real recruiter builds before judging a
resume at all: an ordered list of roles with real durations, total
experience computed from actual dates (a union of covered months, so
overlapping/concurrent roles are never double-counted), and any gaps
between roles.

This exists because asking an LLM to do exact date arithmetic from prose is
exactly the kind of task it's unreliable at — "7 years across 4 roles with
an 8-month gap in 2022" is arithmetic, not reading comprehension. The
resume's own dated work history (already extracted into `employers` by
resume_parser.extract_profile) has everything needed to compute this
correctly instead of asking the model to estimate it. Pure functions, no
AI, fully unit-testable.
"""
from __future__ import annotations

import re
from datetime import date

_MONTH_INDEX = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_MONTH_WORD = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_MONTH_YEAR_RE = re.compile(rf"{_MONTH_WORD}\.?,?\s+(\d{{4}})", re.IGNORECASE)
_NUMERIC_MY_RE = re.compile(r"\b(0?[1-9]|1[0-2])[/\-](\d{4})\b")
_YEAR_ONLY_RE = re.compile(r"\b(19|20)\d{2}\b")

_PRESENT_WORDS = {
    "present", "current", "currently", "till date", "to date", "now",
    "ongoing", "today", "date", "till now", "to present",
}


def is_present(text: str) -> bool:
    return (text or "").strip().lower() in _PRESENT_WORDS


def parse_month_year(text: str) -> tuple[int, int | None] | None:
    """Best-effort (year, month) from free text like "Mar 2021", "03/2021",
    or a bare "2021" (month left as None — the caller decides whether that
    means start-of-year or end-of-year). Returns None when nothing
    plausible is found, rather than guessing wrong."""
    text = (text or "").strip()
    if not text:
        return None
    m = _MONTH_YEAR_RE.search(text)
    if m:
        return int(m.group(2)), _MONTH_INDEX[m.group(1).lower()[:3]]
    m = _NUMERIC_MY_RE.search(text)
    if m:
        return int(m.group(2)), int(m.group(1))
    m = _YEAR_ONLY_RE.search(text)
    if m:
        return int(m.group(0)), None
    return None


def _month_idx(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def _label(idx: int) -> str:
    year, month = divmod(idx, 12)
    return f"{_MONTH_NAMES[month + 1]} {year}"


# A role shorter than this (and not still ongoing) counts toward the
# short-stint tally used to ground the tenure-pattern risk flag (screening.py
# principle 20) in real numbers instead of an LLM's rough read of the prose.
_SHORT_STINT_MONTHS = 11
# Below this, a break between two roles is treated as normal handover/
# joining-date slack rather than a real gap worth asking about.
_MIN_GAP_MONTHS = 2


def build_timeline(employers: list[dict] | None, today: date | None = None) -> dict:
    """From resume_parser's extracted `employers` ([{employer, role, start,
    end}, ...]), reconstruct a deterministic career timeline. Entries whose
    start date can't be parsed at all are skipped — there's nothing to place
    them on a real timeline with, and this is explicitly a best-effort
    deterministic aid, not a replacement for reading the resume."""
    today = today or date.today()
    today_idx = _month_idx(today.year, today.month)

    entries = []
    for e in employers or []:
        start_raw = (e.get("start") or "").strip()
        end_raw = (e.get("end") or "").strip()
        start = parse_month_year(start_raw)
        if start is None:
            continue
        start_idx = _month_idx(start[0], start[1] or 1)
        ongoing = is_present(end_raw) or not end_raw
        if ongoing:
            end_idx = today_idx
        else:
            end = parse_month_year(end_raw)
            end_idx = _month_idx(end[0], end[1] or 12) if end else start_idx
        if end_idx < start_idx:
            end_idx = start_idx
        entries.append({
            "employer": e.get("employer", ""), "role": e.get("role", ""),
            "start_label": start_raw or _label(start_idx),
            "end_label": "Present" if ongoing else (end_raw or _label(end_idx)),
            "start_idx": start_idx, "end_idx": end_idx,
            "duration_months": end_idx - start_idx + 1, "ongoing": ongoing,
        })
    entries.sort(key=lambda x: x["start_idx"])

    # Union of covered months, not a sum — concurrent/overlapping roles
    # (a common resume pattern: freelancing alongside a full-time job) must
    # not be double-counted toward total experience.
    covered: set[int] = set()
    for e in entries:
        covered.update(range(e["start_idx"], e["end_idx"] + 1))

    merged: list[list[int]] = []
    for e in entries:
        if merged and e["start_idx"] <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], e["end_idx"])
        else:
            merged.append([e["start_idx"], e["end_idx"]])
    gaps = []
    for i in range(len(merged) - 1):
        prev_end, next_start = merged[i][1], merged[i + 1][0]
        gap_months = next_start - prev_end - 1
        if gap_months >= _MIN_GAP_MONTHS:
            gaps.append({
                "months": gap_months,
                "from": _label(prev_end + 1), "to": _label(next_start - 1),
            })

    short_stints = sum(
        1 for e in entries if not e["ongoing"] and e["duration_months"] < _SHORT_STINT_MONTHS
    )

    return {
        "entries": entries,
        "total_experience_years": round(len(covered) / 12, 1),
        "gaps": gaps,
        "short_stint_count": short_stints,
        "employer_count": len(entries),
    }


def timeline_block(timeline: dict) -> str:
    """Renders a computed timeline as prompt text: ground truth for date
    arithmetic (total experience, tenure, gaps) that the model should treat
    as authoritative over its own reading of the prose, while still reading
    the resume text itself for everything the dates alone can't tell you —
    what the person actually did, scope, ownership."""
    entries = timeline.get("entries") or []
    if not entries:
        return ""
    lines = [
        f"- {e['role'] or 'role not specified'} at {e['employer'] or 'employer not specified'}: "
        f"{e['start_label']} - {e['end_label']} ({e['duration_months']} months"
        + (", current" if e["ongoing"] else "") + ")"
        for e in entries
    ]
    parts = [
        "Computed career timeline (built deterministically from the resume's own dated "
        "work history — treat these dates and durations as ground truth for any date "
        "arithmetic: total experience, tenure per role, gaps. Do not re-estimate these "
        "from the prose yourself; use the resume text for everything else, like what "
        "the person actually did in each role):",
        "\n".join(lines),
        f"Total experience covered by this timeline (deduplicated for any concurrent "
        f"roles): ~{timeline['total_experience_years']:g} years across "
        f"{timeline['employer_count']} role(s).",
    ]
    if timeline.get("gaps"):
        gap_lines = [
            f"- {g['months']}-month gap between {g['from']} and {g['to']}"
            for g in timeline["gaps"]
        ]
        parts.append(
            "Gaps in the dated timeline (neutral facts to note in missing_information or "
            "verification_questions for the call if meaningful — never evidence against "
            "the candidate; per policy, career gaps are never scored or penalised):\n"
            + "\n".join(gap_lines)
        )
    return "\n".join(parts)
