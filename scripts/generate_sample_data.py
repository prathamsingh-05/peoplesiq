"""Generate the test dataset required by the brief (§18):

- 3 job descriptions (data/sample/jds/*.md)
- 30 resumes for the primary JD (mix of strong / borderline / unsuitable),
  written as DOCX and PDF files + 1 exact duplicate + 1 unreadable file
- recruiter ground-truth labels (data/sample/labels.json) for the
  AI-vs-recruiter evaluation report

All resumes are synthetic. Some intentionally include protected attributes
(DOB, marital status, religion) to exercise the fairness redaction layer.

Usage:  python scripts/generate_sample_data.py
"""
from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

import docx
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

random.seed(42)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sample"
JD_DIR = OUT / "jds"
RESUME_DIR = OUT / "resumes"

# ---------------------------------------------------------------------------
# Job descriptions (3 per brief §18)
# ---------------------------------------------------------------------------
JDS = {
    "01_erp_banner_administrator.md": {
        "title": "ERP Application Administrator (Ellucian Banner)",
        "body": """# ERP Application Administrator — Ellucian Banner
Client: OculusIT | Location: Gurugram, India (Hybrid) | Shift: US EST overlap (6 PM – 3 AM IST)

OculusIT provides managed IT services to higher-education institutions across the US.
We are hiring an ERP Application Administrator to support Ellucian Banner environments
for multiple university clients.

## Responsibilities
- Administer and support Ellucian Banner 9 (Student, Finance, HR modules)
- Apply upgrades, patches and page builds; manage Banner environment cloning
- Troubleshoot production incidents on Oracle 19c databases and WebLogic
- Write and tune PL/SQL for data fixes, interfaces and reporting
- Support Argos / evisions reporting and integrations (Ethos, APIs)
- Work US business hours (EST overlap) with on-call rotation

## Requirements (essential)
- 5+ years administering Ellucian Banner in a production environment
- Strong Oracle PL/SQL and database troubleshooting skills
- Hands-on experience with Banner 9 self-service and admin pages
- Experience supporting US higher-education clients
- Willingness to work the night shift (US EST overlap) from Gurugram (hybrid)

## Preferred
- Ellucian Ethos / Banner APIs / Integration experience
- Jenkins or automation for Banner deployments
- Degree Works, Argos or Cognos exposure

Qualification: Bachelor's degree in Computer Science or equivalent.
Compensation: ₹18–28 LPA depending on experience. Notice period preference: ≤ 30 days.
Mandatory: Candidate must confirm willingness to work night shift; must have hands-on
Banner production support experience (not implementation-only)."""
    },
    "02_soc_analyst.md": {
        "title": "SOC Analyst L2 (Security Operations)",
        "body": """# SOC Analyst L2 — Security Operations Center
Client: OculusIT | Location: Remote (India) | Shift: 24x7 rotational

Monitor, triage and respond to security events for US higher-education clients.

## Requirements (essential)
- 3+ years in a SOC performing alert triage and incident response
- Hands-on with a SIEM (Splunk, Sentinel or QRadar) — building queries and dashboards
- Understanding of MITRE ATT&CK, phishing analysis, EDR tooling
- Willingness to work 24x7 rotational shifts

## Preferred
- Security+ / CEH / CySA+ certification
- Higher-education or MSSP experience
- Scripting (Python or PowerShell) for automation

Qualification: Bachelor's degree. Compensation: ₹10–18 LPA. Notice: ≤ 45 days.
Mandatory: rotational shift confirmation; hands-on SIEM experience."""
    },
    "03_network_engineer.md": {
        "title": "Senior Network Engineer",
        "body": """# Senior Network Engineer
Client: OculusIT | Location: Gurugram (Office) | Shift: US EST overlap

Design, implement and support campus networks for US universities.

## Requirements (essential)
- 6+ years enterprise networking (routing/switching) in production
- Deep Cisco experience (Catalyst, Nexus); CCNP or equivalent knowledge
- Hands-on with wireless (Aruba/Cisco), VPN, firewalls (Palo Alto / Fortinet)
- Experience with network monitoring (SolarWinds, PRTG)

## Preferred
- CCNP/CCIE certification, NAC (Clearpass/ISE), SD-WAN
- Higher-education campus network experience

Qualification: Bachelor's degree. Compensation: ₹20–32 LPA. Notice: ≤ 30 days.
Mandatory: office presence in Gurugram; night-shift overlap confirmation."""
    },
}

