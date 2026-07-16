# Security Notes

The Recruiter Agent is an internal tool handling candidate personal data. This
note summarises the security posture implemented in the prototype and the
hardening path for production.

## Implemented

### Authentication
- **JWT bearer tokens** (HS256), short-lived (default 8 hours, configurable).
- The signing secret comes from `PEOPLEIQ_SECRET_KEY`, or is auto-generated on
  first boot and persisted to disk with `0600` permissions — never committed.
- **PBKDF2-HMAC-SHA256** password hashing, 310,000 iterations, per-user random
  salt, constant-time comparison.
- **Brute-force protection:** account lockout after repeated failed logins
  (default 5 attempts / 15-minute window), with failed logins audit-logged.

### Authorisation (RBAC)
Three roles enforced at the API layer:
- **admin** — full access incl. user management, content approval, data purge.
- **recruiter** — full recruiting workflow.
- **hiring_manager** — read-mostly; interview AI evaluations are hidden until a
  recruiter approves them for sharing.

### Input & upload safety
- Upload size cap, extension allow-list (PDF/DOCX/DOC/TXT), and batch-size cap.
- Uploaded filenames are sanitised before storage (path-traversal safe).
- Pydantic schema validation on every request body; regex-constrained enums for
  decision/template/role fields.
- One bad file never aborts a batch — per-file error isolation.

### Transport & headers
- Security headers on every response: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`.
- CORS restricted to the known frontend origin.
- Run behind TLS in any real deployment (terminate at the reverse proxy).

### Auditability
- Every AI action and every human decision is written to an append-only
  `AuditLog` (who, what, entity, details, IP, timestamp), queryable in Governance.

### Data governance
- Candidate PII beyond role-relevance is redacted before AI processing.
- Retention job flags stale non-hired records for deletion review.
- Admin hard-purge for erasure requests (removes the resume file too), leaving a
  non-personal deletion audit record.
- Secrets, the database, uploads and exports are git-ignored.

### Resilience
- Deterministic fallback engine keeps the service usable during AI outages.
- Bounded retries with backoff on transient LLM errors; typed error handling.

## Production hardening checklist

- [ ] Terminate TLS at the proxy; enable HSTS.
- [ ] Move from SQLite to PostgreSQL (Azure Database) with encryption at rest.
- [ ] Store the JWT secret and SMTP/API credentials in a secrets manager
      (Azure Key Vault), not environment files.
- [ ] Put file storage on encrypted object storage (Azure Blob / SharePoint) with
      per-tenant isolation.
- [ ] Add SSO via Microsoft Entra ID (replace the local user store) and enforce MFA.
- [ ] Add rate limiting and a WAF at the edge.
- [ ] Rotate the failed-login tracker to a shared store (Redis) if running
      multiple instances.
- [ ] Externalise the background scheduler (Celery/Azure Functions) for HA.
- [ ] Formalise data-retention automation and DPA/consent records.
- [ ] Periodic penetration testing and dependency scanning in CI.

## Threat notes

- **Prompt-injection via resume content:** resumes are treated as untrusted data
  and passed inside delimited blocks; the model returns structured JSON validated
  against a schema, and scores are computed in code from per-criterion evidence —
  a resume cannot cause an action, only supply text to be judged. Evidence quotes
  are verified against the source, so injected "confirmed" claims are downgraded.
- **PII exposure:** redaction limits what the model sees; RBAC limits what users
  see; audit logs record access to decisions.
