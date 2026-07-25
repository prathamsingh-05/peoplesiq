"""Stage 1 — Convert a job description into a structured evaluation scorecard.

The scorecard is the single source of truth for screening. It is generated
by the AI, then MUST be reviewed, edited and approved by the recruiter
before any resume can be screened (human-in-the-loop gate #1).
"""
from __future__ import annotations

from ..models import CriterionCategory, Job
from . import llm
from .screening import _lpa_band_guidance

SCORECARD_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [c.value for c in CriterionCategory],
                    },
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "weight": {"type": "number"},
                    "is_mandatory": {"type": "boolean"},
                },
                "required": ["category", "name", "description", "weight", "is_mandatory"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["criteria"],
    "additionalProperties": False,
}

_SYSTEM = """You are an expert technical recruiter who converts job descriptions into
structured evaluation scorecards for resume screening.

Rules:
- Produce 8-16 criteria that a screener can verify from a resume.
- Categories: mandatory (must-have conditions), experience (years/depth),
  technical_skills, domain (industry/client exposure), qualifications,
  seniority (level/team scope), location_hours (see LOGISTICS rule below),
  stability (career progression — an employment gap must NEVER be a criterion),
  preferred (nice-to-haves).
- Mark is_mandatory=true sparingly — typically only 1-3 criteria per scorecard, and
  only for genuine knock-out requirements explicitly stated in the JD (e.g. a required
  license, clearance, or work authorization). Do not mark ordinary skills or experience
  levels as mandatory just because the JD lists them under "requirements" — most JD
  "requirements" sections are the target profile, not hard knockouts.
- LOGISTICS RULE: self-selected eligibility conditions — night/rotational shifts,
  work-from-office, relocation, remote/hybrid, notice period, willingness to travel —
  are NEVER mandatory scoring criteria, no matter how the JD phrases them. Applicants
  already self-select for these by choosing to apply once the JD states them, and a
  resume can rarely prove or disprove them anyway. Put these in category=location_hours
  with is_mandatory=false so the recruiter confirms them on the call, not the screening
  score.
- PAY-BAND / SENIORITY CALIBRATION RULE: read the seniority tier, compensation band,
  and "what good enough looks like" context in the job details below. Write each
  criterion's description at the depth that level and pay band actually calls for. A
  role paying an entry-level wage should describe entry-level evidence ("has used X in
  a project or internship") not senior-level evidence ("has architected X at scale") —
  a common, avoidable mistake is writing every scorecard as if it's hiring a top-tier
  specialist regardless of what the role pays or requires. A senior/lead role should
  still expect real depth — don't flatten every scorecard to the same generic bar
  either. The compensation band calibrates how you judge a candidate's SKILLS — it is
  never a criterion that scores or compares a candidate's own expected/current
  compensation. Compensation-expectation fit is a human judgement made on the
  screening call, never an automated screening criterion.
- If the job details below include an example of a strong-fit candidate, use it as a
  concrete anchor for how much depth each criterion's description should demand —
  write descriptions that this example candidate would clearly satisfy, not a higher
  or lower bar you're inferring in the abstract.
- If the job details below explain how industry/domain background should be weighed,
  reflect that explicitly in the domain criterion (or omit a domain criterion entirely
  if the note says domain background doesn't matter). Only mark a domain criterion
  is_mandatory=true if that note explicitly says specific domain experience is a hard
  requirement — by default, domain background is real signal but not a knock-out on
  its own, since capable people cross industries constantly.
- A single pay-band/seniority dial can't express "overall this is a lower-tier role, but
  one specific area still needs real depth" — a common real shape (e.g. an entry-level
  support role that still needs genuinely strong SQL). If the job details name areas
  needing genuine depth despite the general band, write those specific criteria's
  descriptions at the depth a senior/lead role would demand, weighted 2.5-3.0 — do not
  soften them just because the rest of the scorecard is calibrated lower. Conversely, if
  the job details name areas the team is happy to train on, write those criteria's
  descriptions to require only awareness/willingness-to-learn (or omit the criterion
  entirely if nothing to screen for), weighted low (0.5-1.0) or moved to preferred — never
  let a gap there carry real weight.
- Write each criterion broadly enough to credit equivalent or adjacent experience, not
  only an exact keyword match. Prefer "cloud infrastructure experience (AWS, Azure, or
  GCP)" over "AWS Lambda specifically," unless the JD names one exact tool as required.
  A resume that demonstrates the underlying capability in different words should still
  be able to earn "confirmed" or "partial" evidence, not "no_evidence" on a technicality.
- Weights: 1.0 (standard) to 3.0 (critical); preferred criteria 0.5-1.0.
- TECHNICAL SKILL WEIGHTING RULE: every skill listed under "Essential skills" below
  must become its own technical_skills criterion (or be clearly covered by one),
  weighted 2.0-3.0 in proportion to how central the JD treats it — these are the
  skills that should actually differentiate candidates, so don't dilute them by
  weighting them the same as generic/soft criteria like career stability. Every skill
  under "Preferred skills" must become category=preferred, weighted 0.5-1.0 — real
  but bonus-only, never equal-weighted with essentials. Do not invent additional
  skill criteria beyond what the essential/preferred lists and JD text actually call
  for; padding the scorecard with skills nobody asked for dilutes the weight of the
  skills that actually matter for this role.
- Recognize that a skill can appear in the JD/resume under a different name than the
  scorecard uses (e.g. JS/JavaScript, k8s/Kubernetes, Postgres/PostgreSQL, Node/
  Node.js, Golang/Go, ML/machine learning) — write each technical_skills criterion's
  description broadly enough to say so explicitly ("accept common aliases/
  abbreviations"), so the screening engine doesn't miss real evidence over a naming
  technicality.
- Each description must state what EVIDENCE in a resume would satisfy the criterion.
- Never create criteria about age, gender, marital status, religion, caste, nationality,
  health, photographs, school prestige, or anything a resume cannot lawfully evidence."""


