"""§11 — Interview intelligence (post-interview transcript analysis).

Consent gates are enforced in code: analysis refuses to run unless the
candidate consented, the interviewer was aware, transcription was enabled in
the meeting platform, and tenant/administrator permission exists. The result
then sits behind a mandatory human-review gate before it can be attached to
the candidate record or shared (HITL gate #7).
"""
from __future__ import annotations

from ..models import Candidate, InterviewRecord, Job
from . import llm

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "competencies_covered": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "competency": {"type": "string"},
                    "coverage": {"type": "string", "enum": ["covered", "partially_covered", "not_covered"]},
                    "candidate_answer_summary": {"type": "string"},
                    "score": {"type": "integer"},
                },
                "required": ["competency", "coverage", "candidate_answer_summary", "score"],
                "additionalProperties": False,
            },
        },
        "answer_summaries": {"type": "array", "items": {"type": "string"}},
        "resume_consistency": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "verdict": {"type": "string",
                                "enum": ["consistent", "inconsistent", "not_discussed"]},
                    "detail": {"type": "string"},
                },
                "required": ["claim", "verdict", "detail"],
                "additionalProperties": False,
            },
        },
        "vague_or_unsupported_claims": {"type": "array", "items": {"type": "string"}},
        "unanswered_questions": {"type": "array", "items": {"type": "string"}},
        "overall_evaluation": {"type": "string"},
        "overall_score": {"type": "integer"},
        "debrief_suggestions": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "competencies_covered", "answer_summaries", "resume_consistency",
        "vague_or_unsupported_claims", "unanswered_questions",
        "overall_evaluation", "overall_score", "debrief_suggestions",
    ],
    "additionalProperties": False,
}

_SYSTEM = """You analyse a completed interview transcript for a recruitment team, producing
an INDEPENDENT evaluation to inform the hiring-manager debrief. Rules:
- Only use what was actually said in the transcript; quote or paraphrase faithfully.
- Compare the candidate's answers with the resume claims provided and mark each claim
  consistent / inconsistent / not_discussed.
- Highlight vague or unsupported claims and questions the candidate did not answer.
- Score each competency 1-5 and the interview overall 0-100, judging only job-relevant
  competence and communication as it relates to the role.
- Never judge accent, demographics, or any protected attribute.
- debrief_suggestions: concrete topics the hiring manager should explore next round."""


class ConsentError(RuntimeError):
    pass


def check_consent(record: InterviewRecord) -> None:
    missing = []
    if not record.candidate_consent:
        missing.append("candidate notification & consent")
    if not record.interviewer_aware:
        missing.append("interviewer awareness")
    if not record.transcription_enabled:
        missing.append("platform transcription enablement")
    if not record.tenant_permission:
        missing.append("client tenant / administrator permission")
    if missing:
        raise ConsentError(
            "Interview analysis blocked — missing consents: " + "; ".join(missing)
        )


def analyse_transcript(record: InterviewRecord, candidate: Candidate, job: Job) -> dict:
    check_consent(record)
    if not record.transcript_text.strip():
        raise ValueError("No transcript text provided")
    user = f"""Role: {job.title} @ {job.client_name}

Key scorecard areas: {', '.join(c.name for sc in job.scorecards if sc.status == 'approved' for c in sc.criteria) or 'See resume claims'}

Resume claims (redacted resume extract):
<resume>
{candidate.redacted_text[:12000]}
</resume>

Interview transcript:
<transcript>
{record.transcript_text[:40000]}
</transcript>"""
    return llm.structured_call(
        system=_SYSTEM, user_content=user, schema=ANALYSIS_SCHEMA, max_tokens=8000
    )
