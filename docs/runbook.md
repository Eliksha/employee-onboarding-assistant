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
| Chat returns 503 "The AI service is temporarily unavailable" | Azure OpenAI not configured, invalid key, wrong endpoint or deployment, rate limit | Check the `AZURE_OPENAI_*` values in the secrets file; look for `LLM unavailable:` in the log (for example `Azure OpenAI is not configured`, `AuthenticationError (HTTP 401)`, `NotFoundError (HTTP 404)` = wrong deployment, `RateLimitError (HTTP 429)`, `APIConnectionError`) |
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

- **Rebuild the FAISS index** (only after changing `data/raw`): `python -m backend.services.ingest` on the host. It builds a new validated version under `data/index/versions/` and activates it atomically; the previous version stays if anything fails (section 10). `POST /ingest` does the same but requires an administrator session and CSRF token, and returns 409 in Docker because the index is mounted read-only.
- **Import HR reference data from CSV:** `python -m scripts.import_csv data/csv` (dry run) as the dedicated import role (section 10).
- **Reset Docker data**: `docker compose down -v` removes the container database, accounts, sessions, chat history, tickets and logs. The local PostgreSQL and the FAISS index are not affected.
- **Back up a local SQLite database** before experiments: `Copy-Item data\app.db data\app_backup_<date>.db`.

## 7. Tests

| Command | Notes |
|---|---|
| `python -m pytest -q` | Always uses a temporary SQLite database and temporary log folder; PostgreSQL connections are blocked; test accounts get random passwords per run |
| `python -m pytest -q tests/integration/test_postgres_roles.py tests/integration/test_postgres_m4.py tests/integration/test_postgres_m5.py` | Live role, permission, isolation-attack, import-role, CSV-import, schema-dictionary and migration-007 tests; skipped unless `ONBOARDAI_PG_TEST_ADMIN_DSN` points at a disposable PostgreSQL (see section 9) |
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

`$env:` variables last for one PowerShell session. If a later `docker compose up` runs without `DOCKER_PG_APP_*` / `DOCKER_PG_READER_*` / `DOCKER_PG_SCOPE_SECRET`, the backend falls back to the owner account, which it now **refuses** (fail closed: superuser/BYPASSRLS roles are rejected at startup, see `ALLOW_PRIVILEGED_DB_CONNECTION` below). The live stack therefore keeps these values in a file **outside the repository**, readable only by the Windows account that runs Docker:

`C:\Users\Administrator\Desktop\employee-onboarding-assistant-day31\onboardai_secrets\phase1.env` (ACL: owner only, inheritance disabled)

It holds `BACKEND_PORT=8001` and `FRONTEND_PORT=8080` (the ports the stack runs on), the existing `DOCKER_PG_PASSWORD`, and the new `ONBOARDAI_APP_DB_PASSWORD`, `ONBOARDAI_READER_DB_PASSWORD` and `ONBOARDAI_SCOPE_SECRET`. After `--apply` the switch variables are added: `DOCKER_PG_APP_USER`/`_PASSWORD`, `DOCKER_PG_READER_USER`/`_PASSWORD`, `DOCKER_PG_SCOPE_SECRET`. Never print, copy into the repo, or commit this file; store its values in a password manager as well.

Load it literally (no expansion) and pass it to every compose command:

```powershell
$secrets = 'C:\Users\Administrator\Desktop\employee-onboarding-assistant-day31\onboardai_secrets\phase1.env'
Get-Content $secrets | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object { $k, $v = $_ -split '=', 2; Set-Item "Env:$k" $v }
docker compose --env-file $secrets <command>      # e.g. ps, up -d --no-deps backend, run ... (steps above)
```

In Windows PowerShell 5.1, compose progress lines on stderr (`Container ... Creating`) may appear as `NativeCommandError`. They are not failures; check the exit code.

**Rollback:** remove (or comment out) the `DOCKER_PG_APP_*`, `DOCKER_PG_READER_*` and `DOCKER_PG_SCOPE_SECRET` lines in the secrets file, clear them from the shell, and run `docker compose --env-file $secrets up -d --no-deps backend`. Equivalently, without the file: unset the `DOCKER_PG_APP_*`, `DOCKER_PG_READER_*` and `DOCKER_PG_SCOPE_SECRET` variables and run `docker compose up -d --no-deps backend`. **Superseded (pre-Azure remediation S2):** the backend no longer starts as the owner, so this rollback now ends in a clear startup refusal. `docker-compose.yml` pins `ALLOW_PRIVILEGED_DB_CONNECTION` to `false`; the override is honoured only for local non-Docker runs with `APP_ENV=development`. Roll back by fixing the role credentials (`--apply --reset-passwords`), not by switching to the owner.

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

