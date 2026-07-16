"""Administration: audit logs, fairness review queue, scheduler control,
data-retention actions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import log_action
from ..auth import client_ip, require_admin, require_recruiter
from ..database import get_db
from ..models import AuditLog, Candidate, User
from ..services import scheduler

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/audit-logs")
def audit_logs(limit: int = 200, action: str | None = None,
               entity_type: str | None = None,
               user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    query = db.query(AuditLog).order_by(AuditLog.id.desc())
    if action:
        query = query.filter(AuditLog.action.like(f"{action}%"))
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    return [
        {"id": a.id, "username": a.username, "action": a.action,
         "entity_type": a.entity_type, "entity_id": a.entity_id,
         "details": a.details, "ip_address": a.ip_address,
         "created_at": a.created_at.isoformat()}
        for a in query.limit(min(limit, 1000)).all()
    ]


@router.get("/fairness-review-queue")
def fairness_queue(user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    """Randomly sampled AI-rejected profiles awaiting mandatory human review."""
    rows = (db.query(Candidate)
            .filter(Candidate.flagged_for_review.is_(True))
            .order_by(Candidate.id.desc()).all())
    return [
        {"id": c.id, "candidate_code": c.candidate_code, "full_name": c.full_name,
         "job_title": c.job.title, "status": c.status,
         "ai_recommendation": c.evaluations[0].recommendation if c.evaluations else None,
         "recruiter_decision": c.recruiter_decision}
        for c in rows
    ]


@router.post("/fairness-review/{candidate_id}/complete")
def complete_fairness_review(candidate_id: int, request: Request,
                             user: User = Depends(require_recruiter),
                             db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    candidate.flagged_for_review = False
    log_action(db, "fairness.review_completed", user=user, entity_type="candidate",
               entity_id=candidate.id, ip=client_ip(request))
    db.commit()
    return {"ok": True}


@router.post("/scheduler/run")
def run_scheduler_now(user: User = Depends(require_admin)):
    """Manually trigger a keep-warm/retention tick (also runs every 15 min)."""
    return scheduler.run_tick()


@router.delete("/candidates/{candidate_id}/purge")
def purge_candidate(candidate_id: int, request: Request,
                    admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Data-retention / right-to-erasure: hard-delete one candidate's personal
    data. Admin-only; the audit log keeps a non-personal deletion record."""
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    code = candidate.candidate_code
    import os
    if candidate.stored_path and os.path.exists(candidate.stored_path):
        try:
            os.remove(candidate.stored_path)
        except OSError:
            pass
    db.delete(candidate)
    log_action(db, "candidate.purged", user=admin, entity_type="candidate",
               entity_id=code, details={"reason": "retention/erasure request"},
               ip=client_ip(request))
    db.commit()
    return {"ok": True, "purged": code}
