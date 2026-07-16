# Recruiter User Journey

A day in the life of a People IQ recruiter using the Recruiter Agent, mapped to
the exact screens and actions in the product.

## 0. Sign in
Log in with your recruiter credentials. Every action you take from here is
audit-logged. The dashboard shows the live funnel across all your roles.

## 1. Create the requirement (Jobs → New job)
Paste the job description and fill in the structured fields: title, client,
location, working hours, work model, minimum experience, essential and preferred
skills, qualifications, compensation range, notice-period preference, and any
mandatory screening conditions (e.g. "must confirm willingness to work night
shift").

## 2. Generate and approve the scorecard (Job → Scorecard tab)
Click **Generate from JD**. The agent converts the description into weighted,
verifiable criteria across mandatory, experience, technical, domain,
qualification, seniority, location/hours, stability, and preferred categories.
**Review it. Edit anything.** Adjust weights, mark true knock-outs as mandatory,
remove anything irrelevant. Then **Approve**. 
> Screening is locked until you approve — this is human gate #1.

## 3. Drop the CVs (Job → Upload CVs tab)
Select a folder of PDF/Word resumes and upload the batch. The system extracts
each candidate's name and contact details, parses their history, detects exact
and content duplicates, flags anything unreadable, and assigns each a candidate
ID. The **processing log** shows exactly what happened to every file.

## 4. Screen everything (Job → Screen & Leaderboard tab)
Click **Screen all pending resumes**. A progress bar tracks the batch. When it
finishes you get a **ranked leaderboard**: match %, mandatory status, relevant
experience, key strengths, gaps, risk flags, the AI recommendation, confidence,
and evidence — sorted best-fit first. A candidate never ranks high just for
keyword count; scores come from demonstrated, verified evidence.

## 5. Open a candidate (click a name)
The candidate workspace has everything in one place:

- **Assessment** — executive summary, why the recommendation was made, strengths,
  gaps, risk flags, projects, missing info, inconsistencies, and a table of
  **evidence per criterion** with the exact resume quote and its status
  (confirmed / partial / no evidence / contradictory / needs verification).
- **Screening questions** — your 5–7 question pack; record answers inline.
- **Call & decision** — record your decision (shortlist / hold / reject; a
  rejection needs a reason) and capture the screening-call outcome: interest,
  communication, compensation, notice period, motivation, and shift/location
  confirmation. Correct any wrong resume interpretations here. 
  > You decide — the AI only recommended. Your decision is logged separately, and
  > the dashboard tracks how often you and the AI agree.

## 6. Prepare the hiring manager (Candidate → HM summary tab)
Generate the summary after the call, so compensation, notice period, and your
observations are included. Review it, **approve** it (gate #5), and copy the
formatted profile into an email or export all summaries to Excel.

## 7. Communicate (Candidate → Emails tab, or the Outbox)
Draft the initial outreach (AI personalises it from the resume), edit if you
like, **approve**, and send. Nothing goes out without your approval, and an
extracted email address alone never triggers a send. Rejection and hold
templates are draft-only — you send those from your own mailbox.

## 8. Interview intelligence (Candidate → Interviews tab)
Schedule the interview. Afterwards, paste the Teams transcript and confirm the
four consents (candidate notified, interviewer aware, transcription enabled,
tenant permission). The agent produces an **independent evaluation**: competency
coverage, resume consistency, vague/unsupported claims, unanswered questions, an
overall score, and debrief suggestions. **You review and approve it** before it's
shared with the hiring manager (gate #7). Your interviewer feedback is recorded
separately, and the Compare view puts the two side by side for the debrief.

## 9. Offer to joining (Candidate → Keep-warm tab)
When the candidate accepts, enter the joining date and Day-1 details, and the
system prepares the full keep-warm schedule: acceptance confirmation, every-3rd-day
approved content up to two days before joining, a T-7 readiness checklist, T-5
culture intro, T-3 documentation reminder, T-2 final confirmation, T-1 Day-1
instructions, and the Day-0 welcome. **Approve** to activate (gate #6). You can
pause, resume, or stop it at any time (declined, date changed, withdrawn).

## 10. Handover (Candidate → Keep-warm tab)
On joining, confirm the **Day-1 handover** (gate #8). The candidate transfers to
the client's own HR/onboarding team and People IQ automation stops. The record
stays for reporting.

## Always available
- **Tracker** — the master spreadsheet view of every candidate, exportable to Excel.
- **Dashboard** — funnel counts and the AI-vs-recruiter agreement rate.
- **Content Library** — manage the approved keep-warm content.
- **Governance** — the full audit trail, the fairness review queue (a random
  sample of AI rejections you must eyeball), and (for admins) user management.
