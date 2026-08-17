"""Tests for deterministic role-family detection and its guidance block
(app.services.role_archetype). Pure functions — no AI, no DB."""
from app.services.role_archetype import archetype_block, detect_archetype


def test_detects_engineering_from_title():
    a = detect_archetype("Senior Backend Software Engineer", "Build APIs in Python.")
    assert a["key"] == "software_engineering"
    assert "built" in a["evidence_guidance"].lower()


def test_detects_sales_and_expects_quantification():
    a = detect_archetype("Inside Sales Executive",
                         "Own a territory, hit quota, manage pipeline in the CRM.")
    assert a["key"] == "sales"
    # Sales is the family where absent numbers really are a gap.
    assert "quota" in a["quantification"].lower()
    assert "expected to be quantified" in a["evidence_guidance"]


def test_detects_support_family():
    a = detect_archetype("Application Support Engineer (L2)",
                         "Handle incident tickets, ITIL process, night shift.")
    assert a["key"] == "it_support"


def test_detects_data_family():
    a = detect_archetype("Data Analyst", "Build dashboards in Power BI, write SQL.")
    assert a["key"] == "data_analytics"


def test_title_outweighs_incidental_body_mentions():
    # A QA role whose JD happens to mention developers and Python must not be
    # classified as software engineering — the title is the actual job.
    a = detect_archetype(
        "QA Automation Engineer",
        "Work with developers writing Python services; own Selenium test suites.",
    )
    assert a["key"] == "qa_testing"


def test_unknown_role_falls_back_to_generic_not_a_wrong_guess():
    a = detect_archetype("Lighthouse Keeper", "Maintain the lighthouse.")
    assert a["key"] == "generic"
    assert a["label"] == "General / cross-functional"


def test_low_confidence_single_keyword_does_not_pick_a_family():
    # One weak incidental body keyword shouldn't confidently label the role.
    a = detect_archetype("Office Coordinator", "Occasional travel required.")
    assert a["key"] == "generic"


def test_essential_skills_contribute_to_detection():
    a = detect_archetype("Engineer", "", ["Kubernetes", "Terraform", "CI/CD"])
    assert a["key"] == "devops_infrastructure"


def test_archetype_block_carries_lens_not_extra_criteria():
    block = archetype_block(detect_archetype("Data Analyst", "SQL and dashboards"))
    assert "ROLE FAMILY" in block
    assert "trap to avoid" in block
    # It must be explicit that this doesn't add criteria or move scores.
    assert "not as extra criteria" in block
    assert "approved scorecard is still the only thing being scored" in block


def test_archetype_block_empty_for_empty_archetype():
    assert archetype_block({}) == ""


def test_every_archetype_has_all_guidance_fields():
    # A family missing a field would silently render a broken prompt block.
    titles = [
        "Software Engineer", "Data Analyst", "DevOps Engineer", "QA Engineer",
        "Service Desk Analyst", "Sales Executive", "Customer Success Manager",
        "Digital Marketing Manager", "Financial Analyst", "Talent Acquisition Specialist",
        "Product Manager", "UX Designer", "Operations Manager", "Lighthouse Keeper",
    ]
    for title in titles:
        a = detect_archetype(title)
        for field in ("label", "evidence_guidance", "quantification",
                      "false_signal", "depth_probe"):
            assert a.get(field), f"{title} ({a['key']}) missing {field}"
        assert archetype_block(a)