FIRST = ["Aarav", "Vivaan", "Aditya", "Ishaan", "Kabir", "Ananya", "Diya", "Meera",
         "Rohan", "Arjun", "Sneha", "Priya", "Rahul", "Nikhil", "Pooja", "Kiran",
         "Sameer", "Divya", "Amit", "Neha", "Vikram", "Shreya", "Manish", "Ritu",
         "Suresh", "Anjali", "Deepak", "Kavya", "Rajesh", "Tanvi", "Harish", "Lakshmi"]
LAST = ["Sharma", "Verma", "Patel", "Iyer", "Nair", "Reddy", "Gupta", "Malhotra",
        "Bose", "Chatterjee", "Singh", "Mehta", "Joshi", "Kulkarni", "Rao", "Das",
        "Kapoor", "Agarwal", "Menon", "Pillai", "Bhatt", "Saxena", "Tripathi", "Ghosh"]

CITIES = ["Gurugram", "Noida", "Bengaluru", "Hyderabad", "Pune", "Chennai", "Delhi NCR"]


def _contact(name: str, i: int) -> str:
    slug = name.lower().replace(" ", ".")
    return f"{name}\nEmail: {slug}{i}@example-mail.com | Phone: +91 98{i:02d}0 {i:02d}432\nLocation: {random.choice(CITIES)}, India"


def strong_banner(name: str, i: int) -> str:
    years = random.choice([5, 6, 7, 8, 9])
    return f"""{_contact(name, i)}

PROFESSIONAL SUMMARY
ERP Application Administrator with {years} years of hands-on Ellucian Banner production
support for US higher-education institutions. Deep Oracle PL/SQL and Banner 9 experience.

WORK EXPERIENCE
Senior Banner Administrator — CampusWorks Global Services | Mar 2021 – Present
- Administer Ellucian Banner 9 Student and Finance modules for four US universities
- Applied Banner upgrades and CPU patches across DEV/TEST/PROD; managed environment clones
- Resolved 40+ production incidents monthly on Oracle 19c and WebLogic 12c
- Wrote and tuned PL/SQL packages for registration data fixes and Argos reporting feeds
- Built Ethos API integrations for housing and payment vendors
- Worked 6 PM – 3 AM IST supporting US EST clients, including on-call rotation

Banner Application Analyst — EduTech Services Pvt Ltd | Jun 2017 – Feb 2021
- Supported Banner 8 to 9 migration (admin pages and self-service)
- Developed PL/SQL interfaces between Banner and third-party LMS
- Provided L2 production support for US college clients on night shift

EDUCATION
B.Tech, Computer Science — {random.choice(['Pune University', 'VIT', 'Anna University'])}, 2016

SKILLS
Ellucian Banner 9, Oracle 19c, PL/SQL, WebLogic, Ethos APIs, Argos, Jenkins, ITIL

OTHER
Notice period: {random.choice(['15 days', '30 days', 'Immediate'])}. Comfortable with night shift (US EST overlap). Open to hybrid work from Gurugram.
"""


