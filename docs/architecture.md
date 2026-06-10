# TulsaJobSpot — Architecture Document

## Purpose

This document describes the technical architecture of TulsaJobSpot: a free, open-source community job board designed to be deployed by anyone, for any community. It is the authoritative reference for system design decisions and the starting point for all subsequent technical planning.

---

## Philosophy

TulsaJobSpot is built on a deliberate set of tradeoffs:

- **Simplicity over scale** — optimized for a single-server deployment, not distributed systems
- **Forkability** — any community should be able to clone, configure, and run their own instance in under 15 minutes
- **No dark patterns** — no promoted listings, no tracking, no upsells, no ads
- **Server-first** — HTML rendered on the server with targeted interactivity, not a SPA
- **Durable** — minimal dependencies, boring technology, easy to hand off

These choices are features, not limitations.

---

## License

**GNU Affero General Public License v3 (AGPL-3.0)**

The AGPL closes the SaaS loophole: anyone who runs a modified version of this software as a network service must publish their changes. This ensures that improvements made by forks flow back to the community, and prevents a well-funded competitor from taking this codebase commercial without contributing back.

---

## System Overview

```
                        ┌─────────────────────────────────┐
                        │           Caddy (HTTPS)          │
                        │      Reverse proxy + TLS         │
                        └────────────┬────────────────────┘
                                     │
                        ┌────────────▼────────────────────┐
                        │        FastAPI Application       │
                        │   Jinja2 templates + HTMX        │
                        │   Uvicorn + Gunicorn workers     │
                        └────────────┬────────────────────┘
                                     │
               ┌─────────────────────┼──────────────────────┐
               │                     │                       │
   ┌───────────▼──────┐  ┌──────────▼──────────┐  ┌────────▼────────┐
   │   PostgreSQL DB  │  │    ARQ / Redis       │  │  Static Files   │
   │  Primary store   │  │  Background jobs     │  │  WhiteNoise     │
   └──────────────────┘  └─────────────────────┘  └─────────────────┘
```

All components run as Docker containers on a single VPS, orchestrated by Docker Compose.

---

## Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Language | Python 3.12+ | Largest contributor pool, best Claude reliability |
| Web framework | FastAPI | Lightweight, async, auto OpenAPI docs |
| ORM | SQLAlchemy 2.0 | Mature, flexible, good Postgres support |
| Templates | Jinja2 | Server-rendered HTML, no build pipeline |
| Interactivity | HTMX | Progressive enhancement, no JS framework |
| JS utilities | Alpine.js | Minimal JS for things HTMX can't handle |
| Database | PostgreSQL 16 | Full-text search, JSONB, battle-tested |
| Background jobs | ARQ (Redis-backed) | Lighter than Celery, good FastAPI integration |
| Cache / queue | Redis | Required by ARQ; available for caching |
| Reverse proxy | Caddy | Automatic HTTPS, simple config |
| Static files | WhiteNoise | Serves static assets from app process |
| Containerization | Docker + Compose | Single-command deployment, portable |
| Auth | OAuth2 (Authlib) | Five providers supported; no password storage |
| AI extraction | Anthropic Claude API | Structured field extraction in scraper worker |

---

## Application Structure

```
tulsajobspot/
├── app/
│   ├── main.py                  # FastAPI app factory
│   ├── config.py                # Settings via pydantic-settings
│   ├── database.py              # SQLAlchemy engine + session
│   ├── dependencies.py          # FastAPI dependency injection (auth, db session)
│   ├── templates.py             # Jinja2 environment + CSS fingerprinting
│   ├── utils.py                 # Slug generation, URL sanitization, redirect safety
│   │
│   ├── models/                  # SQLAlchemy ORM models (one file per domain)
│   │   ├── user.py
│   │   ├── company.py
│   │   ├── job.py
│   │   ├── application.py
│   │   ├── reference.py         # All taxonomy/lookup tables
│   │   └── scraping.py          # ScraperSource, ScrapingLog
│   │
│   ├── routers/                 # FastAPI routers (one file per domain)
│   │   ├── auth.py              # OAuth login/logout/callback
│   │   ├── jobs.py              # Browse, search, view, create, edit, approve listings
│   │   ├── companies.py         # Company profiles, create, manage, invites
│   │   ├── admin/               # Admin-only routes (single __init__.py)
│   │   └── moderator/           # Moderator-accessible routes (single __init__.py)
│   │
│   ├── templates/               # Jinja2 templates
│   │   ├── base.html            # Base layout
│   │   ├── partials/            # HTMX partial templates
│   │   ├── jobs/
│   │   ├── companies/
│   │   ├── admin/
│   │   ├── moderator/
│   │   └── errors/
│   │
│   ├── static/                  # CSS, JS, images
│   │
│   ├── workers/                 # ARQ background job definitions
│   │   ├── main.py              # WorkerSettings, job registry
│   │   ├── email.py             # Notification emails
│   │   └── scraper.py           # Job board scraping
│   │
│   └── scrapers/                # Per-source scraper implementations
│       └── base.py              # Abstract base scraper
│
├── migrations/                  # Alembic migration files
├── tests/
├── docker/
│   ├── Dockerfile
│   └── Caddyfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── setup.sh                     # Bootstrap script for new deployments
├── LICENSE                      # AGPL-3.0
└── README.md
```

