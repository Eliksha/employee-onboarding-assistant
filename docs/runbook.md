# Runbook: OnboardAI (local and Docker)

Operational guide for running, checking and troubleshooting OnboardAI locally. Installation steps are in the root [README](../README.md); this runbook assumes they are complete. Azure operations are not covered because nothing is deployed to Azure yet.

All commands are PowerShell and run from the project root unless stated otherwise.

## 1. Start and stop

### Local development

| Action | Command |
|---|---|
| Activate environment | `.\.venv\Scripts\Activate.ps1` |
| Start backend | `python -m uvicorn backend.main:app --reload --port 8000` |
| Start frontend | `cd frontend; npm run dev` (http://localhost:5173) |
| Stop | `Ctrl+C` in each terminal |

### Docker Compose

| Action | Command |
|---|---|
| Set container DB password (each new shell) | `$env:DOCKER_PG_PASSWORD = "<local value>"` |
| Build and start, wait for health | `docker compose up -d --build --wait` |
| Status | `docker compose ps` |
| Restart backend only | `docker compose restart backend` |
| Stop, keep data | `docker compose down` |
| Stop and **delete** container DB and logs | `docker compose down -v` |

Use a separate project name for experiments so the volumes stay isolated, for example `docker compose -p onboardai-test up -d --build --wait` and `docker compose -p onboardai-test down -v`.

## 2. Accounts and sign-in

Accounts are never created automatically. Provision them once per database (local or Docker):

| Action | Command |
|---|---|
| Add auth tables to an existing database (additive) | `$env:PYTHONPATH = "."; python backend/migrations/004_auth_tables.py` |
| Create/update an employee account (hidden password prompt) | `python -m backend.manage_accounts set --email aarav.sharma@example.com --employee-id EMP001` |
| Create an administrator | `python -m backend.manage_accounts set --email admin@novatech.example --role admin` |
| List accounts (no secrets) | `python -m backend.manage_accounts list` |
| Disable an account (ends its sessions) | `python -m backend.manage_accounts disable --email <email>` |
| Same commands in Docker | prefix with `docker compose exec backend` (add `-e NAME` and `--password-env NAME` for non-interactive use) |

Re-running `set` with a new password resets the password and signs the account out everywhere. Passwords must be at least 12 characters.

## 3. Health checks

| Check | Expected |
|---|---|
| `curl http://localhost:8000/health` (local or Docker) | `{"status":"ok","database":"ok"}` (HTTP 200) |
| `curl http://localhost:8080/api/health` (Docker, through nginx) | `{"status":"ok","database":"ok"}` (HTTP 200) |
| `curl http://localhost:8080/api/employees/EMP001` | 401 when not signed in (proves the API is up and protected); sign in through the UI to check data access |
| `docker compose ps` | `db`, `backend`, `frontend` all `(healthy)` |

`/health` is **database-aware**: it runs `SELECT 1` with a 3-second timeout (`HEALTH_DB_TIMEOUT_SECONDS`) and returns HTTP 503 `{"status":"unavailable","database":"unavailable","detail":...}` when the database is unreachable; the Docker backend container then becomes `unhealthy` until the database is back (it is not restarted automatically). The log shows `health check: database unavailable (<error type>)` without connection details.

## 4. Logs and request tracing

- Local: `logs/app.log` (rotating, 1 MB x 3 backups) and the console.
- Docker: `docker compose logs backend` (console) and `/app/logs/app.log` on the `logs` volume.
- Format: `time | LEVEL | rid=<request id> | message`. Every HTTP response carries an `X-Request-ID` header, and 500 responses include the same `request_id` in the JSON body. Search the log for that ID to find the server-side cause and traceback.
- Question text, API keys, passwords, session identifiers and CSRF tokens are not logged. Login events: `login succeeded user_id=... role=...`, `login failed account=<fingerprint>`, `login rate-limited account=<fingerprint>`, `logout user_id=...` (the fingerprint is a short one-way hash of the email).

## 5. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Chat returns 503 "The AI service is temporarily unavailable" | LLM unreachable, invalid `GROQ_API_KEY`, wrong `GROQ_BASE_URL`/`MODEL_NAME`, rate limit | Check `.env`; look for `LLM unavailable:` in the log (for example `Error code: 401 - Invalid API Key` or `Connection error.`) |
| 500 "Something went wrong on our side" on employee pages | Database unavailable | Search the log for the `request_id`; `psycopg2.OperationalError` means PostgreSQL is down or unreachable. In Docker, `docker compose ps db` then `docker compose start db`; the backend reconnects automatically |
| `FileNotFoundError: Database not found` (SQLite) | `data/app.db` not created or not migrated | Run the SQLite steps in the README (init + migrations 001-003) |
| `ModuleNotFoundError: No module named 'backend'` when running migration 003 | Project root not on the Python path | `$env:PYTHONPATH = "."` then rerun |
| Chat always answers "I could not find this in the NovaTech employee handbook" | Question outside the handbook, or retrieval score below the gate | Expected for unknown topics; see `docs/rag_eval_report.md` for known retrieval gaps |
| Chat 500 with `PermissionError` or a FAISS `could not open` error | FAISS index missing (the backend then tries to build it) or the index folder is read-only | Build the index locally with `python -m backend.services.ingest` **before** `docker compose up`; the Docker mount is read-only by design |
| `required variable DOCKER_PG_PASSWORD is missing a value` | Variable not set in the current shell | `$env:DOCKER_PG_PASSWORD = "<local value>"` |
| Docker DB has no data / seed changes not applied | Init scripts run only on an **empty** volume | `docker compose down -v` (deletes container data), then `up` again |
| `port is already allocated` / port in use | Another process on 8000, 8080 or 5173 | Stop it, or set `$env:BACKEND_PORT` / `$env:FRONTEND_PORT` for Docker |
| Frontend shows "Profile unavailable. Start the FastAPI backend." | Backend not running or proxy target wrong | Start the backend; the dev proxy targets `http://127.0.0.1:8000` |
| 422 "Invalid input (...)" | Request failed validation (for example question longer than 500 characters) | Correct the input; the message names the field |
| Login page says "Invalid email or password." | Wrong password, unknown email, or disabled account (deliberately indistinguishable) | Check with `manage_accounts list`; reset with `manage_accounts set` |
| "Too many failed sign-in attempts" (429) | 5 failures for the email or 20 for the client IP within 15 minutes | Wait for the `Retry-After` period, or restart the backend (the limiter is in memory) |
| Redirected to login with "Your session has ended" | Session expired (8 h absolute / 60 min idle), signed out elsewhere, or password changed | Sign in again |
| 403 "Missing or invalid CSRF token." | Client did not send `X-CSRF-Token` (for example a raw `curl` POST) | Use the UI, or send the `csrf_token` from `/auth/login` in the header |
| 403 "You can only access your own records." | Request for another employee's ID | Expected: employees only see their own data |
| Backend fails to start: "Authentication tables are missing in PostgreSQL" | Existing PostgreSQL database predates authentication | Run migration 004 (section 2) |
| Docker: login works but no accounts exist | Fresh container database | Provision accounts with `docker compose exec backend python -m backend.manage_accounts set ...` |

## 6. Data and index operations

- **Rebuild the FAISS index** (only after changing `data/raw`): `python -m backend.services.ingest`. This overwrites `data/index`. `POST /ingest` does the same but requires an administrator session and CSRF token.
- **Reset Docker data**: `docker compose down -v` removes the container database, accounts, sessions, chat history, tickets and logs. The local PostgreSQL and the FAISS index are not affected.
- **Back up a local SQLite database** before experiments: `Copy-Item data\app.db data\app_backup_<date>.db`.

## 7. Tests

| Command | Notes |
|---|---|
| `python -m pytest -q` | Always uses a temporary SQLite database and temporary log folder; PostgreSQL connections are blocked; test accounts get random passwords per run |
| `python -m pytest -q tests/integration/test_postgres_roles.py` | Live role, permission and isolation-attack tests; skipped unless `ONBOARDAI_PG_TEST_ADMIN_DSN` points at a disposable PostgreSQL (see section 9) |
| `cd frontend; npm test; npm run build` | Frontend helper tests and production build |
| `python -m scripts.rag_eval` | Live LLM evaluation; **rewrites `docs/rag_eval_report.md`**. Use `--no-llm` for deterministic checks only |

## 8. Safety rules

- Never commit `.env`; never paste output of `docker compose config` (without `--quiet`) because it shows resolved secrets.
- Do not reuse a real password for `DOCKER_PG_PASSWORD`.
- Keep ports bound to `127.0.0.1`; serve over HTTPS (and set `SESSION_COOKIE_SECURE=true`) before any non-local use.
- Never put account passwords in files, scripts or chat; use the hidden prompt or a temporary environment variable.
- Use synthetic data only.
- The backend must not connect as a PostgreSQL superuser outside local development (section 9).

## 9. Database roles (least privilege)

The application must not connect to PostgreSQL as a superuser. Migration 005 creates two roles; schema migrations keep running as the database owner.

| Role | Used by | Privileges |
|---|---|---|
| `onboardai_app` | FastAPI app (`PG_USER`) | SELECT on application tables; INSERT on messages, feedback, escalations, tickets, user_accounts, user_sessions; UPDATE only on `checklist.done`, `checklist_assignments.done`, `user_sessions.last_seen_at`, `user_accounts(password_hash, employee_id, role, is_active, updated_at)`; DELETE only on user_sessions. No DDL, TRUNCATE, role or database creation; does not bypass row-level security; no access to the signing-key or verifier schemas. Role defaults: `statement_timeout=15s`, idle-in-transaction 60 s, 20 connections |
| `onboardai_reader` | SQL-agent / read-only lookups (`PG_READER_USER`) | SELECT only on employees, leave_balances, assets, payroll_calendar, checklist, checklist_assignments, tickets. No access to accounts, sessions, chat history, feedback, escalations or the signing key. Role defaults: `default_transaction_read_only=on`, `statement_timeout=5s`, idle-in-transaction 10 s, 10 connections. Row-level security on the five employee tables shows only the employee of a **signed scope** (below) |

**Signed employee scope.** The reader's row-level security policies call `onboardai_rls.current_employee()`, a `SECURITY DEFINER` function (search path pinned) that returns the employee only if `app.scope_sig` is a valid HMAC-SHA256 over `v1:<employee>:<connection id>:<expiry>`. The connection id is the server's backend PID plus its start time, so a signature cannot be replayed from another connection, and it expires after 60 seconds. The key lives in `onboardai_private.scope_key`; only the owner can reach that schema. The backend signs each read-only transaction with `PG_SCOPE_SECRET` (the same secret migration 005 stored). Changing `app.*` settings with `SET` or `set_config` therefore removes access instead of widening it. A wrong or missing signature means no employee rows (fail closed). The backend refuses to start when `PG_READER_USER` is set without a `PG_SCOPE_SECRET` of at least 32 characters.

**Statement validation.** Every read-only query is parsed with PostgreSQL's own parser (pglast) and must be exactly one SELECT built from allow-listed syntax, tables (the reader's seven), functions and cast types. `SET`, `DO`, `set_config`/`current_setting` in any spelling (quoted, schema-qualified, Unicode-escaped), data-modifying CTEs, `SELECT INTO`, `FOR UPDATE`, functions in `FROM` and catalog tables are rejected before reaching the database.

