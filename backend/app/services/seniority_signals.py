"""Demonstrated seniority from scope language — the title-inflation defence.

Job titles are an unreliable level signal in both directions, and this is
well documented: title inflation hands senior-sounding titles to roles
without the matching scope, while some large employers systematically
under-title (a "senior engineer" at one company doing what another calls
staff). A "manager" at a 20-person company might manage one person or six.
What actually indicates level is SCOPE — the responsibility held, the team
and impact size, whether they decided or executed.

So this module reads the resume for scope language and reports the level the
resume actually DEMONSTRATES, independently of any title claimed, then
compares that against the level the role is calibrated for.

Design constraints, consistent with the engine's existing principles:
  - Deterministic and unit-testable; no AI call.
  - It NEVER moves a score. Like career gaps, logistics and the other risk
    signals (screening.py principles 8, 12, 20), a scope/title mismatch is
    something a recruiter should know and probe on the call, not something
    the engine silently prices in. Under-titling in particular is a reason
    to look HARDER at a candidate, not to mark them down.
  - It reports evidence found, not a verdict — the prompt and the recruiter
    do the interpreting.
"""
from __future__ import annotations

import re

# Scope tiers, weakest to strongest. Phrases are matched as whole words/
# phrases against normalised text. The tier a resume "reaches" is the
# strongest one with enough distinct evidence, not the most frequent one —
# so a resume that says "developed" thirty times and "led the design of the
# billing system" once still registers ownership.
SCOPE_TIERS = ["assisted", "executed", "owned", "org_scope"]

_TIER_PHRASES: dict[str, tuple[str, ...]] = {
    "assisted": (
        "assisted", "assisted with", "supported the", "helped", "shadowed",
        "participated in", "under supervision", "under the guidance",
        "as part of a team", "contributed to", "aided", "learned",
        "trainee", "intern", "internship", "apprentice",
    ),
    "executed": (
        "developed", "implemented", "built", "created", "wrote", "coded",
        "performed", "handled", "maintained", "executed", "processed",
        "prepared", "tested", "configured", "resolved", "delivered",
        "administered", "documented", "analysed", "analyzed",
    ),
    "owned": (
        "owned", "ownership of", "led", "led the", "leading the", "drove",
        "spearheaded", "architected", "designed", "defined", "established",
        "initiated", "from scratch", "end to end", "end-to-end",
        "responsible for the", "accountable for", "sole", "single-handedly",
        "independently", "overhauled", "re-architected", "rearchitected",
        "migrated", "scaled", "set up the", "founded", "introduced",
    ),
    "org_scope": (
        "managed a team", "led a team", "team of", "direct reports",
        "line manager", "mentored", "coached", "hired", "recruited and",
        "onboarded new", "head of", "supervised", "managed the team",
        "cross-functional teams", "reporting to me", "people management",
        "performance reviews", "budget of", "p&l", "department",
        "grew the team", "built the team", "technical direction",
        "set the roadmap", "stakeholder management across",
    ),
}

# Distinct phrases needed in a tier before the resume is treated as genuinely
# reaching it — one incidental word shouldn't promote a level.
_MIN_DISTINCT_HITS = {"assisted": 1, "executed": 2, "owned": 2, "org_scope": 2}

# Which scope tier a role's calibrated seniority actually calls for. Used
# only to describe alignment; it never gates or scores.
_TIER_EXPECTATION = {
    "entry": "executed",
    "associate": "executed",
    "mid": "owned",
    "senior": "owned",
    "lead_plus": "org_scope",
}

# Quantified scale claims ("500+ users", "₹2 crore budget", "12 member team",
# "3 million requests") — real magnitude evidence regardless of tier language.
_SCALE_RE = re.compile(
    r"\b\d[\d,.]*\s*(?:\+|k|m|bn|b)?\s*"
    r"(?:%|percent|users?|customers?|clients?|accounts?|requests?|transactions?|"
    r"tickets?|records?|rows?|gb|tb|pb|qps|rps|crore|lakh|lpa|million|billion|"
    r"thousand|people|members?|engineers?|reports?|stores?|vendors?|countries|"
    r"regions?|servers?|nodes?|services?|hours?|days?)\b",
    re.IGNORECASE,
)


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9+#&/.%,₹$-]+", " ", (text or "").lower())


def scope_signals(resume_text: str) -> dict:
    """Reads scope/ownership language and quantified scale out of a resume.
    Returns the strongest tier genuinely evidenced, the matched phrases per
    tier (so a recruiter can see WHY, not just the label), and a count of
    quantified scale claims."""
    text = _normalise(resume_text)
    if not text.strip():
        return {
            "demonstrated_scope": None, "tier_hits": {}, "scale_claim_count": 0,
            "evidence": {},
        }

    tier_hits: dict[str, int] = {}
    evidence: dict[str, list[str]] = {}
    for tier, phrases in _TIER_PHRASES.items():
        matched = sorted({p for p in phrases if p in text})
        if matched:
            tier_hits[tier] = len(matched)
            evidence[tier] = matched[:6]

    demonstrated = None
    for tier in SCOPE_TIERS:  # weakest → strongest; keep the strongest that qualifies
        if tier_hits.get(tier, 0) >= _MIN_DISTINCT_HITS[tier]:
            demonstrated = tier

    return {
        "demonstrated_scope": demonstrated,
        "tier_hits": tier_hits,
        "scale_claim_count": len(_SCALE_RE.findall(text)),
        "evidence": evidence,
    }


