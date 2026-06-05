# TulsaJobSpot — Feature Specification

## How to Read This Document

Features are organized by functional area, then by role. Each feature has:
- A short description
- Acceptance criteria (what "done" means)
- Priority: **P1** (launch blocker), **P2** (ship soon after launch), **P3** (nice to have)
- Notes where relevant

Features marked P1 must be complete and working before the site goes live. P2 features can launch shortly after. P3 features are backlog.

---

## 1. Authentication & Sessions

### 1.1 OAuth Sign-In
**Priority:** P1

Users can sign in using any OAuth provider configured by the site admin. Only providers with both `CLIENT_ID` and `CLIENT_SECRET` set in `.env` appear as sign-in options.

**Providers supported:** Google, LinkedIn, GitHub, Microsoft, Facebook

**Acceptance criteria:**
- Sign-in buttons rendered only for configured providers
- Successful OAuth callback creates or updates user record
- `oauth_provider` + `oauth_subject` uniqueness enforced — same person signing in twice with Google creates one record
- Session cookie issued: signed, httponly, secure, reasonable expiry (30 days)
- Failed OAuth (user cancels, provider error) returns to home page with a non-alarming message
- New user lands on a "complete your profile" prompt (name, optional)

### 1.2 Sign-Out
**Priority:** P1

**Acceptance criteria:**
- Session cookie cleared on sign-out
- User returned to home page
- No sensitive data cached in browser after sign-out

### 1.3 Session Persistence
**Priority:** P1

**Acceptance criteria:**
- User remains signed in across browser restarts for session duration
- Expired sessions redirect to sign-in with a return URL so user lands back where they were

---

## 2. Anonymous Browsing

### 2.1 Browse Job Listings
**Priority:** P1

Any visitor can browse all approved, active job listings without signing in.

**Acceptance criteria:**
- Listings displayed in reverse chronological order by default
- Each listing card shows: job title, company name, city, job type, date posted, salary range (if available), "Scraped" badge if `is_scraped=true`
- Pagination — 25 listings per page
- No login prompt or nag to view listings
- Listings with `approved=false` or non-active status never appear

### 2.2 Search & Filter
**Priority:** P1

**Filters available:**
- Keyword (searches job title and description via Postgres FTS)
- City (multi-select, only `is_served=true` cities shown)
- Function / Specialty
- Job type (full-time, part-time, contract, etc.)
- Office location (remote, hybrid, on-site)
- Salary minimum (slider or input)
- Experience level
- Date posted (last 24h, last 7 days, last 30 days, any)

**Acceptance criteria:**
- Filters applied via HTMX — no full page reload
- Active filters shown as removable chips above results
- Result count updates as filters change
- URL reflects current filter state (shareable/bookmarkable search URLs)
- Empty results shows helpful message, not a blank page

### 2.3 View Job Detail
**Priority:** P1

**Acceptance criteria:**
- Full job description rendered (sanitized HTML or plain text)
- Company name links to company profile
- Application method drives CTA:
  - `external_url` → "Apply on [Company] website" button, opens in new tab, labeled "Scraped listing"
  - `email` → "Apply via Email" button, opens mailto
  - `in_platform` → "Apply Now" shows inline application form
- Salary range displayed if available
- Skills and certifications listed if present
- Date posted shown; expired/closed listings show a clear status banner
- Signed-in users see Save / Hide buttons

### 2.4 View Company Profile
**Priority:** P1

**Acceptance criteria:**
- Company name, description, website, industry, size, location
- Active job listings for this company
- Social media links if present
- Scraped companies display no "contact us" or ownership-implying information

---

## 3. Signed-In User Features

### 3.1 Save a Job
**Priority:** P2

**Acceptance criteria:**
- Save button on listing card and detail page
- Saved jobs accessible from user profile / dashboard
- Saving a job that's already saved toggles it off (unsave)
- Saved jobs that expire or close show the company name and job title with a "this listing is no longer active" indicator rather than disappearing silently

### 3.2 Hide a Job
**Priority:** P2

Users can hide listings they're not interested in so they stop appearing in results.

**Acceptance criteria:**
- Hide button on listing card (visible on hover or tap)
- Hidden jobs no longer appear in search results for that user
- "Manage hidden jobs" in profile lets user un-hide
- Hiding is local to the user — does not affect anyone else

### 3.3 Saved Searches
**Priority:** P2

**Acceptance criteria:**
- User can save current filter state with a name
- Saved searches accessible from profile dashboard
- Saved searches can be deleted
- Optionally, user can enable email notifications for a saved search
- Notification sends when new matching listings are approved (daily digest, not per-listing)

### 3.4 User Profile — Basic Info
**Priority:** P2

**Acceptance criteria:**
- User can set display name, optional headline
- Avatar pulled from OAuth provider, not editable in v1
- Profile page is private (not publicly visible in v1)

