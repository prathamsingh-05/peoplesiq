"""§8-10 — Candidate communication module.

Covers, exactly per the brief:
- Initial outreach email (drafted; sent only after recruiter approval — the
  presence of an extracted address is never sufficient).
- Rejection / hold templates: not suitable, retained for future, more info
  required, unreachable, position on hold. Rejections are DRAFT-ONLY.
- Offer-accepted keep-warm protocol: confirmation, every-3rd-day content
  drip from the approved content library, T-7 checklist, T-5 culture,
  T-3 documentation, T-2 final confirmation, T-1 Day-1 instructions,
  Day-0 welcome + induction agenda.
- SMTP sending is opt-in (PEOPLEIQ_EMAIL_SENDING=true + SMTP config);
  otherwise all mail stays in the outbox as drafts/approved items.
"""
from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.utils import formataddr

from sqlalchemy.orm import Session

from .. import config
from ..models import (
    Candidate,
    ContentItem,
    EmailMessage,
    EmailStatus,
    EngagementSequence,
    Job,
)
from . import llm

logger = logging.getLogger("peopleiq.email")

SIGNATURE = f"""
Warm regards,
{config.SMTP_FROM_NAME}
{config.COMPANY_NAME} · https://thepeopleiq.com/
"""


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------
def _first_name(candidate: Candidate) -> str:
    return (candidate.full_name.split()[0] if candidate.full_name else "there")


