"""Role-family (archetype) detection and per-family evidence guidance.

Why this exists — the accuracy gap it closes:

Everything else in this engine judges "does the resume evidence this
criterion," but *what counts as real evidence differs fundamentally by role
family*. A recruiter screening a sales role knows to look for quota
attainment, deal sizes and cycle lengths; one screening a backend engineer
looks for systems built, scale handled and ownership; one screening support
looks for ticket volume, SLAs and escalation handling. Judging all three
with the same generic "did they demonstrate the capability" lens is exactly
how a screener produces plausible-but-wrong scores.

The hiring-research literature says the same thing two ways: assessment
mapped to competencies derived from an actual job analysis carries far
higher validity than generic assessment, and screening scores should be
calibrated per role family rather than on one universal scale.

So each archetype here carries four things a domain-experienced recruiter
would know without being told:
  - `evidence_guidance`  — what genuinely strong evidence looks like here
  - `quantification`     — which numbers actually matter for this family
                           (and are worth asking for if absent)
  - `false_signal`       — what LOOKS impressive in this family but isn't
                           real evidence; the trap a naive screener falls for
  - `depth_probe`        — what separates someone who did the work from
                           someone who was merely present for it

Detection is deterministic (weighted keyword scoring over title + skills +
JD text), so it is unit-testable and cannot vary run to run. Everything is
advisory context injected into prompts — it never directly moves a score,
so a misdetected archetype degrades gracefully into slightly-off guidance
rather than a wrong number.
"""
from __future__ import annotations

import re

