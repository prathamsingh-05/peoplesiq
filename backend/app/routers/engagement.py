"""§9-10 — Offer acceptance, keep-warm protocol, content library, Day-1 handover."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import log_action
from ..auth import client_ip, require_any_user, require_admin, require_recruiter
from ..database import get_db
from ..models import (
    Candidate, CandidateStatus, ContentItem, EmailMessage, EmailStatus,
    EngagementSequence, SequenceStatus, User,
)
from ..schemas import ContentItemCreate, OfferAccepted
from ..services import emailer

router = APIRouter(prefix="/api", tags=["engagement"])


def _sequence_out(sequence: EngagementSequence, db: Session) -> dict:
    emails = (db.query(EmailMessage)
              .filter(EmailMessage.sequence_id == sequence.id)
              .order_by(EmailMessage.scheduled_for).all())
    return {
        "id": sequence.id, "candidate_id": sequence.candidate_id,
        "status": sequence.status,
        "offer_accepted_date": sequence.offer_accepted_date.isoformat()
            if sequence.offer_accepted_date else None,
        "joining_date": sequence.joining_date.isoformat()
            if sequence.joining_date else None,
        "approved_at": sequence.approved_at.isoformat() if sequence.approved_at else None,
        "stop_reason": sequence.stop_reason,
        "handover_confirmed_at": sequence.handover_confirmed_at.isoformat()
            if sequence.handover_confirmed_at else None,
        "emails": [
            {"id": m.id, "step": m.sequence_step, "subject": m.subject,
             "scheduled_for": m.scheduled_for.isoformat() if m.scheduled_for else None,
             "status": m.status, "sent_at": m.sent_at.isoformat() if m.sent_at else None}
            for m in emails
        ],
    }


@router.post("/candidates/{candidate_id}/offer-accepted")
def offer_accepted(candidate_id: int, payload: OfferAccepted, request: Request,
                   user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    """The recruiter marks Offer Accepted; the system prepares (but does not
    start) the full keep-warm schedule. Starting requires a second explicit
    approval (HITL gate #6)."""
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    joining = payload.joining_date
    if joining.tzinfo is None:
        joining = joining.replace(tzinfo=timezone.utc)
    if joining <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Joining date must be in the future")
    if candidate.sequence and candidate.sequence.status in (
        SequenceStatus.active.value, SequenceStatus.pending_approval.value,
        SequenceStatus.paused.value,
    ):
        raise HTTPException(status_code=409,
                            detail="An engagement sequence already exists for this candidate")

    candidate.status = CandidateStatus.offer_accepted.value
    candidate.offer_status = "Accepted"
    candidate.joining_date = joining
    candidate.joining_status = "Awaiting joining"
    candidate.next_action = "Approve keep-warm engagement sequence"

    if candidate.sequence:  # a previously stopped sequence — replace it
        db.delete(candidate.sequence)
        db.flush()
    sequence = EngagementSequence(
        candidate_id=candidate.id,
        offer_accepted_date=datetime.now(timezone.utc),
        joining_date=joining,
    )
    db.add(sequence)
    db.flush()
    messages = emailer.build_keepwarm_schedule(db, sequence, candidate, candidate.job)
    # Until the sequence itself is approved, its emails stay inert.
    for message in messages:
        message.status = EmailStatus.draft.value
    # Inject Day-1 specifics provided by the recruiter into the T-1 email.
    for message in messages:
        if message.sequence_step in ("day1_t1", "welcome_day0"):
            subject, body = emailer.render_template(
                message.sequence_step, candidate, candidate.job,
                joining_date=joining.strftime("%A, %d %B %Y"),
                reporting_time=payload.reporting_time,
                induction_link=payload.induction_link or "Will be shared by the onboarding team",
                reporting_manager=payload.reporting_manager or "Shared in your welcome pack",
                help_contact=payload.help_contact or emailer.config.SMTP_FROM,
            )
            message.subject, message.body = subject, body

    log_action(db, "offer.accepted", user=user, entity_type="candidate",
               entity_id=candidate.id,
               details={"joining_date": joining.isoformat(), "planned_emails": len(messages)},
               ip=client_ip(request))
    db.commit()
    return _sequence_out(sequence, db)


@router.get("/candidates/{candidate_id}/sequence")
def get_sequence(candidate_id: int, user: User = Depends(require_any_user),
                 db: Session = Depends(get_db)):
    sequence = (db.query(EngagementSequence)
                .filter(EngagementSequence.candidate_id == candidate_id).first())
    if sequence is None:
        raise HTTPException(status_code=404, detail="No engagement sequence")
    return _sequence_out(sequence, db)


@router.post("/sequences/{sequence_id}/approve")
def approve_sequence(sequence_id: int, request: Request,
                     user: User = Depends(require_recruiter),
                     db: Session = Depends(get_db)):
    """HITL gate #6 — the sequence only becomes live after explicit approval."""
    sequence = db.get(EngagementSequence, sequence_id)
    if sequence is None:
        raise HTTPException(status_code=404, detail="Sequence not found")
    if sequence.status != SequenceStatus.pending_approval.value:
        raise HTTPException(status_code=409, detail=f"Sequence is {sequence.status}")
    sequence.status = SequenceStatus.active.value
    sequence.approved_by_id = user.id
    sequence.approved_at = datetime.now(timezone.utc)
    db.query(EmailMessage).filter(
        EmailMessage.sequence_id == sequence.id,
        EmailMessage.status == EmailStatus.draft.value,
    ).update({"status": EmailStatus.approved.value})
    log_action(db, "sequence.approved", user=user, entity_type="sequence",
               entity_id=sequence.id, ip=client_ip(request))
    db.commit()
    return _sequence_out(sequence, db)


@router.post("/sequences/{sequence_id}/pause")
def pause_sequence(sequence_id: int, request: Request,
                   user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    return _transition(sequence_id, SequenceStatus.paused, "Paused by recruiter",
                       request, user, db)


@router.post("/sequences/{sequence_id}/resume")
def resume_sequence(sequence_id: int, request: Request,
                    user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    sequence = db.get(EngagementSequence, sequence_id)
    if sequence is None:
        raise HTTPException(status_code=404, detail="Sequence not found")
    if sequence.status != SequenceStatus.paused.value:
        raise HTTPException(status_code=409, detail="Only paused sequences can resume")
    sequence.status = SequenceStatus.active.value
    sequence.stop_reason = ""
    log_action(db, "sequence.resumed", user=user, entity_type="sequence",
               entity_id=sequence.id, ip=client_ip(request))
    db.commit()
    return _sequence_out(sequence, db)


@router.post("/sequences/{sequence_id}/stop")
def stop_sequence(sequence_id: int, reason: str, request: Request,
                  user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    """Stop rules §9: declined / joining-date change / withdrawn / paused / joined."""
    return _transition(sequence_id, SequenceStatus.stopped, reason or "Stopped by recruiter",
                       request, user, db, cancel_pending=True)


def _transition(sequence_id: int, target: SequenceStatus, reason: str,
                request: Request, user: User, db: Session,
                cancel_pending: bool = False) -> dict:
    sequence = db.get(EngagementSequence, sequence_id)
    if sequence is None:
        raise HTTPException(status_code=404, detail="Sequence not found")
    sequence.status = target.value
    sequence.stop_reason = reason
    if cancel_pending:
        db.query(EmailMessage).filter(
            EmailMessage.sequence_id == sequence.id,
            EmailMessage.status.in_([EmailStatus.approved.value, EmailStatus.draft.value]),
        ).update({"status": EmailStatus.cancelled.value})
    log_action(db, f"sequence.{target.value}", user=user, entity_type="sequence",
               entity_id=sequence.id, details={"reason": reason}, ip=client_ip(request))
    db.commit()
    return _sequence_out(sequence, db)


@router.post("/candidates/{candidate_id}/handover")
def confirm_handover(candidate_id: int, request: Request,
                     user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    """HITL gate #8 — explicit confirmation before transferring to the client's
    onboarding team. After this, no further automated communication is sent."""
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.status not in (CandidateStatus.joined.value,
                                CandidateStatus.offer_accepted.value):
        raise HTTPException(status_code=409,
                            detail="Handover applies to joined candidates")
    candidate.status = CandidateStatus.handover_complete.value
    candidate.joining_status = "Joined — handed over to client HR"
    candidate.next_action = "None — record retained for reporting only"
    if candidate.sequence:
        candidate.sequence.status = SequenceStatus.completed.value
        candidate.sequence.handover_confirmed_by_id = user.id
        candidate.sequence.handover_confirmed_at = datetime.now(timezone.utc)
        db.query(EmailMessage).filter(
            EmailMessage.sequence_id == candidate.sequence.id,
            EmailMessage.status.in_([EmailStatus.approved.value, EmailStatus.draft.value]),
        ).update({"status": EmailStatus.cancelled.value})
    log_action(db, "candidate.handover_confirmed", user=user, entity_type="candidate",
               entity_id=candidate.id, ip=client_ip(request))
    db.commit()
    return {"ok": True, "status": candidate.status}


# ---------------------------------------------------------------------------
# Content library (preloaded, approved keep-warm content)
# ---------------------------------------------------------------------------
@router.get("/content-library")
def list_content(user: User = Depends(require_any_user), db: Session = Depends(get_db)):
    return [
        {"id": c.id, "title": c.title, "content_type": c.content_type,
         "body": c.body, "url": c.url, "is_approved": c.is_approved,
         "is_active": c.is_active}
        for c in db.query(ContentItem).order_by(ContentItem.id).all()
    ]


@router.post("/content-library", status_code=201)
def create_content(payload: ContentItemCreate, request: Request,
                   user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    item = ContentItem(**payload.model_dump())
    db.add(item)
    db.flush()
    log_action(db, "content.created", user=user, entity_type="content",
               entity_id=item.id, ip=client_ip(request))
    db.commit()
    return {"id": item.id}


@router.post("/content-library/{item_id}/approve")
def approve_content(item_id: int, request: Request,
                    admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(ContentItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Content item not found")
    item.is_approved = True
    item.approved_by_id = admin.id
    log_action(db, "content.approved", user=admin, entity_type="content",
               entity_id=item.id, ip=client_ip(request))
    db.commit()
    return {"ok": True}


@router.post("/content-library/{item_id}/toggle-active")
def toggle_content(item_id: int, request: Request,
                   user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    item = db.get(ContentItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Content item not found")
    item.is_active = not item.is_active
    log_action(db, "content.toggled", user=user, entity_type="content",
               entity_id=item.id, details={"is_active": item.is_active},
               ip=client_ip(request))
    db.commit()
    return {"ok": True, "is_active": item.is_active}