def assess_level_alignment(resume_text: str, seniority_tier: str = "") -> dict:
    """Compares the scope a resume actually demonstrates against the level
    the role is calibrated for, and describes any mismatch in plain language.

    Deliberately symmetrical and never punitive: scope ABOVE the role's level
    is flagged as a motivation/retention conversation (and a reason to look
    harder at a strong candidate, since under-titling is common), while scope
    BELOW it is flagged as something to verify on the call — never as proof
    the candidate is unqualified, because resumes routinely under-describe
    real ownership."""
    signals = scope_signals(resume_text)
    demonstrated = signals["demonstrated_scope"]
    expected = _TIER_EXPECTATION.get((seniority_tier or "").strip())

    result = {
        **signals,
        "expected_scope": expected,
        "alignment": "unknown",
        "note": "",
    }
    if demonstrated is None:
        result["note"] = (
            "The resume doesn't use enough concrete scope or ownership language to tell "
            "what level this person has actually operated at. That's a thin-resume "
            "signal, not evidence of a junior candidate — worth establishing on the call."
        )
        return result
    if expected is None:
        result["alignment"] = "no_target"
        result["note"] = (
            f"The resume demonstrates {_readable(demonstrated)}. No seniority tier is set "
            "on this job, so there's nothing to compare it against — set the tier to get "
            "level-alignment context."
        )
        return result

    demonstrated_idx = SCOPE_TIERS.index(demonstrated)
    expected_idx = SCOPE_TIERS.index(expected)
    if demonstrated_idx == expected_idx:
        result["alignment"] = "matches"
        result["note"] = (
            f"The resume demonstrates {_readable(demonstrated)}, which is what this "
            "role's level calls for."
        )
    elif demonstrated_idx > expected_idx:
        result["alignment"] = "above"
        result["note"] = (
            f"The resume demonstrates {_readable(demonstrated)}, which is above what this "
            f"role's level strictly calls for ({_readable(expected)}). Two things this "
            "could mean, and only a call will tell you which: they're genuinely "
            "over-qualified (worth probing motivation and retention), or their previous "
            "employer under-titled them and they're simply a strong candidate. Do not "
            "treat it as a mark against them either way."
        )
    else:
        result["alignment"] = "below"
        result["note"] = (
            f"The resume demonstrates {_readable(demonstrated)}, where this role's level "
            f"typically calls for {_readable(expected)}. Titles and resume wording "
            "routinely under-describe real ownership, so treat this as something to "
            "establish on the call — ask what they personally decided and owned — rather "
            "than as proof they haven't operated at this level."
        )
    return result


_READABLE = {
    "assisted": "supporting/assisting-level scope",
    "executed": "hands-on execution and delivery scope",
    "owned": "independent ownership scope (designing and driving work, not just executing it)",
    "org_scope": "team/organisational scope (people, direction or budget beyond their own delivery)",
}


def _readable(tier: str | None) -> str:
    return _READABLE.get(tier or "", "unclear scope")


def scope_block(assessment: dict) -> str:
    """Renders the scope assessment as prompt text — deterministic evidence
    about demonstrated level for the model to reason from, with an explicit
    instruction that it must not become a scoring penalty."""
    if not assessment or not assessment.get("demonstrated_scope"):
        return ""
    parts = [
        "Demonstrated-scope signals (computed deterministically from the resume's own "
        "language, not from job titles — titles are unreliable in both directions, since "
        "some employers inflate them and others systematically under-title):",
        f"- Scope the resume actually demonstrates: {_readable(assessment['demonstrated_scope'])}.",
    ]
    if assessment.get("evidence", {}).get(assessment["demonstrated_scope"]):
        phrases = ", ".join(f'"{p}"' for p in assessment["evidence"][assessment["demonstrated_scope"]])
        parts.append(f"- Language this was drawn from: {phrases}.")
    if assessment.get("scale_claim_count"):
        parts.append(
            f"- Quantified scale/impact claims found in the resume: "
            f"{assessment['scale_claim_count']}."
        )
    if assessment.get("note"):
        parts.append(f"- Read on level fit: {assessment['note']}")
    parts.append(
        "Use this to judge the candidate's real level rather than trusting their job "
        "titles, and to decide between confirmed and partial on seniority/ownership "
        "criteria. This is context and a risk_flags candidate ONLY — a scope mismatch in "
        "either direction must never itself lower the evidence-based score, exactly like "
        "career gaps and logistics never do."
    )
    return "\n".join(parts)
