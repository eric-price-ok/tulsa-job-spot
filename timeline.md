# Tulsa Job Spot — Development Timeline

All work happened between June 5–11, 2026 across 16 branches, 66+ PRs, and ~100 commits.

---

## June 5 — Initial scaffold and deployment

**Branch:** `development` → main (PRs #1–5)

The project started from a blank repo. All architecture decisions were made upfront and documented in `docs/architecture.md` and `docs/feature-spec.md` before any code was written. Phase 1 delivered a fully working production deployment.

**Phase 1 scaffold (PR #1):**
- Full Docker Compose stack: app, worker, PostgreSQL 16, Redis, Caddy (auto-HTTPS)
- FastAPI app factory with async SQLAlchemy 2.0 engine
- All 25+ schema tables in one initial Alembic migration
- Seed data: 15 Tulsa-area cities, 20 industries, 13 job functions, 80+ skills, 11 certifications, admin user bootstrap
- OAuth-only auth via Authlib: Google, GitHub, LinkedIn, Microsoft, Facebook (enabled dynamically per `.env`)
- Job browse with PostgreSQL full-text search, HTMX partial updates, shareable filter URLs, pagination
- Jinja2 templates with custom CSS (~500 lines, CSS variables for fork theming — no framework)
- `setup.sh`: full Ubuntu 24.04 bootstrap in one pass
- ARQ worker shell and abstract scraper base class stubbed for future phases
- `docs/architecture.md`, `docs/feature-spec.md`, `docs/deployment-runbook.md`

**Deployment troubleshooting (PRs #2–5):**
- Fix admin login: seeded accounts now claim on first real OAuth sign-in instead of triggering email-conflict error
- Fix OAuth redirect URI generating `http://` behind Caddy — added `ProxyHeadersMiddleware`
- Fix auth callback 500: `func.now()` → `datetime.now()` on ORM attribute
- Fix migrations: switched Alembic env to sync psycopg2 driver (asyncpg's prepared-statement protocol rejects multi-statement blocks)

Site deployed and running at https://tulsajobspot.com by end of day.

---

## June 8 — Phases 2, 3, and 4

**Branches:** `phase-2`, `phase-3`, `phase-4-admin-gaps` → main (PRs #6–7)

Each phase was implemented as a single large branch and merged as one commit.

**Phase 2 — Employer workflow (PR #6):**
- Job posting form with full field set
- Employer job listings page
- Moderator job queue (approve/reject with email notification via ARQ)
- Company creation form and company approval queue
- Auth `?next=` redirect handling
- ARQ worker wired into the app lifecycle
- `docs/deferred.md` added to track intentionally skipped Phase 2 items

**Phase 3 — Admin and operations:**
- Admin panel (site config, reference data management)
- Cities management UI
- Scraper source management UI
- Link checker background job (ARQ)

**Phase 4 gap-fill — Admin user management (PR #7):**
- Admin user list with role management
- Admin moderator management
- Implemented spec sections 7.4 and 7.5

---

## June 9 — Testing, security hardening, Browse Companies, and company slugs

Four independent workstreams landed the same day via separate branches.

### Testing infrastructure — `feat/pytest-setup` (PRs #8–10)
- pytest with async DB isolation (per-test transaction rollback against a real PostgreSQL database — no mocking)
- `docs/running-tests.md` documenting test DB setup workflow
- Fix asyncio event loop mismatch in test suite
- Fix admin auth test URL (trailing slash)

### Security hardening — `fix/security-xss-urls-redirect` (PRs #11–13)
- `docs/security-review.md` documenting full security audit
- Fix critical XSS in job description rendering
- Fix URL injection vulnerability
- Fix open redirect in login page
- Add security test suite covering all three vulnerabilities
- Switched test DB setup to clone-from-prod workflow for higher fidelity
- Fix session cookie signing and httpx cookie deprecation in tests

### Browse Companies — `feature/browse-companies` (PRs #42–45)
- Browse Companies page with name search, industry filter, city filter
- Redesigned as sortable data table (replaced card layout)
- Edit Company Profile form
- Company location form with address fields
- Fix 500 on company profile page (missing `selectinload`)

### Company slugs — `company-slugs` (PRs #46–50)
- Slug-based company URLs: `/companies/enduro-pipeline-services`
- `generate_slug()` in `app/utils.py` strips common legal entity suffixes (LLC, Inc, Corp, etc.) before slugifying; collision handling appends numeric suffix
- `generate_slug` test suite; fix: strip apostrophes before hyphenating
- Fix `MissingGreenlet` errors from accessing `company.slug` post-commit in `companies.py`
- Fix browser devtools warnings: security headers, cache busting, CSS prefix, form IDs
- Fix separate `MissingGreenlet` in `job_create_submit`

---

## June 9–10 — Company CSV import

**Branch:** `Import-Companies` (PRs #52–55)

- Bulk company import from CSV (deferred item #26)
- Extended import format: social links, location, industry, new industries
- Company Types added to admin Data Management menu
- Fix import template (new columns, broken doc link)
- Add industry field to import
- `docs/how-to-import-companies.md`
- Architecture docs updated to reflect current project state

---

## June 10 — Site admin editing, jobs page overhaul, misc hardening

### Admin action bar — `Site-Admin-Editing` (PR #56)
- Floating admin action bar on company profile and job detail pages (edit/approve/reject without leaving the page)

### Misc-Improvements (PRs #57–64) — incremental fixes and polish
Delivered in rapid succession as individual commits on a shared branch:

| Area | Changes |
|---|---|
| Filters | Fix select filters on companies and jobs browse pages; fix `hx-get` placement; fix company filter reset for empty city/industry |
| Company socials | Sort alphabetically; Font Awesome brand icons (replaced simpleicons) |
| Admin | Add admin disable/enable company |
| Tests | Add company tests; fix `running-tests.md` for test DB and docker-compose syntax |
| DevOps | Harden `docker-compose` for production; move postgres credentials from `docker-compose.yml` to `.env`; revert partial change and document correct `COMPOSE_FILE` prod deploy pattern |
| Jobs | Fix crash when approving/rejecting scraped jobs with no poster (null check) |
| Jobs browse | Replace card layout with data table on `/jobs` |
| Job detail | Render job description HTML (was showing raw markup) |
| Jobs filters | Fix 422 on job filters; switch to horizontal filter bar layout |
| Tooling | Add `CLAUDE.md` with codebase guidance |

### Job slugs — `job-slug-implementation`
- Slug-based job URLs: `/jobs/some-title-56` (format: slugified title + numeric job ID suffix for uniqueness)

---

## June 11 — Company locations/sites, Recruiters page, admin dashboard

### Company sites — `company-sites` (PRs #65–66)
- Locations table on company profile page with per-location admin site management
- Job Site Types admin page
- `site_name` field added to `CompanySite` model
- Inline site editing directly in the locations table (HTMX swap)

### Misc-Improvements (merged 3×)
- Add Spotify, TikTok, and Pinterest to social media types
- Recruiters page with admin feature toggle (hidden unless enabled in admin settings)
- "Visit job board" link on company profile pages
- Job Boards section on Recruiters page with admin toggle
- Site name and type fields on Add Location form (company edit page)

### Admin dashboard — `misc-improvements`
- Admin company creation page (create a company directly from the admin panel without going through the public approval flow)
- Reorganized admin dashboard layout

---

## Branch inventory

| Branch | Purpose | Status |
|---|---|---|
| `development` | Phase 1 deployment fixes | Merged → main |
| `phase-2` | Employer workflow, moderator queue | Merged → main |
| `phase-3` | Admin panel, scrapers, link checker | Merged → main |
| `phase-4-admin-gaps` | Admin user/moderator management | Merged → main |
| `feat/pytest-setup` | pytest infrastructure | Merged → main |
| `fix/security-xss-urls-redirect` | XSS, URL injection, open redirect fixes | Merged → main |
| `feature/browse-companies` | Browse Companies page | Merged → main |
| `company-slugs` | `/companies/<slug>` URLs | Merged → main |
| `Import-Companies` | Bulk CSV company import | Merged → main |
| `Site-Admin-Editing` | Admin action bar | Merged → main |
| `Misc-Improvements` | Incremental fixes and polish (many PRs) | Merged → main |
| `job-slug-implementation` | `/jobs/<slug>` URLs | Merged → main |
| `company-sites` | Company locations/sites management | Merged → main |
| `misc-improvements` | Recruiters page, social types, admin creation | Merged → main |

---

## State as of June 11

The site is live at https://tulsajobspot.com. Core job-board functionality is complete: job browsing with FTS and filters, company profiles with slugged URLs, employer job posting with moderator approval, OAuth sign-in, background workers, and a full admin panel. Scraper integration exists at the framework level but no production scrapers are running yet.

Deferred items are tracked in `docs/deferred.md`.
