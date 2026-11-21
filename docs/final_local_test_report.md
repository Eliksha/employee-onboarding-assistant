# Final Local Test Report - OnboardAI

**Step 10 - Final local testing and release readiness**
Date: 21 November 2026 | Commit under test: `9af56cc` (branch `dev`) | Tester: Eliksha Maheshwari (with AI-assisted test automation)

**Verdict:** the local release (React + FastAPI + PostgreSQL + FAISS + temporary Groq, run with Docker Compose) **passes** all functional, failure-handling, persistence and evaluation checks below. It is **not production-ready**: there is no authentication, Azure is not implemented, and the hardening items in section 6 remain open.

> **Update (21 November 2026, Local Improvement 1):** the frontend lint failure in row 4 has since been resolved - `npm run lint` reports 0 errors and 0 warnings. Details in `docs/project_plan.md`. The rest of this report is unchanged.

## 1. Test environment

| Item | Version / setting |
|---|---|
| OS | Windows Server 2022 |
| Python | 3.14.8 (local venv), 3.12.16 (backend container) |
| Node.js | 24.21.0 |
| Docker Engine / Compose | 29.8.2 / v5.5.1 |
| Database | PostgreSQL 16 (`postgres:16-alpine`, disposable volume); SQLite for pytest |
| LLM | Groq, `qwen/qwen3.8-27b` (temporary) |
| Embeddings / index | `BAAI/bge-small-en-v1.5`, existing FAISS index (48 chunks), mounted read-only |
| Browser automation | Playwright with headless Google Chrome (installed in a scratch environment, not a project dependency) |

Isolation: Docker tests used project `onboardai-step10` with a random container-only database password; containers, volumes and images were removed afterwards. The real PostgreSQL database was not accessed. SHA-256 hashes of the FAISS index and `docs/rag_eval_report.md` were unchanged after testing.

## 2. Results summary

Legend: **Auto** = scripted check executed in Step 10; **Manual** = human/assistant review of configuration or output; **Not tested** = not executed.

| # | Area | Type | Result |
|---|---|---|---|
| 1 | Backend unit + integration tests (`python -m pytest -q`) | Auto | **PASS** - 80 passed |
| 2 | Frontend tests (`npm test`) | Auto | **PASS** - 4 passed |
| 3 | Frontend production build (`npm run build`) | Auto | **PASS** - 300.86 kB JS (97.10 kB gzip) |
| 4 | Frontend lint (`npm run lint`) | Auto | **FAIL (unresolved, pre-existing)** - 7 errors (5 x `react-hooks/set-state-in-effect`, 2 unused variables); identical since Step 6; no functional defect observed |
| 5 | RAG evaluation, live LLM, existing index (report written to a temporary path) | Auto | **PASS** - 50/50 (KB 6, retrieval 17, grounding 17, unknown questions 7, prompt injection 3); MRR 0.971 |
| 6 | Docker build and startup (`up --build --wait`) | Auto | **PASS** - db, backend, frontend healthy in dependency order |
| 7 | API integration through nginx (`/api`) | Auto | **PASS** - 18/18 |
| 8 | Browser end-to-end workflows (headless Chrome via nginx) | Auto | **PASS** - 16/16 |
| 9 | Workflow sweep: 3 employees x 5 endpoints, payroll, 5 policy categories with citations, routing | Auto | **PASS** - 15/15 |
| 10 | Invalid inputs and unknown employees | Auto | **PASS** - 20/20 |
| 11 | Database outage and recovery (PostgreSQL container stopped/started) | Auto | **PASS** - 5/5 during outage, 1/1 recovery without backend restart |
| 12 | Live LLM outage (unreachable endpoint) | Auto | **PASS** - 503 with friendly message, logged with request ID |
| 13 | Live retrieval failure (index path missing and unwritable) | Auto | **PASS** - generic 500, cause logged server-side only |
| 14 | Backend restart, simulated crash, full down/up with volumes | Auto | **PASS** - 4/4 each; restart count 0 to 1 after crash; init SQL not re-run |
| 15 | Secret and log scan (git, history, images, logs) | Auto | **PASS** - see section 4 |
| 16 | Dependency audit (`npm audit`) | Auto | **PASS** - 0 vulnerabilities |
| 17 | Security configuration review (auth, exposure, headers) | Manual | Findings in section 4 |
| 18 | Documentation accuracy (README, runbook, demo script) | Manual + Auto | **PASS** - commands taken from verified runs |

## 3. End-to-end workflow results

| Workflow | Evidence | Result |
|---|---|---|
| Employee profile and switching | Browser: EMP001 dashboard, switch to EMP002 (Meera) and back; API: profiles for EMP001-EMP003 | PASS |
| Onboarding checklist | Browser: toggle, counter updated, persisted after reload, restored; API: 15 items per employee, PATCH persisted | PASS |
| Policies via chat with citations | HR (notice period, section 9), leave (2.3), payroll (3), IT (5.3), onboarding (4.1); each answer found and cited the correct retrieved section only | PASS |
| Leave balances and payroll calendar | Browser tables; API for all employees; chat "What is my leave balance?" served from the database | PASS |
| Assets | Browser table; API; chat "What are my assigned assets?" served from the database with no LLM sources | PASS |
| HR/IT tickets | Browser create + list refresh, validation blocks a 2-character subject; API 201 and persisted across restarts | PASS |
| Unknown questions | "What is the office dress code?" returns the fallback with no sources | PASS |
| Conversation history | Reload restores history in order; history newest-first via API; survives backend restart and full down/up | PASS |
| Personal question without an employee | Returns a prompt to select an employee (`found=false`) | PASS |

