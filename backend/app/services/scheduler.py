"""Background scheduler.

Runs inside the FastAPI process (asyncio task) and, every 15 minutes:
1. Dispatches due keep-warm emails for ACTIVE sequences (sending only when
   SMTP sending is enabled; otherwise items stay queued and visible).
2. Applies stop rules: paused/stopped sequences never send; a sequence whose
   joining date passed is completed and the candidate handed over.
3. Data retention: flags candidates past the retention window for deletion
   review (never silently deletes personal data).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from ..database import SessionLocal
from ..models import (
    Candidate,
    CandidateStatus,
    EmailMessage,
    EmailStatus,
    EngagementSequence,
    SequenceStatus,
)
from .. import config
from ..audit import log_action
from . import emailer

logger = logging.getLogger("peopleiq.scheduler")

TICK_SECONDS = 15 * 60
_task: asyncio.Task | None = None


async def start() -> None:
    global _task
    _task = asyncio.create_task(_loop())


async def stop() -> None:
    if _task:
        _task.cancel()


async def _loop() -> None:
    while True:
        try:
            await asyncio.to_thread(run_tick)
        except Exception:  # noqa: BLE001
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(TICK_SECONDS)


def run_tick(now: datetime | None = None) -> dict:
    """One scheduler pass. Separated from the loop for testability and for
    the manual 'Run scheduler now' admin endpoint."""
    now = now or datetime.now(timezone.utc)
    stats = {"sent": 0, "skipped": 0, "failed": 0, "completed_sequences": 0}
    db = SessionLocal()
    try:
        active = (
            db.query(EngagementSequence)
            .filter(EngagementSequence.status == SequenceStatus.active.value)
            .all()
        )
        for sequence in active:
            candidate = db.get(Candidate, sequence.candidate_id)
            if candidate is None:
                continue

            # Stop rules (brief §9): declined / withdrawn / paused handled at
            # the API layer by setting status; here we catch joining-date data
            # drift as a safety net.
            if candidate.status in (
                CandidateStatus.offer_declined.value,
                CandidateStatus.offer_withdrawn.value,
                CandidateStatus.withdrawn.value,
            ):
                _stop_sequence(db, sequence, f"candidate status became {candidate.status}")
                continue
            if sequence.joining_date and candidate.joining_date and \
                    sequence.joining_date.date() != candidate.joining_date.date():
                _stop_sequence(db, sequence, "joining date changed — sequence must be re-approved")
                continue

            due = (
                db.query(EmailMessage)
                .filter(
                    EmailMessage.sequence_id == sequence.id,
                    EmailMessage.status == EmailStatus.approved.value,
                    EmailMessage.scheduled_for <= now,
                )
                .order_by(EmailMessage.scheduled_for)
                .all()
            )
            for message in due:
                if not emailer.sending_configured():
                    stats["skipped"] += 1
                    continue
                try:
                    emailer.send_email(message)
                    message.status = EmailStatus.sent.value
                    message.sent_at = now
                    stats["sent"] += 1
                    log_action(db, "email.sent", entity_type="email", entity_id=message.id,
                               details={"template": message.template_key,
                                        "candidate_id": message.candidate_id})
                except Exception as exc:  # noqa: BLE001
                    message.status = EmailStatus.failed.value
                    message.error = str(exc)[:500]
                    stats["failed"] += 1
                    logger.warning("Keep-warm send failed for email %s: %s", message.id, exc)

            # Sequence complete once the joining day has passed → handover.
            if sequence.joining_date and now.date() > sequence.joining_date.date():
                sequence.status = SequenceStatus.completed.value
                if candidate.status == CandidateStatus.offer_accepted.value:
                    candidate.status = CandidateStatus.joined.value
                    candidate.joining_status = "Joined"
                stats["completed_sequences"] += 1
                log_action(db, "sequence.completed", entity_type="sequence",
                           entity_id=sequence.id, details={"candidate_id": candidate.id})

        _retention_pass(db, now)
        db.commit()
    finally:
        db.close()
    return stats


def _stop_sequence(db, sequence: EngagementSequence, reason: str) -> None:
    sequence.status = SequenceStatus.stopped.value
    sequence.stop_reason = reason
    db.query(EmailMessage).filter(
        EmailMessage.sequence_id == sequence.id,
        EmailMessage.status == EmailStatus.approved.value,
    ).update({"status": EmailStatus.cancelled.value})
    log_action(db, "sequence.stopped", entity_type="sequence", entity_id=sequence.id,
               details={"reason": reason})


def _retention_pass(db, now: datetime) -> None:
    """Flag (never silently delete) candidates past the retention window."""
    cutoff = now - timedelta(days=config.CANDIDATE_RETENTION_DAYS)
    stale = (
        db.query(Candidate)
        .filter(
            Candidate.received_at < cutoff,
            Candidate.status.in_([
                CandidateStatus.rejected.value,
                CandidateStatus.withdrawn.value,
                CandidateStatus.unreachable.value,
                CandidateStatus.duplicate.value,
                CandidateStatus.unreadable.value,
            ]),
            Candidate.next_action != "RETENTION REVIEW: delete or re-consent",
        )
        .all()
    )
    for candidate in stale:
        candidate.next_action = "RETENTION REVIEW: delete or re-consent"
        log_action(db, "retention.flagged", entity_type="candidate",
                   entity_id=candidate.id,
                   details={"retention_days": config.CANDIDATE_RETENTION_DAYS})