---

## User Roles and Access

### Site-Level Roles
Stored on the `users` table as boolean flags.

| Role | How Granted | Capabilities |
|---|---|---|
| `anonymous` | No auth required | Browse jobs, search, view company profiles |
| `user` | OAuth sign-in | + Save jobs, hide jobs, saved searches, notifications, user profile/skills |
| `admin` | `is_admin=true` on users | Everything |
| `moderator` | `is_moderator=true` on users | Work approval queues, manage companies and listings, cannot change site config |

### Company-Scoped Roles
Stored in `user_company_roles` junction table. A user may hold roles at multiple companies.

| Role | How Granted | Capabilities |
|---|---|---|
| `job_poster` | Invited by company_admin, or assigned by admin/moderator | Post jobs for that company |
| `company_admin` | Admin/moderator approval, or assigned at company creation | + Manage company profile, invite/approve job_posters |

**Rules:**
- One `company_admin` per company
- A user may be `company_admin` at multiple companies (entrepreneur use case)
- A user may be `job_poster` at multiple companies (fractional HR use case)
- Scraped companies are owned by the site admin account

---

## Authentication

OAuth2 only. No passwords stored. Implemented via Authlib.

**Supported providers:**
- Google
- LinkedIn
- GitHub
- Microsoft / Azure AD
- Facebook

Providers are **configured by the site admin** via environment variables. Only providers with `CLIENT_ID` and `CLIENT_SECRET` set in `.env` are enabled. A community deploying this for a tech-heavy audience might enable GitHub; one focused on enterprise might enable Microsoft. No code changes required to add or remove providers.

**Flow:**
1. User clicks "Sign in with Google/LinkedIn"
2. Redirected to provider, user authenticates
3. Provider redirects back with auth code
4. App exchanges code for token, retrieves user profile
5. User record created or updated (`oauth_provider` + `oauth_subject` unique constraint)
6. Session cookie issued (signed, httponly, secure)

**New user flow after OAuth:**
- User lands in `pending` state (no company role yet)
- They may browse as an authenticated user immediately
- To post jobs: they submit a company association request which enters the moderator queue

---

## Job Listing Workflow

### Scraped Jobs
1. ARQ worker runs scraper on schedule
2. Scraper fetches listings from external board
3. AI (Claude API) extracts structured fields from raw text
4. Deduplication via `scraping_hash` (hash of source URL + posting ID)
5. Listing created with `approved=true`, `posted_by=NULL`, `application_method='external_url'`
6. Scraper-sourced companies default to admin ownership

### Employer-Posted Jobs
1. Authenticated user with `job_poster` or `company_admin` role submits listing
2. Listing created with `approved=false`
3. **If first post from unverified user:** one listing allowed in queue, admin notified
4. **If company is approved and user has active role:** listing enters moderator queue
5. Moderator or admin approves → `approved=true`, listing goes live
6. Notification sent to matching saved searches

### Application Methods
- `external_url` — link out to employer's own board (scraped jobs)
- `email` — application sent to employer's email address
- `in_platform` — application form captured in TulsaJobSpot (v1: no file uploads)

---

## Approval Queues

Three queues, all visible to `admin` and `moderator` roles. Exposed as database views and surfaced in the moderator dashboard.

| Queue | Trigger | Action |
|---|---|---|
| `pending_companies` | New company submitted | Approve + assign company_admin, or reject |
| `pending_joblistings` | New job posted by unverified/new poster | Approve or reject |
| `pending_user_company_roles` | User requests company association | Approve as job_poster or company_admin, or reject |

Email notifications fire to admin/moderators when items enter queues.

---

## Background Jobs (ARQ)

All background work runs as ARQ tasks backed by Redis.

| Job | Trigger | Description |
|---|---|---|
| `send_notification_email` | Event-driven | Sends email for approvals, application updates, invites |
| `run_scraper` | Scheduled (cron) | Scrapes configured job boards, extracts listings |
| `match_saved_searches` | After new listings approved | Finds users with matching saved searches, queues notifications |
| `expire_invites` | Scheduled (daily) | Marks expired company invites as inactive |
| `expire_scraped_jobs` | Scheduled (after each scrape) | Marks listings as expired when not found in latest scrape for that source |
| `check_external_links` | Scheduled (nightly) | HEAD request against all active external_url listings; expires any that return 404 |
| `close_expired_jobs` | Scheduled (daily) | Sets job status to closed when date_closed passes |

---

## Search

**v1:** PostgreSQL full-text search using `tsvector` on `job_title` and `job_description`. GIN index for performance.

Filters available:
- City (FK to `cities` where `is_served=true`)
- Function / Specialty
- Job type (full-time, part-time, contract, etc.)
- Office location (remote, hybrid, on-site)
- Salary range
- Experience level
- Skills (multi-select)
- Date posted

Saved searches store filter state as JSONB. The matching worker rehydrates the JSONB and runs the same query logic to find new matches.