## 4. Security and error-handling findings

**Verified (Auto):**
- No real API key or password in tracked files or git history; `.env` never committed and git-ignored. The only `gsk_` strings are fake keys in tests.
- Images contain no `.env` and no secret environment variables; the backend runs as non-root `appuser`.
- Published ports: frontend `127.0.0.1:8080`, backend `127.0.0.1:8000`; PostgreSQL not published.
- Logs (container volume, 647 lines; local `logs/app.log`, 3,814 lines): 0 occurrences of the Groq key, local or container DB password, `gsk_` tokens or chat question text.
- Errors: invalid input returns 422 with a readable string; unknown employee 404; LLM outage 503; database, retrieval and unexpected failures return a generic 500 with `request_id` and no stack trace; tracebacks are logged server-side with the same request ID.
- FAISS index is read-only in Docker; `POST /ingest` fails safely there.

**Open findings (Manual review, not fixed - none is critical for a local synthetic-data demo):**

| Finding | Severity (production) | Note |
|---|---|---|
| No authentication or authorization; any client can read any employee's data (for example EMP002) | High | Known design limit of the demo selector |
| `POST /ingest` unauthenticated | High | Blocked in Docker by the read-only mount; writable in local development |
| Swagger UI and OpenAPI schema reachable through nginx (`/api/docs`, `/api/openapi.json`) | Medium | Disable or protect before deployment |
| `/health` is liveness only (stays 200 while the DB is down); container stays "healthy" | Medium | Add a readiness check before cloud hosting |
| nginx discloses its version; no security headers (CSP, X-Content-Type-Options, X-Frame-Options); no HTTPS | Low (local) / Medium (cloud) | Address in the Azure hosting layer |
| Backend port also published on localhost, bypassing nginx | Low | Local convenience only |
| LLM key present in the running container's environment (visible to host administrators) | Low (local) | Use Key Vault / managed identity in Azure |

## 5. Issues found and resolved in Step 10

- No critical or high-impact functional defects were found, so no application code was changed.
- Documentation gaps resolved: `docs/runbook.md` and `docs/demo_script.md` completed (previously placeholders); this report created; README documentation index and limitations updated.

## 6. Known limitations (unresolved)

- Groq is temporary; no Azure resources exist.
- No authentication/authorization; synthetic data only.
- Retrieval gaps (informational in the RAG report): "Is there a cab if I work late?" (Handbook 7 not retrieved) and "What happens if I come in late often?" (score 0.596, below the band).
- Grounding validation is lexical (numbers, emails, citations); paraphrased unsupported claims could pass.
- Frontend lint fails (7 pre-existing errors).
- `requirements.txt` unpinned and includes test tools (container resolved newer package versions than local).
- PostgreSQL schema provided as a snapshot; `backend/migrations/` targets SQLite only.
- Browser, Docker and workflow test scripts used in Steps 6-10 are not in the repository or CI; no CI pipeline is configured.

**Not tested:** Azure deployment and Azure OpenAI; load/performance and concurrency (`tests/load/` is empty); mobile/responsive layout; accessibility; browsers other than Chrome; HTTPS; loading the schema into a non-Docker PostgreSQL with `psql -f`; LLM rate-limit behaviour under load.

## 7. Azure deployment prerequisites

| Prerequisite | Status |
|---|---|
| Azure subscription, role assignments, approved region and quotas | Pending access |
| Azure OpenAI resource and chat model deployment | Pending access |
| LLM configuration for Azure (endpoint, key or managed identity, deployment name; rename Groq-specific variables or add a provider switch in `backend/services/llm.py`) | Not started |
| Re-run `pytest` and `python -m scripts.rag_eval`; recalibrate `SIMILARITY_THRESHOLD`, `BORDERLINE_MARGIN` and `NOT_FOUND` behaviour with the Azure model | Not started |
| Hosting for frontend and backend containers (for example Azure Container Apps or App Service) and Azure Container Registry | To be decided |
| Managed PostgreSQL (Azure Database for PostgreSQL) initialised from `docker/postgres/` | To be decided |
| Secrets in Azure Key Vault / managed identity; no `.env` in cloud | Not started |
| Authentication (for example Microsoft Entra ID) and per-employee authorization | Not started (required before any non-local use) |
| Protect or remove `POST /ingest`; disable public API docs; add readiness probe; HTTPS and security headers | Not started |
| Monitoring (Azure Monitor / Application Insights) using the existing request IDs | Not started |
| CI/CD pipeline running pytest, npm test/build and image builds | Not started |
| Pin Python dependencies and separate runtime from test requirements | Recommended |
