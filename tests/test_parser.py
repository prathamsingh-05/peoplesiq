"""Resume text extraction, contact extraction and unreadable-file handling."""
import io

import docx as docx_lib
from app.services import resume_parser


def _docx_bytes(text: str) -> bytes:
    document = docx_lib.Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


RESUME = """Priya Nair
Email: priya.nair@example.com | Phone: +91 98200 45678

PROFESSIONAL SUMMARY
SOC analyst with 4 years of experience in Splunk and incident response.

SKILLS
Splunk, Sentinel, Python, MITRE ATT&CK
"""


def test_docx_extraction_and_contact():
    result = resume_parser.extract_text("resume.docx", _docx_bytes(RESUME))
    assert result["readable"], result["error"]
    assert "Splunk" in result["text"]
    contact = resume_parser.extract_contact(result["text"])
    assert contact["email"] == "priya.nair@example.com"
    assert contact["full_name"] == "Priya Nair"
    assert "98200" in contact["phone"].replace(" ", "")


def test_corrupt_file_flagged_unreadable():
    result = resume_parser.extract_text("scan.pdf", b"%PDF-1.4 garbage \x00\x01" * 2)
    assert not result["readable"]
    assert result["error"]


def test_unsupported_extension_rejected():
    result = resume_parser.extract_text("resume.exe", b"MZ....")
    assert not result["readable"]
    assert "Unsupported" in result["error"]


def test_fallback_profile_extracts_skills_offline():
    profile = resume_parser._fallback_profile(RESUME)
    assert profile["extraction_engine"] == "deterministic"
    assert any("Splunk" in s for s in profile["skills"])
