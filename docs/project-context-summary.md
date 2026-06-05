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
- `scraper_sources` — admin-managed scraper config (to be added to schema)
- `federation_peers` — instance sync config (to be added to schema, P3 feature)

---

## Project Structure

```
tulsajobspot/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── dependencies.py
│   ├── models/
│   ├── routers/
│   │   ├── auth.py
│   │   ├── jobs.py
│   │   ├── companies.py
│   │   ├── applications.py
│   │   ├── profile.py
│   │   ├── admin/
│   │   └── moderator/
│   ├── templates/
│   │   ├── base.html
│   │   ├── partials/
│   │   ├── jobs/
│   │   ├── companies/
│   │   ├── profile/
│   │   ├── admin/
│   │   └── moderator/
│   ├── static/
│   ├── workers/
│   └── scrapers/
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

## Phase 1 Build Plan (what we're starting now)

1. Project scaffolding — directory structure, pyproject.toml, requirements
2. Docker Compose setup — app, worker, db, redis, caddy services
3. Caddy config — reverse proxy, auto HTTPS, www redirect
4. FastAPI app factory — main.py, config.py, database.py
5. SQLAlchemy models — all tables from schema
6. Alembic — migration setup and initial migration
7. Seed data script — reference tables (countries, states, cities, job types, functions, etc.)
8. OAuth auth — sign in/out with at least Google, session management
9. Base templates — base.html, nav, static assets (CSS/JS)
10. Anonymous browse — job listing index, search/filter, job detail, company profile
11. setup.sh — bootstrap script tying it all together

---

## Artifacts in This Project

- `create-tulsajobspot-db.sql` — full database schema
- `architecture.md` — system architecture document
- `feature-spec.md` — full feature specification with priorities
- `deployment-runbook.md` — VPS setup and deployment instructions (needs revision pass after first real deployment)

---

## Open Items / Known TODOs

- `scraper_sources` table not yet added to schema (needed before scraper work)
- `federation_peers` and `federation_log` tables not yet added to schema (P3)
- Google OAuth setup instructions in runbook are outdated — need to update after email is configured for the site
- Deployment runbook needs revision pass: sudo prefixes on apt commands, SSH key section needs console-session note, hosts file edit is optional
- Scraper design document to be written in a separate chat
- Scraper migration (100 existing Python scripts) to be handled in separate chat
