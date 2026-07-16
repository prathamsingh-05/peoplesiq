"""Fairness controls: protected attributes must never reach the scoring engine."""
from app.services.fairness import redact_protected_attributes

SAMPLE = """Rahul Sharma
Email: rahul.sharma@example.com | Phone: +91 98100 12345
Date of Birth: 12/08/1990
Marital Status: Married
Religion: Hindu
Nationality: Indian
Father's Name: R. K. Sharma
Gender: Male
Blood Group: O+
Permanent Address: H-42, Sector 15, Gurugram, Haryana 122001

PROFESSIONAL SUMMARY
Banner administrator with 6 years of experience. Eligible to work in India.

SKILLS
Ellucian Banner, PL/SQL
"""


def test_redacts_all_protected_attributes():
    redacted, applied = redact_protected_attributes(SAMPLE)
    for leak in ("12/08/1990", "Married", "Hindu", "R. K. Sharma",
                 "Sector 15", "O+"):
        assert leak not in redacted, f"Leaked protected attribute: {leak}"
    assert "date_of_birth" in applied
    assert "marital_status" in applied
    assert "religion_caste" in applied


def test_keeps_professional_content():
    redacted, _ = redact_protected_attributes(SAMPLE)
    assert "Banner administrator with 6 years" in redacted
    assert "Ellucian Banner" in redacted
    assert "PL/SQL" in redacted


def test_keeps_work_authorisation():
    text = "Work Authorisation: eligible to work in the US (H1B).\nNationality: Indian"
    redacted, _ = redact_protected_attributes(text)
    assert "eligible to work" in redacted.lower()
    assert "Nationality: Indian" not in redacted