def render_template(key: str, candidate: Candidate, job: Job, **extra) -> tuple[str, str]:
    """Return (subject, body) for a template key."""
    name = _first_name(candidate)
    client = job.client_name or config.CLIENT_NAME_DEFAULT

    if key == "initial_outreach":
        subject = f"{job.title} opportunity with {client} — are you interested?"
        body = f"""Hi {name},

I'm reaching out from {config.COMPANY_NAME}, the talent partner for {client}. Your profile
came up as a strong potential match for the role below and I'd love to know if you are
open to a conversation.

Role        : {job.title}
Client      : {client} — a global higher-education technology services provider
Location    : {job.location or 'Shared during the call'}
Work model  : {job.work_model or 'Shared during the call'}
Working hours: {job.working_hours or 'Standard business hours'}

About the opportunity:
{(job.description or '')[:500].strip()}...

If you are interested, simply reply to this email with:
  1. Your current location and notice period.
  2. Your current and expected compensation.
  3. A good time for a 15-minute introductory call.

You can also apply directly by replying with your updated resume.
{SIGNATURE}"""

    elif key == "reject_not_suitable":
        subject = f"Update on your application — {job.title}"
        body = f"""Hi {name},

Thank you for the time you invested in applying for the {job.title} role with {client}.

After careful review against the specific requirements of this position, we will not be
moving forward with your application for this role. This decision reflects the match to
this particular role only — not your capabilities or experience overall.

We genuinely appreciate your interest and encourage you to apply for future roles that
match your profile.
{SIGNATURE}"""

    elif key == "hold_future":
        subject = f"Your profile with {config.COMPANY_NAME} — retained for future roles"
        body = f"""Hi {name},

Thank you for applying for the {job.title} role with {client}. While we are not
progressing your application for this specific position, your background stood out and,
with your permission, we would like to retain your profile for upcoming opportunities
that fit your experience.

If you would rather we delete your details instead, just reply to this email and we
will action it promptly.
{SIGNATURE}"""

    elif key == "more_info_needed":
        subject = f"Quick question about your application — {job.title}"
        body = f"""Hi {name},

Thanks for your application for the {job.title} role with {client}. To progress your
profile we need a little more information:

{extra.get('info_needed', '  • Please share your updated resume, current location, notice period and compensation expectations.')}

A quick reply will help us move your application to the next stage.
{SIGNATURE}"""

    elif key == "unreachable":
        subject = f"We tried to reach you — {job.title} with {client}"
        body = f"""Hi {name},

We have been trying to reach you regarding your application for the {job.title} role
with {client}, but haven't managed to connect.

If you are still interested, please reply with a convenient time for a short call. If
we don't hear back within 5 working days we will assume you are no longer pursuing this
opportunity — though you are welcome to reconnect at any time.
{SIGNATURE}"""

    elif key == "position_on_hold":
        subject = f"Status update — {job.title} with {client}"
        body = f"""Hi {name},

A quick update on the {job.title} role you applied for: the position has been placed
temporarily on hold by the client. Your application remains active and we will contact
you as soon as the role reopens.

Thank you for your patience — and if your situation changes in the meantime, do let us
know.
{SIGNATURE}"""

    elif key == "offer_confirmation":
        subject = f"Congratulations — offer accepted for {job.title} at {client}!"
        body = f"""Hi {name},

Congratulations, and welcome aboard! 🎉 We're delighted to confirm your acceptance of the
offer for {job.title} with {client}.

Your joining date is {extra.get('joining_date', 'being finalised')}. Between now and then
we'll stay in touch with useful content about {client} — the team, the culture, and what
to expect in your first week — so you can hit the ground running.

If anything changes or you have any questions at all, reply here or call your recruiter
directly. We're with you all the way to Day 1.
{SIGNATURE}"""

    elif key == "keepwarm_content":
        item: ContentItem | None = extra.get("content_item")
        title = item.title if item else f"Life at {client}"
        content_body = (item.body if item else "")
        url = (item.url if item else "")
        subject = f"{title} — from the {client} team"
        body = f"""Hi {name},

While you count down to your start date, here's something we thought you'd enjoy:

{title}
{content_body}
{('Watch/read here: ' + url) if url else ''}

More to come soon. If you have questions about your onboarding, just reply here.
{SIGNATURE}"""

    elif key == "checklist_t7":
        subject = f"One week to go — your joining readiness checklist ({client})"
        body = f"""Hi {name},

You're one week away from joining {client} as {job.title}! Here's your readiness checklist:

  ☐ Government photo ID (original + copy)
  ☐ Educational certificates and mark sheets
  ☐ Relieving letter / resignation acceptance from your current employer
  ☐ Last 3 months' payslips
  ☐ Passport-size photographs
  ☐ Bank account details for payroll
  ☐ Signed offer letter copy

Reply to confirm you have everything in hand, or tell us what's pending so we can help.
{SIGNATURE}"""

    elif key == "culture_t5":
        subject = f"Meet the team — culture at {client}"
        body = f"""Hi {name},

Five days to go! Here's a quick introduction to the team and culture you're joining at
{client}: a collaborative, service-driven organisation supporting higher-education
institutions worldwide, with a strong tradition of mentoring new joiners through their
first 90 days.

You'll meet your team lead on Day 1, and a buddy will be assigned for your first month.
{SIGNATURE}"""

    elif key == "docs_t3":
        subject = f"Documentation reminder — 3 days to joining ({client})"
        body = f"""Hi {name},

Just 3 days to go. A gentle reminder to have your joining documents ready (see the
checklist we sent earlier). If any document is delayed — especially your relieving
letter — tell us NOW so we can flag it to {client} HR and keep your Day 1 smooth.
{SIGNATURE}"""

    elif key == "confirm_t2":
        subject = f"Final confirmation — joining {client} in 2 days"
        body = f"""Hi {name},

Two days to go! Please reply to this email with a quick "Confirmed" so we know you're
all set for your start date {extra.get('joining_date', '')}.

Tomorrow you'll receive your complete Day 1 instructions — reporting time, induction
link, your reporting manager's details and the full agenda.
{SIGNATURE}"""

    elif key == "day1_t1":
        subject = f"Your Day 1 instructions — {job.title} at {client}"
        body = f"""Hi {name},

Tomorrow's the day! Here is everything you need:

Reporting time      : {extra.get('reporting_time', '9:00 AM (local office time)')}
Video induction link: {extra.get('induction_link', 'Will be shared by the onboarding team')}
Reporting manager   : {extra.get('reporting_manager', 'Shared in your welcome pack')}
Documents to carry  : Photo ID, education certificates, relieving letter, payslips, photos
Technology/login    : Your {client} credentials will be issued during induction
Contact for help    : {extra.get('help_contact', config.SMTP_FROM)}

Day 1 agenda:
  09:00  Welcome & video induction (join via the link above)
  10:30  HR documentation and system access
  12:00  Team introductions with your reporting manager
  14:00  Role orientation and first-week plan

We're excited for you — see you tomorrow!
{SIGNATURE}"""

    elif key == "welcome_day0":
        subject = f"Welcome to {client}! 🎉 Your induction starts now"
        body = f"""Hi {name},

Today's the day — welcome to {client}!

Please join the video induction at {extra.get('reporting_time', '9:00 AM')} using the link
shared yesterday. Your induction agenda is attached to your welcome pack, and your
reporting manager is expecting you.

From this point, the {client} HR and onboarding team takes over and will be your primary
contact. It has been a pleasure guiding you through the process — on behalf of everyone
at {config.COMPANY_NAME}, we wish you a brilliant start!

(This is the final message from the {config.COMPANY_NAME} recruitment desk; your candidate
record now transfers to {client}'s own people team.)
{SIGNATURE}"""

    else:
        raise ValueError(f"Unknown template: {key}")

    return subject, body


# Optional AI polish of the outreach draft (kept structured & factual)
POLISH_SCHEMA = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["subject", "body"],
    "additionalProperties": False,
}


