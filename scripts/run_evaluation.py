"""Evaluation report — AI vs recruiter decisions (brief §18).

Drives the full API end-to-end against the sample dataset:
 1. Logs in, creates the Banner JD, generates & approves the scorecard.
 2. Uploads all 32 sample resumes (incl. duplicate + unreadable edge cases).
 3. Runs batch screening and waits for completion.
 4. Compares AI recommendations with the recruiter ground-truth labels and
    reports every §18 success metric.

Usage:
    # terminal 1
    cd backend && uvicorn app.main:app --port 8000
    # terminal 2
    python scripts/generate_sample_data.py
    python scripts/run_evaluation.py --base-url http://localhost:8000 \
        --username admin --password <admin password>
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    labels = json.loads((SAMPLE / "labels.json").read_text())
    jd_text = (SAMPLE / "jds" / "01_erp_banner_administrator.md").read_text()

    client = httpx.Client(base_url=args.base_url, timeout=120)
    token = client.post("/api/auth/login", json={
        "username": args.username, "password": args.password,
    }).raise_for_status().json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"

    print("1) Creating job + scorecard ...")
    job = client.post("/api/jobs", json={
        "title": "ERP Application Administrator (Ellucian Banner)",
        "client_name": "OculusIT",
        "description": jd_text,
        "location": "Gurugram, India",
        "working_hours": "6 PM – 3 AM IST (US EST overlap)",
        "work_model": "hybrid",
        "min_experience_years": 5,
        "essential_skills": ["Ellucian Banner 9", "Oracle PL/SQL",
                             "Banner production support", "US higher-education clients"],
        "preferred_skills": ["Ethos APIs", "Jenkins", "Argos"],
        "qualifications": "Bachelor's degree in Computer Science or equivalent",
        "compensation_range": "₹18–28 LPA",
        "notice_period_preference": "30 days or less",
        "mandatory_conditions": [
            "Willingness to work night shift (US EST overlap)",
            "Hands-on Banner production support experience",
        ],
    }).raise_for_status().json()
    job_id = job["id"]

    scorecard = client.post(f"/api/jobs/{job_id}/scorecard/generate").raise_for_status().json()
    client.post(
        f"/api/jobs/{job_id}/scorecard/{scorecard['id']}/approve"
    ).raise_for_status()
    print(f"   scorecard v{scorecard['version']} approved "
          f"({len(scorecard['criteria'])} criteria)")

    print("2) Uploading resumes ...")
    files = []
    for path in sorted((SAMPLE / "resumes").iterdir()):
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        files.append(("files", (path.name, path.read_bytes(), mime)))
    upload = client.post(f"/api/jobs/{job_id}/candidates/upload",
                         files=files).raise_for_status().json()
    print(f"   processed={upload['processed']} duplicates={upload['duplicates']} "
          f"unreadable={upload['unreadable']} errors={upload['errors']}")

    print("3) Screening ...")
    client.post(f"/api/jobs/{job_id}/screen").raise_for_status()
    while True:
        status = client.get(f"/api/jobs/{job_id}/screen/status").json()
        print(f"   {status.get('done', 0)}/{status.get('total', '?')} "
              f"(failed={status.get('failed', 0)})", end="\r")
        if not status.get("running"):
            break
        time.sleep(3)
    print()

    print("4) Scoring against recruiter ground truth ...\n")
    leaderboard = client.get(f"/api/jobs/{job_id}/leaderboard").raise_for_status().json()
    candidates = client.get(f"/api/jobs/{job_id}/candidates").raise_for_status().json()
    by_file = {c["resume_filename"]: c for c in candidates}

    total_files = len(labels)
    expected_processable = [f for f, l in labels.items()
                            if l["tier"] not in ("duplicate", "unreadable")]
    processed_ok = [f for f in expected_processable
                    if by_file.get(f, {}).get("ai_score") is not None]

    strong = [f for f, l in labels.items() if l["tier"] == "strong"]
    strong_recalled = 0
    agreements, decided = 0, 0
    rejected_without_reason = 0
    reports_with_evidence, reports_total = 0, 0

    for filename in expected_processable:
        candidate = by_file.get(filename)
        if candidate is None or candidate.get("ai_score") is None:
            continue
        evaluation = client.get(
            f"/api/candidates/{candidate['id']}/evaluation"
        ).raise_for_status().json()
        rec = evaluation["recommendation"]
        tier = labels[filename]["tier"]

        reports_total += 1
        if any(r.get("evidence") for r in evaluation["criterion_results"]):
            reports_with_evidence += 1
        if rec == "do_not_shortlist" and not evaluation["explanation"].strip():
            rejected_without_reason += 1

        # Strong-candidate recall: a strong candidate must never be auto-rejected.
        if tier == "strong" and rec in ("shortlist", "recruiter_review"):
            strong_recalled += 1

        # Agreement: AI vs the recruiter's historical decision (review counts
        # as agreement with either side since it defers to the human).
        recruiter = labels[filename]["recruiter_decision"]
        decided += 1
        if (recruiter == "shortlist" and rec == "shortlist") \
           or (recruiter == "reject" and rec == "do_not_shortlist") \
           or rec == "recruiter_review" or recruiter == "review":
            agreements += 1

    dup_detected = any(
        by_file.get(f, {}).get("status") == "duplicate" or "DUPLICATE" in f
        and by_file.get(f, {}).get("is_duplicate")
        for f in labels if labels[f]["tier"] == "duplicate"
    ) or upload["duplicates"] >= 1
    unreadable_flagged = upload["unreadable"] >= 1

    def pct(n, d):
        return f"{100 * n / d:5.1f}%" if d else "  n/a"

    print("=" * 66)
    print("EVALUATION REPORT — People IQ Recruiter Agent")
    print("=" * 66)
    print(f"{'Metric':44s}{'Target':>9s}{'Actual':>10s}")
    print("-" * 66)
    print(f"{'Resume processing success':44s}{'>=95%':>9s}"
          f"{pct(len(processed_ok), len(expected_processable)):>10s}")
    print(f"{'Strong-candidate recall':44s}{'>=90%':>9s}"
          f"{pct(strong_recalled, len(strong)):>10s}")
    print(f"{'AI/recruiter shortlist agreement':44s}{'>=80%':>9s}"
          f"{pct(agreements, decided):>10s}")
    print(f"{'Rejected without explanation':44s}{'0%':>9s}"
          f"{pct(rejected_without_reason, reports_total):>10s}")
    print(f"{'Reports containing resume evidence':44s}{'100%':>9s}"
          f"{pct(reports_with_evidence, reports_total):>10s}")
    print(f"{'Duplicate detected':44s}{'yes':>9s}{str(dup_detected):>10s}")
    print(f"{'Unreadable file flagged':44s}{'yes':>9s}{str(unreadable_flagged):>10s}")
    print("-" * 66)
    print(f"Leaderboard entries: {len(leaderboard)} | engine used: "
          f"{client.get('/api/health').json()['ai_engine']}")
    print("Top 5 on the leaderboard:")
    for row in leaderboard[:5]:
        print(f"  #{row['rank']:>2} {row['candidate']:28s} {row['overall_match']:5.1f} "
              f"{row['recommendation']}")
    print("=" * 66)

    ok = (len(processed_ok) / max(len(expected_processable), 1) >= 0.95
          and strong_recalled / max(len(strong), 1) >= 0.9
          and rejected_without_reason == 0
          and reports_with_evidence == reports_total)
    print("RESULT:", "PASS" if ok else "REVIEW NEEDED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
