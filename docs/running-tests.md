# Running the Test Suite

Tests run inside the existing app Docker container — no separate Python environment is needed.

---

## Does this run against production?

**Yes, unless you pass a `DATABASE_URL` override.**

Inside the container, the `.env` file sets `DATABASE_URL` to the production database. The conftest fallback (a local test database) is only effective when running pytest outside Docker. To be safe, always pass the override shown below.

The current test suite happens to be safe against production even without the override — the security/slug tests are pure unit tests with no database access, and the smoke tests are read-only GETs. However, integration tests (like the company fixtures in `test_company.py`) INSERT rows before rolling them back, and could hit unique-constraint conflicts on the production schema. Always use the test database for the full suite.

---

## Setup

### 1. Confirm your container names

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

You should see services named `app` and `db`. The commands below use `docker compose exec`, which targets services by name (not container name).

### 2. Clone production data into the test database

The integration tests run against a copy of the production database. All writes roll back after each test via database-level savepoints — production data is never modified.

Run this before each test session to get a fresh snapshot:

```bash
# Drop and recreate the test database
docker compose exec db psql -U tulsajobspot postgres \
  -c "DROP DATABASE IF EXISTS tulsajobspot_test;"
docker compose exec db psql -U tulsajobspot postgres \
  -c "CREATE DATABASE tulsajobspot_test;"

# Copy production data into it
docker compose exec db bash -c \
  "pg_dump -U tulsajobspot tulsajobspot | psql -U tulsajobspot tulsajobspot_test"
```

This is safe to run while the app is live — `pg_dump` takes a consistent snapshot without locking the production database.

### 3. Install dev dependencies inside the app container

```bash
docker compose exec app pip install pytest pytest-asyncio
```

These are not in the production requirements. Re-run this after any container rebuild.

---

## Running the Tests

```bash
docker compose exec \
  -e DATABASE_URL=postgresql+asyncpg://tulsajobspot:tulsajobspot@db:5432/tulsajobspot_test \
  app pytest -v
```

The `DATABASE_URL` override is required when running the full suite. Without it, pytest inherits the production database URL from the container environment.

---

## Reading the Output

**All passing — safe to proceed:**

```
============================= test session starts ==============================
platform linux -- Python 3.12.x, pytest-9.x.x
asyncio: mode=Mode.AUTO
collected 39 items

tests/test_company.py::test_active_company_profile_loads PASSED          [  2%]
tests/test_company.py::test_defunct_company_hidden_from_anon PASSED      [  5%]
tests/test_company.py::test_defunct_company_visible_to_staff PASSED      [  7%]
tests/test_security.py::test_slug_basic PASSED                           [ 10%]
...
tests/test_smoke.py::test_home_redirects_to_jobs PASSED                  [ 97%]
tests/test_smoke.py::test_jobs_page_loads PASSED                         [100%]

============================== 39 passed in 2.5s ===============================
```

Every test shows `PASSED` and the final line reads `N passed`.

**A failure — revert the checkpoint:**

```
FAILED tests/test_company.py::test_defunct_company_hidden_from_anon - AssertionError: assert 200 == 404
```

Any `FAILED` or `ERROR` in the output means something is broken. The line immediately below the `FAILED` marker shows the exact assertion that did not hold. Revert to your checkpoint and share the output so the issue can be diagnosed.

**An error during setup (not a test failure):**

```
ERROR at setup of test_active_company_profile_loads - ConnectionRefusedError
```

`ERROR` during setup means a fixture failed before the test ran — usually the test database doesn't exist or the DATABASE_URL is pointing to production. Re-run the setup steps above.

---

## Useful Variations

Run only the fast unit tests (no database needed, safe on any environment):
```bash
docker compose exec app pytest tests/test_security.py -v
```

Run a single test file with the test database:
```bash
docker compose exec \
  -e DATABASE_URL=postgresql+asyncpg://tulsajobspot:tulsajobspot@db:5432/tulsajobspot_test \
  app pytest tests/test_company.py -v
```

Stop on the first failure (faster feedback):
```bash
docker compose exec \
  -e DATABASE_URL=postgresql+asyncpg://tulsajobspot:tulsajobspot@db:5432/tulsajobspot_test \
  app pytest -x -v
```

---

## After a Git Pull / Deploy

1. If the container was rebuilt, re-run step 3 (pip install).
2. If the pull included a new migration, re-clone the test database (step 2) so its schema matches production.
3. Run the test suite before deciding whether to keep or revert the deployment.
