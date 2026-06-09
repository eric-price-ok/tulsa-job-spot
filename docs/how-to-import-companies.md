# How to Import Companies from CSV

Site admins can bulk-import companies from a CSV file via the Admin dashboard at
`/admin/import-companies`. The import does a dry run first so you can review what will be
created before anything is saved.

---

## Access

Navigate to **Admin → Data Management → Import Companies** or go directly to
`https://tulsajobspot.com/admin/import-companies`.

---

## How the Import Works

1. Upload a CSV file.
2. The system parses every row and shows you a preview:
   - **To Import** — rows that will create new company records.
   - **Skipped** — rows where a company with the same `common_name` already exists (case-insensitive). These are silently skipped to prevent duplicates.
   - **Errors** — rows with missing required values or unrecognized lookup values. Fix these in your CSV and re-upload if you want them included.
3. Review the preview and click **Confirm Import** to save the records.

All imported companies are immediately **approved** and visible on the site. The importing admin
is recorded as the approver.

---

## CSV Format

The file must be a plain CSV (comma-separated) with **column headers in the first row**.

- UTF-8 or UTF-8-with-BOM encoding is supported.
- Column names are case-insensitive and leading/trailing whitespace is ignored.
- Columns can be in any order — only the names matter.

### Required Columns

| Column | Description |
|--------|-------------|
| `common_name` | The company's display name (e.g. `ONEOK`). Must be unique — rows where a company with this name already exists are skipped. |
| `company_type` | Must exactly match one of the company type names configured in the system (e.g. `Private`, `Public`, `Non-Profit`). Case-insensitive. |

### Optional Columns

| Column | Description |
|--------|-------------|
| `legal_name` | Full legal entity name (e.g. `ONEOK, Inc.`). Leave blank if the same as `common_name`. |
| `website` | Company website. Must include the scheme: `https://example.com`. Invalid or non-http(s) URLs are ignored. |
| `jobboard` | URL of the company's own job board, if separate from the main website. |
| `description` | A short description of the company shown on their profile page. Plain text. |
| `company_size` | Approximate employee count range. Accepted values: `1-10`, `11-50`, `51-200`, `201-500`, `501-1000`, `1001+`. |
| `date_founded` | Year the company was founded. Format: `YYYY-MM-DD` (e.g. `1906-01-01`). Use January 1 if only the year is known. |
| `date_closed` | Date the company closed. Format: `YYYY-MM-DD`. Only include for companies that are no longer operating. |

---

## Example CSV

```csv
common_name,legal_name,company_type,website,company_size,description,date_founded
ONEOK,ONEOK Inc.,Public,https://www.oneok.com,1001+,Midstream natural gas operator headquartered in Tulsa.,1906-01-01
Williams Companies,The Williams Companies Inc.,Public,https://www.williams.com,1001+,Energy infrastructure company.,1908-01-01
QuikTrip,,Private,https://www.quiktrip.com,1001+,Convenience store and gas station chain.,1958-01-01
Vast Bank,,Private,https://www.vast.bank,51-200,,2018-06-01
```

### Notes on the example

- `legal_name` can be left blank (as with QuikTrip and Vast Bank) — use empty columns, not missing ones.
- `description` is optional; an empty value is fine.
- Only `date_founded` is included here; `date_closed`, `jobboard`, and `company_size` can be omitted entirely or left blank.

---

## Handling Errors

| Error | Fix |
|-------|-----|
| `Missing required column(s): common_name` | Add a `common_name` header to your CSV. |
| `Missing required column(s): company_type` | Add a `company_type` header to your CSV. |
| `common_name is blank` | Fill in the company name for that row. |
| `unknown company_type "Startup"` | Use a type name that exists in the system. See the upload page for the current list. |
| `invalid date_founded "01/01/1906"` | Use `YYYY-MM-DD` format: `1906-01-01`. |

Rows with errors are listed in the preview and skipped during the import. All other valid rows
are still imported — you do not need to fix errors before confirming if you are comfortable
skipping those rows.

---

## Duplicate Handling

A row is skipped (not an error) if a company with the same `common_name` already exists in the
database. The comparison is **case-insensitive**, so `ONEOK`, `oneok`, and `Oneok` all match the
same existing record.

Duplicate rows **within the same CSV file** are also deduplicated — only the first occurrence of
a name is imported.

---

## After Import

Imported companies:
- Appear immediately on the public Companies browse page.
- Have no `company_admin` — admins can assign one via the moderator queue or by editing the record directly.
- Can be edited by an admin via the company edit page (`/companies/{slug}/edit`).
- Cannot be deleted from the UI; mark as `defunct` to hide from browsing.
