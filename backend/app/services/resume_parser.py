"""Stage 2 — Resume ingestion & structured extraction.

- Extracts raw text from PDF (pypdf), DOCX (python-docx) and TXT files.
- Flags unreadable / incomplete documents instead of failing the batch.
- Extracts contact details deterministically (regex) so the identity block
  never depends on the LLM, then optionally enriches the structured profile
  (employers, roles, dates, skills, qualifications, projects) via Claude.
- Duplicate detection: exact file hash + normalised email/phone match.
"""
from __future__ import annotations

import io
import logging
import re

from . import llm

logger = logging.getLogger("peopleiq.parser")

MIN_READABLE_CHARS = 120  # below this we flag the document as unreadable/incomplete

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_CANDIDATE_RE = re.compile(r"\+?\d[\d\s\-.()]{8,18}\d")


class _PhoneMatcher:
    """Regex-like facade: matches digit runs that look like real phone numbers
    (10-13 digits once separators are stripped)."""

    def search(self, text: str):
        for match in _PHONE_CANDIDATE_RE.finditer(text):
            digits = re.sub(r"\D", "", match.group(0))
            if 10 <= len(digits) <= 13:
                return match
        return None


PHONE_RE = _PhoneMatcher()


class ParseResult(dict):
    """text, readable(bool), error(str)"""


def extract_text(filename: str, raw: bytes) -> ParseResult:
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    text, error = "", ""
    try:
        if ext == ".pdf":
            text = _extract_pdf(raw)
        elif ext == ".docx":
            text = _extract_docx(raw)
        elif ext == ".doc":
            # Legacy binary .doc — attempt naive text salvage; flag if hopeless.
            text = _extract_doc_binary(raw)
        elif ext == ".txt":
            text = raw.decode("utf-8", errors="replace")
        else:
            error = f"Unsupported file type: {ext or 'unknown'}"
    except Exception as exc:  # noqa: BLE001 — one bad file must not kill a batch
        error = f"Extraction failed: {exc}"
        logger.warning("Failed to extract %s: %s", filename, exc)

    text = _normalise(text)
    readable = not error and len(text) >= MIN_READABLE_CHARS
    if not error and not readable:
        error = (
            f"Document appears unreadable or incomplete "
            f"({len(text)} characters extracted; likely a scanned image or corrupt file)"
        )
    return ParseResult(text=text, readable=readable, error=error)


def _extract_pdf(raw: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ValueError("PDF is password protected") from exc
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _extract_docx(raw: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(raw))
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def _extract_doc_binary(raw: bytes) -> str:
    """Best-effort salvage of legacy .doc: pull printable ASCII/UTF-8 runs."""
    candidate = raw.decode("latin-1", errors="ignore")
    runs = re.findall(r"[\x20-\x7E\n\r\t]{20,}", candidate)
    return "\n".join(runs)


def _normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Contact extraction (deterministic — never LLM-dependent)
# ---------------------------------------------------------------------------
def extract_contact(text: str) -> dict:
    email_match = EMAIL_RE.search(text)
    phone_match = PHONE_RE.search(text)
    name = _guess_name(text)
    return {
        "full_name": name,
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0).strip() if phone_match else "",
    }


_NAME_STOPWORDS = {
    "resume", "curriculum", "vitae", "cv", "profile", "summary", "objective",
    "career", "professional", "contact", "email", "phone", "address",
}


def _guess_name(text: str) -> str:
    for line in text.splitlines()[:8]:
        line = line.strip().strip("|,:;")
        if not line or EMAIL_RE.search(line) or PHONE_RE.search(line):
            continue
        words = line.split()
        if 1 < len(words) <= 5 and all(w[0].isalpha() for w in words if w):
            lowered = {w.lower().strip(".") for w in words}
            if not lowered & _NAME_STOPWORDS:
                return line.title() if line.isupper() else line
    return ""


def normalise_email(email: str) -> str:
    return email.strip().lower()


def normalise_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)[-10:]  # last 10 digits — country-code tolerant


# ---------------------------------------------------------------------------
# Structured profile extraction (LLM with schema; regex fallback)
# ---------------------------------------------------------------------------
PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "full_name": {"type": "string"},
        "current_role": {"type": "string"},
        "current_employer": {"type": "string"},
        "location_city": {"type": "string"},
        "total_experience_years": {"type": "number"},
        "employers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "employer": {"type": "string"},
                    "role": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                },
                "required": ["employer", "role", "start", "end"],
                "additionalProperties": False,
            },
        },
        "skills": {"type": "array", "items": {"type": "string"}},
        "qualifications": {"type": "array", "items": {"type": "string"}},
        "certifications": {"type": "array", "items": {"type": "string"}},
        "projects": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "full_name", "current_role", "current_employer", "location_city",
        "total_experience_years", "employers", "skills", "qualifications",
        "certifications", "projects",
    ],
    "additionalProperties": False,
}

_PROFILE_SYSTEM = """You are a precise resume information extractor for a recruitment platform.
Extract ONLY facts stated in the resume text. Never invent employers, dates, skills or
qualifications that are not present. If a field is unknown, use an empty string, empty
array, or 0. Dates should be returned as they appear in the resume (e.g. "Mar 2021").
Do not extract or mention age, gender, marital status, religion, caste, nationality,
health information, or photographs."""


def extract_profile(text: str) -> dict:
    """LLM-based structured extraction with deterministic fallback."""
    try:
        profile = llm.structured_call(
            system=_PROFILE_SYSTEM,
            user_content=f"Resume text:\n<resume>\n{text[:30000]}\n</resume>",
            schema=PROFILE_SCHEMA,
            max_tokens=4000,
        )
        profile["extraction_engine"] = "llm"
        return profile
    except llm.LLMUnavailable:
        return _fallback_profile(text)


_SKILL_SECTION_RE = re.compile(
    r"(?:technical\s+)?skills?\s*[:\-\n](.{0,600})", re.IGNORECASE | re.DOTALL
)
_YEARS_RE = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*years?", re.IGNORECASE)


def _fallback_profile(text: str) -> dict:
    skills: list[str] = []
    match = _SKILL_SECTION_RE.search(text)
    if match:
        chunk = match.group(1).split("\n\n")[0]
        skills = [
            s.strip(" •-\t")
            for s in re.split(r"[,;•|\n]", chunk)
            if 1 < len(s.strip(" •-\t")) < 40
        ][:30]
    years_match = _YEARS_RE.search(text)
    return {
        "full_name": _guess_name(text),
        "current_role": "",
        "current_employer": "",
        "location_city": "",
        "total_experience_years": float(years_match.group(1)) if years_match else 0.0,
        "employers": [],
        "skills": skills,
        "qualifications": [],
        "certifications": [],
        "projects": [],
        "extraction_engine": "deterministic",
    }