The backend also sets READ ONLY transactions, `SQL_AGENT_STATEMENT_TIMEOUT_MS` (default 5000) and `SQL_AGENT_MAX_ROWS` (default 200) on every read-only query, and `PG_STATEMENT_TIMEOUT_MS` (default 10000) on application connections. At startup the backend logs a warning (development) or refuses to start (`APP_ENV=production`) when it connects as a superuser or has no reader role.

### Provisioning (requires the database owner; changes the live database - get approval first)

Docker stack (PowerShell, project root). The running backend image predates migration 005, so rebuild it first; rebuilding does not touch the database volume:

```powershell
docker compose build backend
$env:DOCKER_PG_PASSWORD = "<existing container DB password>"   # unchanged
$env:ONBOARDAI_APP_DB_PASSWORD = "<new random value, 16+ chars>"
$env:ONBOARDAI_READER_DB_PASSWORD = "<new random value, 16+ chars>"
$env:ONBOARDAI_SCOPE_SECRET = "<new random value, 32+ chars>"   # e.g. python -c "import secrets;print(secrets.token_urlsafe(48))"

# 1. Read-only check of the current state (exit 1 = roles missing / problems listed)
docker compose run --rm --no-deps -e ONBOARDAI_SCOPE_SECRET backend python backend/migrations/005_least_privilege_roles.py --verify
# 2. Dry run: prints the plan with passwords and key material redacted; executes nothing
docker compose run --rm --no-deps -e ONBOARDAI_APP_DB_PASSWORD -e ONBOARDAI_READER_DB_PASSWORD -e ONBOARDAI_SCOPE_SECRET backend python backend/migrations/005_least_privilege_roles.py
# 3. Apply (one transaction, verified before commit; idempotent)
docker compose run --rm --no-deps -e ONBOARDAI_APP_DB_PASSWORD -e ONBOARDAI_READER_DB_PASSWORD -e ONBOARDAI_SCOPE_SECRET backend python backend/migrations/005_least_privilege_roles.py --apply
# 4. Switch the backend to the new roles (a credential change for the app) and recreate only the backend
$env:DOCKER_PG_APP_USER = "onboardai_app";       $env:DOCKER_PG_APP_PASSWORD = $env:ONBOARDAI_APP_DB_PASSWORD
$env:DOCKER_PG_READER_USER = "onboardai_reader"; $env:DOCKER_PG_READER_PASSWORD = $env:ONBOARDAI_READER_DB_PASSWORD
$env:DOCKER_PG_SCOPE_SECRET = $env:ONBOARDAI_SCOPE_SECRET
docker compose up -d --no-deps backend
```

