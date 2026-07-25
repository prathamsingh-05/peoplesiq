"""Stage 8 — Candidate summary for the hiring manager.

Structured fields exactly per the brief, produced as (a) a JSON structure for
the Excel export and (b) a formatted text profile shareable by email.
Requires recruiter approval before it can be marked as shared (HITL gate #5).
"""
from __future__ import annotations

from ..models import Candidate, Evaluation, Job
from . import llm

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "current_role_and_employer": {"type": "string"},
        "total_experience": {"type": "string"},
        "relevant_experience": {"type": "string"},
        "core_skills": {"type": "array", "items": {"type": "string"}},
        "industry_client_exposure": {"type": "string"},
        "key_achievements": {"type": "array", "items": {"type": "string"}},
        "areas_to_probe": {"type": "array", "items": {"type": "string"}},
        "reason_for_recommendation": {"type": "string"},
    },
    "required": [
        "current_role_and_employer", "total_experience", "relevant_experience",
        "core_skills", "industry_client_exposure", "key_achievements",
        "areas_to_probe", "reason_for_recommendation",
    ],
    "additionalProperties": False,
}

_SYSTEM = """You draft concise candidate summaries for hiring managers.
Use ONLY facts from the evaluation and resume provided. Keep every field short and
factual. key_achievements: max 4 bullets with concrete outcomes. areas_to_probe: max 4
targeted topics for the interview. Never mention protected attributes."""


def build_summary(candidate: Candidate, evaluation: Evaluation, job: Job) -> dict:
    """Compose the full Stage-8 structure; AI drafts narrative fields."""
    ai_fields = _draft_ai_fields(candidate, evaluation)
    content = {
        "candidate_name": candidate.full_name,
        "candidate_code": candidate.candidate_code,
        "job_title": job.title,
        "client": job.client_name,
        "current_role_and_employer": ai_fields["current_role_and_employer"]
            or f"{candidate.current_role} @ {candidate.current_employer}".strip(" @"),
        "total_experience": ai_fields["total_experience"],
        "relevant_experience": ai_fields["relevant_experience"]
            or f"{evaluation.relevant_experience_years:g} years",
        "core_skills": ai_fields["core_skills"] or evaluation.key_strengths,
        "industry_client_exposure": ai_fields["industry_client_exposure"],
        "key_achievements": ai_fields["key_achievements"],
        # Facts collected by the human recruiter on the call:
        "current_compensation": candidate.current_compensation,
        "expected_compensation": candidate.expected_compensation,
        "notice_period": candidate.notice_period,
        "location_confirmed": candidate.location_confirmed,
        "shift_confirmed": candidate.shift_confirmed,
        "recruiter_observations": candidate.call_notes or candidate.recruiter_comments,
        "areas_to_probe": ai_fields["areas_to_probe"],
        "reason_for_recommendation": ai_fields["reason_for_recommendation"]
            or evaluation.explanation,
        "ai_score": evaluation.overall_score,
        "ai_recommendation": evaluation.recommendation,
        # Already computed during screening but previously never reached the
        # hiring manager — the whole-career "who is this person" read and
        # anything worth a conversation on the call, both piped straight
        # from the evaluation rather than re-derived by another AI call.
        "career_pattern": evaluation.overall_impression_note,
        "risk_flags": evaluation.risk_flags,
    }
    return content


def _draft_ai_fields(candidate: Candidate, evaluation: Evaluation) -> dict:
    empty = {
        "current_role_and_employer": "", "total_experience": "",
        "relevant_experience": "", "core_skills": [],
        "industry_client_exposure": "", "key_achievements": [],
        "areas_to_probe": [], "reason_for_recommendation": "",
    }
    try:
        user = f"""Evaluation summary: {evaluation.executive_summary}
Strengths: {'; '.join(evaluation.key_strengths)}
Gaps: {'; '.join(evaluation.gaps)}
Relevant projects: {'; '.join(evaluation.relevant_projects)}
Recruiter call notes: {candidate.call_notes or 'None yet'}

Resume (redacted):
<resume>
{candidate.redacted_text[:20000]}
</resume>"""
        return {**empty, **llm.structured_call(
            system=_SYSTEM, user_content=user, schema=SUMMARY_SCHEMA, max_tokens=3000
        )}
    except llm.LLMUnavailable:
        return empty


def format_profile(content: dict) -> str:
    """Email-shareable formatted profile."""
    skills = ", ".join(content.get("core_skills", []))
    achievements = "\n".join(f"  • {a}" for a in content.get("key_achievements", [])) or "  —"
    probes = "\n".join(f"  • {p}" for p in content.get("areas_to_probe", [])) or "  —"
    risk_flags = "\n".join(f"  • {r}" for r in content.get("risk_flags", [])) or "  —"
    shift = {True: "Confirmed", False: "Not confirmed", None: "To be confirmed"}
    return f"""CANDIDATE PROFILE — {content.get('candidate_name', '')} ({content.get('candidate_code', '')})
Role: {content.get('job_title', '')} | Client: {content.get('client', '')}
{'=' * 72}
Current role & employer : {content.get('current_role_and_employer') or '—'}
Total experience        : {content.get('total_experience') or '—'}
Relevant experience     : {content.get('relevant_experience') or '—'}
Core skills             : {skills or '—'}
Industry/client exposure: {content.get('industry_client_exposure') or '—'}

Career pattern (who this person is, as a professional):
  {content.get('career_pattern') or '—'}

Key achievements:
{achievements}

Compensation (current → expected): {content.get('current_compensation') or '—'} → {content.get('expected_compensation') or '—'}
Notice period          : {content.get('notice_period') or '—'}
Location confirmation  : {shift[content.get('location_confirmed')]}
Shift confirmation     : {shift[content.get('shift_confirmed')]}

Recruiter observations:
  {content.get('recruiter_observations') or '—'}

Areas for the hiring manager to probe:
{probes}

Worth a conversation (not marks against the candidate — context to confirm):
{risk_flags}

Why we recommend this candidate:
  {content.get('reason_for_recommendation') or '—'}

AI screening score: {content.get('ai_score')} / 100 (recommendation: {content.get('ai_recommendation')})
— Prepared by People IQ Recruiter Agent; reviewed and approved by the recruiting team.
"""
