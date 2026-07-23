"""Database models for the People IQ Recruiter Agent.

The model set maps 1:1 to the project brief:
  Stage 1  Job + Scorecard (+ criteria) with recruiter approval
  Stage 2  Candidate ingestion with duplicate/unreadable handling + ProcessingLog
  Stage 3  Evaluation (evidence-linked, criterion-level results)
  Stage 4  Leaderboard (derived from Evaluation)
  Stage 5  Individual assessment (Evaluation + recruiter decision fields)
  Stage 6  ScreeningQuestion
  Stage 7  Screening call capture (fields on Candidate)
  Stage 8  Hiring-manager summary (HMSummary)
  Stage 9  Tracker/dashboard (derived) + status pipeline
  §8       EmailMessage (drafts, approval, sending)
  §9-10    EngagementSequence + ContentItem (keep-warm & Day-1 handover)
  §11      InterviewRecord (transcript intelligence with consent gates)
  §12-15   AuditLog, role-based Users, fairness review flags
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Users & security
# --------------------------------------------------------------------------
class UserRole(str, enum.Enum):
    admin = "admin"
    recruiter = "recruiter"
    hiring_manager = "hiring_manager"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(32), default=UserRole.recruiter.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --------------------------------------------------------------------------
# Stage 1 — Requirement (Job) and Scorecard
# --------------------------------------------------------------------------
class JobStatus(str, enum.Enum):
    draft = "draft"                      # created, scorecard not yet approved
    active = "active"                    # scorecard approved; screening allowed
    on_hold = "on_hold"
    closed = "closed"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # JOB-0001
    title: Mapped[str] = mapped_column(String(255))
    client_name: Mapped[str] = mapped_column(String(255), default="OculusIT")
    description: Mapped[str] = mapped_column(Text)                 # full JD text
    location: Mapped[str] = mapped_column(String(255), default="")
    working_hours: Mapped[str] = mapped_column(String(255), default="")
    work_model: Mapped[str] = mapped_column(String(32), default="")  # remote/hybrid/office
    min_experience_years: Mapped[float] = mapped_column(Float, default=0)
    essential_skills: Mapped[list] = mapped_column(JSON, default=list)
    preferred_skills: Mapped[list] = mapped_column(JSON, default=list)
    qualifications: Mapped[str] = mapped_column(Text, default="")
    compensation_range: Mapped[str] = mapped_column(String(255), default="")
    notice_period_preference: Mapped[str] = mapped_column(String(255), default="")
    mandatory_conditions: Mapped[list] = mapped_column(JSON, default=list)
    # Seniority/pay-band calibration (brief-independent addition): the screening
    # engine reads these to judge candidates against what THIS role actually
    # needs, not a one-size-fits-all "impressive resume" bar. An entry-level,
    # 6 LPA role and a staff-level, 40 LPA role should never be screened to the
    # same standard of technical depth.
    seniority_tier: Mapped[str] = mapped_column(String(32), default="")  # entry/associate/mid/senior/lead_plus
    good_enough_note: Mapped[str] = mapped_column(Text, default="")  # "what good enough looks like here"
    success_criteria: Mapped[str] = mapped_column(Text, default="")  # first 6-12 months expectations
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.draft.value)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    owner: Mapped[User | None] = relationship()
    scorecards: Mapped[list["Scorecard"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    candidates: Mapped[list["Candidate"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class ScorecardStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    superseded = "superseded"


class Scorecard(Base):
    __tablename__ = "scorecards"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default=ScorecardStatus.draft.value)
    generated_by_ai: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job: Mapped[Job] = relationship(back_populates="scorecards")
    approved_by: Mapped[User | None] = relationship()
    criteria: Mapped[list["ScorecardCriterion"]] = relationship(
        back_populates="scorecard", cascade="all, delete-orphan", order_by="ScorecardCriterion.id"
    )


class CriterionCategory(str, enum.Enum):
    mandatory = "mandatory"
    experience = "experience"
    technical_skills = "technical_skills"
    domain = "domain"
    qualifications = "qualifications"
    seniority = "seniority"
    location_hours = "location_hours"
    stability = "stability"          # career progression; gaps never auto-penalised
    preferred = "preferred"


class ScorecardCriterion(Base):
    __tablename__ = "scorecard_criteria"

    id: Mapped[int] = mapped_column(primary_key=True)
    scorecard_id: Mapped[int] = mapped_column(ForeignKey("scorecards.id"), index=True)
    category: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)

    scorecard: Mapped[Scorecard] = relationship(back_populates="criteria")


# --------------------------------------------------------------------------
# Stage 2 — Candidates
# --------------------------------------------------------------------------
class CandidateStatus(str, enum.Enum):
    """Full pipeline; drives the tracker and the dashboard."""
    received = "received"
    unreadable = "unreadable"
    duplicate = "duplicate"
    screened = "screened"                      # AI evaluation complete
    awaiting_review = "awaiting_review"        # AI said "review" or flagged for audit
    shortlisted = "shortlisted"                # recruiter decision
    rejected = "rejected"                      # recruiter decision (reason mandatory)
    on_hold = "on_hold"
    screening_call_done = "screening_call_done"
    submitted_to_hm = "submitted_to_hm"
    interview_scheduled = "interview_scheduled"
    interview_complete = "interview_complete"
    offer_made = "offer_made"
    offer_accepted = "offer_accepted"          # keep-warm eligible
    offer_declined = "offer_declined"
    offer_withdrawn = "offer_withdrawn"
    joined = "joined"
    handover_complete = "handover_complete"    # out of People IQ scope
    withdrawn = "withdrawn"
    unreachable = "unreachable"


class Candidate(Base):
    __tablename__ = "candidates"
    __table_args__ = (UniqueConstraint("job_id", "file_sha256", name="uq_job_filehash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # CAND-00001
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)

    # Identity & contact (extracted; correctable by the recruiter)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(64), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    current_role: Mapped[str] = mapped_column(String(255), default="")
    current_employer: Mapped[str] = mapped_column(String(255), default="")

    # Resume artefacts
    resume_filename: Mapped[str] = mapped_column(String(512), default="")
    stored_path: Mapped[str] = mapped_column(String(1024), default="")
    file_sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    resume_text: Mapped[str] = mapped_column(Text, default="")
    redacted_text: Mapped[str] = mapped_column(Text, default="")   # fairness-scrubbed text used for scoring
    parsed_profile: Mapped[dict] = mapped_column(JSON, default=dict)  # employers/roles/dates/skills/quals/projects
    source: Mapped[str] = mapped_column(String(128), default="Direct upload")
    parse_error: Mapped[str] = mapped_column(Text, default="")
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("candidates.id"), nullable=True)

    # Pipeline / tracker fields
    status: Mapped[str] = mapped_column(String(40), default=CandidateStatus.received.value)
    recruiter_decision: Mapped[str] = mapped_column(String(40), default="")   # shortlist/reject/hold
    recruiter_comments: Mapped[str] = mapped_column(Text, default="")
    rejection_reason: Mapped[str] = mapped_column(Text, default="")           # mandatory on reject
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    flagged_for_review: Mapped[bool] = mapped_column(Boolean, default=False)  # random fairness audit
    correction_note: Mapped[str] = mapped_column(Text, default="")            # data-correction trail

    # Stage 7 — screening call capture (human)
    call_outcome: Mapped[str] = mapped_column(String(64), default="")   # interested/not_interested/unreachable/...
    call_notes: Mapped[str] = mapped_column(Text, default="")
    current_compensation: Mapped[str] = mapped_column(String(128), default="")
    expected_compensation: Mapped[str] = mapped_column(String(128), default="")
    notice_period: Mapped[str] = mapped_column(String(128), default="")
    motivation_notes: Mapped[str] = mapped_column(Text, default="")
    communication_rating: Mapped[str] = mapped_column(String(32), default="")
    shift_confirmed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    location_confirmed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Interview / offer / joining tracker fields
    interview_stage: Mapped[str] = mapped_column(String(128), default="")
    interview_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    feedback_status: Mapped[str] = mapped_column(String(128), default="")
    offer_status: Mapped[str] = mapped_column(String(64), default="")
    joining_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    joining_status: Mapped[str] = mapped_column(String(64), default="")
    next_action: Mapped[str] = mapped_column(String(255), default="")
    owner: Mapped[str] = mapped_column(String(128), default="")

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    job: Mapped[Job] = relationship(back_populates="candidates")
    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", order_by="Evaluation.id.desc()"
    )
    questions: Mapped[list["ScreeningQuestion"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", order_by="ScreeningQuestion.order"
    )
    emails: Mapped[list["EmailMessage"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", order_by="EmailMessage.id"
    )
    hm_summaries: Mapped[list["HMSummary"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    interviews: Mapped[list["InterviewRecord"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    sequence: Mapped["EngagementSequence | None"] = relationship(
        back_populates="candidate", uselist=False, cascade="all, delete-orphan"
    )


class ProcessingLog(Base):
    """Per-file record of a resume batch (brief: 'a log showing the number and
    status of resumes processed')."""
    __tablename__ = "processing_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    batch_id: Mapped[str] = mapped_column(String(36), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32))   # processed/duplicate/unreadable/error/screened
    message: Mapped[str] = mapped_column(Text, default="")
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidates.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------
# Stage 3/5 — Evidence-linked evaluation
# --------------------------------------------------------------------------
class Recommendation(str, enum.Enum):
    shortlist = "shortlist"
    review = "recruiter_review"
    do_not_shortlist = "do_not_shortlist"


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    scorecard_id: Mapped[int] = mapped_column(ForeignKey("scorecards.id"))
    input_hash: Mapped[str] = mapped_column(String(64), index=True)  # sha256(redacted_text + scorecard) → consistency

    overall_score: Mapped[float] = mapped_column(Float, default=0)          # 0-100
    mandatory_status: Mapped[str] = mapped_column(String(32), default="")   # met/partially_met/not_met
    relevant_experience_years: Mapped[float] = mapped_column(Float, default=0)
    key_strengths: Mapped[list] = mapped_column(JSON, default=list)
    gaps: Mapped[list] = mapped_column(JSON, default=list)
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[str] = mapped_column(String(32), default="")
    confidence: Mapped[str] = mapped_column(String(16), default="")          # high/medium/low
    executive_summary: Mapped[str] = mapped_column(Text, default="")
    explanation: Mapped[str] = mapped_column(Text, default="")               # why this recommendation
    # How the engine calibrated its bar for THIS role (level/pay-band/what-good-
    # looks-like) before judging evidence — surfaced to the recruiter so "why this
    # score" is answerable in plain terms, not just "the model said so".
    calibration_notes: Mapped[str] = mapped_column(Text, default="")

    # Per-criterion results: [{criterion_id, name, category, status, evidence,
    #   evidence_verified, weight, score, notes}] where status ∈
    #   confirmed / partial / no_evidence / contradictory / needs_verification
    criterion_results: Mapped[list] = mapped_column(JSON, default=list)
    relevant_projects: Mapped[list] = mapped_column(JSON, default=list)
    missing_information: Mapped[list] = mapped_column(JSON, default=list)
    inconsistencies: Mapped[list] = mapped_column(JSON, default=list)
    verification_questions: Mapped[list] = mapped_column(JSON, default=list)

    engine: Mapped[str] = mapped_column(String(32), default="llm")           # llm / deterministic
    model_used: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    candidate: Mapped[Candidate] = relationship(back_populates="evaluations")
    scorecard: Mapped[Scorecard] = relationship()


# --------------------------------------------------------------------------
# Stage 6 — Screening questions
# --------------------------------------------------------------------------
class QuestionCategory(str, enum.Enum):
    eligibility = "eligibility"
    skill_evidence = "skill_evidence"
    gap_probing = "gap_probing"
    motivation = "motivation"


class ScreeningQuestion(Base):
    __tablename__ = "screening_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    category: Mapped[str] = mapped_column(String(32))
    question: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    order: Mapped[int] = mapped_column(Integer, default=0)
    answer: Mapped[str] = mapped_column(Text, default="")   # recruiter records the outcome

    candidate: Mapped[Candidate] = relationship(back_populates="questions")


# --------------------------------------------------------------------------
# Stage 8 — Hiring-manager summary
# --------------------------------------------------------------------------
class HMSummary(Base):
    __tablename__ = "hm_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    content: Mapped[dict] = mapped_column(JSON, default=dict)   # structured fields per brief §Stage 8
    formatted_text: Mapped[str] = mapped_column(Text, default="")  # email-shareable profile
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft/approved/shared
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    candidate: Mapped[Candidate] = relationship(back_populates="hm_summaries")


# --------------------------------------------------------------------------
# §8 — Candidate communication
# --------------------------------------------------------------------------
class EmailStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"      # approved but not yet sent (or scheduled)
    sent = "sent"
    failed = "failed"
    cancelled = "cancelled"


class EmailMessage(Base):
    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    sequence_id: Mapped[int | None] = mapped_column(
        ForeignKey("engagement_sequences.id"), nullable=True, index=True
    )
    template_key: Mapped[str] = mapped_column(String(64))     # initial_outreach / reject_not_suitable / keepwarm_content / ...
    subject: Mapped[str] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text)
    to_address: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default=EmailStatus.draft.value)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sequence_step: Mapped[str] = mapped_column(String(64), default="")
    content_item_id: Mapped[int | None] = mapped_column(ForeignKey("content_items.id"), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    candidate: Mapped[Candidate] = relationship(back_populates="emails")


# --------------------------------------------------------------------------
# §9/10 — Keep-warm protocol & Day-1 handover
# --------------------------------------------------------------------------
class SequenceStatus(str, enum.Enum):
    pending_approval = "pending_approval"
    active = "active"
    paused = "paused"
    stopped = "stopped"
    completed = "completed"


class EngagementSequence(Base):
    __tablename__ = "engagement_sequences"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), unique=True)
    status: Mapped[str] = mapped_column(String(32), default=SequenceStatus.pending_approval.value)
    offer_accepted_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    joining_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stop_reason: Mapped[str] = mapped_column(String(255), default="")
    handover_confirmed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    handover_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    candidate: Mapped[Candidate] = relationship(back_populates="sequence")