def personalise_outreach(candidate: Candidate, job: Job, subject: str, body: str) -> tuple[str, str]:
    """Have the model lightly personalise the outreach using resume facts."""
    try:
        result = llm.structured_call(
            system="You lightly personalise a recruitment outreach email. Keep ALL factual "
                   "details (role, client, location, model, hours, instructions) unchanged. "
                   "Add one specific, professional sentence referencing the candidate's "
                   "relevant experience. Never mention protected attributes. Keep it concise.",
            user_content=f"Candidate resume extract:\n{candidate.redacted_text[:6000]}\n\n"
                         f"Subject: {subject}\n\nBody:\n{body}",
            schema=POLISH_SCHEMA,
            max_tokens=2000,
        )
        if result.get("subject") and result.get("body"):
            return result["subject"], result["body"]
    except llm.LLMUnavailable:
        pass
    return subject, body


# ---------------------------------------------------------------------------
# Keep-warm schedule builder (§9)
# ---------------------------------------------------------------------------
def build_keepwarm_schedule(
    db: Session, sequence: EngagementSequence, candidate: Candidate, job: Job
) -> list[EmailMessage]:
    """Create the full scheduled email plan for an accepted offer.

    - Day 0 (acceptance): confirmation
    - Every 3rd day: approved content from the library, up to T-2 days
    - T-7 checklist, T-5 culture, T-3 docs, T-2 final confirmation,
      T-1 Day-1 instructions, Day 0 (joining): welcome + agenda.
    Milestone emails take precedence over drip content on collision days.
    """
    assert sequence.joining_date is not None
    start = sequence.offer_accepted_date or datetime.now(timezone.utc)
    joining = sequence.joining_date
    join_day = joining.date()

    plan: dict = {}  # date -> (template_key, extra)
    jd_str = join_day.strftime("%A, %d %B %Y")

    plan[start.date()] = ("offer_confirmation", {"joining_date": jd_str})
    for offset, key in ((7, "checklist_t7"), (5, "culture_t5"), (3, "docs_t3"),
                        (2, "confirm_t2"), (1, "day1_t1")):
        d = join_day - timedelta(days=offset)
        if d > start.date():
            plan[d] = (key, {"joining_date": jd_str})
    plan[join_day] = ("welcome_day0", {})

    # Every-3rd-day content drip from the approved library, up to T-minus 2,
    # skipping days already taken by milestones.
    content_items = (
        db.query(ContentItem)
        .filter(ContentItem.is_approved.is_(True), ContentItem.is_active.is_(True))
        .order_by(ContentItem.id)
        .all()
    )
    drip_date = start.date() + timedelta(days=3)
    idx = 0
    while drip_date <= join_day - timedelta(days=2):
        if drip_date not in plan:
            item = content_items[idx % len(content_items)] if content_items else None
            plan[drip_date] = ("keepwarm_content", {"content_item": item})
            idx += 1
        drip_date += timedelta(days=3)

    messages: list[EmailMessage] = []
    for send_date in sorted(plan):
        key, extra = plan[send_date]
        subject, body = render_template(key, candidate, job, **extra)
        scheduled = datetime(
            send_date.year, send_date.month, send_date.day, 9, 0, tzinfo=timezone.utc
        )
        message = EmailMessage(
            candidate_id=candidate.id,
            sequence_id=sequence.id,
            template_key=key,
            subject=subject,
            body=body,
            to_address=candidate.email,
            status=EmailStatus.approved.value,   # sequence approval covers its emails
            scheduled_for=scheduled,
            sequence_step=key,
            content_item_id=(extra.get("content_item").id
                             if isinstance(extra.get("content_item"), ContentItem) else None),
        )
        db.add(message)
        messages.append(message)
    return messages


# ---------------------------------------------------------------------------
# Sending (SMTP; disabled unless explicitly enabled)
# ---------------------------------------------------------------------------
def sending_configured() -> bool:
    return bool(config.EMAIL_SENDING_ENABLED and config.SMTP_HOST and config.SMTP_FROM)


def send_email(message: EmailMessage) -> None:
    """Physically send one approved email. Raises on failure."""
    if not sending_configured():
        raise RuntimeError(
            "Email sending is not enabled. Set PEOPLEIQ_EMAIL_SENDING=true and the "
            "PEOPLEIQ_SMTP_* variables (drafts remain available in the outbox)."
        )
    if not message.to_address:
        raise RuntimeError("Candidate has no email address on record")

    mime = MIMEText(message.body, "plain", "utf-8")
    mime["Subject"] = message.subject
    mime["From"] = formataddr((config.SMTP_FROM_NAME, config.SMTP_FROM))
    mime["To"] = message.to_address

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
        smtp.ehlo()
        try:
            smtp.starttls()
            smtp.ehlo()
        except smtplib.SMTPNotSupportedError:
            logger.warning("SMTP server does not support STARTTLS")
        if config.SMTP_USER:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.sendmail(config.SMTP_FROM, [message.to_address], mime.as_string())
