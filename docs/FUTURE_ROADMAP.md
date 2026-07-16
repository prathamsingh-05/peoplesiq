# Recommendations for Future Development

The prototype fully implements the brief's four phases. These are the recommended
enhancements to take it to an enterprise production deployment, roughly in
priority order.

## 1. Microsoft 365 integration (the biggest lever)

- **Outlook / Microsoft Graph** for real email send/receive, threading, and
  reply tracking — replacing SMTP and enabling two-way candidate conversations.
- **Microsoft Teams** transcript retrieval via Graph, so interview transcripts
  flow in automatically (with the consent gates already built) instead of being
  pasted. Optional Graph calendar integration for interview scheduling.
- **SharePoint / OneDrive** for resume and export storage with tenant isolation.
- **Entra ID (Azure AD) SSO + MFA** replacing the local user store.

## 2. Data platform hardening

- Move from SQLite to **PostgreSQL / Azure Database** with encryption at rest.
- Externalise file storage to **Azure Blob**; secrets to **Azure Key Vault**.
- Replace the in-process scheduler with **Celery / Azure Functions** for HA and
  reliable keep-warm dispatch across multiple app instances.

## 3. ATS interoperability

- Two-way sync with **Keka** or another ATS: pull requisitions and candidates,
  push decisions, statuses, and summaries — so the agent augments the existing
  system of record rather than duplicating it.

## 4. Screening quality & tuning

- **Recruiter feedback loop:** learn per-recruiter/per-client calibration from
  overrides (which criteria they weight differently) and surface it — without
  ever learning protected attributes.
- **Configurable thresholds per role family** (the shortlist/review cut-offs are
  currently global constants).
- **Semantic skill matching** (embeddings) to catch synonymous skills and adjacent
  technologies the current evidence match may miss.
- **Batch prompt caching** of the scorecard to cut cost/latency on large batches.

## 5. Formal bias auditing

- Scheduled **Local-Law-144-style bias audits**: compute selection-rate and
  impact-ratio (four-fifths) across protected categories from a separate lawful
  data source, with a published audit artefact. The data model already separates
  AI and human decisions to make this a query, not a rebuild.
- **Adverse-impact alerts** when the agreement rate or a decision distribution
  drifts.

## 6. Interview intelligence, richer

- **Competency scorecards per role** driving the interview evaluation (currently
  competencies are inferred from the JD scorecard).
- **Live Graph-based transcript ingestion** and speaker diarisation.
- **Structured debrief documents** generated for the hiring-manager meeting.

## 7. Candidate experience

- A lightweight **candidate portal** for interested candidates to confirm details,
  upload documents for the joining checklist, and track their status.
- **SMS / WhatsApp** keep-warm channels alongside email (with consent).

## 8. Analytics & reporting

- **Time-to-hire, funnel conversion, source effectiveness** dashboards for
  recruitment leaders.
- **Recruiter productivity** metrics (screening time saved, throughput).
- Exportable **compliance reports** (decisions + reasons + evidence per requisition).

## 9. Platform & UX

- **Multi-tenant** separation for multiple clients beyond OculusIT.
- **Bulk actions** on the leaderboard (shortlist/reject with reason in one pass).
- **Notifications** (in-app / email) for gate approvals and due keep-warm sends.
- **Internationalisation** for non-English resumes and multi-region roles.

## 10. Operational maturity

- CI with the existing pytest suite + dependency and secret scanning.
- Structured logging/metrics (OpenTelemetry) and error tracking.
- A managed-agent deployment option (Anthropic Managed Agents) for the
  long-running screening/engagement workflows.
