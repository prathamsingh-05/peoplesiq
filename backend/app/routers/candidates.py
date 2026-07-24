"""Stage 2 — Resume upload (folder/batch), parsing, duplicates, processing log."""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from .. import config
from ..audit import log_action
from ..auth import client_ip, require_any_user, require_recruiter
from ..database import get_db
from ..models import (
    Candidate, CandidateStatus, Job, ProcessingLog, User,
)
from ..schemas import CandidateCorrection, StatusUpdate
from ..services import career_timeline, resume_parser
from ..services.fairness import redact_protected_attributes

router = APIRouter(prefix="/api", tags=["candidates"])

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-]")


def candidate_out(candidate: Candidate, include_text: bool = False) -> dict:
    latest = candidate.evaluations[0] if candidate.evaluations else None
    data = {
        "id": candidate.id, "candidate_code": candidate.candidate_code,
        "job_id": candidate.job_id, "full_name": candidate.full_name,
        "email": candidate.email, "phone": candidate.phone,
        "location": candidate.location, "current_role": candidate.current_role,
        "current_employer": candidate.current_employer,
        "resume_filename": candidate.resume_filename, "source": candidate.source,
        "status": candidate.status, "is_duplicate": candidate.is_duplicate,
        "parse_error": candidate.parse_error,
        "recruiter_decision": candidate.recruiter_decision,
        "recruiter_comments": candidate.recruiter_comments,
        "rejection_reason": candidate.rejection_reason,
        "flagged_for_review": candidate.flagged_for_review,
        "correction_note": candidate.correction_note,
        "call_outcome": candidate.call_outcome, "call_notes": candidate.call_notes,
        "current_compensation": candidate.current_compensation,
        "expected_compensation": candidate.expected_compensation,
        "notice_period": candidate.notice_period,
        "motivation_notes": candidate.motivation_notes,
        "communication_rating": candidate.communication_rating,
        "shift_confirmed": candidate.shift_confirmed,
        "location_confirmed": candidate.location_confirmed,
        "interview_stage": candidate.interview_stage,
        "interview_date": candidate.interview_date.isoformat() if candidate.interview_date else None,
        "feedback_status": candidate.feedback_status,
        "offer_status": candidate.offer_status,
        "joining_date": candidate.joining_date.isoformat() if candidate.joining_date else None,
        "joining_status": candidate.joining_status,
        "next_action": candidate.next_action, "owner": candidate.owner,
        "received_at": candidate.received_at.isoformat(),
        "processed_at": candidate.processed_at.isoformat() if candidate.processed_at else None,
        "parsed_profile": candidate.parsed_profile,
        "career_timeline": career_timeline.build_timeline(
            (candidate.parsed_profile or {}).get("employers")
        ),
        "latest_evaluation_id": latest.id if latest else None,
        "ai_score": latest.overall_score if latest else None,
        "ai_recommendation": latest.recommendation if latest else None,
    }
    if include_text:
        data["resume_text"] = candidate.resume_text
    return data


