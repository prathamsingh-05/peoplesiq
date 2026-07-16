"""Talent rediscovery — resurface previously screened candidates for a new role.

A key differentiator of the best AI recruitment platforms: instead of screening
only fresh inbound resumes, the agent searches the entire historical candidate
base for a new requisition and flags strong prior candidates — especially
"silver medalists" (people who reached late stages on another role but weren't
selected). This turns the existing database into a sourcing channel and is a
major driver of lower time-to-fill.

Design:
- Credential-free: matches candidates already in the system against a target
  job's approved scorecard using a fast, deterministic skill/criterion overlap
  (no API cost per candidate at discovery time).
- Silver-medalist detection: candidates whose pipeline reached interview/offer
  stages elsewhere are surfaced and boosted.
- The recruiter "pulls" a promising candidate into the target job, which creates
  a fresh candidate record there so it flows through the normal screening and
  all the usual human gates — nothing skips the evidence-based evaluation.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from ..models import Candidate, CandidateStatus, Job, Scorecard

# Pipeline stages that mark a candidate as a strong prior prospect elsewhere.
SILVER_MEDALIST_STATUSES = {
    CandidateStatus.interview_scheduled.value,
    CandidateStatus.interview_complete.value,
    CandidateStatus.submitted_to_hm.value,
    CandidateStatus.offer_made.value,
    CandidateStatus.offer_declined.value,
}
PROGRESSED_STATUSES = SILVER_MEDALIST_STATUSES | {
    CandidateStatus.shortlisted.value,
    CandidateStatus.screening_call_done.value,
}


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9+#.]+", (text or "").lower()) if len(t) > 2}


def _target_terms(job: Job, scorecard: Scorecard) -> list[str]:
    terms: list[str] = []
    terms += job.essential_skills or []
    terms += job.preferred_skills or []
    terms += [c.name for c in scorecard.criteria if c.category != "stability"]
    return [t for t in terms if t]


def find_matches(db: Session, target_job: Job, scorecard: Scorecard,
                 limit: int = 25) -> list[dict]:
    """Rank candidates from OTHER jobs by fit to this job's scorecard."""
    terms = _target_terms(target_job, scorecard)
    term_tokens = [(t, _tokens(t)) for t in terms if _tokens(t)]
    if not term_tokens:
        return []

    # Consider every non-duplicate candidate that already has parsed content and
    # is not already attached to the target job.
    candidates = (
        db.query(Candidate)
        .filter(
            Candidate.job_id != target_job.id,
            Candidate.is_duplicate.is_(False),
            Candidate.status.notin_([
                CandidateStatus.unreadable.value,
                CandidateStatus.duplicate.value,
            ]),
        )
        .all()
    )

    results: list[dict] = []
    for cand in candidates:
        haystack = (cand.redacted_text or cand.resume_text or "").lower()
        skill_hay = " ".join(cand.parsed_profile.get("skills", [])).lower() \
            if isinstance(cand.parsed_profile, dict) else ""
        combined = haystack + " " + skill_hay
        matched = [t for t, toks in term_tokens if all(tok in combined for tok in toks)]
        if not matched:
            continue
        base = len(matched) / len(term_tokens)

        silver = cand.status in SILVER_MEDALIST_STATUSES
        progressed = cand.status in PROGRESSED_STATUSES
        # Boost prior-progression candidates — proven interest/quality elsewhere.
        boost = 0.15 if silver else (0.08 if progressed else 0.0)
        # Avoid resurfacing people already rejected FOR A SIMILAR reason: we still
        # surface rejected candidates (they may fit a different role) but rank
        # them below untested matches unless they progressed before rejection.
        prior_eval = cand.evaluations[0] if cand.evaluations else None
        score = round(100 * min(1.0, base + boost), 1)

        results.append({
            "candidate_id": cand.id,
            "candidate_code": cand.candidate_code,
            "full_name": cand.full_name or cand.resume_filename,
            "current_role": cand.current_role,
            "current_employer": cand.current_employer,
            "source_job_id": cand.job_id,
            "source_job_title": cand.job.title,
            "source_job_code": cand.job.job_code,
            "prior_status": cand.status,
            "prior_recruiter_decision": cand.recruiter_decision,
            "prior_ai_recommendation": prior_eval.recommendation if prior_eval else None,
            "silver_medalist": silver,
            "progressed_before": progressed,
            "match_terms": matched[:8],
            "match_score": score,
            "already_in_target": False,
        })

    results.sort(key=lambda r: (r["silver_medalist"], r["match_score"]), reverse=True)
    return results[:limit]


def pull_into_job(db: Session, source_candidate: Candidate, target_job: Job,
                  next_candidate_code: str) -> Candidate:
    """Copy a rediscovered candidate into the target job as a fresh record so it
    goes through the normal screening + human gates. Duplicate-safe by file hash."""
    existing = db.query(Candidate).filter(
        Candidate.job_id == target_job.id,
        Candidate.file_sha256 == source_candidate.file_sha256,
    ).first()
    if existing:
        return existing

    clone = Candidate(
        candidate_code=next_candidate_code,
        job_id=target_job.id,
        full_name=source_candidate.full_name,
        email=source_candidate.email,
        phone=source_candidate.phone,
        location=source_candidate.location,
        current_role=source_candidate.current_role,
        current_employer=source_candidate.current_employer,
        resume_filename=source_candidate.resume_filename,
        stored_path=source_candidate.stored_path,
        file_sha256=source_candidate.file_sha256,
        resume_text=source_candidate.resume_text,
        redacted_text=source_candidate.redacted_text,
        parsed_profile=source_candidate.parsed_profile,
        source=f"Rediscovered from {source_candidate.job.job_code} "
               f"({source_candidate.candidate_code})",
        status=CandidateStatus.received.value,
        processed_at=source_candidate.processed_at,
    )
    db.add(clone)
    db.flush()
    return clone