### 3.5 User Profile — Skills
**Priority:** P3

**Acceptance criteria:**
- User can add skills from the site taxonomy
- Per skill: proficiency level, years of experience, featured flag
- Up to 3 featured skills shown prominently on profile
- Skills can be removed

### 3.6 User Profile — Certifications
**Priority:** P3

**Acceptance criteria:**
- User can add certifications from the site taxonomy
- Per cert: obtained date, expiry date, credential ID, credential URL
- Expired certifications shown with visual indicator
- Certs can be removed

### 3.7 Notifications
**Priority:** P2

**Acceptance criteria:**
- Notification bell in nav shows unread count
- Notification types: saved search match, application status update, company invite received, job posting approved/rejected
- Notifications marked read on view
- Notification links to relevant entity (job, application, company)
- Email notification sent for each (user can opt out per type)

---

## 4. Job Posting — Employer Workflow

### 4.1 Request Company Association
**Priority:** P1

A signed-in user who wants to post jobs must associate with a company first.

**Acceptance criteria:**
- "Post a Job" CTA prompts unapproved users to claim or create a company
- User can search for existing company by name
- If company exists and has a `company_admin`: user requests to join → enters `pending_user_company_roles` queue, `company_admin` is notified
- If company exists but has no `company_admin`: request goes to admin/moderator queue
- If company doesn't exist: user submits new company record → enters `pending_companies` queue
- One job listing allowed in pending state while waiting for approval

### 4.2 Create a Job Listing
**Priority:** P1

Available to approved `job_poster` and `company_admin` roles.

**Fields:**
- Job title (required)
- Job description (required, rich text or markdown)
- Application method: external URL, email, or in-platform (required)
- Application URL or email address (required based on method)
- City (select from served cities)
- Office location (remote, hybrid, on-site)
- Job type (full-time, part-time, contract, etc.)
- Salary range (optional, min/max + frequency)
- Function / Specialty
- Skills (multi-select from taxonomy)
- Certifications (multi-select from taxonomy)
- Experience level
- Close date (optional)

**Acceptance criteria:**
- Form validates all required fields before submission
- Listing created with `approved=false`
- Moderator/admin notified of new listing in queue
- Poster sees "Your listing is pending approval" confirmation
- Poster can edit listing while pending
- Once approved, poster notified via notification + email

### 4.3 Manage Company Listings
**Priority:** P1

`company_admin` and `job_poster` can view and manage their company's listings.

**Acceptance criteria:**
- Dashboard shows all listings for their company: pending, active, closed, expired
- Can edit any listing; edits to approved listings go live immediately without re-approval
- Can manually close a listing
- Cannot delete — listings are hidden, not removed

### 4.4 Manage Company Profile
**Priority:** P2

`company_admin` only.

**Acceptance criteria:**
- Edit company name, description, website, social links, industry, size, type
- Add/remove company locations
- Cannot change `is_scraped` flag or `approved` status

### 4.5 Invite a Job Poster
**Priority:** P1

`company_admin` can invite users to post jobs on behalf of their company.

**Acceptance criteria:**
- Enter email address to send invite
- Token-based invite link emailed to recipient, expires in 7 days
- Recipient clicks link → if already has account, role granted immediately; if not, prompted to sign in via OAuth first
- `company_admin` can see pending invites and revoke them
- Inviting an email already associated with an active role shows a warning

### 4.6 Approve / Remove Job Posters
**Priority:** P1

`company_admin` can manage who posts for their company.

**Acceptance criteria:**
- View all current `job_poster` roles for their company
- Remove a poster (role deactivated, existing listings remain)
- Posters removed cannot create new listings for that company

---

## 5. In-Platform Applications

### 5.1 Submit an Application
**Priority:** P2

Available when `application_method = 'in_platform'`. Requires sign-in via OAuth — anonymous applications not accepted.

**Fields:**
- Full name (pre-filled from profile, editable)
- Email (pre-filled from OAuth, not editable)
- Phone (optional)
- Cover letter (optional, text)
- No file uploads in v1

**Acceptance criteria:**
- Unauthenticated users shown sign-in prompt instead of application form
- Form shown inline on job detail page via HTMX
- Submission creates application record with status `submitted`
- Applicant receives confirmation email
- `company_admin` and any `job_poster` for that company notified of new application
- Signed-in users have application pre-filled with profile info
- User cannot submit duplicate application to same listing

### 5.2 Manage Applications (Employer)
**Priority:** P2

`company_admin` and `job_poster` can view and manage applications for their listings.

**Acceptance criteria:**
- Application list per listing: name, email, date submitted, current status
- Status can be updated: `submitted` → `reviewing` → `shortlisted` / `rejected` / `hired`
- Status change triggers notification + email to applicant
- Internal notes field per application (not visible to applicant)
- Cannot delete applications