**Future:** Meilisearch as a drop-in upgrade if Postgres FTS proves insufficient.

---

## Email

Transactional email via SMTP. No proprietary email provider required.

`.env` exposes `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`. Works with any SMTP provider (Postfix self-hosted, Mailgun, SES, etc.).

Email types:
- Company approval notification
- Job posting approved/rejected
- Company invite
- Application received (to employer)
- Application status update (to applicant)
- Saved search match digest

---

## Deployment

### Requirements
- A VPS with Ubuntu 22.04+ (1GB RAM minimum, 2GB recommended)
- A domain name pointed at the server
- Ports 80 and 443 open

### Bootstrap
```bash
curl -fsSL https://raw.githubusercontent.com/[org]/tulsajobspot/main/setup.sh | bash
```

`setup.sh` does the following:
1. Installs Docker and Docker Compose if not present
2. Clones the repository
3. Copies `.env.example` to `.env` and prompts for required values
4. Runs `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`
5. Runs database migrations via Alembic
6. Seeds reference data (countries, states, job types, office locations, etc.)

Caddy handles TLS certificate provisioning automatically via Let's Encrypt.

### Environment Variables (required)
```
DOMAIN=tulsajobspot.com
SECRET_KEY=<random 64-char string>
DATABASE_URL=postgresql://...
REDIS_URL=redis://redis:6379
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
SMTP_HOST=
SMTP_PORT=
SMTP_USER=
SMTP_PASSWORD=
ADMIN_EMAIL=                  # seeded as first admin account on first run
ANTHROPIC_API_KEY=            # used by scraper AI extraction
```

### Docker Compose Services
| Service | Image | Notes |
|---|---|---|
| `app` | Custom (Dockerfile) | FastAPI + Gunicorn + Uvicorn workers |
| `worker` | Same image, different command | ARQ background worker |
| `db` | postgres:16 | Persistent volume |
| `redis` | redis:7-alpine | Persistent volume |
| `caddy` | caddy:2 | Reverse proxy, auto TLS |

---

## Forkability

To run this for a different community:

1. Fork the repository
2. Run `setup.sh` on a new VPS
3. Set `DOMAIN` and `ADMIN_EMAIL` in `.env`
4. Log in as admin and configure:
   - Served cities (which cities appear in filters)
   - Site name and branding (via admin config panel, stored in DB)
   - Which job boards to scrape
5. Done

No code changes required for a new community deployment.

---

## GitHub Repository

- **Org/repo:** `eric-price-ok/tulsa-job-spot`
- **Visibility:** Public
- **Branching:** `main` (production-ready), feature branches
- **Issues:** Used for feature tracking and bug reports
- **Discussions:** Community Q&A for people deploying their own instances

---

## Data Retention

**No job listings, companies, or user accounts are ever hard-deleted.** All records are retained indefinitely. Visibility is controlled via `approved`, `job_status_id`, and `is_active` flags. Reasons:

- Historical data enables community analytics ("most in-demand skills over time")
- Scraping deduplication relies on historical hashes
- Moderation context is preserved (why a company was rejected, who approved what)
- Employer posting history informs future moderation decisions

Scraped listings are expired (not deleted) via two mechanisms:
1. **Post-scrape expiration** — listings not found in the latest scrape for a given source are marked expired
2. **Nightly link check** — HEAD request against all active `external_url` listings; any returning 404 are expired

---

## Scraper Management

Scrapers are managed through a dedicated admin interface rather than config files. Non-developer admins can manage sources without touching code or redeploying.

### `scraper_sources` Table
| Field | Description |
|---|---|
| `name` | Human-readable label |
| `scraper_class` | Python class name to invoke |
| `url` | Entry point URL |
| `company_id` | FK to company (for company-specific boards) |
| `cron_schedule` | Cron expression for run frequency |
| `is_active` | Toggle without deleting |
| `selenium_required` | Flag for sources needing a headless browser |
| `last_run_at` | Timestamp of last execution |
| `last_status` | Status string from last run |
| `config` | JSON for scraper-specific parameters |

### Admin Interface Capabilities
- View all sources with last run status and job counts
- Enable / disable individual sources
- Trigger a manual scrape run
- View paginated scraping log history
- Add new sources

### Scraper Architecture
Each scraper inherits from a `BaseScraper` abstract class that handles deduplication, AI extraction, logging, and error handling. Individual scrapers only implement `fetch_listings()`. AI extraction via Claude API handles unstructured job descriptions, replacing manual field parsing and reducing per-scraper maintenance burden.

Individual scraper implementations (`app/scrapers/`) are not yet written; only `base.py` exists.

---

## Out of Scope (v1)

- File uploads / resume storage
- Multi-server / horizontal scaling
- Native mobile apps
- Kubernetes / Nomad orchestration
- Paid promoted listings (by design, not just v1)
- Social features (messaging between users)
- Rate limiting (revisit if abuse occurs)

---

## Open Questions / TBD

- Scraper implementations — `BaseScraper` is in place; individual scrapers for specific job boards are not yet written
- Apple OAuth — requires paid Apple Developer account; low priority; not currently implemented