class ContentItem(Base):
    """Pre-loaded, approved keep-warm content (People IQ / OculusIT library)."""
    __tablename__ = "content_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(64))  # leadership_welcome/company_video/employee_story/...
    body: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(1024), default="")
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------
# §11 — Interview intelligence (consent-gated)
# --------------------------------------------------------------------------
class InterviewRecord(Base):
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    stage: Mapped[str] = mapped_column(String(128), default="Technical interview")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    interviewer: Mapped[str] = mapped_column(String(255), default="")

    # Mandatory consent gates — analysis is refused unless all are true.
    candidate_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    interviewer_aware: Mapped[bool] = mapped_column(Boolean, default=False)
    transcription_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    tenant_permission: Mapped[bool] = mapped_column(Boolean, default=False)

    transcript_text: Mapped[str] = mapped_column(Text, default="")
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    analysis_status: Mapped[str] = mapped_column(String(32), default="none")  # none/complete/failed
    interviewer_feedback: Mapped[str] = mapped_column(Text, default="")
    # Human review gate before the evaluation is attached to the candidate record / shared.
    review_status: Mapped[str] = mapped_column(String(32), default="pending_review")  # pending_review/approved/rejected
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    candidate: Mapped[Candidate] = relationship(back_populates="interviews")


# --------------------------------------------------------------------------
# §12/13 — Audit trail
# --------------------------------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(80), default="system")
    action: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), default="")
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