def borderline_banner(name: str, i: int) -> str:
    flavour = random.choice(["peoplesoft", "dba", "implementation", "junior"])
    if flavour == "peoplesoft":
        body = f"""PROFESSIONAL SUMMARY
ERP consultant with 6 years across PeopleSoft Campus Solutions and 1 year of Ellucian
Banner exposure during a migration project.

WORK EXPERIENCE
ERP Consultant — UniSys Campus Solutions | Jan 2019 – Present
- PeopleSoft Campus Solutions administration for two universities
- Participated in a Banner 9 migration assessment (6 months, shadowing role)
- Strong SQL (Oracle and SQL Server); wrote data conversion scripts

Systems Analyst — TechServe | Jul 2016 – Dec 2018
- ERP helpdesk L1/L2, ticket triage, user provisioning

EDUCATION
B.Sc. Information Technology, 2016

SKILLS
PeopleSoft, Oracle SQL, PL/SQL (basic), ERP support, ITIL"""
    elif flavour == "dba":
        body = f"""PROFESSIONAL SUMMARY
Oracle DBA with 7 years managing production databases; supported Banner databases at a
university client for 18 months, but not the Banner application layer itself.

WORK EXPERIENCE
Senior Oracle DBA — DataCore Managed Services | 2018 – Present
- Oracle 12c/19c administration: RMAN, Data Guard, performance tuning
- Supported the database tier of an Ellucian Banner environment (backups, cloning)
- Extensive PL/SQL for maintenance automation

EDUCATION
B.E. Computer Engineering, 2015

SKILLS
Oracle 19c, PL/SQL, RMAN, Data Guard, Linux, shell scripting

OTHER
Notice period: 60 days. Night shift: negotiable."""
    elif flavour == "implementation":
        body = f"""PROFESSIONAL SUMMARY
Ellucian Banner functional consultant, 5 years — implementation and configuration focus
(Student module), limited production-support exposure.

WORK EXPERIENCE
Banner Functional Consultant — EduImplement LLC | 2019 – Present
- Configured Banner 9 Student for new implementations at three US colleges
- Gathered requirements, configured validation tables, trained registrars
- Occasional post-go-live hypercare support

EDUCATION
MBA (Systems), 2018; B.Com, 2015

SKILLS
Ellucian Banner Student, requirement analysis, SQL (reporting), Argos (viewer)"""
    else:
        body = f"""PROFESSIONAL SUMMARY
Application support engineer with 3 years, including 2 years on Ellucian Banner L1/L2
support for a US university — eager to grow into an administrator role.

WORK EXPERIENCE
Application Support Engineer — GlobalEdu Services | 2022 – Present
- L1/L2 Banner 9 support: password resets, job submission issues, page errors
- Escalated complex issues to senior administrators; wrote simple SQL queries
- Night shift (US EST) for the past 18 months

EDUCATION
B.Tech IT, 2021

SKILLS
Ellucian Banner (support), SQL basics, ServiceNow, Jira"""
    return f"{_contact(name, i)}\n\n{body}\n"


def unsuitable_banner(name: str, i: int) -> str:
    flavour = random.choice(["java", "marketing", "fresher", "mainframe"])
    protected = random.random() < 0.5
    extra = ("\nPERSONAL DETAILS\nDate of Birth: 12/08/1994\nMarital Status: Married\n"
             "Religion: Hindu\nFather's Name: R. K. Sharma\n") if protected else ""
    if flavour == "java":
        body = """PROFESSIONAL SUMMARY
Java backend developer, 6 years, building microservices for fintech products.

WORK EXPERIENCE
Senior Software Engineer — FinPay Technologies | 2019 – Present
- Spring Boot microservices, Kafka, PostgreSQL, AWS
- Led a team of 4 engineers on the payments platform

EDUCATION
B.Tech CSE, 2018

SKILLS
Java, Spring Boot, Kafka, PostgreSQL, AWS, Docker, Kubernetes"""
    elif flavour == "marketing":
        body = """PROFESSIONAL SUMMARY
Digital marketing specialist with 5 years in campaign management and SEO.

WORK EXPERIENCE
Marketing Manager — BrandBoost Agency | 2020 – Present
- Managed Google Ads and Meta campaigns for 12 clients
- Grew organic traffic 3x through SEO strategy

EDUCATION
BBA Marketing, 2017

SKILLS
SEO, SEM, Google Analytics, content strategy, HubSpot"""
    elif flavour == "fresher":
        body = """PROFESSIONAL SUMMARY
Recent graduate seeking an entry-level IT position. Academic projects in web development.

PROJECTS
- College event management website (PHP, MySQL)
- Attendance tracker mobile app (Flutter)

EDUCATION
B.Tech IT, 2025 (fresh graduate)

SKILLS
HTML, CSS, JavaScript, PHP, MySQL, Flutter (academic)"""
    else:
        body = """PROFESSIONAL SUMMARY
Mainframe developer with 12 years on COBOL/JCL banking systems.

WORK EXPERIENCE
Lead Mainframe Developer — LegacyBank Systems | 2013 – Present
- COBOL, JCL, DB2, CICS development and batch support

EDUCATION
B.Sc. Mathematics, 2011

SKILLS
COBOL, JCL, DB2, CICS, VSAM, Endevor"""
    return f"{_contact(name, i)}\n{extra}\n{body}\n"


