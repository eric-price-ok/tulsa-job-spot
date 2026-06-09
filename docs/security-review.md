# Security Review

**Date:** 2026-06-09  
**Scope:** Full codebase — routers, templates, middleware, config, workers  
**Framework:** OWASP Top 10 (2021) + general web security best practices

---

## Executive Summary

The application has a strong architectural foundation: SQLAlchemy ORM prevents SQL injection, OAuth delegation eliminates password-related vulnerabilities, and session cookies are correctly configured for production. However, there is one **Critical** XSS vulnerability that must be fixed before users post live job listings, and several **Medium** gaps — CSRF protection, security headers, URL validation, and audit logging — that should be addressed in the near term.

---

## Findings

### 1. Stored XSS — Job Description Rendered with `|safe`
**Severity:** Critical  
**OWASP:** A03:2021 — Injection  

The job description is rendered in the template with Jinja2's `|safe` filter, which disables auto-escaping:

```jinja2
{# app/templates/jobs/detail.html #}
{{ job.job_description | safe }}
```

A job poster can submit a description containing `<script>` tags or event-handler attributes. Once a moderator approves the listing, the payload executes in every visitor's browser — allowing session cookie theft, phishing redirects, or page defacement.

`nh3` is already in `requirements.txt` for exactly this purpose but is not imported or called anywhere in the codebase.

**Fix:** Sanitize on write in `app/routers/jobs.py` before storing to the database:
```python
import nh3
job.job_description = nh3.clean(job_description.strip())
```
Then remove the `|safe` filter from the template and let Jinja2 auto-escape the stored value. Sanitizing on write (rather than on render) means the safe value is in the database and future template changes can't accidentally re-introduce the vulnerability.

---

### 2. Unvalidated URLs Rendered in `href` Attributes
**Severity:** High  
**OWASP:** A03:2021 — Injection  

Three user-supplied URL fields are stored without scheme validation and rendered directly in `href` attributes:

| Field | Template | Router |
|---|---|---|
| `job.posting_url` | `app/templates/jobs/detail.html` | `app/routers/jobs.py` |
| `company.website` | `app/templates/companies/profile.html` | `app/routers/companies.py` |
| `social.company_url` | `app/templates/companies/profile.html` | `app/models/company.py` |

A `javascript:` or `data:` URI in any of these fields executes arbitrary code when a user clicks the link. Only `http` and `https` schemes are legitimate.

**Fix:** Add a URL validator and call it on each field before storing:
```python
from urllib.parse import urlparse

def validate_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return None
        return url.strip()
    except Exception:
        return None
```

---

### 3. Open Redirect via Unvalidated `next` Parameter
**Severity:** Medium  
**OWASP:** A01:2021 — Broken Access Control  

In `app/routers/auth.py`, the `next` query parameter is stored in the session and used verbatim as a post-login redirect target:

```python
if next_url := request.query_params.get("next"):
    request.session["next"] = next_url
# ... after OAuth callback:
next_url = request.session.pop("next", "/")
return RedirectResponse(next_url, status_code=303)
```

An attacker sends a user to `/auth/login?next=https://attacker.com`. After OAuth completes, the user is redirected off-site. This is a classic phishing setup.

**Fix:** Reject any `next` value with a scheme or netloc (i.e., allow only relative paths):
```python
from urllib.parse import urlparse

def is_safe_next(url: str) -> bool:
    parsed = urlparse(url)
    return not parsed.scheme and not parsed.netloc

next_url = request.session.pop("next", "/")
if not is_safe_next(next_url):
    next_url = "/"
return RedirectResponse(next_url, status_code=303)
```

---

### 4. No CSRF Protection on State-Changing Endpoints
**Severity:** Medium  
**OWASP:** A01:2021 — Broken Access Control  

FastAPI has no built-in CSRF middleware. All POST endpoints that mutate state — job creation, company creation, approvals, rejections, role changes, user deactivation — are vulnerable to cross-site request forgery. A logged-in user visiting a malicious page could unknowingly trigger any of these actions.

The `same_site="lax"` cookie attribute provides partial mitigation: it blocks cross-site POST form submissions in modern browsers. However, it does not protect against top-level navigation-triggered requests and is not a substitute for explicit CSRF tokens.

**Fix:** Add the `starlette-csrf` package and wire it up in `app/main.py`. All forms then need a `{{ csrf_token }}` hidden field. This is a moderate effort change that touches every template — plan it as a dedicated task.

---

### 5. Missing Security Headers
**Severity:** Medium  
**OWASP:** A05:2021 — Security Misconfiguration  

The application sets no security response headers. Missing headers:

| Header | Risk Without It |
|---|---|
| `X-Content-Type-Options: nosniff` | MIME-type sniffing attacks |
| `X-Frame-Options: DENY` | Clickjacking |
| `Referrer-Policy: strict-origin-when-cross-origin` | Referrer leakage |
| `Content-Security-Policy` | XSS, data injection |
| `Strict-Transport-Security` | SSL stripping (production) |

**Fix:** Add a middleware function in `app/main.py`:
```python
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response
```

A Content-Security-Policy header requires more care since the app uses HTMX, Alpine.js, and inline styles — draft it separately to avoid breaking the UI.

---

### 6. Proxy Headers Trusted from All Hosts
**Severity:** Medium  
**OWASP:** A05:2021 — Security Misconfiguration  

