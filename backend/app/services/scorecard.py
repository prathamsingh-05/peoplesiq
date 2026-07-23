"""Stage 1 — Convert a job description into a structured evaluation scorecard.

The scorecard is the single source of truth for screening. It is generated
by the AI, then MUST be reviewed, edited and approved by the recruiter
before any resume can be screened (human-in-the-loop gate #1).
"""
from __future__ import annotations

from ..models import CriterionCategory, Job
from . import llm

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
  seniority (level/team scope), location_hours (only if the JD states an explicit
  location/shift requirement), stability (career progression — an employment gap must
  NEVER be a criterion), preferred (nice-to-haves).
- Mark is_mandatory=true sparingly — typically only 1-3 criteria per scorecard, and
  only for genuine knock-out requirements explicitly stated in the JD (e.g. a required
  license, clearance, or work authorization). Do not mark ordinary skills or experience
  levels as mandatory just because the JD lists them under "requirements" — most JD
  "requirements" sections are the target profile, not hard knockouts.
- Write each criterion broadly enough to credit equivalent or adjacent experience, not
  only an exact keyword match. Prefer "cloud infrastructure experience (AWS, Azure, or
  GCP)" over "AWS Lambda specifically," unless the JD names one exact tool as required.
  A resume that demonstrates the underlying capability in different words should still
  be able to earn "confirmed" or "partial" evidence, not "no_evidence" on a technicality.
- Weights: 1.0 (standard) to 3.0 (critical); preferred criteria 0.5-1.0.
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


def _deterministic_scorecard(job: Job) -> list[dict]:
    """Rule-built scorecard from the structured job fields (offline mode)."""
    criteria: list[dict] = []
    for cond in job.mandatory_conditions:
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