# Each archetype: (keyword -> weight). Title matches are weighted far higher
# than description matches at scoring time, since a JD body mentions many
# adjacent technologies while the title names the actual job.
_ARCHETYPES: dict[str, dict] = {
    "software_engineering": {
        "label": "Software engineering",
        "keywords": {
            "software engineer": 5, "developer": 4, "backend": 4, "frontend": 4,
            "full stack": 4, "fullstack": 4, "programmer": 4, "sde": 4,
            "web developer": 4, "mobile developer": 4, "android": 3, "ios": 3,
            "api": 2, "microservices": 2, "java": 2, "python": 2, "node": 2,
            "react": 2, "django": 2, "spring boot": 2, "code review": 2,
        },
        "evidence_guidance": (
            "Strong evidence is what they actually BUILT and OWNED: named systems, "
            "services or features they were personally responsible for, the technical "
            "problem being solved, and what happened after it shipped. A resume that "
            "describes systems, trade-offs and outcomes is evidencing engineering "
            "capability even when it never names the exact framework in the criterion."
        ),
        "quantification": (
            "scale and reliability numbers — request/user volume, data size, latency "
            "or uptime improvements, deployment frequency, incident/bug reduction"
        ),
        "false_signal": (
            "a long technology list with no system, project or outcome attached to any "
            "of it. Naming twenty technologies is not evidence of using twenty "
            "technologies — a candidate who names four and shows what they built with "
            "them is the stronger technical signal."
        ),
        "depth_probe": (
            "whether they made design decisions and understood trade-offs, versus "
            "implementing tickets someone else designed"
        ),
    },
    "data_analytics": {
        "label": "Data / analytics",
        "keywords": {
            "data analyst": 5, "data scientist": 5, "analytics": 4, "bi ": 4,
            "business intelligence": 4, "data engineer": 5, "reporting analyst": 4,
            "machine learning": 4, "ml engineer": 4, "statistician": 4,
            "power bi": 3, "tableau": 3, "looker": 3, "dashboard": 3,
            "sql": 2, "etl": 3, "data warehouse": 3, "pandas": 2,
        },
        "evidence_guidance": (
            "Strong evidence is the DECISION or OUTCOME their analysis drove, not the "
            "tool they opened. 'Built a dashboard' is weak; 'built the churn dashboard "
            "the retention team used to prioritise outreach' is real. Look for the chain "
            "from data to insight to action, and for whether they owned data correctness."
        ),
        "quantification": (
            "data volume/complexity, number of sources integrated, decision or revenue "
            "impact of the analysis, report/pipeline reliability, query-time improvements"
        ),
        "false_signal": (
            "tool-name accumulation (Power BI, Tableau, Looker, SQL, Python all listed) "
            "with no analysis question, stakeholder or decision attached. Also treat "
            "'created N reports' as volume, not impact — a hundred unused reports is "
            "weaker evidence than one that changed a decision."
        ),
        "depth_probe": (
            "whether they defined the analytical question and validated the data "
            "themselves, versus running queries someone else specified"
        ),
    },
    "devops_infrastructure": {
        "label": "DevOps / infrastructure / SRE",
        "keywords": {
            "devops": 5, "sre": 5, "site reliability": 5, "infrastructure": 4,
            "platform engineer": 5, "cloud engineer": 4, "systems engineer": 4,
            "kubernetes": 3, "terraform": 3, "ci/cd": 3, "aws": 2, "azure": 2,
            "gcp": 2, "docker": 2, "linux administrator": 4, "monitoring": 2,
        },
        "evidence_guidance": (
            "Strong evidence is production ownership: what they ran, what broke, what "
            "they did about it, and what they automated so it stopped breaking. "
            "On-call experience, incident response and migration ownership are the "
            "real signals — far more than a list of cloud services."
        ),
        "quantification": (
            "uptime/SLA figures, incident count or MTTR reduction, deployment frequency, "
            "infrastructure cost savings, scale of environment (nodes, services, regions)"
        ),
        "false_signal": (
            "a cloud-services checklist (EC2, S3, Lambda, EKS...) with no environment "
            "size, no production responsibility and no incident they actually handled. "
            "Having touched a service in a tutorial is not having operated it."
        ),
        "depth_probe": (
            "whether they were accountable when production broke, versus supporting "
            "someone else who was"
        ),
    },
    "qa_testing": {
        "label": "QA / testing",
        "keywords": {
            "qa ": 5, "quality assurance": 5, "test engineer": 5, "sdet": 5,
            "automation tester": 5, "manual tester": 5, "testing": 3,
            "selenium": 3, "cypress": 3, "test automation": 4, "qa analyst": 5,
        },
        "evidence_guidance": (
            "Strong evidence is what their testing PREVENTED and how they thought about "
            "risk — coverage they built, defects caught before release, test strategy "
            "they designed. Look for judgement about what is worth testing, not just "
            "tool familiarity."
        ),
        "quantification": (
            "coverage percentages, defect-escape rate, regression-suite size and runtime, "
            "release cadence they supported, automation ratio achieved"
        ),
        "false_signal": (
            "'wrote test cases' with no scope, no product context and no outcome. Also "
            "beware equating tool lists with test-design skill — the scarce skill is "
            "knowing what to test, not driving Selenium."
        ),
        "depth_probe": (
            "whether they designed the test strategy and pushed back on risk, versus "
            "executing a test plan handed to them"
        ),
    },
    "it_support": {
        "label": "IT support / service desk / application support",
        "keywords": {
            "support engineer": 5, "service desk": 5, "help desk": 5, "helpdesk": 5,
            "technical support": 5, "application support": 5, "production support": 5,
            "desktop support": 5, "l1": 3, "l2": 3, "l3": 3, "itil": 3,
            "incident management": 3, "ticket": 2, "troubleshooting": 3,
        },
        "evidence_guidance": (
            "Strong evidence is the difficulty and independence of what they resolved: "
            "the systems they supported, the escalation tier they held, and problems "
            "they diagnosed rather than routed. Shift coverage and user-facing "
            "communication are genuine parts of the job here, not extras."
        ),
        "quantification": (
            "ticket volume handled, SLA/first-response compliance, resolution rate at "
            "their tier, escalation rate, CSAT, size of user base supported"
        ),
        "false_signal": (
            "generic 'resolved user issues' with no system named and no tier stated. "
            "Also don't confuse long tenure at a support desk with growing capability — "
            "look for whether the problems they handled actually got harder."
        ),
        "depth_probe": (
            "whether they root-caused issues independently, versus following a runbook "
            "and escalating anything unfamiliar"
        ),
    },
    "sales": {
        "label": "Sales / business development",
        "keywords": {
            "sales": 5, "business development": 5, "account executive": 5,
            "account manager": 4, "inside sales": 5, "sales development": 5,
            "sdr": 5, "bdr": 5, "quota": 3, "pipeline": 2, "crm": 2,
            "lead generation": 3, "revenue": 2, "territory": 3, "closing": 2,
        },
        "evidence_guidance": (
            "Strong evidence is quantified attainment against a real target, plus the "
            "SHAPE of what they sold: deal size, sales-cycle length, who they sold to "
            "(SMB vs enterprise, technical vs business buyer), and whether they sourced "
            "or only closed. A sales resume without numbers is a serious gap here — "
            "unlike most families, this one is expected to be quantified."
        ),
        "quantification": (
            "quota attainment percentage, revenue/ACV closed, deal count and average "
            "size, sales-cycle length, pipeline generated, win rate, ranking on team"
        ),
        "false_signal": (
            "activity metrics dressed as results — 'made 100 calls a day', 'managed a "
            "large pipeline' — with no attainment figure. Also a percentage with no "
            "base ('achieved 150%') is only half a number; the quota size matters as "
            "much as the percentage."
        ),
        "depth_probe": (
            "whether they owned the number themselves, versus supporting a closer who "
            "did"
        ),
    },
    "customer_success": {
        "label": "Customer success / account management",
        "keywords": {
            "customer success": 5, "csm": 5, "client servicing": 4,
            "account management": 4, "relationship manager": 4, "onboarding": 3,
            "retention": 3, "churn": 3, "client success": 5, "customer experience": 4,
        },
        "evidence_guidance": (
            "Strong evidence is retention and expansion outcomes on a named book of "
            "business: how many accounts, what size, what they were accountable for "
            "(renewals, adoption, escalations). Look for evidence of handling an "
            "unhappy customer, not just describing a smooth process."
        ),
        "quantification": (
            "book size (accounts and revenue), renewal/retention rate, churn reduction, "
            "expansion/upsell revenue, NPS or CSAT, adoption metrics"
        ),
        "false_signal": (
            "warm relationship language ('built strong client relationships', 'ensured "
            "customer satisfaction') with no book size, no renewal figure and no "
            "specific escalation handled."
        ),
        "depth_probe": (
            "whether they were accountable for the renewal decision, versus a "
            "coordinator inside someone else's account plan"
        ),
    },
    "marketing": {
        "label": "Marketing",
        "keywords": {
            "marketing": 5, "seo": 4, "content marketing": 5, "digital marketing": 5,
            "brand": 3, "campaign": 3, "social media": 4, "growth marketing": 5,
            "performance marketing": 5, "demand generation": 5, "google ads": 3,
            "copywriter": 4, "communications": 3,
        },
        "evidence_guidance": (
            "Strong evidence is a campaign or channel they OWNED end to end plus its "
            "measured result, and the budget/scale they worked at. Look for whether "
            "they can connect activity to a funnel outcome rather than to output volume."
        ),
        "quantification": (
            "budget managed, traffic/lead/conversion lift, CAC or ROAS, pipeline "
            "contribution, audience growth, campaign reach"
        ),
        "false_signal": (
            "output counting — 'wrote 50 blog posts', 'managed social media accounts' — "
            "with no funnel or business metric attached. Also treat vanity metrics "
            "(impressions, followers) as weaker than conversion or pipeline evidence."
        ),
        "depth_probe": (
            "whether they set the strategy and owned the metric, versus executing "
            "someone else's campaign brief"
        ),
    },
    "finance_accounting": {
        "label": "Finance / accounting",
        "keywords": {
            "accountant": 5, "accounting": 5, "finance": 4, "financial analyst": 5,
            "audit": 4, "taxation": 4, "accounts payable": 4, "accounts receivable": 4,
            "controller": 4, "bookkeeping": 4, "gst": 3, "reconciliation": 3,
            "financial reporting": 4, "fp&a": 5,
        },
        "evidence_guidance": (
            "Strong evidence is ownership of a specific close, filing, audit or "
            "reporting cycle, at a stated scale, with accuracy/compliance implied by "
            "the responsibility level. Systems experience (ERP, specific accounting "
            "software) matters, but process ownership matters more."
        ),
        "quantification": (
            "transaction/invoice volume, size of books or entity revenue, close-cycle "
            "days reduced, audit findings avoided, number of entities or jurisdictions"
        ),
        "false_signal": (
            "listing accounting activities generically ('prepared financial statements', "
            "'handled reconciliations') with no scale, entity size or cycle ownership. "
            "The difference between assisting with a close and owning one is the whole "
            "signal."
        ),
        "depth_probe": (
            "whether they owned and signed off on the cycle, versus preparing inputs "
            "for someone who did"
        ),
    },
    "hr_recruiting": {
        "label": "HR / recruiting / talent",
        "keywords": {
            "recruiter": 5, "recruitment": 5, "talent acquisition": 5,
            "human resources": 5, "hr ": 4, "hrbp": 5, "people operations": 5,
            "sourcing": 3, "onboarding": 2, "payroll": 3, "employee relations": 4,
            "hr generalist": 5,
        },
        "evidence_guidance": (
            "Strong evidence is the hiring or people outcome they delivered at a stated "
            "volume and difficulty: roles closed, the seniority/scarcity of those roles, "
            "and the stakeholders they managed. For HR generalist work, look for "
            "specific processes they owned rather than a list of HR functions."
        ),
        "quantification": (
            "positions closed, time-to-fill, offer-acceptance rate, sourcing conversion, "
            "headcount or employee population supported, attrition change"
        ),
        "false_signal": (
            "naming the full HR function list (recruitment, onboarding, payroll, "
            "engagement, exit) with no volume, no difficulty and no outcome — a very "
            "common resume shape that says nothing about capability."
        ),
        "depth_probe": (
            "whether they owned the mandate and the stakeholder relationship, versus "
            "coordinating scheduling and paperwork"
        ),
    },
    "product_project_management": {
        "label": "Product / project / program management",
        "keywords": {
            "product manager": 5, "product owner": 5, "project manager": 5,
            "program manager": 5, "scrum master": 5, "delivery manager": 5,
            "business analyst": 4, "pmo": 4, "agile": 2, "roadmap": 3,
            "stakeholder management": 3, "pmp": 3,
        },
        "evidence_guidance": (
            "Strong evidence is a shipped outcome they were accountable for, plus the "
            "scope they coordinated: team size, number of stakeholders/teams, budget or "
            "timeline. Look for decisions they made under ambiguity or trade-off, not "
            "just ceremonies they ran."
        ),
        "quantification": (
            "team/stakeholder count, budget or project value, timeline and whether it "
            "was met, adoption or business metric of what shipped, scope of programme"
        ),
        "false_signal": (
            "process vocabulary as a substitute for outcomes — 'ran daily standups', "
            "'maintained the backlog', 'followed Agile methodology' — with nothing "
            "shipped and no decision owned."
        ),
        "depth_probe": (
            "whether they made prioritisation/trade-off calls, versus administering a "
            "plan someone else set"
        ),
    },
    "design": {
        "label": "Design / UX",
        "keywords": {
            "designer": 5, "ux": 5, "ui ": 4, "user experience": 5,
            "graphic design": 5, "product design": 5, "visual design": 5,
            "figma": 3, "wireframe": 3, "prototyping": 3, "user research": 4,
        },
        "evidence_guidance": (
            "Strong evidence is a design problem they solved and the reasoning behind "
            "it — user need, constraint, what they changed, what improved. Look for "
            "evidence of research and iteration, and for shipped work rather than "
            "concept pieces."
        ),
        "quantification": (
            "usability or conversion improvement, users affected, research sessions run, "
            "design-system scope, shipped surfaces owned"
        ),
        "false_signal": (
            "tool proficiency (Figma, Sketch, Adobe suite) plus aesthetic adjectives, "
            "with no problem statement, no user and no measured change."
        ),
        "depth_probe": (
            "whether they owned the problem definition and validated with users, versus "
            "producing screens to a given spec"
        ),
    },
    "operations": {
        "label": "Operations / process",
        "keywords": {
            "operations": 5, "process improvement": 4, "supply chain": 5,
            "logistics": 5, "procurement": 4, "vendor management": 4,
            "operations manager": 5, "back office": 4, "bpo": 4,
            "six sigma": 3, "lean": 3, "sla": 2, "process": 2,
        },
        "evidence_guidance": (
            "Strong evidence is a process they ran or improved, at a stated throughput, "
            "with a measured efficiency or quality result. Look for ownership of an "
            "outcome (cost, turnaround, error rate) rather than a description of daily "
            "activity."
        ),
        "quantification": (
            "throughput/volume processed, turnaround-time reduction, cost savings, error "
            "or defect-rate reduction, headcount or vendor count managed, SLA attainment"
        ),
        "false_signal": (
            "activity narration — 'handled daily operations', 'coordinated with "
            "vendors' — with no volume, no metric and no improvement owned."
        ),
        "depth_probe": (
            "whether they redesigned the process and owned its numbers, versus "
            "executing it as defined"
        ),
    },
}

