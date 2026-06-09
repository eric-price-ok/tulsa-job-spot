# Running the Test Suite

Tests run against a dedicated `tulsajobspot_test` database — never the production database. All tests run inside the existing app Docker container, so no separate Python environment is needed.

---

## One-Time Setup

These steps only need to be done once (or repeated after a full container rebuild).

**1. Confirm your container names**

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

You should see containers named `tulsa-job-spot-app-1` and `tulsa-job-spot-db-1`. If yours differ, substitute your actual names in the commands below.

**2. Create the test database**

```bash
docker exec tulsa-job-spot-db-1 psql -U tulsajobspot -c "CREATE DATABASE tulsajobspot_test;"
```

**3. Install dev dependencies inside the app container**

```bash
docker exec tulsa-job-spot-app-1 pip install pytest pytest-asyncio
```

These are not in the production requirements, so they must be installed after any container rebuild.

---

## Running the Tests

```bash
docker exec tulsa-job-spot-app-1 \
  env DATABASE_URL=postgresql+asyncpg://tulsajobspot:tulsajobspot@db:5432/tulsajobspot_test \
  python -m pytest -v
```

The `DATABASE_URL` override is required. Without it, pytest would inherit the production database URL from the container environment and run against live data.

---

## Reading the Output

**All passing — safe to proceed:**

```
============================= test session starts ==============================
platform linux -- Python 3.12.x, pytest-9.x.x
asyncio: mode=Mode.AUTO
collected 3 items

tests/test_smoke.py::test_home_redirects_to_jobs PASSED               [ 33%]
tests/test_smoke.py::test_jobs_page_loads PASSED                      [ 66%]
tests/test_smoke.py::test_admin_requires_auth PASSED                  [100%]

============================== 3 passed in 2.3s ===============================
```

Every test shows `PASSED` and the final line reads `N passed`. This means the code is working correctly and it is safe to keep the changes.

**A failure — revert the checkpoint:**

```
FAILED tests/test_smoke.py::test_jobs_page_loads - AssertionError: assert 500 == 200
```

Any `FAILED` or `ERROR` in the output means something is broken. The line immediately below the `FAILED` marker shows the exact assertion that did not hold. Revert to your checkpoint and share the output so the issue can be diagnosed.

**An error during setup (not a test failure):**

```
ERROR at setup of test_jobs_page_loads - ConnectionRefusedError
```

`ERROR` during setup means a fixture failed before the test ran — usually the test database doesn't exist or the container name is wrong. This is a configuration problem, not a code problem. Re-run the one-time setup steps above.

---

## Useful Variations

Run a single test file:
```bash
docker exec tulsa-job-spot-app-1 \
  env DATABASE_URL=postgresql+asyncpg://tulsajobspot:tulsajobspot@db:5432/tulsajobspot_test \
  python -m pytest tests/test_smoke.py -v
```

Stop on the first failure (faster feedback):
```bash
docker exec tulsa-job-spot-app-1 \
  env DATABASE_URL=postgresql+asyncpg://tulsajobspot:tulsajobspot@db:5432/tulsajobspot_test \
  python -m pytest -x -v
```

---

## After a Git Pull / Deploy

If you pull new code and restart containers:

1. The test database persists (it is in the same Docker volume as the main database), so you do not need to recreate it.
2. Re-run step 3 (pip install) if the container was rebuilt, since dev dependencies are not persisted in the image.
3. Run the test suite before deciding whether to keep or revert the deployment.
