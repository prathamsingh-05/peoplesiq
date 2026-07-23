"""Stages 3-8 — Batch screening, leaderboard, assessments, decisions,
screening questions, call outcomes and hiring-manager summaries."""
from __future__ import annotations

import random
import threading
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import config
from ..audit import log_action
from ..auth import client_ip, require_any_user, require_recruiter
from ..database import SessionLocal, get_db
from ..models import (
    Candidate, CandidateStatus, Evaluation, HMSummary, Job, ProcessingLog,
    Scorecard, ScorecardStatus, ScreeningQuestion, User,
)
from ..schemas import BulkDecisionRequest, CallOutcome, DecisionRequest, QuestionAnswer
from ..services import screening as engine
from ..services import summary as summary_service
from ..services.questions import generate_questions
from ..services.summary import format_profile

router = APIRouter(prefix="/api", tags=["screening"])

# job_id -> progress dict (in-process; suitable for the single-instance prototype)
_screen_progress: dict[int, dict] = {}


def _approved_scorecard(db: Session, job: Job) -> Scorecard:
    scorecard = (
        db.query(Scorecard)
        .filter(Scorecard.job_id == job.id,
                Scorecard.status == ScorecardStatus.approved.value)
        .order_by(Scorecard.version.desc())
        .first()
    )
    if scorecard is None:
        raise HTTPException(
            status_code=409,
            detail="No approved scorecard. The recruiter must review and approve the "
                   "scorecard before screening (human-in-the-loop gate #1).",
        )
    return scorecard