_GENERIC = {
    "label": "General / cross-functional",
    "evidence_guidance": (
        "Judge evidence on what the work actually was: the responsibility held, the "
        "problem addressed, and the result. Since this role doesn't map cleanly to one "
        "well-known family, lean on the scorecard criteria and the JD's own framing "
        "rather than assumptions about what this kind of role 'usually' looks like."
    ),
    "quantification": (
        "whatever the role's own outputs are measured in — scale handled, outcome "
        "achieved, scope owned"
    ),
    "false_signal": (
        "responsibility lists with no outcome attached, and skill/tool inventories with "
        "no context showing the skill was actually applied."
    ),
    "depth_probe": (
        "whether they owned the outcome, versus contributing to someone else's"
    ),
}

# A detected archetype needs a minimum score before we trust it — otherwise a
# single incidental keyword in a long JD would pick a family confidently and
# feed the model misleading domain guidance.
_MIN_CONFIDENCE = 5
_TITLE_MULTIPLIER = 3


def _normalise(text: str) -> str:
    # Keep a trailing space so keywords written with one (e.g. "hr ", "bi ")
    # can match a word at the very end of the text too.
    return re.sub(r"[^a-z0-9+#&/.]+", " ", (text or "").lower()) + " "


def detect_archetype(title: str, description: str = "",
                     essential_skills: list[str] | None = None) -> dict:
    """Deterministically pick the best-matching role family. Returns the
    archetype dict plus `key` and `confidence`; falls back to a generic
    archetype when nothing scores convincingly, so a niche or oddly-titled
    role never gets confidently mis-labelled."""
    title_text = _normalise(title)
    body_text = _normalise(" ".join([description or ""] + list(essential_skills or [])))

    scores: dict[str, int] = {}
    for key, archetype in _ARCHETYPES.items():
        score = 0
        for keyword, weight in archetype["keywords"].items():
            if keyword in title_text:
                score += weight * _TITLE_MULTIPLIER
            elif keyword in body_text:
                score += weight
        if score:
            scores[key] = score

    if not scores:
        return {**_GENERIC, "key": "generic", "confidence": 0}
    best_key, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score < _MIN_CONFIDENCE:
        return {**_GENERIC, "key": "generic", "confidence": best_score}
    archetype = {k: v for k, v in _ARCHETYPES[best_key].items() if k != "keywords"}
    return {**archetype, "key": best_key, "confidence": best_score}


def archetype_block(archetype: dict) -> str:
    """Renders archetype guidance as prompt text. Advisory context only — it
    shapes how evidence is READ, and never directly moves a score, so a
    misdetection degrades into slightly-off guidance rather than a wrong
    number."""
    if not archetype:
        return ""
    return (
        f"ROLE FAMILY: {archetype['label']}. What counts as real evidence differs by "
        "role family, and this is what an experienced recruiter who specialises in this "
        "family would already know:\n"
        f"- What strong evidence looks like here: {archetype['evidence_guidance']}\n"
        f"- Numbers that actually matter for this family: {archetype['quantification']}. "
        "If the resume shows work in this family but omits these numbers entirely, that "
        "is a specific thing to ask for on the call (missing_information / "
        "verification_questions) — not automatically a lower score, unless the guidance "
        "above says this family is normally expected to be quantified.\n"
        f"- The trap to avoid in this family: {archetype['false_signal']}\n"
        f"- What separates real depth from surface involvement here: "
        f"{archetype['depth_probe']}. Weigh this when choosing between confirmed and "
        "partial/needs_verification.\n"
        "Apply this as a lens for reading evidence, not as extra criteria — the approved "
        "scorecard is still the only thing being scored."
    )
