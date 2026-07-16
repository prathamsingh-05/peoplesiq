"""§8 — Candidate communication: drafts, approval gate, sending, outbox.

Guardrails enforced here:
- No email is ever sent without explicit recruiter approval (HITL gate #3);
  an extracted email address alone never triggers communication.
- Rejection templates are draft-only in this version: they can be approved
  and exported but the send endpoint refuses to transmit them automatically.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import log_action
from ..auth import client_ip, require_any_user, require_recruiter
from ..database import get_db
from ..models import Candidate, EmailMessage, EmailStatus, User
from ..schemas import EmailDraftRequest, EmailEdit
from ..services import emailer

router = APIRouter(prefix="/api", tags=["emails"])

REJECTION_TEMPLATES = {"reject_not_suitable", "hold_future", "position_on_hold"}


def _email_out(message: EmailMessage) -> dict:
    return {
        "id": message.id, "candidate_id": message.candidate_id,
        "template_key": message.template_key, "subject": message.subject,
        "body": message.body, "to_address": message.to_address,
        "status": message.status,
        "scheduled_for": message.scheduled_for.isoformat() if message.scheduled_for else None,
        "sequence_step": message.sequence_step, "sequence_id": message.sequence_id,
        "approved_at": message.approved_at.isoformat() if message.approved_at else None,
        "sent_at": message.sent_at.isoformat() if message.sent_at else None,
        "error": message.error, "created_at": message.created_at.isoformat(),
    }


@router.post("/candidates/{candidate_id}/emails/draft")
def draft_email(candidate_id: int, payload: EmailDraftRequest, request: Request,
                user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    subject, body = emailer.render_template(
        payload.template_key, candidate, candidate.job,
        info_needed=payload.info_needed,
    )
    if payload.template_key == "initial_outreach" and payload.personalise:
        subject, body = emailer.personalise_outreach(candidate, candidate.job, subject, body)
    message = EmailMessage(
        candidate_id=candidate.id, template_key=payload.template_key,
        subject=subject, body=body, to_address=candidate.email,
        created_by_id=user.id,
    )
    db.add(message)
    db.flush()
    log_action(db, "email.drafted", user=user, entity_type="email",
               entity_id=message.id,
               details={"template": payload.template_key, "candidate_id": candidate.id},
               ip=client_ip(request))
    db.commit()
    return _email_out(message)


@router.get("/candidates/{candidate_id}/emails")
def candidate_emails(candidate_id: int, user: User = Depends(require_any_user),
                     db: Session = Depends(get_db)):
    return [
        _email_out(m) for m in
        db.query(EmailMessage).filter(EmailMessage.candidate_id == candidate_id)
        .order_by(EmailMessage.id.desc()).all()
    ]


@router.get("/emails/outbox")
def outbox(status: str | None = None, user: User = Depends(require_any_user),
           db: Session = Depends(get_db)):
    query = db.query(EmailMessage).order_by(EmailMessage.id.desc()).limit(500)
    if status:
        query = query.filter(EmailMessage.status == status)
    return [_email_out(m) for m in query.all()]


@router.put("/emails/{email_id}")
def edit_email(email_id: int, payload: EmailEdit, request: Request,
               user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    message = db.get(EmailMessage, email_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Email not found")
    if message.status == EmailStatus.sent.value:
        raise HTTPException(status_code=409, detail="Sent emails cannot be edited")
    message.subject = payload.subject
    message.body = payload.body
    if payload.to_address:
        message.to_address = payload.to_address
    # Any edit resets approval — the human must re-approve what actually goes out.
    message.status = EmailStatus.draft.value
    message.approved_by_id = None
    message.approved_at = None
    log_action(db, "email.edited", user=user, entity_type="email",
               entity_id=message.id, ip=client_ip(request))
    db.commit()
    return _email_out(message)


@router.post("/emails/{email_id}/approve")
def approve_email(email_id: int, request: Request,
                  user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    """HITL gate #3 — approval is a distinct recorded act."""
    message = db.get(EmailMessage, email_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Email not found")
    if message.status not in (EmailStatus.draft.value,):
        raise HTTPException(status_code=409, detail=f"Cannot approve a {message.status} email")
    if not message.to_address:
        raise HTTPException(status_code=400,
                            detail="Candidate has no email address — correct the record first")
    message.status = EmailStatus.approved.value
    message.approved_by_id = user.id
    message.approved_at = datetime.now(timezone.utc)
    log_action(db, "email.approved", user=user, entity_type="email",
               entity_id=message.id, ip=client_ip(request))
    db.commit()
    return _email_out(message)


@router.post("/emails/{email_id}/send")
def send_email(email_id: int, request: Request,
               user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    message = db.get(EmailMessage, email_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Email not found")
    if message.status != EmailStatus.approved.value:
        raise HTTPException(status_code=409,
                            detail="Only approved emails can be sent (approve first)")
    if message.template_key in REJECTION_TEMPLATES:
        raise HTTPException(
            status_code=403,
            detail="Rejection/hold communications are draft-only in this version — "
                   "export the approved text and send it from your own mailbox "
                   "(brief §8: early prototypes must not auto-send rejections)",
        )
    try:
        emailer.send_email(message)
    except Exception as exc:  # noqa: BLE001
        message.status = EmailStatus.failed.value
        message.error = str(exc)[:500]
        log_action(db, "email.send_failed", user=user, entity_type="email",
                   entity_id=message.id, details={"error": message.error},
                   ip=client_ip(request))
        db.commit()
        raise HTTPException(status_code=502, detail=f"Send failed: {exc}")
    message.status = EmailStatus.sent.value
    message.sent_at = datetime.now(timezone.utc)
    log_action(db, "email.sent", user=user, entity_type="email",
               entity_id=message.id,
               details={"template": message.template_key,
                        "candidate_id": message.candidate_id},
               ip=client_ip(request))
    db.commit()
    return _email_out(message)


@router.post("/emails/{email_id}/cancel")
def cancel_email(email_id: int, request: Request,
                 user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    message = db.get(EmailMessage, email_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Email not found")
    if message.status == EmailStatus.sent.value:
        raise HTTPException(status_code=409, detail="Sent emails cannot be cancelled")
    message.status = EmailStatus.cancelled.value
    log_action(db, "email.cancelled", user=user, entity_type="email",
               entity_id=message.id, ip=client_ip(request))
    db.commit()
    return _email_out(message)


@router.get("/emails/config")
def email_config(user: User = Depends(require_any_user)):
    return {
        "sending_enabled": emailer.sending_configured(),
        "mode": "live" if emailer.sending_configured() else "draft-only",
    }
