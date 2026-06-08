# Deferred Items

Items that were deliberately skipped during a phase but not forgotten. Each entry notes which phase it belongs to, its spec priority, and why it was deferred.

---

## Phase 2 — Employer Workflow

### Manage Company Profile (spec 4.4) — P2
`company_admin` can edit their company's own details: name, description, website, social links, industry, size, type.

Currently the `/companies/{id}/manage` page handles team and invites only. There is no form for editing the company record itself.

**What to build:** Add `GET/POST /companies/{id}/edit` with a form pre-populated from the `Company` model. Reuse the `.form-card` / `.form-group` CSS already in place.

---

### Moderator dashboard — recent activity log (spec 6.4) — P1
The dashboard shows queue counts and quick links but is missing the "last 20 approvals/rejections by any moderator" activity log called for in the spec.

**What to build:** Query the last 20 rows across companies, roles, and job listings where `approved_at IS NOT NULL` or `defunct = true` (for rejections), ordered by timestamp descending. Render as a simple chronological list on the dashboard.

---