`app/main.py` configures `ProxyHeadersMiddleware` to trust `X-Forwarded-For` and `X-Forwarded-Proto` from any host:

```python
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
```

Any client can spoof `X-Forwarded-For` to fake its IP address. If rate limiting or IP-based logging is added (both recommended below), this makes them trivially bypassable.

**Fix:** Restrict to the actual upstream proxy. In the Docker Compose setup, Caddy is the only upstream, and its container IP is in the Docker bridge network:
```python
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["caddy"])
```

---

### 7. No Application-Level Email Validation for `application_email`
**Severity:** Medium  
**OWASP:** A03:2021 — Injection  

When a job is posted with `application_method="email"`, the `application_email` field is accepted without format validation. `email-validator` is already in `requirements.txt`.

```python
# app/routers/jobs.py — current code
application_email: Optional[str] = Form(None)
# stored directly with no validation
```

An invalid or empty email stored here results in a broken `mailto:` link for job seekers, or potential injection if the email is later passed to an SMTP client.

**Fix:**
```python
from email_validator import validate_email, EmailNotValidError

if application_method == "email":
    if not application_email:
        # return form error
    try:
        application_email = validate_email(application_email.strip()).email
    except EmailNotValidError:
        # return form error
```

---

### 8. No Rate Limiting on Sensitive Endpoints
**Severity:** Medium  
**OWASP:** A07:2021 — Identification and Authentication Failures  

No endpoints have rate limiting. High-value targets:

- `/auth/callback/*` — OAuth callback (abuse could spam account creation)
- `/companies/request-role` — can flood the moderator queue
- `/companies/{id}/invite` — can spam invites to a company
- All moderator and admin action endpoints

**Fix:** Add `slowapi` (a thin wrapper around `limits` for Starlette/FastAPI) and apply `@limiter.limit("5/minute")` to the endpoints above.

---

### 9. No Audit Log for Admin and Moderator Actions
**Severity:** Medium  
**OWASP:** A09:2021 — Security Logging and Monitoring Failures  

Moderator and admin actions — company approvals, job approvals, role grants, user deactivation, moderator promotion — are applied to the database with no log entry recording who took the action and when.

Without an audit trail it is impossible to investigate disputes, detect a compromised moderator account, or demonstrate compliance.

**Fix:** A minimal approach is structured logging on each action:
```python
import logging
logger = logging.getLogger("audit")

logger.info(
    "company_approved company_id=%s moderator=%s",
    company.id, current_user.email
)
```

A more robust approach writes to a dedicated `audit_log` table. Either is acceptable; the key is that the record is immutable and includes actor, action, target, and timestamp.

---

### 10. Weak Default `SECRET_KEY`
**Severity:** Medium  
**OWASP:** A02:2021 — Cryptographic Failures  

`app/config.py` defaults to:
```python
SECRET_KEY: str = "dev-secret-change-me"
```

If a deployment skips setting this in `.env`, all session cookies are signed with a publicly known key — any attacker can forge sessions.

**Fix:** Add a startup validator that refuses to run in production with the default value:
```python
@property
def is_valid_secret(self) -> bool:
    return self.SECRET_KEY != "dev-secret-change-me" and len(self.SECRET_KEY) >= 32
```
And raise at startup if `is_production and not is_valid_secret`.

---

### 11. 30-Day Session Lifetime
**Severity:** Low  
**OWASP:** A07:2021 — Identification and Authentication Failures  

The session cookie `max_age` is set to 30 days (`app/main.py:35`). For a job board this is longer than necessary and increases the window of exposure if a device is lost or stolen.

**Fix:** Reduce to 7 days. If users find this inconvenient, a "remember me" checkbox can opt in to the longer lifetime rather than it being the default.

---

## What Is Working Well

- **SQL injection:** All database access uses SQLAlchemy ORM with parameterized queries. No raw SQL found.
- **Authentication:** OAuth delegation (Google, LinkedIn, etc.) eliminates password storage, reset flows, and credential stuffing risk entirely.
- **Session cookies:** `https_only=settings.is_production` and `same_site="lax"` are correctly set.
- **Access control structure:** `require_user`, `require_moderator`, and `require_admin` dependencies are consistently applied across all routers. No unguarded elevated routes were found.
- **Error pages:** The 404 and 500 templates display generic messages with no stack traces or internal detail.
- **Template auto-escaping:** Jinja2 escapes by default everywhere except where `|safe` is explicitly used. The only `|safe` instance found is the job description (Issue 1).

---

## Priority Order

**Before any public job postings go live:**
1. Fix XSS in job descriptions (Issue 1) — `nh3` is already installed, wire it up
2. Validate URL schemes for posting_url, website, social URLs (Issue 2)
3. Fix open redirect in `next` parameter (Issue 3)

**Near-term (next phase):**

4. Security headers middleware (Issue 5)
5. CSRF protection (Issue 4)
6. Email validation for application_email (Issue 7)
7. Rate limiting on sensitive endpoints (Issue 8)
8. Audit logging for admin/moderator actions (Issue 9)

**Lower priority:**

9. Restrict trusted proxy hosts (Issue 6)
10. Secret key startup validation (Issue 10)
11. Reduce session lifetime to 7 days (Issue 11)
