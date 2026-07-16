"""Stage 6 — Screening-question generation (5-7 questions in four categories)."""
from __future__ import annotations

from ..models import Candidate, Evaluation, Job
from . import llm

QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["eligibility", "skill_evidence", "gap_probing", "motivation"],
                    },
                    "question": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["category", "question", "rationale"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}

_SYSTEM = """You prepare screening-call questions for a human recruiter.
Generate 5-7 questions total, spread across four categories:

1. eligibility — location, willingness to work the required shift/model, notice period,
   current and expected compensation.
2. skill_evidence — anchored in a SPECIFIC claim from THIS candidate's resume
   (e.g. "You mention supporting Ellucian Banner environments. Which Banner modules did
   you work on directly, and what production issues did you resolve?").
3. gap_probing — anchored in a SPECIFIC gap between the scorecard and this resume
   (e.g. "The role requires Power BI and Tableau, but your resume mainly describes SQL
   reporting. What hands-on experience do you have with each?").
4. motivation — why a change now, what they seek, what could stop them accepting.

Rules: questions must be answerable in a 15-minute call; reference the candidate's own
resume wording where possible; never ask about age, family, religion, health, caste,
nationality or other protected attributes; the rationale explains what the recruiter
learns from the answer."""


def generate_questions(candidate: Candidate, evaluation: Evaluation, job: Job) -> list[dict]:
    try:
        gaps = "; ".join(evaluation.gaps) or "None identified"
        flags = "; ".join(evaluation.risk_flags) or "None"
        needs = "; ".join(
            r["name"] for r in evaluation.criterion_results
            if r["status"] == "needs_verification"
        ) or "None"
        user = f"""Job title: {job.title} @ {job.client_name}
Location/model/hours: {job.location} | {job.work_model} | {job.working_hours}
Notice-period preference: {job.notice_period_preference or 'Not specified'}

Evaluation summary: {evaluation.executive_summary}
Identified gaps: {gaps}
Risk flags: {flags}
Criteria needing verification: {needs}

Resume (redacted):
<resume>
{candidate.redacted_text[:20000]}
</resume>"""
        result = llm.structured_call(
            system=_SYSTEM, user_content=user, schema=QUESTIONS_SCHEMA, max_tokens=4000
        )
        questions = [q for q in result.get("questions", []) if q.get("question")][:7]
        if len(questions) >= 5:
            return questions
    except llm.LLMUnavailable:
        pass
    return _fallback_questions(candidate, evaluation, job)


def _fallback_questions(candidate: Candidate, evaluation: Evaluation, job: Job) -> list[dict]:
    questions = [
        {
            "category": "eligibility",
            "question": f"Where are you currently located, and are you able to work "
                        f"{job.work_model or 'the required model'} from {job.location or 'the role location'}"
                        + (f" on {job.working_hours}" if job.working_hours else "") + "?",
            "rationale": "Confirms location and shift suitability, which a resume rarely proves.",
        },
        {
            "category": "eligibility",
            "question": "What is your current notice period, and what are your current and "
                        "expected compensation?",
            "rationale": "Mandatory tracker fields; sets expectations before the HM stage.",
        },
    ]
    for gap in evaluation.gaps[:2]:
        questions.append({
            "category": "gap_probing",
            "question": f"The role requires {gap}. Can you walk me through any hands-on "
                        f"experience you have in this area, even if it is not on your resume?",
            "rationale": f"Probes the identified gap: {gap}.",
        })
    for r in evaluation.criterion_results:
        if r["status"] in ("confirmed", "partial") and r.get("evidence") and len(questions) < 6:
            questions.append({
                "category": "skill_evidence",
                "question": f"Your resume mentions: \"{r['evidence'][:140]}\". What was your "
                            f"specific, personal contribution there, and what results did you own?",
                "rationale": f"Validates the depth behind the claim for criterion: {r['name']}.",
            })
    questions.append({
        "category": "motivation",
        "question": "What is prompting you to consider a change now, and what would make you "
                    "hesitate to accept an offer for this role?",
        "rationale": "Surfaces motivation and closing risks early.",
    })
    return questions[:7]
