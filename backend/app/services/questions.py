"""Stage 6 — Screening-question generation (5-7 questions in four categories)."""
from __future__ import annotations

from ..models import Candidate, Evaluation, Job
from . import llm, role_archetype

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
learns from the answer.

HOLISTIC COVERAGE — this is what turns a checklist into a real conversation:
- If any risk flags are listed below (retention risk from over-qualification, tenure/
  job-hopping patterns, thin resume specificity, or similar), turn the single most
  significant one into a direct, respectful question — never an accusation, genuine
  curiosity about context the resume can't show. E.g. a tenure-pattern flag becomes
  "I noticed a couple of shorter stints on your resume — can you walk me through what
  was going on there?" This is exactly what these calls are for.
- If critical depth areas are named below (places the hiring team needs genuine depth
  even though the role overall is lower-tier/lower-pay), make sure at least one
  skill_evidence question probes that specific area hard, not just the generic
  essential skills.
- If the hiring team named what they would most want verified, or what actually makes
  this role hard, at least one question must go directly at each of those — they are the
  highest-value minutes of the call.
- Ask for the numbers that this ROLE FAMILY is actually measured in when the resume
  omits them (a sales resume with no quota attainment, a support resume with no ticket
  volume or tier, a data resume with no decision the analysis drove). The role-family
  section below names them; a question that recovers a missing family-standard number is
  worth more than another generic skills question.
- Do not turn every category into a rote checklist item — a holistic pack reads like a
  recruiter who actually read this specific resume, not a generic template."""


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
Areas needing genuine depth despite the general level: {job.critical_depth_areas or 'None specified'}
What actually makes this role hard, per the hiring team: {job.role_challenges or 'Not specified'}
The things the hiring team would most want verified: {job.screening_priorities or 'Not specified'}
{role_archetype.archetype_block(role_archetype.detect_archetype(
    job.title, job.description or '', list(job.essential_skills or [])))}

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
    if evaluation.risk_flags:
        flag = evaluation.risk_flags[0]
        questions.append({
            "category": "motivation",
            "question": f"There's something worth asking you about directly: {flag} Can you "
                        f"tell me more about the context there?",
            "rationale": "Follows up on a flagged risk signal — context to gather on the "
                        "call, never evidence against the candidate on its own.",
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
