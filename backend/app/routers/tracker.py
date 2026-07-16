"""Stage 9 — Master recruitment tracker, dashboard metrics and Excel exports."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth import require_any_user
from ..database import get_db
from ..models import (
    AuditLog, Candidate, CandidateStatus, Evaluation, HMSummary, Job, User,
)
from ..services import excel as excel_service
from ..services import screening as engine

router = APIRouter(prefix="/api", tags=["tracker"])


@router.get("/tracker")
def tracker_rows(job_id: int | None = None, user: User = Depends(require_any_user),
                 db: Session = Depends(get_db)):
    query = db.query(Candidate).order_by(Candidate.id.desc())
    if job_id:
        query = query.filter(Candidate.job_id == job_id)
    rows = []
    for candidate in query.limit(1000).all():
        evaluation = candidate.evaluations[0] if candidate.evaluations else None
        rows.append({
            "job_id": candidate.job.job_code, "job_title": candidate.job.title,
            "candidate_id": candidate.candidate_code, "id": candidate.id,
            "candidate_name": candidate.full_name, "resume_source": candidate.source,
            "date_received": candidate.received_at.isoformat(),
            "date_screened": candidate.processed_at.isoformat() if candidate.processed_at else None,
            "ai_score": evaluation.overall_score if evaluation else None,
            "ai_recommendation": evaluation.recommendation if evaluation else None,
            "recruiter_decision": candidate.recruiter_decision,
            "screening_status": candidate.status,
            "interview_stage": candidate.interview_stage,
            "interview_date": candidate.interview_date.isoformat() if candidate.interview_date else None,
            "feedback_status": candidate.feedback_status,
            "offer_status": candidate.offer_status,
            "joining_status": candidate.joining_status,
            "rejection_reason": candidate.rejection_reason,
            "next_action": candidate.next_action,
            "owner": candidate.owner,
            "last_updated": candidate.updated_at.isoformat(),
        })
    return rows


@router.get("/dashboard")
def dashboard(user: User = Depends(require_any_user), db: Session = Depends(get_db)):
    candidates = db.query(Candidate).all()
    evaluated = [c for c in candidates if c.evaluations]

    def count(*statuses: str) -> int:
        return sum(1 for c in candidates if c.status in statuses)

    ai_shortlist = sum(1 for c in evaluated
                       if c.evaluations[0].recommendation == "shortlist")

    # AI-versus-recruiter agreement on decided candidates.
    decided = [c for c in evaluated if c.recruiter_decision in ("shortlist", "reject")]
    agreements = sum(
        1 for c in decided
        if (c.recruiter_decision == "shortlist"
            and c.evaluations[0].recommendation == "shortlist")
        or (c.recruiter_decision == "reject"
            and c.evaluations[0].recommendation == "do_not_shortlist")
    )
    return {
        "total_resumes_received": len(candidates),
        "total_resumes_screened": len(evaluated),
        "unreadable_or_duplicates": count(
            CandidateStatus.unreadable.value, CandidateStatus.duplicate.value),
        "ai_recommended": ai_shortlist,
        "recruiter_shortlisted": sum(
            1 for c in candidates if c.recruiter_decision == "shortlist"),
        "rejected": count(CandidateStatus.rejected.value),
        "awaiting_review": count(
            CandidateStatus.awaiting_review.value, CandidateStatus.screened.value),
        "interviews_scheduled": count(
            CandidateStatus.interview_scheduled.value),
        "offers_made": count(CandidateStatus.offer_made.value),
        "offers_accepted": count(
            CandidateStatus.offer_accepted.value, CandidateStatus.joined.value,
            CandidateStatus.handover_complete.value),
        "expected_joiners": sum(
            1 for c in candidates
            if c.status == CandidateStatus.offer_accepted.value and c.joining_date),
        "joined": count(CandidateStatus.joined.value,
                        CandidateStatus.handover_complete.value),
        "ai_recruiter_agreement_rate":
            round(100 * agreements / len(decided), 1) if decided else None,
        "decided_count": len(decided),
        "flagged_for_fairness_review": sum(
            1 for c in candidates if c.flagged_for_review),
        "open_jobs": db.query(Job).filter(Job.status == "active").count(),
        "total_jobs": db.query(Job).count(),
    }


# --- Excel exports ------------------------------------------------------------
@router.get("/jobs/{job_id}/export/leaderboard")
def export_leaderboard(job_id: int, user: User = Depends(require_any_user),
                       db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    pairs = sorted(
        ((c.evaluations[0], c) for c in job.candidates if c.evaluations),
        key=lambda pair: pair[0].overall_score, reverse=True,
    )
    rows = [engine.leaderboard_row(e, rank, c) for rank, (e, c) in enumerate(pairs, 1)]
    path = excel_service.export_leaderboard(job, rows)
    return FileResponse(path, filename=path.name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/export/tracker")
def export_tracker(user: User = Depends(require_any_user), db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.id).all()
    path = excel_service.export_tracker(jobs)
    return FileResponse(path, filename=path.name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/jobs/{job_id}/export/hm-summaries")
def export_summaries(job_id: int, user: User = Depends(require_any_user),
                     db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    summaries = []
    for candidate in job.candidates:
        record = (db.query(HMSummary).filter(HMSummary.candidate_id == candidate.id)
                  .order_by(HMSummary.id.desc()).first())
        if record:
            summaries.append(record.content)
    if not summaries:
        raise HTTPException(status_code=404,
                            detail="No hiring-manager summaries generated for this job yet")
    path = excel_service.export_hm_summaries(job, summaries)
    return FileResponse(path, filename=path.name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
