"""§11 — Interview intelligence (post-interview transcript analysis with
mandatory consent gates and human review before sharing)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import log_action
from ..auth import client_ip, require_any_user, require_recruiter
from ..database import get_db
from ..models import Candidate, CandidateStatus, InterviewRecord, User
from ..schemas import InterviewCreate, InterviewFeedback, InterviewReview, TranscriptUpload
from ..services import interview as intel
from ..services.llm import LLMUnavailable

router = APIRouter(prefix="/api", tags=["interviews"])


def _interview_out(record: InterviewRecord, include_analysis: bool = True) -> dict:
    data = {
        "id": record.id, "candidate_id": record.candidate_id, "stage": record.stage,
        "scheduled_at": record.scheduled_at.isoformat() if record.scheduled_at else None,
        "interviewer": record.interviewer,
        "consents": {
            "candidate_consent": record.candidate_consent,
            "interviewer_aware": record.interviewer_aware,
            "transcription_enabled": record.transcription_enabled,
            "tenant_permission": record.tenant_permission,
        },
        "has_transcript": bool(record.transcript_text),
        "analysis_status": record.analysis_status,
        "review_status": record.review_status,
        "interviewer_feedback": record.interviewer_feedback,
        "created_at": record.created_at.isoformat(),
    }
    # The AI evaluation is only exposed once a human has approved it — except
    # to recruiters performing the review itself (handled in the route).
    if include_analysis:
        data["analysis"] = record.analysis
    return data


@router.post("/candidates/{candidate_id}/interviews", status_code=201)
def create_interview(candidate_id: int, payload: InterviewCreate, request: Request,
                     user: User = Depends(require_recruiter),
                     db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    record = InterviewRecord(candidate_id=candidate.id, **payload.model_dump())
    db.add(record)
    candidate.status = CandidateStatus.interview_scheduled.value
    if payload.scheduled_at:
        candidate.interview_date = payload.scheduled_at
    candidate.interview_stage = payload.stage
    db.flush()
    log_action(db, "interview.created", user=user, entity_type="interview",
               entity_id=record.id, details={"candidate_id": candidate.id},
               ip=client_ip(request))
    db.commit()
    return _interview_out(record)


@router.get("/candidates/{candidate_id}/interviews")
def list_interviews(candidate_id: int, user: User = Depends(require_any_user),
                    db: Session = Depends(get_db)):
    records = (db.query(InterviewRecord)
               .filter(InterviewRecord.candidate_id == candidate_id)
               .order_by(InterviewRecord.id.desc()).all())
    out = []
    for record in records:
        show = record.review_status == "approved" or user.role in ("admin", "recruiter")
        out.append(_interview_out(record, include_analysis=show))
    return out


@router.post("/interviews/{interview_id}/transcript")
def upload_transcript(interview_id: int, payload: TranscriptUpload, request: Request,
                      user: User = Depends(require_recruiter),
                      db: Session = Depends(get_db)):
    """Store the Teams/meeting transcript and run the post-interview analysis.
    Refuses to analyse without all four consents (§11 restrictions)."""
    record = db.get(InterviewRecord, interview_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Interview not found")

    record.transcript_text = payload.transcript_text
    record.candidate_consent = payload.candidate_consent
    record.interviewer_aware = payload.interviewer_aware
    record.transcription_enabled = payload.transcription_enabled
    record.tenant_permission = payload.tenant_permission

    try:
        intel.check_consent(record)
    except intel.ConsentError as exc:
        db.commit()  # keep the transcript stored, but no analysis
        raise HTTPException(status_code=403, detail=str(exc))

    candidate = record.candidate
    try:
        record.analysis = intel.analyse_transcript(record, candidate, candidate.job)
        record.analysis_status = "complete"
        record.review_status = "pending_review"
    except LLMUnavailable as exc:
        record.analysis_status = "failed"
        db.commit()
        raise HTTPException(status_code=503,
                            detail=f"AI analysis unavailable: {exc}. Transcript stored; retry later.")
    candidate.status = CandidateStatus.interview_complete.value
    candidate.feedback_status = "AI analysis pending human review"
    log_action(db, "interview.analysed", user=user, entity_type="interview",
               entity_id=record.id,
               details={"candidate_id": candidate.id,
                        "overall_score": record.analysis.get("overall_score")},
               ip=client_ip(request))
    db.commit()
    return _interview_out(record)


@router.post("/interviews/{interview_id}/feedback")
def record_feedback(interview_id: int, payload: InterviewFeedback, request: Request,
                    user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    record = db.get(InterviewRecord, interview_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    record.interviewer_feedback = payload.interviewer_feedback
    record.candidate.feedback_status = "Interviewer feedback recorded"
    log_action(db, "interview.feedback_recorded", user=user, entity_type="interview",
               entity_id=record.id, ip=client_ip(request))
    db.commit()
    return _interview_out(record)


@router.post("/interviews/{interview_id}/review")
def review_analysis(interview_id: int, payload: InterviewReview, request: Request,
                    user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    """HITL gate #7 — human review before the AI evaluation is shared or added
    to the candidate record."""
    record = db.get(InterviewRecord, interview_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    if record.analysis_status != "complete":
        raise HTTPException(status_code=409, detail="No completed analysis to review")
    record.review_status = "approved" if payload.approve else "rejected"
    record.reviewed_by_id = user.id
    record.reviewed_at = datetime.now(timezone.utc)
    record.candidate.feedback_status = (
        "Interview evaluation approved & shared" if payload.approve
        else "Interview AI evaluation rejected by reviewer"
    )
    log_action(db, "interview.review", user=user, entity_type="interview",
               entity_id=record.id, details={"approved": payload.approve},
               ip=client_ip(request))
    db.commit()
    return _interview_out(record)


@router.get("/interviews/{interview_id}/compare")
def compare_with_feedback(interview_id: int, user: User = Depends(require_any_user),
                          db: Session = Depends(get_db)):
    """Compare interviewer feedback with the AI findings for the HM debrief."""
    record = db.get(InterviewRecord, interview_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    if record.review_status != "approved" and user.role == "hiring_manager":
        raise HTTPException(status_code=403,
                            detail="The AI evaluation has not been approved for sharing yet")
    return {
        "interviewer_feedback": record.interviewer_feedback or "(none recorded)",
        "ai_overall_score": record.analysis.get("overall_score"),
        "ai_overall_evaluation": record.analysis.get("overall_evaluation"),
        "vague_or_unsupported_claims": record.analysis.get("vague_or_unsupported_claims", []),
        "unanswered_questions": record.analysis.get("unanswered_questions", []),
        "resume_consistency": record.analysis.get("resume_consistency", []),
        "debrief_suggestions": record.analysis.get("debrief_suggestions", []),
    }