def _evaluation_out(evaluation: Evaluation) -> dict:
    return {
        "id": evaluation.id, "candidate_id": evaluation.candidate_id,
        "scorecard_id": evaluation.scorecard_id,
        "overall_score": evaluation.overall_score,
        "mandatory_status": evaluation.mandatory_status,
        "relevant_experience_years": evaluation.relevant_experience_years,
        "key_strengths": evaluation.key_strengths, "gaps": evaluation.gaps,
        "risk_flags": evaluation.risk_flags,
        "recommendation": evaluation.recommendation,
        "confidence": evaluation.confidence,
        "recruiter_guidance": engine.guidance_for_evaluation(evaluation),
        "executive_summary": evaluation.executive_summary,
        "calibration_notes": evaluation.calibration_notes,
        "overall_impression": evaluation.overall_impression,
        "overall_impression_note": evaluation.overall_impression_note,
        "explanation": evaluation.explanation,
        "criterion_results": evaluation.criterion_results,
        "relevant_projects": evaluation.relevant_projects,
        "missing_information": evaluation.missing_information,
        "inconsistencies": evaluation.inconsistencies,
        "verification_questions": evaluation.verification_questions,
        "engine": evaluation.engine, "model_used": evaluation.model_used,
        "created_at": evaluation.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Stage 3 — Batch screening (background; handles 50+ resumes per batch)
# ---------------------------------------------------------------------------
@router.post("/jobs/{job_id}/screen")
def start_screening(job_id: int, request: Request,
                    user: User = Depends(require_recruiter),
                    db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    scorecard = _approved_scorecard(db, job)

    pending_ids = [
        c.id for c in job.candidates
        if c.status in (CandidateStatus.received.value,)
        or (c.status == CandidateStatus.screened.value and not _has_current_eval(c, scorecard))
    ]
    if not pending_ids:
        raise HTTPException(status_code=400,
                            detail="No candidates awaiting screening for this job")

    progress = _screen_progress.get(job_id)
    if progress and progress.get("running"):
        raise HTTPException(status_code=409, detail="Screening already running for this job")

    batch_id = str(uuid.uuid4())
    _screen_progress[job_id] = {
        "running": True, "batch_id": batch_id, "total": len(pending_ids),
        "done": 0, "failed": 0, "started_at": datetime.now(timezone.utc).isoformat(),
    }
    log_action(db, "screening.batch_started", user=user, entity_type="job",
               entity_id=job.id, details={"batch_id": batch_id, "count": len(pending_ids)},
               ip=client_ip(request), commit=True)

    thread = threading.Thread(
        target=_screen_batch, args=(job_id, scorecard.id, pending_ids, batch_id),
        daemon=True,
    )
    thread.start()
    return {"batch_id": batch_id, "queued": len(pending_ids)}


def _has_current_eval(candidate: Candidate, scorecard: Scorecard) -> bool:
    return any(e.scorecard_id == scorecard.id for e in candidate.evaluations)


def _screen_batch(job_id: int, scorecard_id: int, candidate_ids: list[int],
                  batch_id: str, force: bool = False) -> None:
    """Worker thread: one DB session, one candidate at a time; API failures on a
    single resume never abort the batch."""
    db = SessionLocal()
    progress = _screen_progress[job_id]
    try:
        scorecard = db.get(Scorecard, scorecard_id)
        job = db.get(Job, job_id)
        for cid in candidate_ids:
            candidate = db.get(Candidate, cid)
            try:
                _screen_one(db, candidate, scorecard, job, batch_id, force=force)
                progress["done"] += 1
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                progress["failed"] += 1
                db.add(ProcessingLog(job_id=job_id, batch_id=batch_id,
                                     filename=candidate.resume_filename,
                                     status="error",
                                     message=f"Screening failed: {exc}"[:400],
                                     candidate_id=cid))
                db.commit()
    finally:
        progress["running"] = False
        progress["finished_at"] = datetime.now(timezone.utc).isoformat()
        db.close()


def _screen_one(db: Session, candidate: Candidate, scorecard: Scorecard,
                job: Job, batch_id: str, force: bool = False) -> Evaluation:
    text = candidate.redacted_text or candidate.resume_text
    ihash = engine.input_hash(text, scorecard, job)

    # Consistency guarantee: identical resume + scorecard + job calibration
    # context → reuse the result — for the automatic "screen pending" flow,
    # where idempotency matters more than a fresh read. An explicit recruiter
    # "rescreen" action (force=True) is a request for a genuine fresh look,
    # not idempotency — a recruiter clicking rescreen and getting the exact
    # same cached judgement back, even after the engine itself has improved,
    # would look like nothing happened at all. See scoring principle 14 (judge
    # the whole person) and the docstring's consistency principle (5).
    cached = None if force else (
        db.query(Evaluation)
        .filter(Evaluation.input_hash == ihash, Evaluation.candidate_id == candidate.id)
        .first()
    )
    if cached:
        evaluation = cached
    else:
        result = engine.evaluate(text, scorecard, job)
        evaluation = Evaluation(
            candidate_id=candidate.id, scorecard_id=scorecard.id, input_hash=ihash,
            model_used=config.ANTHROPIC_MODEL if result["engine"] == "llm" else "",
            **{k: v for k, v in result.items() if k != "engine"},
            engine=result["engine"],
        )
        db.add(evaluation)
        db.flush()

        # Stage 6 — questions for shortlist/borderline candidates.
        if evaluation.recommendation in ("shortlist", "recruiter_review"):
            db.query(ScreeningQuestion).filter(
                ScreeningQuestion.candidate_id == candidate.id
            ).delete()
            for order, q in enumerate(generate_questions(candidate, evaluation, job)):
                db.add(ScreeningQuestion(candidate_id=candidate.id, order=order, **q))

    candidate.processed_at = datetime.now(timezone.utc)
    if evaluation.recommendation == "recruiter_review":
        candidate.status = CandidateStatus.awaiting_review.value
    else:
        candidate.status = CandidateStatus.screened.value

    # Fairness control: random sample of AI negatives flagged for human audit.
    if (evaluation.recommendation == "do_not_shortlist"
            and random.random() < config.REJECT_REVIEW_SAMPLE_RATE):
        candidate.flagged_for_review = True

    db.add(ProcessingLog(
        job_id=job.id, batch_id=batch_id, filename=candidate.resume_filename,
        status="screened",
        message=f"Score {evaluation.overall_score} — {evaluation.recommendation} "
                f"({evaluation.engine} engine)",
        candidate_id=candidate.id,
    ))
    log_action(db, "screening.evaluated", entity_type="candidate",
               entity_id=candidate.id,
               details={"score": evaluation.overall_score,
                        "recommendation": evaluation.recommendation,
                        "engine": evaluation.engine})
    db.commit()
    return evaluation


@router.get("/jobs/{job_id}/screen/status")
def screening_status(job_id: int, user: User = Depends(require_any_user)):
    return _screen_progress.get(job_id, {"running": False, "total": 0, "done": 0})


@router.post("/candidates/{candidate_id}/rescreen")
def rescreen_candidate(candidate_id: int, request: Request,
                       user: User = Depends(require_recruiter),
                       db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    job = candidate.job
    scorecard = _approved_scorecard(db, job)
    evaluation = _screen_one(db, candidate, scorecard, job,
                             batch_id="manual-" + str(uuid.uuid4())[:8], force=True)
    log_action(db, "screening.rescreened", user=user, entity_type="candidate",
               entity_id=candidate.id, ip=client_ip(request), commit=True)
    return _evaluation_out(evaluation)


@router.post("/jobs/{job_id}/rescreen-all")
def rescreen_all_candidates(job_id: int, request: Request,
                            user: User = Depends(require_recruiter),
                            db: Session = Depends(get_db)):
    """Re-runs every already-processed candidate on this job against the
    current approved scorecard — a genuine fresh re-analysis for each
    candidate, not a replay of a cached score. This is an explicit recruiter
    request for a new look (after editing scorecard weights/criteria, after
    an engine/prompt improvement, or just to double-check), so it always
    bypasses the consistency cache (unlike the automatic "screen pending"
    batch, which intentionally reuses cached results for idempotency)."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    scorecard = _approved_scorecard(db, job)

    candidate_ids = [
        c.id for c in job.candidates
        if c.status not in (CandidateStatus.duplicate.value, CandidateStatus.unreadable.value)
        and (c.redacted_text or c.resume_text)
    ]
    if not candidate_ids:
        raise HTTPException(status_code=400,
                            detail="No screenable candidates on this job yet")

    progress = _screen_progress.get(job_id)
    if progress and progress.get("running"):
        raise HTTPException(status_code=409, detail="Screening already running for this job")

    batch_id = str(uuid.uuid4())
    _screen_progress[job_id] = {
        "running": True, "batch_id": batch_id, "total": len(candidate_ids),
        "done": 0, "failed": 0, "started_at": datetime.now(timezone.utc).isoformat(),
    }
    log_action(db, "screening.rescreen_all_started", user=user, entity_type="job",
               entity_id=job.id, details={"batch_id": batch_id, "count": len(candidate_ids)},
               ip=client_ip(request), commit=True)

    thread = threading.Thread(
        target=_screen_batch, args=(job_id, scorecard.id, candidate_ids, batch_id),
        kwargs={"force": True},
        daemon=True,
    )
    thread.start()
    return {"batch_id": batch_id, "queued": len(candidate_ids)}


# ---------------------------------------------------------------------------
# Stage 4 — Leaderboard
# ---------------------------------------------------------------------------
@router.get("/jobs/{job_id}/leaderboard")
def leaderboard(job_id: int, user: User = Depends(require_any_user),
                db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    rows = []
    for candidate in job.candidates:
        if not candidate.evaluations:
            continue
        rows.append((candidate.evaluations[0], candidate))
    rows.sort(key=lambda pair: pair[0].overall_score, reverse=True)
    return [engine.leaderboard_row(e, rank, c) for rank, (e, c) in enumerate(rows, start=1)]


@router.get("/jobs/{job_id}/pool-insight")
def get_pool_insight(job_id: int, user: User = Depends(require_any_user),
                     db: Session = Depends(get_db)):
    """A recruiter reading through a batch of resumes forms an opinion about
    the pool as a whole, not just each candidate in isolation — this is that
    read, computed deterministically from the job's stored evaluations."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    evaluations = [c.evaluations[0] for c in job.candidates if c.evaluations]
    return engine.pool_insight(evaluations)


# ---------------------------------------------------------------------------
# Stage 5 — Individual assessment + recruiter decision (HITL gate #2)
# ---------------------------------------------------------------------------
@router.get("/candidates/{candidate_id}/evaluation")
def get_evaluation(candidate_id: int, user: User = Depends(require_any_user),
                   db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not candidate.evaluations:
        raise HTTPException(status_code=404, detail="Candidate has not been screened yet")
    return _evaluation_out(candidate.evaluations[0])


@router.post("/candidates/{candidate_id}/decision")
def record_decision(candidate_id: int, payload: DecisionRequest, request: Request,
                    user: User = Depends(require_recruiter),
                    db: Session = Depends(get_db)):
    """The recruiter's final decision — recorded separately from the AI's
    recommendation, with a mandatory reason for rejections."""
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not candidate.evaluations:
        raise HTTPException(status_code=409,
                            detail="Screen the candidate before recording a decision")
    if payload.decision == "reject" and not payload.rejection_reason.strip():
        raise HTTPException(
            status_code=400,
            detail="A rejection reason is mandatory — no candidate may be rejected "
                   "without an explanation (fairness control §15)",
        )

    result = _apply_decision(db, candidate, payload.decision, payload.comments,
                             payload.rejection_reason, user, request)
    db.commit()
    return result


def _apply_decision(db, candidate: Candidate, decision: str, comments: str,
                    rejection_reason: str, user: User, request: Request) -> dict:
    """Shared decision logic used by the single and bulk decision endpoints."""
    candidate.recruiter_decision = decision
    candidate.recruiter_comments = comments
    candidate.decided_by_id = user.id
    candidate.decided_at = datetime.now(timezone.utc)
    if decision == "shortlist":
        candidate.status = CandidateStatus.shortlisted.value
        candidate.next_action = "Schedule recruiter screening call"
    elif decision == "reject":
        candidate.status = CandidateStatus.rejected.value
        candidate.rejection_reason = rejection_reason
        candidate.next_action = "Send rejection/hold communication (draft)"
    else:
        candidate.status = CandidateStatus.on_hold.value
        candidate.next_action = "Revisit when position resumes"

    ai_rec = candidate.evaluations[0].recommendation
    agreed = (
        (decision == "shortlist" and ai_rec == "shortlist")
        or (decision == "reject" and ai_rec == "do_not_shortlist")
    )
    log_action(db, "decision.recorded", user=user, entity_type="candidate",
               entity_id=candidate.id,
               details={"decision": decision, "ai_recommendation": ai_rec,
                        "agreement": agreed, "rejection_reason": rejection_reason},
               ip=client_ip(request))
    return {"ok": True, "status": candidate.status,
            "ai_recommendation": ai_rec, "agreement": agreed}


@router.post("/jobs/{job_id}/decisions/bulk")
def bulk_decisions(job_id: int, payload: BulkDecisionRequest, request: Request,
                   user: User = Depends(require_recruiter), db: Session = Depends(get_db)):
    """Apply the same decision to many candidates at once (leaderboard bulk
    action). A bulk rejection still requires a shared reason — no candidate is
    ever rejected without an explanation."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if payload.decision == "reject" and not payload.rejection_reason.strip():
        raise HTTPException(status_code=400,
                            detail="A rejection reason is mandatory for bulk rejection")
    applied, skipped = 0, []
    for cid in payload.candidate_ids:
        candidate = db.get(Candidate, cid)
        if candidate is None or candidate.job_id != job_id or not candidate.evaluations:
            skipped.append(cid)
            continue
        _apply_decision(db, candidate, payload.decision, payload.comments,
                        payload.rejection_reason, user, request)
        applied += 1
    log_action(db, "decision.bulk", user=user, entity_type="job", entity_id=job_id,
               details={"decision": payload.decision, "applied": applied,
                        "skipped": skipped}, ip=client_ip(request))
    db.commit()
    return {"applied": applied, "skipped": skipped}


# ---------------------------------------------------------------------------
# Stage 6 — Questions
# ---------------------------------------------------------------------------
@router.get("/candidates/{candidate_id}/questions")
def get_questions(candidate_id: int, user: User = Depends(require_any_user),
                  db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return [
        {"id": q.id, "category": q.category, "question": q.question,
         "rationale": q.rationale, "order": q.order, "answer": q.answer}
        for q in candidate.questions
    ]


@router.post("/candidates/{candidate_id}/questions/regenerate")
def regenerate_questions(candidate_id: int, request: Request,
                         user: User = Depends(require_recruiter),
                         db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or not candidate.evaluations:
        raise HTTPException(status_code=404, detail="Candidate not screened yet")
    db.query(ScreeningQuestion).filter(
        ScreeningQuestion.candidate_id == candidate.id
    ).delete()
    for order, q in enumerate(
        generate_questions(candidate, candidate.evaluations[0], candidate.job)
    ):
        db.add(ScreeningQuestion(candidate_id=candidate.id, order=order, **q))
    log_action(db, "questions.regenerated", user=user, entity_type="candidate",
               entity_id=candidate.id, ip=client_ip(request))
    db.commit()
    return get_questions(candidate_id, user, db)


@router.patch("/questions/{question_id}/answer")
def answer_question(question_id: int, payload: QuestionAnswer,
                    user: User = Depends(require_recruiter),
                    db: Session = Depends(get_db)):
    question = db.get(ScreeningQuestion, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    question.answer = payload.answer
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Stage 7 — Screening call outcome (HITL gate #4)
# ---------------------------------------------------------------------------
@router.post("/candidates/{candidate_id}/call-outcome")
def record_call_outcome(candidate_id: int, payload: CallOutcome, request: Request,
                        user: User = Depends(require_recruiter),
                        db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    for field in ("call_outcome", "call_notes", "current_compensation",
                  "expected_compensation", "notice_period", "motivation_notes",
                  "communication_rating", "shift_confirmed", "location_confirmed"):
        value = getattr(payload, field)
        if value is not None:
            setattr(candidate, field, value)
    candidate.status = CandidateStatus.screening_call_done.value
    if payload.call_outcome == "unreachable":
        candidate.status = CandidateStatus.unreachable.value
        candidate.next_action = "Send 'unreachable' email draft"
    elif payload.proceed_to_hm:
        candidate.next_action = "Generate & approve hiring-manager summary"
    log_action(db, "call_outcome.recorded", user=user, entity_type="candidate",
               entity_id=candidate.id,
               details={"outcome": payload.call_outcome,
                        "proceed_to_hm": payload.proceed_to_hm},
               ip=client_ip(request))
    db.commit()
    return {"ok": True, "status": candidate.status}


# ---------------------------------------------------------------------------
# Stage 8 — Hiring-manager summary (HITL gate #5)
# ---------------------------------------------------------------------------
@router.post("/candidates/{candidate_id}/hm-summary")
def generate_hm_summary(candidate_id: int, request: Request,
                        user: User = Depends(require_recruiter),
                        db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not candidate.evaluations:
        raise HTTPException(status_code=409, detail="Candidate must be screened first")
    content = summary_service.build_summary(
        candidate, candidate.evaluations[0], candidate.job
    )
    record = HMSummary(candidate_id=candidate.id, content=content,
                       formatted_text=format_profile(content))
    db.add(record)
    db.flush()
    log_action(db, "hm_summary.generated", user=user, entity_type="hm_summary",
               entity_id=record.id, details={"candidate_id": candidate.id},
               ip=client_ip(request))
    db.commit()
    return _summary_out(record)


@router.get("/candidates/{candidate_id}/hm-summary")
def get_hm_summary(candidate_id: int, user: User = Depends(require_any_user),
                   db: Session = Depends(get_db)):
    record = (db.query(HMSummary).filter(HMSummary.candidate_id == candidate_id)
              .order_by(HMSummary.id.desc()).first())
    if record is None:
        raise HTTPException(status_code=404, detail="No summary generated yet")
    return _summary_out(record)


@router.post("/hm-summaries/{summary_id}/approve")
def approve_hm_summary(summary_id: int, request: Request,
                       user: User = Depends(require_recruiter),
                       db: Session = Depends(get_db)):
    record = db.get(HMSummary, summary_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    record.status = "approved"
    record.approved_by_id = user.id
    record.approved_at = datetime.now(timezone.utc)
    candidate = record.candidate
    candidate.status = CandidateStatus.submitted_to_hm.value
    candidate.next_action = "Await hiring-manager feedback"
    log_action(db, "hm_summary.approved", user=user, entity_type="hm_summary",
               entity_id=record.id, details={"candidate_id": record.candidate_id},
               ip=client_ip(request))
    db.commit()
    return _summary_out(record)


def _summary_out(record: HMSummary) -> dict:
    return {
        "id": record.id, "candidate_id": record.candidate_id,
        "content": record.content, "formatted_text": record.formatted_text,
        "status": record.status,
        "approved_at": record.approved_at.isoformat() if record.approved_at else None,
        "created_at": record.created_at.isoformat(),
    }