def write_docx(path: Path, text: str) -> None:
    document = docx.Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    document.save(path)


def write_pdf(path: Path, text: str) -> None:
    page = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 2 * cm
    page.setFont("Helvetica", 9)
    for line in text.split("\n"):
        while len(line) > 105:
            page.drawString(2 * cm, y, line[:105])
            line = line[105:]
            y -= 12
            if y < 2 * cm:
                page.showPage(); page.setFont("Helvetica", 9); y = height - 2 * cm
        page.drawString(2 * cm, y, line)
        y -= 12
        if y < 2 * cm:
            page.showPage(); page.setFont("Helvetica", 9); y = height - 2 * cm
    page.save()


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    JD_DIR.mkdir(parents=True)
    RESUME_DIR.mkdir(parents=True)

    for filename, jd in JDS.items():
        (JD_DIR / filename).write_text(jd["body"])

    names = random.sample([f"{f} {l}" for f in FIRST for l in LAST], 40)
    labels: dict[str, dict] = {}
    makers = ([("strong", strong_banner)] * 10
              + [("borderline", borderline_banner)] * 10
              + [("unsuitable", unsuitable_banner)] * 10)

    for i, (tier, maker) in enumerate(makers, start=1):
        name = names[i]
        text = maker(name, i)
        base = f"{i:02d}_{name.replace(' ', '_')}"
        if i % 3 == 0:
            path = RESUME_DIR / f"{base}.pdf"
            write_pdf(path, text)
        else:
            path = RESUME_DIR / f"{base}.docx"
            write_docx(path, text)
        # Ground truth: what an experienced recruiter decided historically.
        labels[path.name] = {
            "tier": tier,
            "recruiter_decision": {"strong": "shortlist",
                                   "borderline": "review",
                                   "unsuitable": "reject"}[tier],
            "candidate_name": name,
        }

    # Edge cases: an exact duplicate and an unreadable file.
    first_resume = sorted(RESUME_DIR.iterdir())[0]
    dup = RESUME_DIR / f"31_DUPLICATE_{first_resume.name}"
    shutil.copyfile(first_resume, dup)
    labels[dup.name] = {"tier": "duplicate", "recruiter_decision": "duplicate",
                        "candidate_name": "(duplicate)"}

    bad = RESUME_DIR / "32_corrupt_scan.pdf"
    bad.write_bytes(b"%PDF-1.4\n%\xc7\xec\x8f\xa2 corrupted scan bytes \x00\x01\x02" * 3)
    labels[bad.name] = {"tier": "unreadable", "recruiter_decision": "unreadable",
                        "candidate_name": "(unreadable)"}

    (OUT / "labels.json").write_text(json.dumps(labels, indent=2))
    print(f"Wrote {len(JDS)} JDs, {len(labels)} resumes (incl. edge cases) to {OUT}")


if __name__ == "__main__":
    main()