@router.post("/jobs/{job_id}/candidates/upload")
async def upload_resumes(job_id: int, request: Request,
                         files: list[UploadFile] = File(...),
                         user: User = Depends(require_recruiter),
                         db: Session = Depends(get_db)):
    """Batch upload — the 'folder where you dump CVs per JD'. Accepts up to
    MAX_BATCH_FILES PDFs/DOCX per call; every file gets a ProcessingLog row."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if len(files) > config.MAX_BATCH_FILES:
        raise HTTPException(status_code=413,
                            detail=f"Max {config.MAX_BATCH_FILES} files per batch")

    batch_id = str(uuid.uuid4())
    results = {"batch_id": batch_id, "processed": 0, "duplicates": 0,
               "unreadable": 0, "errors": 0, "items": []}

    for upload in files:
        filename = _SAFE_NAME.sub("_", upload.filename or "resume")
        raw = await upload.read()
        item = {"filename": filename, "status": "", "message": "", "candidate_id": None}
        try:
            if len(raw) > config.MAX_UPLOAD_BYTES:
                raise ValueError(f"File exceeds {config.MAX_UPLOAD_BYTES // (1024*1024)} MB limit")
            ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
            if ext not in config.ALLOWED_RESUME_EXTENSIONS:
                raise ValueError(f"Unsupported file type {ext} — allowed: PDF, DOCX, DOC, TXT")

            file_hash = hashlib.sha256(raw).hexdigest()
            existing = db.query(Candidate).filter(
                Candidate.job_id == job.id, Candidate.file_sha256 == file_hash
            ).first()
            if existing:
                item.update(status="duplicate",
                            message=f"Exact duplicate of {existing.candidate_code}",
                            candidate_id=existing.id)
                results["duplicates"] += 1
                _log(db, job.id, batch_id, filename, "duplicate", item["message"], existing.id)
                results["items"].append(item)
                continue

            parse = resume_parser.extract_text(filename, raw)
            candidate = Candidate(
                candidate_code=_next_candidate_code(db),
                job_id=job.id,
                resume_filename=filename,
                file_sha256=file_hash,
                resume_text=parse["text"],
                parse_error=parse["error"],
                source="Batch upload",
            )

            stored = config.UPLOAD_DIR / f"{candidate.candidate_code}_{filename}"
            stored.write_bytes(raw)
            candidate.stored_path = str(stored)

            if not parse["readable"]:
                candidate.status = CandidateStatus.unreadable.value
                db.add(candidate)
                db.flush()
                item.update(status="unreadable", message=parse["error"],
                            candidate_id=candidate.id)
                results["unreadable"] += 1
                _log(db, job.id, batch_id, filename, "unreadable", parse["error"], candidate.id)
                results["items"].append(item)
                continue

            # Deterministic contact extraction, then content-level duplicate check.
            contact = resume_parser.extract_contact(parse["text"])
            candidate.full_name = contact["full_name"]
            candidate.email = contact["email"]
            candidate.phone = contact["phone"]
            dup = _find_content_duplicate(db, job.id, contact)
            if dup:
                candidate.is_duplicate = True
                candidate.duplicate_of_id = dup.id
                candidate.status = CandidateStatus.duplicate.value
                db.add(candidate)
                db.flush()
                item.update(status="duplicate",
                            message=f"Same contact details as {dup.candidate_code}",
                            candidate_id=candidate.id)
                results["duplicates"] += 1
                _log(db, job.id, batch_id, filename, "duplicate", item["message"], candidate.id)
                results["items"].append(item)
                continue

            # Fairness redaction BEFORE any AI sees the text.
            redacted, applied = redact_protected_attributes(parse["text"])
            candidate.redacted_text = redacted

            profile = resume_parser.extract_profile(redacted)
            candidate.parsed_profile = profile
            if profile.get("full_name") and not candidate.full_name:
                candidate.full_name = profile["full_name"]
            candidate.current_role = profile.get("current_role", "")
            candidate.current_employer = profile.get("current_employer", "")
            candidate.location = profile.get("location_city", "")
            candidate.processed_at = datetime.now(timezone.utc)
            candidate.owner = user.full_name
            db.add(candidate)
            db.flush()

            item.update(status="processed", candidate_id=candidate.id,
                        message=f"Parsed OK ({len(parse['text'])} chars"
                                + (f"; redacted: {', '.join(applied)}" if applied else "") + ")")
            results["processed"] += 1
            _log(db, job.id, batch_id, filename, "processed", item["message"], candidate.id)
        except Exception as exc:  # noqa: BLE001 — a bad file must not sink the batch
            db.rollback()
            item.update(status="error", message=str(exc)[:400])
            results["errors"] += 1
            _log(db, job.id, batch_id, filename, "error", str(exc)[:400], None)
            db.commit()
            results["items"].append(item)
            continue
        results["items"].append(item)

    log_action(db, "candidates.batch_uploaded", user=user, entity_type="job",
               entity_id=job.id,
               details={k: results[k] for k in ("batch_id", "processed", "duplicates",
                                                "unreadable", "errors")},
               ip=client_ip(request))
    db.commit()
    return results


def _next_candidate_code(db: Session) -> str:
    return f"CAND-{db.query(Candidate).count() + 1:05d}"


def _find_content_duplicate(db: Session, job_id: int, contact: dict) -> Candidate | None:
    email = resume_parser.normalise_email(contact.get("email", ""))
    phone = resume_parser.normalise_phone(contact.get("phone", ""))
    if not email and not phone:
        return None
    for other in db.query(Candidate).filter(
        Candidate.job_id == job_id, Candidate.is_duplicate.is_(False)
    ).all():
        if email and resume_parser.normalise_email(other.email) == email:
            return other
        if phone and len(phone) >= 10 and resume_parser.normalise_phone(other.phone) == phone:
            return other
    return None


def _log(db: Session, job_id: int, batch_id: str, filename: str, status: str,
         message: str, candidate_id: int | None) -> None:
    db.add(ProcessingLog(job_id=job_id, batch_id=batch_id, filename=filename,
                         status=status, message=message, candidate_id=candidate_id))


def find_candidate_history(db: Session, candidate: Candidate) -> list[dict]:
    """Other applications by the same person, across every job — same
    normalized email/phone match used for within-job duplicate detection
    (_find_content_duplicate), just not scoped to one job. A real recruiter
    remembers (or at least can look up) whether they've seen someone before;
    without this, every screening treats the candidate as a stranger even if
    they applied for three other roles last quarter."""
    email = resume_parser.normalise_email(candidate.email)
    phone = resume_parser.normalise_phone(candidate.phone)
    if not email and not phone:
        return []
    others = (
        db.query(Candidate)
        .filter(Candidate.id != candidate.id, Candidate.job_id != candidate.job_id)
        .all()
    )
    matches = []
    for other in others:
        same_email = bool(email) and resume_parser.normalise_email(other.email) == email
        same_phone = (bool(phone) and len(phone) >= 10
                      and resume_parser.normalise_phone(other.phone) == phone)
        if not (same_email or same_phone):
            continue
        latest = other.evaluations[0] if other.evaluations else None
        matches.append({
            "candidate_id": other.id, "candidate_code": other.candidate_code,
            "job_id": other.job_id, "job_code": other.job.job_code if other.job else "",
            "job_title": other.job.title if other.job else "",
            "status": other.status, "recruiter_decision": other.recruiter_decision,
            "overall_score": latest.overall_score if latest else None,
            "recommendation": latest.recommendation if latest else None,
            "applied_at": other.received_at.isoformat() if other.received_at else None,
        })
    matches.sort(key=lambda m: m["applied_at"] or "", reverse=True)
    return matches


@router.get("/jobs/{job_id}/candidates")
def list_candidates(job_id: int, user: User = Depends(require_any_user),
                    db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return [candidate_out(c) for c in
            sorted(job.candidates, key=lambda c: c.id, reverse=True)]


@router.get("/jobs/{job_id}/processing-log")
def processing_log(job_id: int, user: User = Depends(require_any_user),
                   db: Session = Depends(get_db)):
    rows = (db.query(ProcessingLog).filter(ProcessingLog.job_id == job_id)
            .order_by(ProcessingLog.id.desc()).limit(500).all())
    return [
        {"id": r.id, "batch_id": r.batch_id, "filename": r.filename,
         "status": r.status, "message": r.message, "candidate_id": r.candidate_id,
         "created_at": r.created_at.isoformat()}
        for r in rows
    ]


@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: int, user: User = Depends(require_any_user),
                  db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate_out(candidate, include_text=True)


@router.get("/candidates/{candidate_id}/history")
def get_candidate_history(candidate_id: int, user: User = Depends(require_any_user),
                          db: Session = Depends(get_db)):
    """Other roles this same person has applied to, so a recruiter screening
    them today has continuity instead of treating every job as if the
    candidate has no history with the company."""
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return find_candidate_history(db, candidate)


@router.patch("/candidates/{candidate_id}/correct")
def correct_candidate(candidate_id: int, payload: CandidateCorrection,
                      request: Request, user: User = Depends(require_recruiter),
                      db: Session = Depends(get_db)):
    """Fairness §15 — documented process for correcting candidate information."""
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    changes = payload.model_dump(exclude_unset=True, exclude={"correction_note"})
    before = {k: getattr(candidate, k) for k in changes}
    for key, value in changes.items():
        if value is not None:
            setattr(candidate, key, value)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    candidate.correction_note = (
        candidate.correction_note
        + f"\n[{stamp} by {user.full_name}] {payload.correction_note}"
    ).strip()
    log_action(db, "candidate.corrected", user=user, entity_type="candidate",
               entity_id=candidate.id,
               details={"before": before, "after": changes, "note": payload.correction_note},
               ip=client_ip(request))
    db.commit()
    return candidate_out(candidate)


@router.patch("/candidates/{candidate_id}/status")
def update_status(candidate_id: int, payload: StatusUpdate, request: Request,
                  user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    """Tracker status management (interview stages, offer, joining, next action)."""
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    valid = {s.value for s in CandidateStatus}
    if payload.status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. One of: {sorted(valid)}")
    if payload.status == CandidateStatus.rejected.value and not (
        payload.rejection_reason or candidate.rejection_reason
    ):
        raise HTTPException(status_code=400,
                            detail="A rejection reason is mandatory (fairness control)")
    if payload.status == CandidateStatus.offer_accepted.value:
        raise HTTPException(
            status_code=400,
            detail="Use POST /api/candidates/{id}/offer-accepted so the keep-warm "
                   "sequence is prepared with a joining date",
        )
    before = candidate.status
    candidate.status = payload.status
    for field in ("interview_stage", "interview_date", "feedback_status", "offer_status",
                  "joining_date", "joining_status", "next_action", "owner",
                  "rejection_reason"):
        value = getattr(payload, field)
        if value is not None:
            setattr(candidate, field, value)
    log_action(db, "candidate.status_changed", user=user, entity_type="candidate",
               entity_id=candidate.id,
               details={"from": before, "to": payload.status}, ip=client_ip(request))
    db.commit()
    return candidate_out(candidate)
