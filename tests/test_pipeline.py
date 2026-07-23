"""End-to-end pipeline test through the real API (deterministic engine):

JD → scorecard gate → upload (incl. duplicate & unreadable) → batch screening
→ leaderboard → assessment → decision gates → questions → call outcome →
HM summary gate → emails gate → offer-accepted → keep-warm sequence gate →
scheduler stop rules → handover gate → tracker/dashboard/audit → Excel exports.
"""
import io
import time

import docx as docx_lib

JD = {
    "title": "ERP Application Administrator (Ellucian Banner)",
    "client_name": "OculusIT",
    "description": "Administer Ellucian Banner 9 for US universities. 5+ years Banner "
                   "production support, Oracle PL/SQL, night shift US EST overlap from "
                   "Gurugram (hybrid). Preferred: Ethos APIs, Jenkins.",
    "location": "Gurugram, India",
    "working_hours": "6 PM – 3 AM IST",
    "work_model": "hybrid",
    "min_experience_years": 5,
    "essential_skills": ["Ellucian Banner", "Oracle PL/SQL"],
    "preferred_skills": ["Ethos APIs", "Jenkins"],
    "qualifications": "Bachelor's degree",
    "compensation_range": "₹18–28 LPA",
    "notice_period_preference": "30 days",
    "mandatory_conditions": ["Willingness to work night shift"],
}

STRONG_RESUME = """Kabir Menon
Email: kabir.menon@example.com | Phone: +91 98110 22334
Location: Gurugram, India

PROFESSIONAL SUMMARY
Ellucian Banner administrator with 7 years of production support for US universities.

WORK EXPERIENCE
Senior Banner Administrator - CampusWorks | 2019 - Present
- Administer Ellucian Banner 9 Student and Finance for four US universities
- Oracle PL/SQL tuning, Ethos APIs, Jenkins deployments
- Night shift US EST overlap, on-call rotation, willingness to work night shift confirmed

EDUCATION
B.Tech Computer Science, 2016

SKILLS
Ellucian Banner, Oracle PL/SQL, WebLogic, Ethos APIs, Jenkins
"""

WEAK_RESUME = """Rina Kapoor
Email: rina.kapoor@example.com | Phone: +91 98220 55667

PROFESSIONAL SUMMARY
Digital marketing specialist with 5 years in SEO and campaign management.

SKILLS
SEO, Google Ads, HubSpot, content strategy
"""