The migration runs as the owner account from `PG_USER`/`PG_PASSWORD` inside the container (in Docker that is `onboardai`, from `DOCKER_PG_PASSWORD`). The owner must be a superuser or a member of `pg_read_all_stats`, because the verifier reads `pg_stat_activity.backend_start`. For a local PostgreSQL, set `PG_ADMIN_USER`/`PG_ADMIN_PASSWORD` to the table owner and run the same script with `$env:PYTHONPATH = "."`, then set `PG_USER`/`PG_PASSWORD`, `PG_READER_USER`/`PG_READER_PASSWORD` and `PG_SCOPE_SECRET` in `.env`.

### Durable secrets file (used for the live activation)

`$env:` variables last for one PowerShell session. If a later `docker compose up` runs without `DOCKER_PG_APP_*` / `DOCKER_PG_READER_*` / `DOCKER_PG_SCOPE_SECRET`, the backend silently falls back to the owner account. The live stack therefore keeps these values in a file **outside the repository**, readable only by the Windows account that runs Docker:

`C:\Users\Administrator\Desktop\employee-onboarding-assistant-day31\onboardai_secrets\phase1.env` (ACL: owner only, inheritance disabled)

It holds `BACKEND_PORT=8001` and `FRONTEND_PORT=8080` (the ports the stack runs on), the existing `DOCKER_PG_PASSWORD`, and the new `ONBOARDAI_APP_DB_PASSWORD`, `ONBOARDAI_READER_DB_PASSWORD` and `ONBOARDAI_SCOPE_SECRET`. After `--apply` the switch variables are added: `DOCKER_PG_APP_USER`/`_PASSWORD`, `DOCKER_PG_READER_USER`/`_PASSWORD`, `DOCKER_PG_SCOPE_SECRET`. Never print, copy into the repo, or commit this file; store its values in a password manager as well.