### 5.3 View Application Status (Applicant)
**Priority:** P2

Signed-in users can see the status of applications they've submitted.

**Acceptance criteria:**
- "My Applications" section in profile dashboard
- Shows listing title, company, date applied, current status
- Status updates trigger in-app notification and email

---

## 6. Moderator Features

### 6.1 Company Approval Queue
**Priority:** P1

**Acceptance criteria:**
- List of pending companies with: name, website, submitted by, date submitted
- Moderator can approve — selecting role for submitting user (`company_admin` or `job_poster`)
- Moderator can reject with a reason (reason emailed to submitter)
- Approved companies immediately visible on site
- Scraper-owned companies bypass this queue (auto-approved)

### 6.2 Job Listing Approval Queue
**Priority:** P1

**Acceptance criteria:**
- List of pending listings with: title, company, posted by, date, application method
- Moderator can preview full listing before deciding
- Approve → listing goes live, poster notified
- Reject with reason → poster notified, listing hidden
- Bulk approve option for trusted companies

### 6.3 User Role Approval Queue
**Priority:** P1

Handles requests from users to join companies without a `company_admin` invite.

**Acceptance criteria:**
- List of pending role requests: user email, company, requested role, date
- Approve or reject with reason
- On approval, user gains role and is notified
- Moderator can assign either `job_poster` or `company_admin` regardless of what was requested

### 6.4 Moderator Dashboard
**Priority:** P1

**Acceptance criteria:**
- Single page showing counts of items in each queue
- Quick links to each queue
- Recent activity log (last 20 approvals/rejections by any moderator)

---

## 7. Admin Features

### 7.1 All Moderator Features
**Priority:** P1

Admin can do everything a moderator can do.

### 7.2 Manage Served Cities
**Priority:** P1

**Acceptance criteria:**
- List of all cities in database with `is_served` toggle
- Toggle a city on/off — affects search filters and job posting city selector immediately
- Add new city (name + state)

### 7.3 Manage Site Configuration
**Priority:** P1

Key/value config stored in database, not requiring redeploy.

**Configurable values:**
- Site name (default: "Tulsa Job Spot", overridable for forks)
- Site tagline
- Contact email
- Items per page
- Default city filter
- Notification email from-address

**Acceptance criteria:**
- Admin UI for editing config values
- Changes take effect without restart
- Config values available to templates via context

### 7.4 Manage Users
**Priority:** P2

**Acceptance criteria:**
- Search users by email or name
- View user's company roles
- Promote/demote moderator status
- Deactivate a user account (does not delete)
- View user's job listings and applications

### 7.5 Manage Moderators
**Priority:** P2

**Acceptance criteria:**
- Grant or revoke `is_moderator` flag on any user
- Moderator list view

### 7.6 Manage Reference Data
**Priority:** P2

Admin-maintained lookup tables.

**Tables managed:**
- Functions and specialties
- Industries
- Skills and skill categories
- Certifications and certification providers
- Job types
- Office locations
- Benefits
- Company types

**Acceptance criteria:**
- Add, edit, deactivate entries in each table
- Deactivated entries no longer appear in dropdowns
- Cannot delete entries that are in use (foreign key protection)

### 7.7 Scraper Source Management
**Priority:** P2

**Acceptance criteria:**
- List all scraper sources with: name, type, last run, status, job counts
- Enable / disable a source
- Edit schedule (cron expression with human-readable preview)
- Trigger a manual run
- View scraping log for a source (last 30 runs)
- Add new source (name, URL, scraper class, company association, config JSON)
- `selenium_required` flag visible and editable

### 7.8 Scraping Log
**Priority:** P2

**Acceptance criteria:**
- Log of all scraping runs: source, started, duration, jobs found/added/updated/skipped, status, errors
- Filterable by source and date range
- Error details expandable inline

### 7.9 Ownership Transfer
**Priority:** P3

Transfer `company_admin` role from one user to another.

**Acceptance criteria:**
- Admin selects company, current admin, new admin
- Old admin demoted to `job_poster` or removed
- New admin granted `company_admin`
- Both users notified

---

## 8. Community Features

### 8.1 Skill Demand View
**Priority:** P3

Public-facing page showing most in-demand skills based on active listings.

**Acceptance criteria:**
- Ranked list of skills by listing count
- Filterable by function/industry
- Shows required vs preferred breakdown
- Updates in near-real-time (cached, refreshed hourly)

### 8.2 Instance Federation (Sync)
**Priority:** P3

A site admin can configure synchronization with another TulsaJobSpot instance, allowing approved listings to be replicated to partner communities. This is how the "any community can run this" goal becomes a network rather than a collection of isolated sites.

**Acceptance criteria:**

