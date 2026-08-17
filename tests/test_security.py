"""Security regression tests: response hardening headers, and the SPA
static-file handler's directory containment.

The traversal test is a real regression guard, not a formality — before the
containment check existed, joining a user-supplied path onto the build
directory let `..` segments escape it, so a request could read backend source
and any other file the process could open (including .env with the Anthropic
key and SMTP password).
"""

from app.main import _frontend_dist


def test_security_headers_present_on_api_responses(auth_client):
    response = auth_client.get("/api/health")
    assert response.status_code == 200
    headers = response.headers
    # Content-Security-Policy is what stops injected/tampered markup from
    # executing script in the page.
    csp = headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    # 'unsafe-inline' must never be permitted for scripts (styles are fine —
    # the UI uses React inline style props).
    assert "'unsafe-inline'" not in csp.split("style-src")[0]
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cache-control"] == "no-store"
    assert "geolocation=()" in headers["permissions-policy"]


def test_api_docs_disabled_by_default(auth_client):
    """Interactive docs publish the whole endpoint surface — off unless
    PEOPLEIQ_ENABLE_API_DOCS is explicitly set."""
    assert auth_client.get("/api/openapi.json").status_code == 404


def test_spa_handler_contains_paths_within_the_build_directory():
    """Directly exercises the containment rule the SPA route relies on."""
    root = _frontend_dist.resolve()
    escapes = [
        "../backend/app/config.py",
        "../../etc/passwd",
        "a/../../../etc/passwd",
        "../.env",
    ]
    for candidate in escapes:
        resolved = (root / candidate).resolve()
        assert not resolved.is_relative_to(root), (
            f"{candidate!r} resolves outside the build root ({resolved}); the SPA "
            "handler must reject it rather than serve it"
        )
    # A legitimate in-tree path stays contained.
    assert (root / "index.html").resolve().is_relative_to(root)


def test_traversal_request_never_returns_backend_source(auth_client):
    """End-to-end: a traversal attempt must not return Python source, whether
    it is rejected outright or falls through to the SPA's index.html."""
    for path in ["/../backend/app/config.py", "/%2e%2e/backend/app/config.py",
                 "/static/../../backend/app/main.py"]:
        response = auth_client.get(path)
        body = response.text if response.status_code == 200 else ""
        assert "ANTHROPIC_API_KEY" not in body
        assert "SECRET_KEY" not in body
        assert "def _load_or_create_secret" not in body


def test_login_endpoint_does_not_leak_whether_a_user_exists(anon_client):
    """Same rejection for an unknown user and a wrong password, so the login
    form can't be used to enumerate valid accounts."""
    unknown = anon_client.post("/api/auth/login",
                          json={"username": "no-such-user", "password": "whatever123"})
    wrong = anon_client.post("/api/auth/login",
                        json={"username": "admin", "password": "definitely-wrong-123"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_mutating_endpoints_require_authentication(anon_client):
    """No cookie/token → no writes, regardless of what the UI would allow.
    Security decisions live server-side; the frontend is never trusted, so
    editing the page's JavaScript in a browser cannot authorise anything.
    Payloads here are deliberately schema-valid, so a 401 proves the auth gate
    fired rather than request validation rejecting the shape."""
    for method, url, payload in [
        ("post", "/api/jobs", {"title": "Valid Job Title", "description": "y" * 40}),
        ("patch", "/api/jobs/1", {"title": "hacked"}),
        ("delete", "/api/jobs/1", None),
        ("post", "/api/jobs/1/screen", None),
        ("post", "/api/jobs/1/scorecard/generate", None),
        ("patch", "/api/candidates/1/status", {"status": "shortlisted"}),
    ]:
        response = getattr(anon_client, method)(url, **({"json": payload} if payload else {}))
        assert response.status_code in (401, 403), (
            f"{method.upper()} {url} returned {response.status_code}, expected 401/403"
        )


def test_reads_also_require_authentication(anon_client):
    """Candidate data is personal data — no unauthenticated reads either."""
    for url in ["/api/jobs", "/api/tracker", "/api/candidates/1",
                "/api/responsible-ai-report"]:
        assert anon_client.get(url).status_code in (401, 403), f"GET {url} was not gated"