def _docx(text: str) -> bytes:
    document = docx_lib.Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_full_pipeline(auth_client):
    client = auth_client

    # --- Stage 1: job + scorecard approval gate -----------------------------
    job = client.post("/api/jobs", json=JD).json()
    job_id = job["id"]
    assert job["status"] == "draft"

    # Screening must be blocked before scorecard approval (HITL gate #1).
    blocked = client.post(f"/api/jobs/{job_id}/screen")
    assert blocked.status_code == 409

    scorecard = client.post(f"/api/jobs/{job_id}/scorecard/generate").json()
    assert len(scorecard["criteria"]) >= 5
    approved = client.post(
        f"/api/jobs/{job_id}/scorecard/{scorecard['id']}/approve").json()
    assert approved["status"] == "approved"

    # --- Stage 2: upload with duplicate + unreadable ------------------------
    files = [
        ("files", ("kabir.docx", _docx(STRONG_RESUME),
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
        ("files", ("rina.docx", _docx(WEAK_RESUME),
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
        ("files", ("kabir_copy.docx", _docx(STRONG_RESUME),
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
        ("files", ("corrupt.pdf", b"%PDF-1.4 broken \x00" * 2, "application/pdf")),
    ]
    upload = client.post(f"/api/jobs/{job_id}/candidates/upload", files=files).json()
    assert upload["processed"] == 2
    assert upload["duplicates"] == 1
    assert upload["unreadable"] == 1

    log = client.get(f"/api/jobs/{job_id}/processing-log").json()
    assert {r["status"] for r in log} >= {"processed", "duplicate", "unreadable"}

    # --- Stage 3: batch screening -------------------------------------------
    started = client.post(f"/api/jobs/{job_id}/screen")
    assert started.status_code == 200
    for _ in range(60):
        status = client.get(f"/api/jobs/{job_id}/screen/status").json()
        if not status["running"]:
            break
        time.sleep(0.3)
    assert status["done"] == 2 and status["failed"] == 0

    # --- Stage 4: leaderboard ------------------------------------------------
    board = client.get(f"/api/jobs/{job_id}/leaderboard").json()
    assert len(board) == 2
    assert board[0]["overall_match"] >= board[1]["overall_match"]
    strong_row = next(r for r in board if "Kabir" in r["candidate"])
    weak_row = next(r for r in board if "Rina" in r["candidate"])
    assert strong_row["overall_match"] > weak_row["overall_match"]
    # Offline engine must never hard-reject a candidate whose mandatory
    # criteria aren't clearly failed — recall bias.
    assert weak_row["recommendation"] in ("recruiter_review", "do_not_shortlist")

    strong_id = strong_row["candidate_id"]

    # --- Stage 5: assessment with evidence -----------------------------------
    evaluation = client.get(f"/api/candidates/{strong_id}/evaluation").json()
    assert evaluation["criterion_results"]
    assert any(r["evidence"] for r in evaluation["criterion_results"])
    assert evaluation["explanation"]

    # Rescreen is an explicit request for a fresh look, not a cache replay —
    # it must create a new evaluation (not silently reuse the old DB row),
    # even though the deterministic offline engine's score is reproducible
    # for identical input.
    again = client.post(f"/api/candidates/{strong_id}/rescreen").json()
    assert again["id"] != evaluation["id"]
    assert again["overall_score"] == evaluation["overall_score"]
    assert again["recommendation"] == evaluation["recommendation"]

    # --- Stage 6: questions ----------------------------------------------------
    questions = client.get(f"/api/candidates/{strong_id}/questions").json()
    assert 5 <= len(questions) <= 7
    assert {q["category"] for q in questions} >= {"eligibility", "motivation"}

    # --- HITL gate #2: decisions ------------------------------------------------
    weak_id = weak_row["candidate_id"]
    no_reason = client.post(f"/api/candidates/{weak_id}/decision",
                            json={"decision": "reject", "rejection_reason": ""})
    assert no_reason.status_code == 400  # rejection without reason is forbidden

    rejected = client.post(f"/api/candidates/{weak_id}/decision", json={
        "decision": "reject",
        "rejection_reason": "No Banner/PL-SQL experience; profile is marketing-focused.",
    }).json()
    assert rejected["ok"]

    shortlisted = client.post(f"/api/candidates/{strong_id}/decision", json={
        "decision": "shortlist", "comments": "Strong Banner background.",
    }).json()
    assert shortlisted["ok"]

    # --- Stage 7: call outcome (HITL gate #4) -------------------------------------
    call = client.post(f"/api/candidates/{strong_id}/call-outcome", json={
        "call_outcome": "interested", "call_notes": "Great communication.",
        "current_compensation": "₹18 LPA", "expected_compensation": "₹24 LPA",
        "notice_period": "30 days", "communication_rating": "excellent",
        "shift_confirmed": True, "location_confirmed": True, "proceed_to_hm": True,
    }).json()
    assert call["ok"]

    # --- Stage 8: HM summary (HITL gate #5) -----------------------------------------
    summary = client.post(f"/api/candidates/{strong_id}/hm-summary").json()
    assert summary["status"] == "draft"
    assert summary["content"]["notice_period"] == "30 days"
    assert "CANDIDATE PROFILE" in summary["formatted_text"]
    approved_summary = client.post(f"/api/hm-summaries/{summary['id']}/approve").json()
    assert approved_summary["status"] == "approved"

    # --- §8: emails (HITL gate #3) -----------------------------------------------------
    draft = client.post(f"/api/candidates/{strong_id}/emails/draft",
                        json={"template_key": "initial_outreach"}).json()
    assert draft["status"] == "draft"
    assert "OculusIT" in draft["body"]

    # Sending before approval must fail.
    premature = client.post(f"/api/emails/{draft['id']}/send")
    assert premature.status_code == 409

    approved_email = client.post(f"/api/emails/{draft['id']}/approve").json()
    assert approved_email["status"] == "approved"

    # SMTP is disabled in tests → send must fail gracefully with 502.
    send_attempt = client.post(f"/api/emails/{draft['id']}/send")
    assert send_attempt.status_code == 502

    # Rejection emails are draft-only: even approved, sending is refused.
    rejection_draft = client.post(f"/api/candidates/{weak_id}/emails/draft",
                                  json={"template_key": "reject_not_suitable"}).json()
    client.post(f"/api/emails/{rejection_draft['id']}/approve")
    refuse = client.post(f"/api/emails/{rejection_draft['id']}/send")
    assert refuse.status_code == 403

    # --- §9: offer accepted + keep-warm (HITL gate #6) ----------------------------------
    from datetime import datetime, timedelta, timezone
    joining = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    sequence = client.post(f"/api/candidates/{strong_id}/offer-accepted", json={
        "joining_date": joining, "reporting_time": "9:00 AM IST",
        "induction_link": "https://teams.example.com/induction",
        "reporting_manager": "Anil Kumar (NOC Lead)",
    }).json()
    assert sequence["status"] == "pending_approval"
    steps = [e["step"] for e in sequence["emails"]]
    assert "offer_confirmation" in steps
    assert "keepwarm_content" in steps        # every-3rd-day drip
    assert "checklist_t7" in steps and "docs_t3" in steps
    assert "confirm_t2" in steps and "day1_t1" in steps and "welcome_day0" in steps

    live = client.post(f"/api/sequences/{sequence['id']}/approve").json()
    assert live["status"] == "active"
    assert all(e["status"] in ("approved",) for e in live["emails"])

    # Pause & stop rules.
    paused = client.post(f"/api/sequences/{sequence['id']}/pause").json()
    assert paused["status"] == "paused"
    resumed = client.post(f"/api/sequences/{sequence['id']}/resume").json()
    assert resumed["status"] == "active"

    # --- Scheduler tick (draft mode: nothing sent, nothing lost) --------------------------
    from app.services.scheduler import run_tick
    stats = run_tick()
    assert stats["failed"] == 0

    # --- §10: handover (HITL gate #8) ------------------------------------------------------
    handover = client.post(f"/api/candidates/{strong_id}/handover").json()
    assert handover["status"] == "handover_complete"
    final_sequence = client.get(f"/api/candidates/{strong_id}/sequence").json()
    assert final_sequence["status"] == "completed"
    assert all(e["status"] in ("cancelled", "sent")
               for e in final_sequence["emails"])

    # --- Stage 9: tracker, dashboard, audit -------------------------------------------------
    tracker = client.get("/api/tracker").json()
    assert any(r["candidate_name"] == "Kabir Menon" for r in tracker)
    dashboard = client.get("/api/dashboard").json()
    # Exact-hash duplicates never create a candidate row (only a processing-log
    # entry), so 4 files → 3 candidate records.
    assert dashboard["total_resumes_received"] >= 3
    assert dashboard["unreadable_or_duplicates"] >= 1
    assert dashboard["total_resumes_screened"] >= 2
    assert dashboard["ai_recruiter_agreement_rate"] is not None
    audit = client.get("/api/admin/audit-logs?limit=500").json()
    actions = {a["action"] for a in audit}
    assert {"scorecard.approved", "decision.recorded", "email.approved",
            "sequence.approved", "candidate.handover_confirmed"} <= actions

    # --- Excel exports -------------------------------------------------------------------------
    for url in (f"/api/jobs/{job_id}/export/leaderboard", "/api/export/tracker",
                f"/api/jobs/{job_id}/export/hm-summaries"):
        response = client.get(url)
        assert response.status_code == 200, url
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats")


def test_rbac_hiring_manager_read_only(auth_client):
    client = auth_client
    hm = client.post("/api/auth/users", json={
        "username": "hm.demo", "email": "hm@example.com", "full_name": "HM Demo",
        "password": "a-long-password-1", "role": "hiring_manager",
    })
    assert hm.status_code == 201
    login = client.post("/api/auth/login", json={
        "username": "hm.demo", "password": "a-long-password-1"}).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    assert client.get("/api/jobs", headers=headers).status_code == 200
    forbidden = client.post("/api/jobs", json=JD, headers=headers)
    assert forbidden.status_code == 403
