"""Stage 1 — Jobs and scorecards (with the mandatory approval gate)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import log_action
from ..auth import client_ip, require_any_user, require_recruiter
from ..database import get_db
from ..models import (
    Candidate, Job, JobStatus, Scorecard, ScorecardCriterion, ScorecardStatus, User,
)
from ..schemas import JobCreate, JobUpdate, ScorecardUpdate
from ..services.scorecard import generate_scorecard_criteria

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _job_out(job: Job, db: Session | None = None) -> dict:
    approved = next((s for s in job.scorecards if s.status == "approved"), None)
    return {
        "id": job.id, "job_code": job.job_code, "title": job.title,
        "client_name": job.client_name, "description": job.description,
        "location": job.location, "working_hours": job.working_hours,
        "work_model": job.work_model,
        "min_experience_years": job.min_experience_years,
        "essential_skills": job.essential_skills,
        "preferred_skills": job.preferred_skills,
        "qualifications": job.qualifications,
        "compensation_range": job.compensation_range,
        "notice_period_preference": job.notice_period_preference,
        "mandatory_conditions": job.mandatory_conditions,
        "seniority_tier": job.seniority_tier,
        "good_enough_note": job.good_enough_note,
        "success_criteria": job.success_criteria,
        "ideal_candidate_profile": job.ideal_candidate_profile,
        "domain_context": job.domain_context,
        "status": job.status,
        "owner": job.owner.full_name if job.owner else "",
        "candidate_count": len(job.candidates),
        "has_approved_scorecard": approved is not None,
        "created_at": job.created_at.isoformat(),
    }


def _scorecard_out(scorecard: Scorecard) -> dict:
    return {
        "id": scorecard.id, "job_id": scorecard.job_id, "version": scorecard.version,
        "status": scorecard.status, "generated_by_ai": scorecard.generated_by_ai,
        "approved_by": scorecard.approved_by.full_name if scorecard.approved_by else None,
        "approved_at": scorecard.approved_at.isoformat() if scorecard.approved_at else None,
        "criteria": [
            {
                "id": c.id, "category": c.category, "name": c.name,
                "description": c.description, "weight": c.weight,
                "is_mandatory": c.is_mandatory,
            }
            for c in scorecard.criteria
        ],
    }


def next_code(db: Session, model, column, prefix: str, width: int) -> str:
    count = db.query(model).count()
    return f"{prefix}-{count + 1:0{width}d}"


@router.get("")
def list_jobs(user: User = Depends(require_any_user), db: Session = Depends(get_db)):
    return [_job_out(j) for j in db.query(Job).order_by(Job.id.desc()).all()]


@router.post("", status_code=201)
def create_job(payload: JobCreate, request: Request,
               user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    job = Job(
        job_code=next_code(db, Job, Job.id, "JOB", 4),
        owner_id=user.id,
        **payload.model_dump(),
    )
    db.add(job)
    db.flush()
    log_action(db, "job.created", user=user, entity_type="job", entity_id=job.id,
               details={"title": job.title}, ip=client_ip(request))
    db.commit()
    return _job_out(job)


@router.get("/{job_id}")
def get_job(job_id: int, user: User = Depends(require_any_user),
            db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_out(job)


@router.patch("/{job_id}")
def update_job(job_id: int, payload: JobUpdate, request: Request,
               user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    changes = payload.model_dump(exclude_unset=True)
    jd_fields = {"description", "essential_skills", "preferred_skills",
                 "mandatory_conditions", "min_experience_years", "qualifications",
                 "seniority_tier", "compensation_range", "good_enough_note",
                 "success_criteria", "ideal_candidate_profile", "domain_context"}
    for key, value in changes.items():
        setattr(job, key, value)
    # Changing the requirement invalidates approval: scorecard must be re-approved.
    if jd_fields & set(changes):
        for scorecard in job.scorecards:
            if scorecard.status == ScorecardStatus.approved.value:
                scorecard.status = ScorecardStatus.superseded.value
        if job.status == JobStatus.active.value:
            job.status = JobStatus.draft.value
    log_action(db, "job.updated", user=user, entity_type="job", entity_id=job.id,
               details={"fields": sorted(changes)}, ip=client_ip(request))
    db.commit()
    return _job_out(job)


# --- Scorecard lifecycle ------------------------------------------------------
@router.post("/{job_id}/scorecard/generate")
def generate_scorecard(job_id: int, request: Request,
                       user: User = Depends(require_recruiter),
                       db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    criteria, by_ai = generate_scorecard_criteria(job)
    version = max((s.version for s in job.scorecards), default=0) + 1
    scorecard = Scorecard(job_id=job.id, version=version, generated_by_ai=by_ai)
    db.add(scorecard)
    db.flush()
    for c in criteria:
        db.add(ScorecardCriterion(scorecard_id=scorecard.id, **c))
    log_action(db, "scorecard.generated", user=user, entity_type="scorecard",
               entity_id=scorecard.id,
               details={"job_id": job.id, "criteria": len(criteria), "by_ai": by_ai},
               ip=client_ip(request))
    db.commit()
    db.refresh(scorecard)
    return _scorecard_out(scorecard)


@router.get("/{job_id}/scorecard")
def get_scorecard(job_id: int, user: User = Depends(require_any_user),
                  db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.scorecards:
        raise HTTPException(status_code=404, detail="No scorecard generated yet")
    latest = sorted(job.scorecards, key=lambda s: s.version)[-1]
    return _scorecard_out(latest)


@router.put("/{job_id}/scorecard/{scorecard_id}")
def edit_scorecard(job_id: int, scorecard_id: int, payload: ScorecardUpdate,
                   request: Request, user: User = Depends(require_recruiter),
                   db: Session = Depends(get_db)):
    scorecard = db.get(Scorecard, scorecard_id)
    if scorecard is None or scorecard.job_id != job_id:
        raise HTTPException(status_code=404, detail="Scorecard not found")
    if scorecard.status == ScorecardStatus.approved.value:
        raise HTTPException(
            status_code=409,
            detail="Approved scorecards are immutable — generate a new version instead",
        )
    for criterion in list(scorecard.criteria):
        db.delete(criterion)
    db.flush()
    for c in payload.criteria:
        db.add(ScorecardCriterion(scorecard_id=scorecard.id, **c.model_dump()))
    scorecard.generated_by_ai = False
    log_action(db, "scorecard.edited", user=user, entity_type="scorecard",
               entity_id=scorecard.id, details={"criteria": len(payload.criteria)},
               ip=client_ip(request))
    db.commit()
    db.refresh(scorecard)
    return _scorecard_out(scorecard)


@router.post("/{job_id}/scorecard/{scorecard_id}/approve")
def approve_scorecard(job_id: int, scorecard_id: int, request: Request,
                      user: User = Depends(require_recruiter),
                      db: Session = Depends(get_db)):
    """HITL gate #1 — screening is impossible until a scorecard is approved."""
    scorecard = db.get(Scorecard, scorecard_id)
    if scorecard is None or scorecard.job_id != job_id:
        raise HTTPException(status_code=404, detail="Scorecard not found")
    if not scorecard.criteria:
        raise HTTPException(status_code=400, detail="Cannot approve an empty scorecard")
    for other in scorecard.job.scorecards:
        if other.id != scorecard.id and other.status == ScorecardStatus.approved.value:
            other.status = ScorecardStatus.superseded.value
    scorecard.status = ScorecardStatus.approved.value
    scorecard.approved_by_id = user.id
    scorecard.approved_at = datetime.now(timezone.utc)
    scorecard.job.status = JobStatus.active.value
    log_action(db, "scorecard.approved", user=user, entity_type="scorecard",
               entity_id=scorecard.id, details={"job_id": job_id,
               "version": scorecard.version}, ip=client_ip(request))
    db.commit()
    return _scorecard_out(scorecard)


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: int, request: Request,
               user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    """Removes a job and everything under it (scorecards, candidates, evaluations)."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    log_action(db, "job.deleted", user=user, entity_type="job", entity_id=job.id,
               details={"title": job.title, "job_code": job.job_code,
                        "candidate_count": len(job.candidates)}, ip=client_ip(request))
    # A candidate flagged as a duplicate of another candidate in the same job
    # (routers/candidates.py) points at it via a self-referential FK — clear
    # it defensively so that link can never block deletion, regardless of
    # what order SQLAlchemy happens to delete the candidates in.
    for candidate in job.candidates:
        candidate.duplicate_of_id = None
    db.flush()
    try:
        db.delete(job)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Could not delete this job because related records are still "
                   "linked to it. Please contact support.",
        )
    return None
