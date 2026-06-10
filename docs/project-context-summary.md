# TulsaJobSpot — Project Context Summary

## What This Is

TulsaJobSpot is a free, open-source community job board for Tulsa, Oklahoma. It is designed to be forkable — any community can clone and deploy their own instance. The philosophy is anti-VC, anti-dark-pattern, server-first simplicity. License: AGPL-3.0.

GitHub: https://github.com/eric-price-ok/tulsa-job-spot

---

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Web framework | FastAPI |
| ORM | SQLAlchemy 2.0 |
| Templates | Jinja2 |
| Interactivity | HTMX + Alpine.js |
| Database | PostgreSQL 16 |
| Background jobs | ARQ (Redis-backed) |
| Reverse proxy | Caddy (auto HTTPS) |
| Static files | WhiteNoise |
| Auth | OAuth2 via Authlib (Google, LinkedIn, GitHub, Microsoft, Facebook) |
| Containerization | Docker + Compose |
| AI extraction | Anthropic Claude API (used by scrapers) |

---

## Key Design Decisions

- **No passwords** — OAuth only. No password storage, no reset flows.
- **No hard deletes** — everything is soft-deleted via status flags. Data is retained for analytics.
- **Approved-by-default is false** — all new companies and job listings start unapproved.
- **Scraped jobs are labeled** — listings sourced by scraper show a "Scraped" badge.
- **Scraped companies are admin-owned** — site admin is the default company_admin for scraper-sourced companies.
- **No rate limiting in v1** — revisit if abuse occurs.
- **No file uploads in v1** — in-platform applications capture text only; resume filename columns exist in schema for future use.
- **OAuth required for applications** — anonymous applications not accepted.
- **Edits to approved listings go live immediately** — no re-approval required; flag problematic posters manually if needed.

---

## User Roles

### Site-level (on users table)
| Role | Flag | Capabilities |
|---|---|---|
| anonymous | — | Browse, search, view |
| user | authenticated | + Save/hide jobs, saved searches, notifications, profile |
| moderator | is_moderator | + Work approval queues, manage companies/listings |
| admin | is_admin | Everything |

### Company-scoped (in user_company_roles junction table)
| Role | How granted | Capabilities |
|---|---|---|
| job_poster | Invited by company_admin, or assigned by admin/moderator | Post jobs for that company |
| company_admin | Admin/moderator approval | + Manage company profile, invite/approve posters |

- One company_admin per company
- A user can be company_admin at multiple companies (entrepreneur use case)
- A user can be job_poster at multiple companies (fractional HR use case)

---

## Job Listing Application Methods

Every listing has an `application_method`:
- `external_url` — link out (scraped jobs, companies with own board)
- `email` — apply via email to employer
- `in_platform` — full application form captured in TulsaJobSpot

---

## Approval Queues (worked by admin and moderator)

- `pending_companies` — new company submissions
- `pending_joblistings` — new job postings
- `pending_user_company_roles` — users requesting company association

---

## Background Jobs (ARQ)

- `run_scraper` — scheduled per source cron
- `expire_scraped_jobs` — runs after each scrape, expires listings not found
- `check_external_links` — nightly, expires listings that 404
- `close_expired_jobs` — daily, closes listings past date_closed
- `match_saved_searches` — runs after new listings approved
- `send_notification_email` — event-driven
- `expire_invites` — daily

---

## Database Schema

Full schema is in: `create-tulsajobspot-db.sql`

Key tables:
- `users` — OAuth identity, is_admin, is_moderator flags
- `company` — approved=false default, is_scraped flag, approved_by FK
- `user_company_roles` — junction table, role = 'company_admin' | 'job_poster'
- `company_invites` — token-based, expires_at
- `joblistings` — approved=false default, application_method, posted_by FK
- `joblistingskills` — consolidated (no separate jobskills table)
- `joblistingcertifications` — certs mentioned in listings
- `applications` — in-platform applications, status workflow
- `saved_jobs` — with is_hidden flag
- `saved_searches` — JSONB filters, notify_on_match
- `notifications` — with related FKs
- `user_skills` — user profile skills from taxonomy
- `user_certifications` — with verified flag
- `scrapinglog` — scraper run history
- `scraper_sources` — admin-managed scraper config

---

## Project Structure

```
tulsajobspot/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── dependencies.py
│   ├── templates.py
│   ├── utils.py
│   ├── models/
│   │   ├── user.py
│   │   ├── company.py
│   │   ├── job.py
│   │   ├── application.py
│   │   ├── reference.py
│   │   └── scraping.py
│   ├── routers/
│   │   ├── auth.py
│   │   ├── jobs.py
│   │   ├── companies.py
│   │   ├── admin/__init__.py
│   │   └── moderator/__init__.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── partials/
│   │   ├── jobs/
│   │   ├── companies/
│   │   ├── admin/
│   │   ├── moderator/
│   │   └── errors/
│   ├── static/
│   ├── workers/
│   │   ├── main.py
│   │   ├── email.py
│   │   └── scraper.py
│   └── scrapers/
│       └── base.py
├── migrations/
├── tests/
├── docker/
│   ├── Dockerfile
│   └── Caddyfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── setup.sh
├── LICENSE
└── README.md
```

---

## Artifacts in This Project

- `migrations/` — Alembic migration files (source of truth for schema)
- `architecture.md` — system architecture document
- `feature-spec.md` — full feature specification with priorities
- `deployment-runbook.md` — VPS setup and deployment instructions
- `deferred.md` — items deliberately skipped during a phase; check before starting new work
- `security-review.md` — security analysis
- `running-tests.md` — test execution guide
- `how-to-import-companies.md` — CSV bulk import process

---

## Current Status

Phase 1 is complete. The application is built and deployed. Key capabilities in place:

- OAuth authentication (Google, LinkedIn, GitHub, Microsoft, Facebook)
- Anonymous job browsing with full-text search and faceted filters
- Company profiles
- Employer workflow: company creation, job posting, team invites
- Moderator approval queues (companies, roles, job listings)
- Admin dashboard: reference data management, user/moderator management, scraper source management
- Bulk CSV company import (3-step: upload → preview → confirm)
- ARQ background job framework (scraping, email, expiration)
- Scraper infrastructure (`BaseScraper` + Claude API extraction)

---

## Open Items / Known TODOs

Tracked in `docs/deferred.md`. Current deferred items:

- **Manage Company Profile** — `company_admin` edit form for company details (name, description, website, social links). The `/companies/{slug}/manage` page currently handles team and invites only. Spec 4.4 (P2).
- **Moderator activity log** — last 20 approvals/rejections on the moderator dashboard. Queue counts are present; the chronological log is not. Spec 6.4 (P1).

P3 (federation) tables (`federation_peers`, `federation_log`) are not yet modeled — deferred until federation is actively scoped.