Load it literally (no expansion) and pass it to every compose command:

```powershell
$secrets = 'C:\Users\Administrator\Desktop\employee-onboarding-assistant-day31\onboardai_secrets\phase1.env'
Get-Content $secrets | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object { $k, $v = $_ -split '=', 2; Set-Item "Env:$k" $v }
docker compose --env-file $secrets <command>      # e.g. ps, up -d --no-deps backend, run ... (steps above)
```

In Windows PowerShell 5.1, compose progress lines on stderr (`Container ... Creating`) may appear as `NativeCommandError`. They are not failures; check the exit code.

**Rollback:** remove (or comment out) the `DOCKER_PG_APP_*`, `DOCKER_PG_READER_*` and `DOCKER_PG_SCOPE_SECRET` lines in the secrets file, clear them from the shell, and run `docker compose --env-file $secrets up -d --no-deps backend`. Equivalently, without the file: unset the `DOCKER_PG_APP_*`, `DOCKER_PG_READER_*` and `DOCKER_PG_SCOPE_SECRET` variables and run `docker compose up -d --no-deps backend`. The backend connects as the owner again; the owner bypasses row-level security, so nothing else changes. The roles, key and policies can stay in place.

**Rotation:** role passwords with `--apply --reset-passwords`. Scope key with `--apply --rotate-scope-secret` and a new `ONBOARDAI_SCOPE_SECRET`, then immediately set the same value in `DOCKER_PG_SCOPE_SECRET` and recreate the backend. Between the two steps, employee-scoped reads return no rows (fail closed). Keep the secret in a password manager; losing it only requires a rotation.

**What `--apply` changes:** creates the two roles (passwords sent SCRAM-hashed) and sets their defaults for this database; `REVOKE TEMPORARY ON DATABASE ... FROM PUBLIC`; `REVOKE CREATE ON SCHEMA public FROM PUBLIC`; resets and re-grants the privileges of the two roles only; creates the owner-only schema `onboardai_private` with the `scope_key` table (the key is inserted once and never replaced without `--rotate-scope-secret`); creates schema `onboardai_rls` with `connection_id()` and the `SECURITY DEFINER` `current_employee()` (EXECUTE for the reader only); enables row-level security on employees, leave_balances, assets, checklist_assignments and tickets, with one policy per role (the reader policy uses the signed scope). No application data is changed, nothing is dropped, and existing role passwords are never changed unless `--reset-passwords` is given.

**New tables:** add their grants to `backend/services/db_roles.py` (`tests/unit/test_db_roles.py` fails until every table in the schema is covered) and re-run `--apply`.

**Live permission and attack tests** (disposable server only; never the stack database):

```powershell
docker run -d --rm --name onboardai-roletest -e POSTGRES_PASSWORD=<random> -p 127.0.0.1:55439:5432 postgres:16-alpine
$env:ONBOARDAI_PG_TEST_ADMIN_DSN = "postgresql://postgres:<random>@127.0.0.1:55439/postgres"
python -m pytest -q tests/integration/test_postgres_roles.py
docker stop onboardai-roletest
```
