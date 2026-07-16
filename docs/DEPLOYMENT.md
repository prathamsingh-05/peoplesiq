# Deployment — making the prototype 100% functional and privately visible

This is the precise, complete list of what's needed to take the platform from
"runs on a laptop" to "a private URL your team can log into, with full AI and
email." Nothing here is a code gap — the application is complete; these are the
external inputs and the deploy step.

---

## The app is private by default

Every page requires a login. There is no anonymous access, no public sign-up.
"Privately visible" therefore just means: deploy it to a host your team can
reach, behind TLS, and hand out accounts. The bootstrap admin creates the rest.

---

## Option A — one-command private deploy (recommended)

A `Dockerfile` and `docker-compose.yml` are included. On any host with Docker
(a small cloud VM, an internal server, Azure Container Instances, Fly.io,
Render, Railway, etc.):

```bash
cp .env.example .env          # fill in the values below
# edit .env: set PEOPLEIQ_ADMIN_PASSWORD (required)
docker compose up -d --build
```

The app is then live on port 8000 (API + UI on one origin). Put your platform's
TLS/reverse proxy in front of it and it's a private `https://…` your team logs
into. Candidate data persists in the `peopleiq_data` volume.

## Option B — managed platform

The same image deploys to any container host. For a fully-managed path on the
Microsoft stack your client already uses: **Azure Container Apps** (or App
Service for Containers) + **Azure Database for PostgreSQL** (set
`PEOPLEIQ_DATABASE_URL`) + **Entra ID** in front for SSO. See the roadmap for the
enterprise integration path.

---

## What I need from you — the complete list

### To make it privately visible (required)
1. **A host to run it on** — any of: a cloud VM you own, an internal server, or
   a container platform account (Azure / Render / Railway / Fly). One is enough.
2. **A strong admin password** — set `PEOPLEIQ_ADMIN_PASSWORD` (you keep it; it's
   never stored in plaintext or committed).
3. *(If you want a custom address)* the **domain/subdomain** you mentioned
   providing (e.g. `recruiter.thepeopleiq.com`) pointed at the host, with TLS —
   most platforms issue the certificate automatically.

That's all that's needed for a private, logged-in, fully-navigable deployment.
Screening already works in this state via the deterministic engine.

### To switch AI screening to full Claude quality (recommended)
4. **`ANTHROPIC_API_KEY`** — an Anthropic API key. The model defaults to
   `claude-opus-4-8`; no other change needed. Without it the app still runs, on
   the deterministic fallback engine (basic screening, everything routed to
   recruiter review).

### To send real candidate emails (optional — else safe draft-only)
5. **A mailbox / SMTP details** — the email account you said comes later:
   `PEOPLEIQ_SMTP_HOST`, `PEOPLEIQ_SMTP_PORT`, `PEOPLEIQ_SMTP_USER`,
   `PEOPLEIQ_SMTP_PASSWORD`, `PEOPLEIQ_SMTP_FROM`, and set
   `PEOPLEIQ_EMAIL_SENDING=true`. Until this is provided, every email is created
   and approved but held as a draft — nothing is ever sent.
   *(For the Microsoft-native path, an Outlook/Microsoft Graph app registration
   instead of SMTP — that's the Phase-2 integration in the roadmap.)*

### To make keep-warm content real (optional)
6. **Approved OculusIT content** — real leadership-message links, company/
   employee-story videos (YouTube URLs), office photos, benefits and FAQ text —
   to replace the placeholder library entries that ship seeded.

### Nice-to-have external integrations (Phase 2+, all documented in the roadmap)
7. Microsoft Graph (Outlook mail + Teams transcript retrieval), SharePoint/
   OneDrive storage, Entra ID SSO, and a Keka/ATS connection — each needs the
   corresponding tenant app registration and credentials from your side.

---

## Summary

| To achieve | You provide | Status without it |
|---|---|---|
| Private, logged-in deployment | a host + admin password (+ optional domain) | — (this is the deploy step) |
| Full Claude screening | `ANTHROPIC_API_KEY` | deterministic fallback engine |
| Real email sending | SMTP/mailbox details | safe draft-only mode |
| Real keep-warm content | approved OculusIT media/links | placeholder library |
| MS Graph / Teams / ATS | tenant app registrations | uploaded transcripts; SMTP; manual export |

Give me **items 1–3** and I can stand up a private instance. Add **item 4** and
the AI screening is at full quality. Add **item 5** and it emails candidates for
real.
