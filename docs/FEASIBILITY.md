# Feasibility — answering Shonalie's question

> *"Let me know if this is feasible?"*

**Yes — and it is built.** This repository is a working implementation of the
entire brief, not a proposal. Below is a direct, item-by-item answer to the
original note.

| Your requirement | Feasible? | How it works here |
|---|---|---|
| A folder where you dump CVs per JD | **Yes, done** | Upload a batch of PDF/Word CVs to a job; each is parsed, de-duplicated, and logged. |
| Agent screens CV vs JD criteria | **Yes, done** | The JD becomes an approved scorecard; each CV is scored against it with evidence. |
| Leaderboard: who to shortlist / reject | **Yes, done** | Ranked leaderboard with a shortlist / recruiter-review / do-not-shortlist recommendation per candidate. |
| Agent sends the initial email | **Yes, done** | AI drafts a personalised outreach email; it sends **after you approve it** (never automatically off an extracted address). |
| Agent suggests screening questions | **Yes, done** | 5–7 questions per candidate across eligibility, evidence, gaps and motivation — anchored to that CV. |
| Recruiter probes gaps & shortlists | **Yes, by design** | The human records the call outcome, verifies AI-identified gaps, and makes the decision. The AI only recommends. |
| Candidate summary in Excel | **Yes, done** | One-click Excel export of hiring-manager summaries, plus a formatted profile to paste into email. |
| Update trackers (how many CVs screened) | **Yes, done** | A live processing log and a master Excel tracker; the dashboard shows counts and the AI-vs-recruiter agreement rate. |
| **Nice-to-have:** agent joins Teams calls and gives a separate evaluation | **Yes, with the right consent** | We do this the safe, compliant way: **after** the interview, the agent analyses the Teams transcript and produces an independent evaluation for the hiring-manager debrief. It never covertly records or joins a call live — that requires candidate consent, interviewer awareness, transcription enabled, and tenant permission, all enforced in the system. This is both more defensible legally and more useful (a considered evaluation vs. a live guess). |
| Human does phone contact / builds interest / negotiates salary | **Yes, kept human** | The agent never phones candidates or negotiates. Compensation and motivation are captured as call fields by the recruiter. |
| Back to AI when the offer is accepted | **Yes, done** | Marking "Offer Accepted" prepares the keep-warm sequence (you approve it to start). |
| Email every 3rd day with interesting OculusIT content until T-2 | **Yes, done** | A pre-loaded, approved content library (leadership messages, videos, employee stories, YouTube links, etc.) drips every third day up to two days before joining. |
| Welcome mail + Day-1 agenda + induction, then hand to the client | **Yes, done** | T-1 Day-1 instructions and a Day-0 welcome go out; a **handover** step then transfers the candidate to the client's own people team and People IQ automation stops. |

## What "feasible" required us to get right

1. **Keep humans accountable.** The product is a decision-support system. Eight
   mandatory approval gates ensure a person approves the scorecard, every
   shortlist/rejection, every first email, the call outcome, the HM summary,
   the engagement sequence, interview evaluations, and the final handover.

2. **Be fair and defensible.** Protected attributes are stripped before the AI
   scores anyone; gaps and formatting never cause rejection; every negative
   decision carries an explanation; a random sample of rejections gets human
   review. This is what separates a usable internal tool from a legal risk.

3. **Never lose a good candidate.** The system is deliberately recall-biased:
   borderline candidates go to recruiter review, not the reject pile.

4. **Work even when the AI is down.** A deterministic fallback keeps screening
   running during an API outage, and identical inputs always produce identical
   scores.

## What you'll want to provide to go fully live

- The **domain and email account** (you mentioned this comes later) — plug SMTP
  in and approved emails send for real; until then everything stays as drafts.
- **Approved OculusIT content** (videos, leadership messages, employee stories)
  to replace the placeholder library entries.
- For live Teams transcript pulls at scale, a **Microsoft Graph / Teams
  integration** and the tenant permissions described above (the current version
  accepts pasted or uploaded transcripts, which is enough to run the workflow).

Everything else is working today.
