"""Pydantic request/response models."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# --- Auth -------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.\-]+$")
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=10, max_length=256)
    role: str = Field(pattern=r"^(admin|recruiter|hiring_manager)$")


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=256)


# --- Jobs & scorecards --------------------------------------------------------
class JobCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    client_name: str = Field(default="OculusIT", max_length=255)
    description: str = Field(min_length=20)
    location: str = ""
    working_hours: str = ""
    work_model: str = ""
    min_experience_years: float = Field(default=0, ge=0, le=50)
    essential_skills: list[str] = []
    preferred_skills: list[str] = []
    qualifications: str = ""
    compensation_range: str = ""
    notice_period_preference: str = ""
    mandatory_conditions: list[str] = []
    seniority_tier: str = Field(default="", pattern=r"^(|entry|associate|mid|senior|lead_plus)$")
    good_enough_note: str = ""
    success_criteria: str = ""


class JobUpdate(BaseModel):
    title: str | None = None
    client_name: str | None = None
    description: str | None = None
    location: str | None = None
    working_hours: str | None = None
    work_model: str | None = None
    min_experience_years: float | None = Field(default=None, ge=0, le=50)
    essential_skills: list[str] | None = None
    preferred_skills: list[str] | None = None
    qualifications: str | None = None
    compensation_range: str | None = None
    notice_period_preference: str | None = None
    mandatory_conditions: list[str] | None = None
    seniority_tier: str | None = Field(default=None, pattern=r"^(|entry|associate|mid|senior|lead_plus)$")
    good_enough_note: str | None = None
    success_criteria: str | None = None
    status: str | None = Field(default=None, pattern=r"^(draft|active|on_hold|closed)$")


class CriterionInput(BaseModel):
    category: str
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    weight: float = Field(default=1.0, gt=0, le=5)
    is_mandatory: bool = False


class ScorecardUpdate(BaseModel):
    criteria: list[CriterionInput] = Field(min_length=1, max_length=40)


# --- Candidates ---------------------------------------------------------------
class CandidateCorrection(BaseModel):
    """Recruiter correction of extracted data (fairness §15: correction process)."""
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    current_role: str | None = None
    current_employer: str | None = None
    correction_note: str = Field(min_length=3, max_length=2000)


class DecisionRequest(BaseModel):
    decision: str = Field(pattern=r"^(shortlist|reject|hold)$")
    comments: str = ""
    rejection_reason: str = ""   # mandatory when decision == reject (enforced in route)


class BulkDecisionRequest(BaseModel):
    candidate_ids: list[int] = Field(min_length=1, max_length=200)
    decision: str = Field(pattern=r"^(shortlist|reject|hold)$")
    comments: str = ""
    rejection_reason: str = ""   # mandatory when decision == reject


class RediscoveryPull(BaseModel):
    candidate_ids: list[int] = Field(min_length=1, max_length=100)


class CallOutcome(BaseModel):
    call_outcome: str = Field(pattern=r"^(interested|not_interested|unreachable|callback|other)$")
    call_notes: str = ""
    current_compensation: str = ""
    expected_compensation: str = ""
    notice_period: str = ""
    motivation_notes: str = ""
    communication_rating: str = ""
    shift_confirmed: bool | None = None
    location_confirmed: bool | None = None
    proceed_to_hm: bool = False   # HITL gate #4: confirmation after the call


class StatusUpdate(BaseModel):
    status: str
    interview_stage: str | None = None
    interview_date: datetime | None = None
    feedback_status: str | None = None
    offer_status: str | None = None
    joining_date: datetime | None = None
    joining_status: str | None = None
    next_action: str | None = None
    owner: str | None = None
    rejection_reason: str | None = None


class QuestionAnswer(BaseModel):
    answer: str = Field(max_length=4000)


# --- Emails ---------------------------------------------------------------------
class EmailDraftRequest(BaseModel):
    template_key: str = Field(
        pattern=r"^(initial_outreach|reject_not_suitable|hold_future|more_info_needed|"
                r"unreachable|position_on_hold)$"
    )
    personalise: bool = True
    info_needed: str = ""


class EmailEdit(BaseModel):
    subject: str = Field(min_length=1, max_length=512)
    body: str = Field(min_length=1)
    to_address: str = ""


# --- Engagement -------------------------------------------------------------------
class OfferAccepted(BaseModel):
    joining_date: datetime
    reporting_time: str = "9:00 AM (local office time)"
    induction_link: str = ""
    reporting_manager: str = ""
    help_contact: str = ""


class ContentItemCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    content_type: str = Field(max_length=64)
    body: str = ""
    url: str = ""


# --- Interviews ----------------------------------------------------------------------
class InterviewCreate(BaseModel):
    stage: str = "Technical interview"
    scheduled_at: datetime | None = None
    interviewer: str = ""
    candidate_consent: bool = False
    interviewer_aware: bool = False
    transcription_enabled: bool = False
    tenant_permission: bool = False


class TranscriptUpload(BaseModel):
    transcript_text: str = Field(min_length=50)
    candidate_consent: bool
    interviewer_aware: bool
    transcription_enabled: bool
    tenant_permission: bool


class InterviewFeedback(BaseModel):
    interviewer_feedback: str = Field(min_length=2)


class InterviewReview(BaseModel):
    approve: bool
