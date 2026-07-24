"""Tests for the research-driven additions: talent rediscovery, bulk decisions,
responsible-AI report, and candidate search."""
import io
import time

import docx as docx_lib

BANNER_JD = {
    "title": "Banner Admin (rediscovery source)", "client_name": "OculusIT",
    "description": "Administer Ellucian Banner 9 for US universities, Oracle PL/SQL, "
                   "night shift. 5+ years Banner production support.",
    "min_experience_years": 5, "essential_skills": ["Ellucian Banner", "Oracle PL/SQL"],
    "preferred_skills": ["Ethos APIs"], "mandatory_conditions": ["Willingness to work night shift"],
}
SIMILAR_JD = {
    "title": "Banner Support Engineer (rediscovery target)", "client_name": "OculusIT",
    "description": "Support Ellucian Banner 9 environments, Oracle PL/SQL troubleshooting, "
                   "US higher-education clients, night shift.",
    "min_experience_years": 4, "essential_skills": ["Ellucian Banner", "Oracle PL/SQL"],
    "preferred_skills": ["WebLogic"], "mandatory_conditions": ["Willingness to work night shift"],
}
BANNER_RESUME = """Arjun Rao
Email: arjun.rao@example.com | Phone: +91 98111 33445

PROFESSIONAL SUMMARY
Ellucian Banner administrator with 7 years of production support for US universities.

WORK EXPERIENCE
Senior Banner Administrator - CampusWorks | 2019 - Present
- Ellucian Banner 9 Student and Finance modules, Oracle PL/SQL tuning, Ethos APIs
- Night shift US EST overlap, willingness to work night shift confirmed

SKILLS
Ellucian Banner, Oracle PL/SQL, WebLogic, Ethos APIs
"""
OTHER_RESUME = """Meera Iyer
Email: meera.iyer@example.com | Phone: +91 98222 66778

PROFESSIONAL SUMMARY
Marketing manager, 5 years in SEO and campaigns.

SKILLS
SEO, Google Ads, HubSpot
"""


def _docx(text):
    d = docx_lib.Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    b = io.BytesIO(); d.save(b); return b.getvalue()


def _approve_and_screen(client, jd, resumes):
    """Create job, approve scorecard, upload resumes, screen. Returns job_id."""
    job = client.post("/api/jobs", json=jd).json()
    jid = job["id"]
    sc = client.post(f"/api/jobs/{jid}/scorecard/generate").json()
    client.post(f"/api/jobs/{jid}/scorecard/{sc['id']}/approve")
    files = [("files", (name, _docx(text),
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
             for name, text in resumes]
    client.post(f"/api/jobs/{jid}/candidates/upload", files=files)
    client.post(f"/api/jobs/{jid}/screen")
    for _ in range(60):
        if not client.get(f"/api/jobs/{jid}/screen/status").json()["running"]:
            break
        time.sleep(0.3)
    return jid


def test_talent_rediscovery(auth_client):
    client = auth_client
    # Source job with a strong Banner candidate + an unrelated one.
    source = _approve_and_screen(client, BANNER_JD,
                                 [("arjun.docx", BANNER_RESUME), ("meera.docx", OTHER_RESUME)])
    # Mark the Banner candidate as a "silver medalist" (progressed then not selected).
    board = client.get(f"/api/jobs/{source}/leaderboard").json()
    arjun = next(r for r in board if "Arjun" in r["candidate"])
    client.patch(f"/api/candidates/{arjun['candidate_id']}/status",
                 json={"status": "interview_complete"})

    # A new, similar job — rediscover talent.
    target = client.post("/api/jobs", json=SIMILAR_JD).json()["id"]
    sc = client.post(f"/api/jobs/{target}/scorecard/generate").json()
    # Rediscovery is blocked until the target scorecard is approved.
    assert client.get(f"/api/jobs/{target}/rediscover").status_code == 409
    client.post(f"/api/jobs/{target}/scorecard/{sc['id']}/approve")

    matches = client.get(f"/api/jobs/{target}/rediscover").json()
    assert matches, "expected at least one rediscovered candidate"
    top = matches[0]
    assert "Arjun" in top["full_name"]
    assert top["silver_medalist"] is True
    assert top["source_job_id"] == source
    assert any("banner" in t.lower() for t in top["match_terms"])
    # The unrelated marketing candidate should not match Banner terms.
    assert not any("Meera" in m["full_name"] for m in matches)

    # Pull the candidate into the target job → creates a fresh record to screen.
    pulled = client.post(f"/api/jobs/{target}/rediscover/pull",
                         json={"candidate_ids": [arjun["candidate_id"]]}).json()
    assert len(pulled["pulled"]) == 1
    target_candidates = client.get(f"/api/jobs/{target}/candidates").json()
    assert any("Rediscovered from" in c["source"] for c in target_candidates)

    # Cross-job history: the same person now has a record on both jobs, and
    # each one's history endpoint should surface the other.
    target_arjun_id = next(
        c["id"] for c in target_candidates if "Arjun" in c["full_name"])
    source_history = client.get(f"/api/candidates/{arjun['candidate_id']}/history").json()
    assert any(h["job_id"] == target for h in source_history)
    target_history = client.get(f"/api/candidates/{target_arjun_id}/history").json()
    assert any(h["job_id"] == source for h in target_history)
    # The unrelated candidate has no cross-job history at all.
    meera = next(r for r in board if "Meera" in r["candidate"])
    assert client.get(f"/api/candidates/{meera['candidate_id']}/history").json() == []


def test_bulk_decisions_and_search(auth_client):
    client = auth_client
    jid = _approve_and_screen(client, {**BANNER_JD, "title": "Bulk decisions job"},
                              [("a.docx", BANNER_RESUME), ("b.docx", OTHER_RESUME)])
    board = client.get(f"/api/jobs/{jid}/leaderboard").json()
    ids = [r["candidate_id"] for r in board]

    # Bulk reject without a reason is refused.
    assert client.post(f"/api/jobs/{jid}/decisions/bulk",
                       json={"candidate_ids": ids, "decision": "reject",
                             "rejection_reason": ""}).status_code == 400
    # Bulk hold works.
    res = client.post(f"/api/jobs/{jid}/decisions/bulk",
                      json={"candidate_ids": ids, "decision": "hold"}).json()
    assert res["applied"] == len(ids)

    # Candidate search on the tracker.
    hits = client.get("/api/tracker?q=Arjun").json()
    assert all("arjun" in (r["candidate_name"] or "").lower() for r in hits) or hits == []
    by_status = client.get("/api/tracker?status=on_hold").json()
    assert all(r["screening_status"] == "on_hold" for r in by_status)


def test_responsible_ai_report(auth_client):
    client = auth_client
    report = client.get("/api/responsible-ai-report").json()
    assert "recommendation_distribution" in report
    assert "ai_recruiter_agreement_pct" in report
    assert report["negatives_without_explanation"] == 0     # fairness guarantee
    assert report["protected_class_impact_ratio"] is None    # deliberately not stored
    assert "impact_ratio_note" in report
    assert set(report["health"]) == {"evidence_coverage_ok", "explanation_coverage_ok", "agreement_ok"}