## 10. CSV import, schema dictionary and index versions (M4)

### Import role (migration 006; changes the live database - get approval first)

A dedicated login role `onboardai_importer` is used ONLY by the manual CSV import CLI, never by the running backend. It may SELECT/INSERT/UPDATE (listed columns only) the HR reference tables `employees`, `leave_balances`, `assets`, `payroll_calendar`, `checklist`, and only SELECT/INSERT `checklist_assignments` (an import never changes an employee's progress). No DELETE, TRUNCATE or DDL; no access to `user_accounts`, `user_sessions`, `messages`, `feedback`, `escalations`, `tickets` or the signing-key schemas. It has its own row-level-security policy; the app and reader roles are not changed. Requires migration 005.

```powershell
# 1. backup first (runbook section 9 pattern), then add ONBOARDAI_IMPORT_DB_PASSWORD (24+ random chars) to the secrets file
$secrets = "C:\Users\Administrator\Desktop\employee-onboarding-assistant-day31\onboardai_secrets\phase1.env"
docker compose --env-file $secrets run --rm --no-deps -e ONBOARDAI_IMPORT_DB_PASSWORD -e PG_ADMIN_USER=onboardai -e PG_ADMIN_PASSWORD=$env:DOCKER_PG_PASSWORD backend python backend/migrations/006_import_role.py            # dry run
docker compose --env-file $secrets run --rm --no-deps -e ONBOARDAI_IMPORT_DB_PASSWORD -e PG_ADMIN_USER=onboardai -e PG_ADMIN_PASSWORD=$env:DOCKER_PG_PASSWORD backend python backend/migrations/006_import_role.py --apply
docker compose --env-file $secrets run --rm --no-deps -e PG_ADMIN_USER=onboardai -e PG_ADMIN_PASSWORD=$env:DOCKER_PG_PASSWORD backend python backend/migrations/006_import_role.py --verify
```

Load the secrets file into the shell first (as in section 9) so `$env:DOCKER_PG_PASSWORD` and `ONBOARDAI_IMPORT_DB_PASSWORD` are set; values are never printed. Rollback: `DROP POLICY onboardai_importer_all ON <table>` for the four RLS tables, `REVOKE ALL ... FROM onboardai_importer`, `DROP ROLE onboardai_importer` (no data depends on it).

### CSV import

Files live in `data/csv/` (synthetic; identical to the seed). Format and rules: `backend/services/csv_import.py`. Dry run by default; `--apply` writes in ONE transaction and any invalid row aborts the whole import.

```powershell
docker compose --env-file $secrets run --rm --no-deps -v "${PWD}/data/csv:/app/data/csv:ro" -e ONBOARDAI_IMPORT_DB_USER=onboardai_importer -e ONBOARDAI_IMPORT_DB_PASSWORD backend python -m scripts.import_csv /app/data/csv            # dry run report
docker compose --env-file $secrets run --rm --no-deps -v "${PWD}/data/csv:/app/data/csv:ro" -e ONBOARDAI_IMPORT_DB_USER=onboardai_importer -e ONBOARDAI_IMPORT_DB_PASSWORD backend python -m scripts.import_csv /app/data/csv --apply
```

(`scripts/` is not baked into the image; mount it too with `-v "${PWD}/scripts:/app/scripts:ro"`, or run the CLI on the host with the PG_* settings pointing at the database.) Re-running the same files reports everything "unchanged". Rows that exist in the database but not in a file are only counted, never deleted. The CLI refuses superusers, BYPASSRLS roles and the app/reader roles.

### Schema dictionary

`backend/services/schema_dictionary.json` documents every table in schema `public` (columns, types, keys, relationships, personal-data/RLS/reader/import flags). Check it against a database (read-only): `python -m scripts.schema_dictionary --check`. `tests/integration/test_postgres_m4.py` checks it against a disposable PostgreSQL in CI. After any schema change, update the JSON (the check lists every difference).

### FAISS index versions (PDF canonical)

`data/raw/handbook.pdf` is the canonical handbook; `handbook.md` is a derived copy and is not indexed; `faqs.md` is indexed separately. Each build creates `data/index/versions/<id>/` (index, chunks, manifest), validates it, and only then atomically replaces `data/index/ACTIVE`. A failed build leaves the previous version active; the three newest versions are kept. Without `ACTIVE`, the legacy flat files `data/index/faiss.index` + `chunks.json` are used.

- **Rebuild (host only):** `python -m backend.services.ingest` (Docker mounts `data/index` read-only; an in-container rebuild or `POST /ingest` returns 409 and changes nothing).
- **Activation:** a running M4 backend picks up the new `ACTIVE` version on the next question (no restart); if the new version cannot be loaded it keeps serving the previous one and logs a warning. A pre-M4 backend ignores `ACTIVE` and keeps reading the legacy flat files.
- **Rollback:** write the previous version id into `ACTIVE` (`{"version": "<id>"}`), or delete `ACTIVE` to fall back to the legacy flat files.

## 11. Data integrity, feedback and escalation, security headers (M5)

### Migration 007 (changes the live database - get approval first)

Adds `escalations.employee_id` and `escalations.message_id`; foreign keys `messages.employee_id -> employees`, `feedback.message_id -> messages` (ON DELETE CASCADE), `escalations.employee_id -> employees`, `escalations.message_id -> messages` (ON DELETE SET NULL); `feedback.message_id NOT NULL`; CHECK constraints on `feedback.rating` (up/down), `messages.found` (0/1) and `escalations.status` (open/in_progress/resolved/closed); three indexes. One transaction; refuses without changing anything if existing rows would violate a constraint (they are listed); never deletes or rewrites data. Fresh Docker databases get the same state from `docker/postgres/04_integrity.sql`.

The migration is backward compatible with the M4 backend (new columns are nullable; the M4 code already satisfies every constraint), so it is applied FIRST. The M5 backend refuses to start on PostgreSQL until migration 007 is applied (clear startup error instead of failing requests).

```powershell
# load the secrets file into the shell first (section 9); take a backup (section 9)
docker compose --env-file $secrets run --rm --no-deps -e PG_ADMIN_USER=onboardai -e PG_ADMIN_PASSWORD=$env:DOCKER_PG_PASSWORD backend python backend/migrations/007_data_integrity.py --verify   # exit 1 = not applied yet
docker compose --env-file $secrets run --rm --no-deps -e PG_ADMIN_USER=onboardai -e PG_ADMIN_PASSWORD=$env:DOCKER_PG_PASSWORD backend python backend/migrations/007_data_integrity.py            # dry run
docker compose --env-file $secrets run --rm --no-deps -e PG_ADMIN_USER=onboardai -e PG_ADMIN_PASSWORD=$env:DOCKER_PG_PASSWORD backend python backend/migrations/007_data_integrity.py --apply
docker compose --env-file $secrets run --rm --no-deps -e PG_ADMIN_USER=onboardai -e PG_ADMIN_PASSWORD=$env:DOCKER_PG_PASSWORD backend python backend/migrations/007_data_integrity.py --verify   # exit 0
```

**Rollback:** first return the backend to the M4 image (it works with or without 007). Then, only if the constraints must go: `ALTER TABLE ... DROP CONSTRAINT` for the seven constraints listed above, `ALTER TABLE public.feedback ALTER COLUMN message_id DROP NOT NULL`, `DROP INDEX` for `idx_feedback_message_id`, `idx_escalations_employee_id`, `idx_escalations_message_id`. Dropping the two escalation columns deletes the attribution data and is not needed for the M4 backend; restore from the backup if a full return to the pre-M5 state is required.

### Feedback and escalation in chat

Every answer in the AI Assistant has Helpful / Not helpful buttons (`POST /feedback`) and "Escalate to HR/IT" (`POST /escalate` with the answer's `message_id`). Only the signed-in employee's own answers can be rated or escalated (403 otherwise; 404 for unknown messages); escalating the same answer twice returns the existing escalation. Escalations record the employee (`NULL` for administrator accounts). `GET /history` items carry two extra fields, `feedback` (latest rating or null) and `escalated` (bool). Escalations are simulated: they are stored for HR/IT and not sent anywhere.

### API documentation and security headers

- `/docs`, `/redoc` and `/openapi.json` are served only when `APP_ENV=development` (local runs), or when `API_DOCS=true` is set explicitly. `docker-compose.yml` sets `API_DOCS: "false"`; nginx additionally answers 404 for `/api/docs`, `/api/redoc` and `/api/openapi.json`.
- nginx adds to every response (pages and `/api`): Content-Security-Policy (`default-src 'self'`, scripts from self only, styles from self + Google Fonts, fonts from fonts.gstatic.com, `frame-ancestors 'none'`, `object-src 'none'`), X-Content-Type-Options nosniff, X-Frame-Options DENY, Referrer-Policy no-referrer, Permissions-Policy (camera, microphone, geolocation, payment disabled), Cross-Origin-Opener-Policy same-origin; `server_tokens off`. Check: `curl -sI http://localhost:8080/ | findstr /i "content-security x-frame x-content referrer permissions"`.
- If the page renders without styles after a change to fonts or external assets, the CSP is the first thing to check (browser console).

## 12. PostgreSQL backup and isolated restore

The dump contains the whole `onboardai` database: schema, data, grants, row-level security policies, the employee-scope **signing key** (`onboardai_private.scope_key`), account password hashes and session hashes. Treat every dump as a secret: keep it in `backups\` (git-ignored and Docker-ignored) or outside the repository, never share or commit it. Role definitions and role passwords are server-level and not in the dump; they are in the secrets file (section 9) and are recreated by migration 005.

**Never use `>` or `|` to write a dump in Windows PowerShell 5.1** - it re-encodes binary output as UTF-16 and the file becomes unusable (`backups\onboardai_pre_m5.dump` is such a file: `pg_restore` reports "not a valid archive"). Write the file inside the container with `-f` and copy it out with `docker compose cp`.

### Backup (read-only for the live database)

```powershell
$secrets = 'C:\Users\Administrator\Desktop\employee-onboarding-assistant-day31\onboardai_secrets\phase1.env'
Get-Content $secrets | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object { $k, $v = $_ -split '=', 2; Set-Item "Env:$k" $v }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$dump = "backups\onboardai_$stamp.dump"
New-Item -ItemType Directory -Force backups | Out-Null
docker compose --env-file $secrets exec -T db pg_dump -U onboardai -d onboardai -Fc -f /tmp/onboardai_backup.dump
docker compose --env-file $secrets cp db:/tmp/onboardai_backup.dump $dump
docker compose --env-file $secrets exec -T db rm -f /tmp/onboardai_backup.dump
(Get-FileHash $dump -Algorithm SHA256).Hash        # record it with the backup
```

### Verify the archive (no database involved)

```powershell
docker run --rm --network none -v "${PWD}\backups:/b:ro" postgres:16-alpine pg_restore --list "/b/onboardai_$stamp.dump" | Select-String "TABLE DATA"
```

Expect 13 `TABLE DATA` entries, including `onboardai_private scope_key`, `public user_accounts` and `public user_sessions`.

### Isolated restore test (disposable server; the live database and its volume are never touched)

```powershell
$rpw = [guid]::NewGuid().ToString('N')            # throwaway password for the disposable server only
$attrs = 'LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS'
docker network create --internal onboardai-restore-net
docker run -d --name onboardai-restore --network onboardai-restore-net -e POSTGRES_PASSWORD=$rpw postgres:16-alpine
do { Start-Sleep 2 } until ((docker exec onboardai-restore pg_isready -U postgres -h 127.0.0.1) -match 'accepting')
docker exec onboardai-restore psql -q -U postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE onboardai LOGIN SUPERUSER PASSWORD '$rpw'" -c "CREATE ROLE onboardai_app $attrs" -c "CREATE ROLE onboardai_reader $attrs" -c "CREATE DATABASE onboardai OWNER onboardai"
# if migration 006 was applied, also: -c "CREATE ROLE onboardai_importer $attrs"
docker cp $dump onboardai-restore:/tmp/restore.dump
docker exec onboardai-restore pg_restore -U onboardai -d onboardai --exit-on-error /tmp/restore.dump      # exit code 0 expected
# Signing key, roles, grants and RLS must verify against the REAL scope secret (exit 0, key_matches_secret: true):
docker run --rm --network onboardai-restore-net -e DB_BACKEND=postgresql -e PG_HOST=onboardai-restore -e PG_DATABASE=onboardai -e PG_USER=onboardai -e PG_PASSWORD=$rpw -e ONBOARDAI_SCOPE_SECRET employee-onboarding-assistant-backend python backend/migrations/005_least_privilege_roles.py --verify
# Data-integrity constraints (exit 0):
docker run --rm --network onboardai-restore-net -e DB_BACKEND=postgresql -e PG_HOST=onboardai-restore -e PG_DATABASE=onboardai -e PG_ADMIN_USER=onboardai -e PG_ADMIN_PASSWORD=$rpw employee-onboarding-assistant-backend python backend/migrations/007_data_integrity.py --verify
# Clean up
docker rm -f onboardai-restore; docker network rm onboardai-restore-net
```

### Recovery (owner decision; never restore into the running database)

Restore into a **new** Compose project and volume (for example `docker compose -p onboardai-recovered ...`), run the checks above against it, provision role passwords with `005 --apply --reset-passwords` (same `ONBOARDAI_SCOPE_SECRET`, never `--rotate-scope-secret`, so existing signatures and the restored key stay valid), then switch traffic. Do not run `docker compose down -v`, `DROP DATABASE` or `pg_restore --clean` against the active `onboardai` database.

## 13. Azure OpenAI (LLM provider)

Azure OpenAI is the only LLM provider: GPT-4.1 deployment, OpenAI v1 Responses API, API-key authentication, `store=false`. Settings (in the external secrets file, never in the repository): `AZURE_OPENAI_ENDPOINT` (`https://<resource>.services.ai.azure.com/openai/v1`; the bare resource URL is normalised), `AZURE_OPENAI_DEPLOYMENT` (`gpt-4.1`), `AZURE_OPENAI_API_KEY`. `docker-compose.yml` passes them to the backend from the `--env-file`; optional tuning: `LLM_TIMEOUT_SECONDS` (30), `LLM_MAX_RETRIES` (2), `LLM_MAX_OUTPUT_TOKENS` (600).

Behaviour: missing or invalid settings -> chat answers 503 and no request is sent; provider errors are logged as type + HTTP status only (never the key, endpoint or body); a prompt blocked by Azure content filtering, or an incomplete response, returns the standard fallback. Only retrieved handbook/FAQ passages and the question are sent; employee records (SQL path) never reach the LLM. Sentences in retrieved text that address the assistant ("ignore all previous instructions", "reveal your system prompt", "reply only with") are removed first; the log line `retrieved text screened: N instruction-like sentence(s) removed` (counts only) shows when this happens - investigate the source document.

**Status (24 November 2026):** activated on the local stack (backend rebuilt with the secrets file; backup `backups/onboardai_20261124_094429.dump` taken first). In-container check, functional check and evaluation results: project plan, section "Azure OpenAI Integration".

### Activation (rebuilds the backend; get approval first)

```powershell
$secrets = 'C:\Users\Administrator\Desktop\employee-onboarding-assistant-day31\onboardai_secrets\phase1.env'
Get-Content $secrets | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object { $k, $v = $_ -split '=', 2; Set-Item "Env:$k" $v }
docker compose --env-file $secrets up -d --build --no-deps backend
docker compose --env-file $secrets ps                                  # backend healthy
docker compose --env-file $secrets exec backend python -c "from backend.config import settings as s; print('azure configured:', all([s.azure_openai_endpoint, s.azure_openai_deployment, s.azure_openai_api_key]))"
```

Then ask in the browser: "Is a cab provided if I stay late at work?" (expect a `handbook.pdf` citation with "(p. 3)") and "What is the capital of France?" (expect the fallback).

**Rollback:** rebuild the backend from the previous commit (`445ffce`, Groq) with the old `.env` values; no database or index change is involved. **Key rotation:** regenerate the key in the Azure portal, update `AZURE_OPENAI_API_KEY` in the secrets file, recreate the backend (`up -d --no-deps backend`).

**Evaluation against Azure** (sends only synthetic handbook passages and questions; writes no database rows):

```powershell
Get-Content $secrets | Where-Object { $_ -match '^AZURE_OPENAI_' } | ForEach-Object { $k, $v = $_ -split '=', 2; Set-Item "Env:$k" $v }
python -m scripts.hybrid_eval --report docs/azure_eval_report.md
python -m scripts.rag_eval
```
