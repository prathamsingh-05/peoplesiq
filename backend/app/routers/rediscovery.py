"""Talent rediscovery + responsible-AI reporting endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import log_action
from ..auth import client_ip, require_any_user, require_recruiter
from ..database import get_db
from ..models import Candidate, Job, Scorecard, ScorecardStatus, User
from ..schemas import RediscoveryPull
from ..services import rediscovery, reporting

router = APIRouter(prefix="/api", tags=["rediscovery"])


def _approved(db: Session, job: Job) -> Scorecard:
    sc = (db.query(Scorecard)
          .filter(Scorecard.job_id == job.id,
                  Scorecard.status == ScorecardStatus.approved.value)
          .order_by(Scorecard.version.desc()).first())
    if sc is None:
        raise HTTPException(status_code=409,
                            detail="Approve the scorecard before rediscovering talent")
    return sc


@router.get("/jobs/{job_id}/rediscover")
def rediscover(job_id: int, user: User = Depends(require_any_user),
               db: Session = Depends(get_db)):
    """Resurface previously screened candidates from other roles that match this
    job — including 'silver medalists' who progressed elsewhere."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    scorecard = _approved(db, job)
    return rediscovery.find_matches(db, job, scorecard)


@router.post("/jobs/{job_id}/rediscover/pull")
def pull(job_id: int, payload: RediscoveryPull, request: Request,
         user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    """Pull rediscovered candidates into this job as fresh records so they flow
    through the normal evidence-based screening and all human gates."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    _approved(db, job)
    pulled = []
    for cid in payload.candidate_ids:
        source = db.get(Candidate, cid)
        if source is None or source.job_id == job_id:
            continue
        code = f"CAND-{db.query(Candidate).count() + 1:05d}"
        clone = rediscovery.pull_into_job(db, source, job, code)
        db.flush()
        pulled.append({"candidate_id": clone.id, "candidate_code": clone.candidate_code,
                       "from": source.candidate_code})
    log_action(db, "rediscovery.pulled", user=user, entity_type="job", entity_id=job_id,
               details={"count": len(pulled)}, ip=client_ip(request))
    db.commit()
    return {"pulled": pulled, "next": "Run screening to evaluate the pulled candidates"}


@router.get("/responsible-ai-report")
def responsible_ai_report(job_id: int | None = None,
                          user: User = Depends(require_recruiter),
                          db: Session = Depends(get_db)):
    """Generated responsible-AI / bias-audit report (Brief §15)."""
    return reporting.responsible_ai_report(db, job_id)