def generate_scorecard_criteria(job: Job) -> tuple[list[dict], bool]:
    """Returns (criteria, generated_by_ai)."""
    jd_block = f"""Job title: {job.title}
Client: {job.client_name}
Location: {job.location or 'Not specified'}
Working hours: {job.working_hours or 'Not specified'}
Work model: {job.work_model or 'Not specified'}
Minimum experience: {job.min_experience_years} years
Essential skills: {', '.join(job.essential_skills) or 'See description'}
Preferred skills: {', '.join(job.preferred_skills) or 'See description'}
Qualifications: {job.qualifications or 'See description'}
Notice-period preference: {job.notice_period_preference or 'Not specified'}
Mandatory screening conditions: {'; '.join(job.mandatory_conditions) or 'None listed'}
Seniority tier: {job.seniority_tier or 'Not specified'}
Compensation band: {job.compensation_range or 'Not specified'}{
    (' — ' + _lpa_band_guidance(job.compensation_range)) if _lpa_band_guidance(job.compensation_range) else ''
}
What "good enough" looks like at this level: {job.good_enough_note or 'Not specified'}
Success criteria (first 6-12 months): {job.success_criteria or 'Not specified'}
Example of a strong-fit candidate for this role: {job.ideal_candidate_profile or 'Not specified'}
How industry/domain background should be weighed: {job.domain_context or 'Not specified'}
Areas that need genuine depth even though the overall role/pay is lower-tier (write these
criteria's descriptions at real depth, not the entry-level bar used elsewhere): {job.critical_depth_areas or 'Not specified'}
Areas the team is happy to train on — do not demand existing depth here: {job.flexible_growth_areas or 'Not specified'}

Full job description:
<job_description>
{job.description[:20000]}
</job_description>"""

    try:
        result = llm.structured_call(
            system=_SYSTEM,
            user_content=jd_block,
            schema=SCORECARD_SCHEMA,
            max_tokens=6000,
        )
        criteria = [c for c in result.get("criteria", []) if c.get("name")]
        if criteria:
            return criteria, True
    except llm.LLMUnavailable:
        pass
    return _deterministic_scorecard(job), False


# Self-selected eligibility conditions that a candidate already agreed to by
# applying, and that a resume rarely proves either way — these must never
# become scored mandatory criteria (see scorecard prompt's LOGISTICS RULE and
# screening.py scoring principle 12).
_LOGISTICS_KEYWORDS = (
    "night shift", "night shifts", "graveyard", "rotational shift", "rotating shift",
    "shift", "work from office", "wfo", "onsite", "on-site", "on site", "in-office",
    "in office", "relocate", "relocation", "notice period", "immediate join",
    "immediate joiner", "immediate joining", "willing to travel", "travel",
    "remote", "hybrid", "weekend", "late night", "us shift", "uk shift",
)


def _is_logistics_condition(cond: str) -> bool:
    lowered = cond.lower()
    return any(keyword in lowered for keyword in _LOGISTICS_KEYWORDS)


def _deterministic_scorecard(job: Job) -> list[dict]:
    """Rule-built scorecard from the structured job fields (offline mode)."""
    criteria: list[dict] = []
    for cond in job.mandatory_conditions:
        if _is_logistics_condition(cond):
            criteria.append({
                "category": "location_hours", "name": cond,
                "description": "Self-selected eligibility condition — a resume rarely "
                               f"proves this either way. Confirm on the screening call: {cond}",
                "weight": 1.0, "is_mandatory": False,
            })
        else:
            criteria.append({
                "category": "mandatory", "name": cond,
                "description": f"Resume or screening must confirm: {cond}",
                "weight": 3.0, "is_mandatory": True,
            })
    if job.min_experience_years:
        criteria.append({
            "category": "experience",
            "name": f"Minimum {job.min_experience_years:g} years relevant experience",
            "description": "Dated work history in a relevant role totalling at least "
                           f"{job.min_experience_years:g} years.",
            "weight": 3.0, "is_mandatory": True,
        })
    for skill in job.essential_skills:
        criteria.append({
            "category": "technical_skills", "name": skill,
            "description": f"Demonstrated hands-on use of {skill} in work history or projects.",
            "weight": 2.0, "is_mandatory": False,
        })
    if job.qualifications:
        criteria.append({
            "category": "qualifications", "name": job.qualifications[:200],
            "description": "Education section evidences the required qualification.",
            "weight": 1.5, "is_mandatory": False,
        })
    if job.location or job.working_hours or job.work_model:
        criteria.append({
            "category": "location_hours",
            "name": f"Suitability for {job.location or 'role location'}"
                    + (f" / {job.working_hours}" if job.working_hours else ""),
            "description": "Only where explicitly available in the resume; otherwise "
                           "mark as needs_verification for the screening call.",
            "weight": 1.0, "is_mandatory": False,
        })
    criteria.append({
        "category": "stability", "name": "Career progression",
        "description": "Increasing responsibility over time. Employment gaps are flagged "
                       "neutrally for discussion only and never penalised automatically.",
        "weight": 1.0, "is_mandatory": False,
    })
    for skill in job.preferred_skills:
        criteria.append({
            "category": "preferred", "name": skill,
            "description": f"Exposure to {skill} (nice-to-have).",
            "weight": 0.75, "is_mandatory": False,
        })
    return criteria
