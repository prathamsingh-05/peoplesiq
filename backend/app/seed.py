"""First-boot seeding: bootstrap admin account and the pre-loaded keep-warm
content library (People IQ / OculusIT approved content placeholders)."""
from __future__ import annotations

import logging
import os
import secrets

from .auth import hash_password
from .database import SessionLocal
from .models import ContentItem, User, UserRole

logger = logging.getLogger("peopleiq.seed")

CONTENT_LIBRARY = [
    ("A welcome from OculusIT leadership", "leadership_welcome",
     "A personal welcome message from the OculusIT leadership team, introducing the "
     "company's mission of powering IT for higher education worldwide.",
     "https://www.youtube.com/watch?v=oculusit-welcome"),
    ("OculusIT company overview (video)", "company_video",
     "A 4-minute overview of OculusIT's managed IT, security and cloud services for "
     "colleges and universities.",
     "https://www.youtube.com/watch?v=oculusit-overview"),
    ("Employee story: growing with OculusIT", "employee_story",
     "How one engineer grew from L1 support to leading a global NOC team — in their own words.",
     "https://www.youtube.com/watch?v=oculusit-employee-story"),
    ("Inside our offices", "office_photos",
     "A photo tour of the OculusIT offices and collaboration spaces.",
     "https://thepeopleiq.com/oculusit/office-tour"),
    ("Learning path for your role", "learning_content",
     "Curated learning resources relevant to your new role, so you can hit the ground running.",
     "https://thepeopleiq.com/oculusit/learning"),
    ("Meet your team", "team_introduction",
     "Short introductions to the team members you will be working with from Day 1.",
     ""),
    ("Your benefits at a glance", "benefits",
     "Health cover, leave policy, night-shift allowances and growth benefits — summarised.",
     ""),
    ("New joiner FAQs", "faq",
     "The 15 questions every new joiner asks — answered (payroll dates, laptop policy, "
     "probation, buddy program).",
     ""),
    ("Working the night shift / hybrid model", "shift_info",
     "What the night-shift and hybrid working model looks like in practice, and the "
     "support available to you.",
     ""),
    ("Joining documentation guide", "docs_instructions",
     "Step-by-step instructions for the documents you need on Day 1 and how to submit them.",
     ""),
]


def seed_initial_data() -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            password = os.environ.get("PEOPLEIQ_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
            admin = User(
                username="admin",
                email=os.environ.get("PEOPLEIQ_ADMIN_EMAIL", "admin@thepeopleiq.com"),
                full_name="People IQ Administrator",
                password_hash=hash_password(password),
                role=UserRole.admin.value,
            )
            db.add(admin)
            db.commit()
            if os.environ.get("PEOPLEIQ_ADMIN_PASSWORD"):
                logger.info("Bootstrap admin 'admin' created (password from environment).")
            else:
                # One-time display; never stored in plaintext anywhere.
                logger.warning(
                    "Bootstrap admin created — username: admin  password: %s "
                    "(change it immediately after first login)", password
                )

        if db.query(ContentItem).count() == 0:
            db_admin = db.query(User).filter(User.role == "admin").first()
            for title, ctype, body, url in CONTENT_LIBRARY:
                db.add(ContentItem(
                    title=title, content_type=ctype, body=body, url=url,
                    is_approved=True,
                    approved_by_id=db_admin.id if db_admin else None,
                ))
            db.commit()
            logger.info("Seeded %d approved keep-warm content items.", len(CONTENT_LIBRARY))
    finally:
        db.close()
