"""Fairness & responsible-AI controls (brief §15).

Before any scoring happens, the resume text is passed through this module,
which redacts protected or sensitive attributes so the evaluation engine
never sees them:

  - age / date of birth
  - gender and gendered honorifics
  - marital / family status
  - religion & caste
  - nationality / ethnicity (work-authorisation phrases are preserved)
  - disability / health details
  - photographs (references)
  - residential address beyond city-level location

The candidate's *identity block* (name, email, phone, city) is extracted
separately for contact purposes and is NOT provided to the scoring model.

The module also provides guardrail assertions used elsewhere:
  - employment gaps must never trigger an automatic rejection
  - poor formatting must never trigger an automatic rejection
  - every negative recommendation must carry an explanation
"""
from __future__ import annotations

import re

REDACTED = "[REDACTED]"

# Patterns are deliberately conservative: better to over-redact for scoring
# purposes than to leak a protected attribute into the ranking model.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("date_of_birth", re.compile(
        r"(?:date\s+of\s+birth|d\.?o\.?b\.?|born\s+on|birth\s*date)\s*[:\-]?\s*[^\n,;]{0,40}",
        re.IGNORECASE)),
    ("age", re.compile(r"\bage\s*[:\-]?\s*\d{1,2}\s*(?:years?|yrs?)?\b", re.IGNORECASE)),
    ("gender", re.compile(
        r"(?:gender|sex)\s*[:\-]?\s*(?:male|female|man|woman|non[- ]?binary|other)\b",
        re.IGNORECASE)),
    ("honorific", re.compile(r"\b(?:mr|mrs|ms|miss)\.?\s+(?=[A-Z])", re.IGNORECASE)),
    ("marital_status", re.compile(
        r"(?:marital\s+status|married|unmarried|single|divorced|widowed)"
        r"(?:\s*[:\-]?\s*(?:married|unmarried|single|divorced|widowed|yes|no))?\b",
        re.IGNORECASE)),
    ("family", re.compile(
        r"(?:father'?s?\s+name|mother'?s?\s+name|husband'?s?\s+name|wife'?s?\s+name|"
        r"spouse|children|dependents)\s*[:\-]?\s*[^\n,;]{0,50}",
        re.IGNORECASE)),
    ("religion_caste", re.compile(
        r"(?:religion|caste|community)\s*[:\-]?\s*[^\n,;]{0,40}", re.IGNORECASE)),
    ("nationality", re.compile(
        r"(?:nationality|ethnicity)\s*[:\-]?\s*[^\n,;]{0,40}", re.IGNORECASE)),
    ("health", re.compile(
        r"(?:disability|differently[- ]abled|health\s+status|blood\s+group|medical\s+condition)"
        r"\s*[:\-]?\s*[^\n,;]{0,50}",
        re.IGNORECASE)),
    ("photo", re.compile(r"(?:photograph|passport\s+(?:size\s+)?photo|photo\s+attached)[^\n]{0,30}",
                         re.IGNORECASE)),
]

# Street-level address lines (keep city/state which may be a legitimate
# location requirement; strip house/flat/street detail).
_ADDRESS = re.compile(
    r"(?:^|\n)\s*(?:permanent\s+address|current\s+address|residential\s+address|address)"
    r"\s*[:\-]\s*[^\n]{0,120}",
    re.IGNORECASE,
)

# Work-authorisation phrases are lawful & preserved (brief §15 exception).
_WORK_AUTH_KEEP = re.compile(
    r"(?:work\s+authorisation|work\s+authorization|visa\s+status|eligible\s+to\s+work|"
    r"right\s+to\s+work|work\s+permit)",
    re.IGNORECASE,
)


def redact_protected_attributes(text: str) -> tuple[str, list[str]]:
    """Return (redacted_text, list_of_redaction_categories_applied)."""
    applied: list[str] = []
    redacted = text

    for line in _ADDRESS.findall(redacted):
        if not _WORK_AUTH_KEEP.search(line):
            redacted = redacted.replace(line, f"\n{REDACTED} (address)")
            if "address" not in applied:
                applied.append("address")

    for name, pattern in _PATTERNS:
        def _sub(match: re.Match) -> str:
            if _WORK_AUTH_KEEP.search(match.group(0)):
                return match.group(0)
            return REDACTED
        new = pattern.sub(_sub, redacted)
        if new != redacted:
            applied.append(name)
            redacted = new

    return redacted, applied


# ---------------------------------------------------------------------------
# Guardrails used by the screening engine
# ---------------------------------------------------------------------------
FAIRNESS_RULES_PROMPT = """FAIRNESS RULES (non-negotiable):
- Base every judgement ONLY on demonstrated skills, experience, qualifications and
  role-relevant facts explicitly present in the resume text.
- NEVER use or infer age, gender, photograph, marital/family status, religion, caste,
  disability/health, ethnicity or nationality (except explicit lawful work-authorisation
  statements when the scorecard requires them).
- Do NOT treat school or employer prestige as a proxy for ability.
- An employment gap is NEVER by itself a reason to lower a score or recommend rejection;
  at most flag it neutrally as an item for the recruiter to discuss.
- Poor resume formatting is NEVER a reason to lower a score.
- Do NOT penalise non-native English phrasing unless written communication is an
  explicitly listed essential requirement in the scorecard.
- Keyword frequency is NOT evidence: score demonstrated, dated, contextualised experience,
  not the number of times a term appears.
- Every negative statement must reference the specific scorecard criterion it relates to.
"""


def enforce_negative_explanation(recommendation: str, explanation: str) -> str:
    """Fairness control: a negative recommendation must carry an explanation."""
    if recommendation == "do_not_shortlist" and not (explanation or "").strip():
        return (
            "Recommendation downgraded to recruiter_review: the engine did not supply "
            "an explanation for a negative decision, which is not permitted."
        )
    return ""