Setup:
- Admin configures a sync target: remote instance URL, which functions to replicate
- A sync request is sent to the remote instance's admin notifying them of the incoming sync request
- Remote admin must approve before any data flows
- Approved sync relationships stored in a `federation_peers` table (local instance URL, remote instance URL, approved functions, approval status, last sync timestamp)

Nightly sync job:
- Runs after midnight
- Collects all active approved listings matching configured functions added or updated since last sync
- POSTs listings to remote instance API endpoint
- Remote instance creates listings with `is_scraped=true`, source attributed to origin instance
- Sync result logged (listings sent, accepted, rejected, errors)
- Both admins notified of sync summary

Remote receive:
- Remote instance exposes an authenticated API endpoint for receiving federated listings
- Listings created as external_url type pointing back to origin instance listing
- Remote admin can disable a sync relationship at any time; origin admin notified

**Notes:**
- Shared secret or API key authentication between instances
- Federation is one-directional per relationship (A pushes to B); bidirectional requires two configured relationships
- Remote instance is never given write access to origin — push only
- Listings received from federation are clearly attributed ("Originally posted on [instance name]")

### 8.3 Job Market Snapshot
**Priority:** P3

Simple public stats page.

**Acceptance criteria:**
- Total active listings
- Listings added in last 7/30 days
- Top hiring companies
- Most common job functions
- Average salary by function (where data exists)

---

## 9. Background Jobs

### 9.1 Scraper Runner
**Priority:** P1

**Acceptance criteria:**
- ARQ worker picks up scraper jobs from queue per configured cron schedule
- One job per source, no overlapping runs for same source
- Scraping log entry created on start, updated on completion
- On failure: log updated with error, source not disabled automatically

### 9.2 Link Checker
**Priority:** P1

Nightly job checking all active `external_url` listings.

**Acceptance criteria:**
- HEAD request to each `posting_url`
- 404 response → listing marked expired
- Non-404 errors (timeout, 5xx) → retry next night before expiring
- Results logged; summary available in scraping log

### 9.3 Saved Search Matching
**Priority:** P2

Runs after new listings are approved.

**Acceptance criteria:**
- Finds all saved searches with `notify_on_match=true`
- Evaluates each against newly approved listings
- Queues digest email for users with matches (one email per user per day max)
- Does not re-notify for listings already notified

### 9.4 Invite Expiration
**Priority:** P1

**Acceptance criteria:**
- Daily job marks invites past `expires_at` as inactive
- Expired invite links return a clear "this invite has expired" message

### 9.5 Notification Emails
**Priority:** P1

**Acceptance criteria:**
- Email sent for: company approved/rejected, listing approved/rejected, invite received, application received, application status changed, saved search match
- Plain text + HTML versions
- From address configurable via site config
- Delivery failures logged, not retried indefinitely

---

## 10. Non-Functional Requirements

### 10.1 Performance
- Page load under 2 seconds on a $10/month VPS for typical queries
- Search results under 500ms with GIN index on FTS columns
- HTMX partial updates feel instant (< 200ms for simple operations)

### 10.2 Security
- All user input sanitized before storage
- Job descriptions rendered with HTML sanitization (no XSS)
- CSRF protection on all state-changing forms
- OAuth state parameter validated to prevent CSRF on auth flow
- Admin and moderator routes protected by role check dependency
- Rate limiting on auth endpoints (prevent OAuth abuse)

### 10.3 Accessibility
- Semantic HTML throughout
- HTMX updates announce to screen readers via `aria-live`
- Color contrast meets WCAG AA
- Keyboard navigable

### 10.4 Forkability
- All community-specific values (site name, served cities, branding) configurable without code changes
- `setup.sh` gets a new deployment to running state in under 15 minutes
- README documents the full setup process clearly

---

## Build Order

Suggested implementation sequence to reach a functional v1:

**Phase 1 — Foundation**
1. Project scaffolding, Docker Compose, Caddy, database migrations
2. Auth (OAuth sign-in/out, session management)
3. Database models and seed data
4. Basic job listing browse and search (anonymous)
5. Job detail page

**Phase 2 — Employer Workflow**
6. Company creation and approval queue
7. Job posting form
8. Job listing approval queue
9. Moderator dashboard
10. Company invite system

**Phase 3 — Admin & Operations**
11. Admin config panel
12. Served cities management
13. Reference data management
14. Scraper source management UI
15. Link checker background job
16. Scraper runner integration

**Phase 4 — User Features**
17. Save / hide jobs
18. Saved searches
19. User profile (basic)
20. Notifications (in-app + email)

**Phase 5 — Applications**
21. In-platform application form
22. Employer application management
23. Applicant status tracking

**Phase 6 — Profile & Community**
24. User skills and certifications
25. Skill demand view
26. Job market snapshot
