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
| `curl http://localhost:8000/health` (local or Docker) | `{"status":"ok"}` |
| `curl http://localhost:8080/api/health` (Docker, through nginx) | `{"status":"ok"}` |
| `curl http://localhost:8080/api/employees/EMP001` | 401 when not signed in (proves the API is up and protected); sign in through the UI to check data access |
| `docker compose ps` | `db`, `backend`, `frontend` all `(healthy)` |

`/health` is a **liveness** check only: it stays 200 while PostgreSQL is down. Use an employee endpoint to confirm database connectivity.

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
| `cd frontend; npm test; npm run build` | Frontend helper tests and production build |
| `python -m scripts.rag_eval` | Live LLM evaluation; **rewrites `docs/rag_eval_report.md`**. Use `--no-llm` for deterministic checks only |

## 8. Safety rules

- Never commit `.env`; never paste output of `docker compose config` (without `--quiet`) because it shows resolved secrets.
- Do not reuse a real password for `DOCKER_PG_PASSWORD`.
- Keep ports bound to `127.0.0.1`; serve over HTTPS (and set `SESSION_COOKIE_SECURE=true`) before any non-local use.
- Never put account passwords in files, scripts or chat; use the hidden prompt or a temporary environment variable.
- Use synthetic data only.
