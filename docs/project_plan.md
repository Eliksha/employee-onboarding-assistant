# OnboardAI â€” Project Plan

**Project:** OnboardAI: RAG-Powered New Joiner Support Platform  
**Domain:** Generative AI for Human Resources  
**Team member:** Eliksha Maheshwari  
**Location:** Pune  
**Mentor:** Shankhalika Sarkar  
**Last updated:** 21 November 2026

## 1. Milestones

| Milestone | Planned day | Deliverable | Current status |
|---|---|---|---|
| M1 â€” Design | 31 | Charter, architecture, repository, synthetic data | Completed for local prototype |
| M2 â€” Backend + AI | 32 | FastAPI, RAG, FAISS, employee data APIs, orchestration | Completed locally (RAG eval 50/50, guardrails); Azure OpenAI migration pending |
| M3 â€” UI + Middleware | 33 | React dashboard, chat, checklist, support center, validation | Completed; browser E2E 16/16 |
| M4 â€” Deploy + Test | 34 | Docker, Azure deployment, CI/CD, unit/integration/load/security tests | Docker + local testing completed (Step 10); Azure deployment, CI/CD and load tests pending |
| M5 â€” Wrap-up | After | Runbook, architecture diagrams, storyboard, slides, demo, final repository | Runbook, architecture, demo script, final test report done; slides pending |

## 2. Scope and Technology Decisions

- **Backend:** Python, FastAPI, explicit deterministic agent orchestrator.
- **AI:** Retrieval-augmented generation over onboarding/policy content, using embeddings and FAISS. Azure OpenAI is the **target** LLM service; Groq was used temporarily during development and must be replaced before Azure completion.
- **Frontend:** React + Vite, connected to the FastAPI backend.
- **Prototype persistence:** SQLite at `data/app.db`.
- **Cloud target:** Azure only for the final solution. Production persistence, hosting, identity, secrets management, and monitoring require configuration and validation.
- **Data:** Synthetic fictional employees only; demo selectors EMP001, EMP002, EMP003.
- **Authentication:** Not implemented in the demo. An employee selector is **not** an authentication or authorization mechanism. Do not expose employee-specific APIs with real data or deploy them publicly without proper identity and access controls.

## 3. Implementation Progress

### Completed â€” Backend and data

- Reviewed existing FastAPI routes and SQLite tables; backed up the database before migrations.
- Applied non-destructive employee-specific migrations and synthetic seed data; preserved legacy records.
- Added employee profile, leave balance, IT asset, payroll calendar, checklist, and support ticket endpoints.
- Added employee-scoped chat history and request routing between employee information and policy/RAG responses.
- Implemented explicit Python orchestration for the local prototype.
- Added checklist updates via `PATCH /employees/{employee_id}/checklist/{item_id}`.
- Added support ticket creation via `POST /employees/{employee_id}/tickets`.

### Completed â€” Frontend

- React/Vite OnboardAI dashboard and employee demo selector.
- AI Assistant with employee-specific chat history.
- Leave & Payroll and My Assets views.
- Interactive checklist: mark complete/incomplete, persist changes, show progress and errors.
- Support Center: create tickets, show feedback, and refresh employee-specific ticket history.

### Completed â€” Verification (20 November 2026)

| Verification | Observed result | Scope |
|---|---|---|
| `python -m pytest -q` | **16 passed in 6.25 s** | Existing automated test suite |
| Live HTTP GET checks | **5/5 returned 200** | EMP001 profile, leave balances, checklist, assets, tickets |
| Employee-ID consistency | **6/6 checks; 0 mismatches** | Checklist and ticket API records for EMP001â€“EMP003 |
| SQLite schema inspection | Expected application tables present | `data/app.db` |
| SQLite checklist persistence | **45 assignments**, including `done=0` and `done=1` | `checklist_assignments` |
| SQLite support ticket persistence | **1 ticket** for EMP001, category IT, status `open` | `tickets` |
| UI acceptance checks | Checklist and support tickets reported working | Local React/FastAPI integration |

**Interpretation:** These checks support local functional correctness and employee-ID consistency. They do **not** demonstrate production-grade authorization, penetration testing, load readiness, or successful Azure deployment.

## 4. Remaining Work â€” Prioritized

1. **Security readiness:** Determine the identity approach for Azure deployment (e.g., Microsoft Entra ID), enforce backend authorization, protect ingestion/admin endpoints, verify RBAC and secret handling. Keep synthetic-only, access-controlled demo if authentication remains out of scope.
2. **Azure OpenAI integration:** Replace temporary Groq usage; configure model deployments and environment variables securely; verify RAG answer quality, grounding, and fallback behavior.
3. **Azure infrastructure:** Confirm subscription, permissions, region, quotas, resource availability, deployment architecture, and production database choice.
4. **Container and deployment validation:** Verify Docker build/run, configure frontend/backend hosting, HTTPS, CORS, health checks, and environment separation.
5. **Operational controls:** Add structured logging with minimal PII, monitoring, alerts, backup/restore and rollback procedures.
6. **Quality assurance:** Add targeted API integration, authorization, failure-path, security, and load tests; record evidence and known limitations.
7. **CI/CD:** Add automated checks and deployment pipeline, with secrets excluded from source control.
8. **Final deliverables:** Update architecture diagrams, README, deployment/runbook, demo script, slides, and submission package.

## 5. Roles

Solo project: Eliksha Maheshwari handles architecture/integration, backend, AI/LLM, frontend, DevOps, QA, and documentation.

## 6. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Azure access, quota, or model deployment unavailable | Blocks cloud integration/deployment | Confirm subscription, region, roles, and quotas before provisioning; document blocker |
| Employee selector mistaken for secure identity | Unauthorized access if deployed with real data | Synthetic-only controlled demo; add server-side authentication and authorization before public/real-data use |
| Hallucinated or unsupported policy answers | Incorrect onboarding guidance | Ground responses in retrieved sources; abstain/escalate when evidence is insufficient; evaluate against test set |
| Weak retrieval | Irrelevant answers | Evaluate chunking, similarity threshold, top-k, and source coverage |
| Secret exposure | Credential compromise | Use environment/secret stores; rotate exposed keys; enable scanning; avoid committing `.env` |
| SQLite unsuitable for production scaling | Data reliability/performance concerns | Choose and test managed Azure persistence before production |
| Time constraints | Incomplete deliverables | Prioritize secure demo path and document deferred items |

## 7. Decision Log

| When | Decision | Reason |
|---|---|---|
| Day 31 | FAISS rather than Pinecone | Local, no additional account |
| Day 31 | SQLite for prototype | Minimal setup |
| Day 31 | Defer login, uploads, analytics in initial MVP | Control solo scope |
| 20 Nov 2026 | Use synthetic demo employees EMP001â€“EMP003 | Enable employee-specific feature testing |
| 20 Nov 2026 | Use employee selector without authentication **for controlled local demo only** | Capstone prototype constraint |
| 20 Nov 2026 | Azure-only final cloud target; Groq temporary | Align implementation with capstone platform decision |
| 20 Nov 2026 | Backend first, React second, Azure last | Incremental verification |

## 8. Migration and Backup History

- Existing database backup: `data/app_backup_20261120_113654.db`.
- Migration 001: `backend/migrations/001_employee_schema.py`; tested on a temporary copy and for repeat execution; preserved original records.
- Pre-seed backup: `data/app_pre_seed_20261120_115842.db`.
- Migration 002: `backend/migrations/002_seed_demo_data.py`; seeded three employees, six leave balances, three IT assets, two payroll entries, and 45 checklist assignments; repeat execution checked for duplicates.
- Subsequent local implementation includes employee-specific chat and ticket features; confirm exact migration filenames and checks in repository before final submission.

## 9. Blocker Log

| Blocker | Original status | Current action |
|---|---|---|
| Azure subscription/role/region availability | Open at Day 31 | Reconfirm before deployment; no successful deployment evidenced yet |
| Azure OpenAI access/model deployments | Open at Day 31 | Confirm deployment names, quotas, and credentials; replace temporary Groq |
| Production authentication/authorization | Deferred for local demo | Required before public deployment or real employee data |

## 10. Next Immediate Step

**Next (after Step 10):** Azure milestones A1-A6 listed under "Step 10 - Final Local Testing and Release Readiness" below, starting with A1 (confirm Azure access). Local Steps 1-10 are complete.

### PostgreSQL Dependency Update — 20 November 2026

- Added `psycopg2-binary==2.9.13` to `requirements.txt`.
- Verified that version 2.9.13 is installed in the local Python virtual environment.
- Purpose: Ensure PostgreSQL connectivity dependencies are included in fresh installations and future deployment environments.
- Existing application functionality and database records remain unchanged by this dependency update.


### PostgreSQL Configuration Documentation — 20 November 2026

- Added DB_BACKEND and PG_* connection variables to .env.example.
- Documented PostgreSQL 16 as the intended database backend.
- Preserved SQLite as an available local fallback.
- No changes made to the private .env file or existing database records.
- Database credentials must remain outside version control.

### Frontend Asset Cleanup — 20 November 2026

- Removed unused frontend assets: hero.png, react.svg, vite.svg, and icons.svg.
- Confirmed no references to these filenames in frontend source or configuration files before removal.
- Retained favicon.svg for future browser icon configuration.
- No application logic, API routes, or database functionality was modified.

### Documentation Cleanup — 20 November 2026

- Removed the redundant project_plan_backup.md from the active repository.
- Retained docs/project_plan.md as the authoritative project plan.
- Preserved historical project decisions through existing backups and Git history.
- No application functionality or database records were modified.

### Frontend Documentation Cleanup — 20 November 2026

- Replaced the default React/Vite README with OnboardAI-specific frontend documentation.
- Removed outdated README_ONBOARDAI.txt.
- Preserved Vite, ESLint, and favicon configuration files.
- No application logic, API endpoints, or database records were modified.

### Backend Test Verification — 20 November 2026

- Executed automated tests with DB_BACKEND=sqlite.
- Result: 16 tests passed in 5.74 seconds.
- No test failures.
- PostgreSQL was not used for this test run.

### PostgreSQL Verification — 20 November 2026

- Successfully connected to PostgreSQL 16 using local environment configuration.
- Verified database: onboardai.
- Confirmed 10 application tables and 114 records.
- Verified 3 synthetic employees and 45 checklist assignments.
- All verification queries were read-only.
- No existing records or application logic were modified.

### Step 3 — FastAPI Endpoint Verification (Completed: 20 November 2026)

- FastAPI OpenAPI specification: HTTP 200.
- Employee GET endpoints: 6/6 passed (user-reported).
- Chat history: GET /history?employee_id=EMP001&limit=5 returned HTTP 200.
- Chat history response: valid JSON array.
- Tests performed against the locally running API configured for PostgreSQL.
- Verification was read-only; no POST, PATCH or DELETE operations performed.
- Detailed response-content validation and chat-generation testing remain pending.


### Step 4 - RAG Evaluation (Completed: 20 November 2026)

**Status:** Completed. All deterministic and live-LLM evaluation categories were executed (2 full runs, identical results). No application code, FAISS index, or database records were modified.

**Files inspected:** `backend/config.py`, `backend/services/embeddings.py`, `ingest.py`, `retriever.py`, `rag.py`, `llm.py`, `orchestrator.py`, `employee_query_router.py`, `db.py`, `backend/routes/chat.py`, `data/raw/handbook.md`, `data/raw/faqs.md`, `data/index/*`, `scripts/run_test_questions.py`, `tests/conftest.py`, existing unit/integration tests, `docs/test_report.md`.

**Files created:**
- `scripts/rag_eval.py` - evaluation runner (`python -m scripts.rag_eval`, `--no-llm` for deterministic-only). Writes `docs/rag_eval_report.md`. Stubs chat-history writes, never rebuilds the index, never prints secrets; LLM cases become NOT TESTED if the LLM is unreachable.
- `tests/unit/test_rag_eval.py` - 8 deterministic pytest checks (index presence/sync, KB-derived expectations, real-embedding retrieval relevance, grounding-checker helpers, prompt-role separation for injected text, leak detector).
- `docs/rag_eval_report.md` - generated per-question evidence (retrieved sources, scores, answers).

**RAG configuration verified in code:** `BAAI/bge-small-en-v1.5` via fastembed (384-dim, L2-normalised); FAISS `IndexFlatIP` (cosine) at `data/index/faiss.index` + `chunks.json`; 48 chunks (25 FAQ, 23 handbook; `handbook.pdf` skipped because a Markdown version exists); section-aware chunking 350 words / 40 overlap; top-k 4; similarity threshold 0.65 on the top hit; LLM must reply `NOT_FOUND` when context is insufficient, otherwise a fixed fallback with HR/IT escalation is returned; citations are requested in the prompt as `[Handbook x.y]` / `[FAQ]`.

**Evaluation categories and results (live LLM: Groq `qwen/qwen3.8-27b`, temperature 0):**

| Category | Cases | Pass | Fail | Not tested | Notes |
|---|---|---|---|---|---|
| A. KB / index availability | 6 | 6 | 0 | 0 | 48 vectors = 48 chunks; index in sync with `data/raw`; re-embedded chunk cosine 1.0000 |
| B. Retrieval relevance (deterministic) | 13 | 13 | 0 | 0 | Leave (3), payroll (3), IT (3), HR policy (2), onboarding (2); expected section at rank 1 for all (MRR 1.000) |
| C. Answer grounding (LLM) | 13 | 13 | 0 | 0 | Expected fact present, citation present and matching a retrieved section, no unsupported numbers/emails |
| D. Unknown-question handling | 7 | 7 | 0 | 0 | Relocation, dress code, stock options, pets, shift allowance, joining bonus, Wi-Fi password; all returned the fallback |
| E. Prompt-injection resistance | 3 | 3 | 0 | 0 | Injected rank-1 passage (override, secret/system-prompt request) ignored; user-message injection abstained |
| Backend regression (`pytest`) | 24 | 24 | 0 | 0 | 16 existing + 8 new, `DB_BACKEND=sqlite` |

**Observations:**
- Retrieval is strong for this small corpus. The weakest legitimate query ("Who do I contact for payroll queries?") scored 0.681, only 0.031 above the threshold, so a small rephrasing could cause a false abstention.
- 4 of 7 unknown questions scored **above** the 0.65 threshold (0.660-0.731). The threshold alone does not filter out-of-scope HR questions; abstention for those depended on the LLM returning `NOT_FOUND`.
- E03 abstained at the retrieval gate (score 0.610), so it did not exercise the LLM. E01/E02 did exercise the LLM.
- The API returns all top-k retrieved chunks as `sources`, not only the passages actually cited in the answer.

**Known limitations:**
- Grounding checks are lexical (key facts, numbers, emails, citation-to-section match). Paraphrased unsupported claims without numbers or emails could go undetected; answers were also reviewed manually for this run.
- Small test set (13 answerable, 7 unanswerable, 3 injection) on a single synthetic corpus, with one sample per question. LLM output can vary between runs or model versions.
- Document-level injection was simulated in memory; the system prompt's rule (5) addresses instructions "in the question" but does not explicitly tell the model to treat context passages as untrusted data.
- `tests/conftest.py` `env` fixture redirects `db_path` but not `db_backend`. With `.env` set to PostgreSQL, run tests with `DB_BACKEND=sqlite`, otherwise state-changing tests (e.g. checklist PATCH) can modify PostgreSQL records. Not changed in this step; recommended follow-up.

**Azure migration considerations:**
- Re-run `python -m scripts.rag_eval` after switching to Azure OpenAI; the 0.65 threshold and `NOT_FOUND` behaviour must be re-validated for the new chat model.
- If embeddings move to Azure OpenAI, the FAISS index must be rebuilt and check A05 will flag a model mismatch; the similarity threshold must be recalibrated (score distributions differ by model).
- Enable Azure OpenAI content filtering / Prompt Shields for indirect (document) injection, and keep keys in Azure Key Vault / managed identity.
- If FAISS is replaced by Azure AI Search, port the B-category cases as a retrieval regression gate in CI.

### Step 5 - AI Guardrails (Completed: 20 November 2026)

**Status:** Completed. Fixes the five issues found in Step 4. Endpoints, response schema (`ChatResponse`/`Source`), frontend, PostgreSQL data and the FAISS index are unchanged (index files still dated 19 Nov 2026). Not yet committed.

**Files:** new `backend/services/guardrails.py`, new `tests/unit/test_guardrails.py` (20 tests); modified `backend/config.py` (`borderline_margin = 0.05`), `backend/services/llm.py` (prompt rules 6-7, `<untrusted_context>` wrapper, passage sanitising), `backend/services/rag.py` (retrieval gate, answer validation, cited-only sources), `tests/conftest.py` (DB isolation), `scripts/rag_eval.py` + `tests/unit/test_rag_eval.py` (use production gate, 4 borderline cases, known-gap probe, API-source checks), `docs/rag_eval_report.md` (regenerated).

| # | Issue | Fix | Verification |
|---|---|---|---|
| 1 | Tests could write to PostgreSQL | `conftest.py` forces `DB_BACKEND=sqlite` before config import; autouse fixture gives every test a temporary SQLite file and makes `psycopg2.connect` raise | 3 tests; full suite run **without** a `DB_BACKEND` override (`.env` = postgresql): 44 passed |
| 2 | Retrieved documents not treated as untrusted | Context wrapped in `<untrusted_context>`; passages cannot forge the wrapper; prompt rules: never follow instructions inside passages, never reveal instructions/keys/credentials; output check blocks API key, DB password, `gsk_` tokens and system-prompt text | 3 unit tests; live E01-E03 passed |
| 3 | Unsupported answers | `NOT_FOUND` kept; accepted answers must also have >= 1 citation, every citation must map to a retrieved passage, and every number/email must appear in the retrieved text; otherwise the existing fallback is returned | 5 unit tests; live: 17/17 grounded, 7/7 unknown questions abstained |
| 4 | 0.65 threshold unreliable | Threshold **not lowered**. Band 0.60-0.65 reaches the LLM only if a distinctive question keyword occurs in a band passage; below 0.60 the LLM is not called. Steps 2-3 still apply | 5 tests (incl. real index); live: 4 previously refused answerable questions (ID card 0.640, certifications 0.637, counselling 0.634, WFH Fridays 0.621) now answered correctly; borderline unknowns U04/U07 reached the LLM and abstained |
| 5 | API returned all top-k chunks | `sources` = only retrieved passages referenced by the answer's citations (`[Handbook N]` -> matching section, or FAQ back-reference; `[FAQ]` -> best-matching retrieved FAQ) | 4 unit tests; live G01-G17 each returned exactly the cited section |

**Results:** `python -m pytest -q` -> **44 passed** (24 existing + 20 new). `python -m scripts.rag_eval` (live Groq `qwen/qwen3.8-27b`) -> **50/50 passed, 0 failed, 0 not tested** (A 6, B 17, C 17, D 7, E 3), retrieval MRR 0.971; 2 consecutive full runs on the final code with identical counts.

**Observations and remaining limitations:**
- Known retrieval gaps (reported, not counted): K01 "Is there a cab if I work late?" - Handbook 7 is not in the top-4 (embedding recall miss); the gate still passes on generic words ("work", "late"), so the LLM/validators must refuse. K02 "What happens if I come in late often?" (0.596) is just below the band and still refused. Fixing these needs hybrid (keyword + vector) retrieval or query rewriting - a design change, not done here.
- Keyword corroboration is lexical and can be satisfied by generic words; it only decides whether the LLM is consulted, so safety still rests on `NOT_FOUND` + output validation.
- Output validation is lexical: a fabricated claim with no number/email and a valid citation can still pass. Correct answers that paraphrase numbers (e.g. "six months" vs "6-month") are accepted; answers that compute a number not in the text are rejected (conservative).
- E03 (user-message injection) is stopped by the retrieval gate (0.610, no keyword match); the LLM's own resistance to user-message injection is covered only by mocked unit tests.
- An initial test question, "What is the counselling helpline?", returned `NOT_FOUND` because the KB states a helpline exists but gives no contact details; it was reworded to "Is there a counselling helpline for employees?".
- Guardrail rejections are logged (reason only, no question text) via the `app` logger.

**Azure migration notes:** re-run `python -m scripts.rag_eval` after switching to Azure OpenAI; re-validate the 0.65 threshold and 0.05 band with the new embedding model; add Azure AI Content Safety Prompt Shields for document injection; keep the output validators as model-independent checks.

### Step 6 - Frontend Integration Verification (Completed: 21 November 2026)

**Status:** Completed. No UI redesign, no API contract change, no Azure work. Not yet committed.

**Inspected:** `frontend/src/App.jsx`, `api.js`, `main.jsx`, `vite.config.js`, `package.json`, `.gitignore`; `backend/main.py`, `middleware/__init__.py`, `routes/employees.py`, `routes/chat.py`, `schemas/models.py`, `services/db.py`, `services/employee_db.py`.

**Changes:**
- `frontend/src/format.js` (new): `formatSources()` and `CHAT_MAX_LENGTH = 500`.
- `frontend/src/App.jsx`: chat sources shown as `file â€º section` (not raw JSON) and hidden when empty (previously "Sources: []" on every fallback answer); chat input `maxLength` 2000 -> 500 to match backend `ChatRequest`.
- `frontend/src/format.test.js` (new, 4 tests) + `npm test` script (`node --test`, no new dependencies).
- `tests/integration/test_frontend_contract.py` (new, 14 tests): every call in `api.js` maps to a FastAPI route; `/employees/payroll/calendar` not shadowed by `/employees/{id}`; chat length limits match; 422 `detail` is a string.

**Verification:**
- `npm run build`: success (JS 300.86 kB / 97.10 kB gzip). `npm test`: 4/4 passed.
- `python -m pytest -q`: **58 passed** (44 existing + 14 new; isolated SQLite).
- Browser E2E (headless Chrome via Playwright installed in a scratch venv only; backend on a **scratch copy** of `data/app.db`, `DB_BACKEND=sqlite`; live Groq): **16/16 passed** after fixes (14/16 before: chat maxlength and raw sources confirmed as defects). Covered: dashboard/profile, employee switching, leave & payroll, assets, checklist toggle + persistence after reload, ticket create + refresh, ticket validation (no POST sent), RAG answer with cited source, unknown-question fallback, employee-specific chat, history reload order, mocked 503, mocked empty lists, network-down error messages, no console errors.
- API through Vite proxy: 8 GET endpoints 200; 404/422 paths return readable string `detail`. `vite preview` also proxies `/api` (inherits `server.proxy`).
- Real `data/app.db` (timestamp 20 Nov 15:30, 0 E2E tickets) and the FAISS index unchanged; PostgreSQL not used.

**Limitations / not changed:**
- `npm run lint` fails with 7 **pre-existing** errors (5 x React 19 `react-hooks/set-state-in-effect`, 2 unused variables); identical on the committed code. Fixing requires refactoring data-loading effects; deferred.
- No CORS middleware and API base URL is hard-coded to `/api`: works only same-origin via the Vite dev/preview proxy. Production hosting needs a reverse proxy (or CORS + configurable base URL) - to be decided with the Azure deployment design.
- Employee list (EMP001-EMP003) is hard-coded in the frontend; selector is not authentication.
- Chat history has no loading indicator (shows the empty-state prompt until history arrives); dashboard header shows the employee ID until the profile loads. Cosmetic, left unchanged.
- E2E script lives outside the repository (scratch) and is not part of CI; mobile layout not tested.

### Step 7 - Logging and Error Handling (Completed: 21 November 2026)

**Status:** Completed. No API contract or frontend change; PostgreSQL, FAISS index and Azure untouched. Not yet committed.

**Inspected:** `backend/logging_config.py`, `backend/middleware/__init__.py`, `backend/main.py`, all routes (`chat`, `employees`, `feedback`, `checklist`, `admin`), `services/llm.py`, `rag.py`, `orchestrator.py`, `employee_query_router.py`, `db.py`, `employee_db.py`, `postgres.py`, existing `logs/app.log` (secret scan only).

**Verified before changes (probes with fake credentials, isolated SQLite):**
- Groq 401 error text and psycopg2 connection/DSN errors do **not** contain the API key or password; existing `logs/app.log` (3,490 lines) had 0 key-like tokens and 0 "password" matches. No redaction filter added (no confirmed leak).
- Database failures (employees, chat, history), retrieval `RuntimeError`, and unhandled errors already returned a generic JSON 500 with `request_id`, no stack trace; tracebacks were logged server-side. 404/405/422 already returned JSON string `detail`; chat logs only question length, not text.

**Confirmed issues fixed:**
1. A server-side `ValueError` inside the chat pipeline (e.g. retrieval/embedding failure, bad `DB_BACKEND`) was returned as **400 "Invalid employee or query."** and logged without traceback. Added `UnknownEmployeeError(ValueError)` in `employee_db.py` (raised in `db.py`, `orchestrator.py`, `employee_query_router.py`); `routes/chat.py` maps only that to the unchanged 400. Other errors now reach the middleware: safe 500 + logged traceback.
2. Service-level log lines (LLM unavailable, guardrail rejection, chat answered) had no request ID. Added a `ContextVar` set by the middleware and a `RequestIdFilter`; log format is now `time | LEVEL | rid=<id> | message` (`rid=-` outside requests). Existing `request_id=` text in middleware lines kept for compatibility.
3. Malformed JSON returned `Invalid input (1): JSON decode error` ("1" was a character offset). Now `Invalid input: request body is not valid JSON`.
4. Each pytest run appended ~108 lines of synthetic traffic and deliberate tracebacks to the real `logs/app.log`. `tests/conftest.py` now sets `LOG_DIR` to a temporary directory (verified: real log line count unchanged after a run).

**Tests:** new `tests/integration/test_error_handling.py` (16 tests: log directory isolation, `rid` format, request-ID correlation and reset, DB failure on employee/history/feedback, LLM 503, retrieval `RuntimeError`/`ValueError` -> 500, unknown employee still 400, invalid JSON/missing field/too long -> string 422, 404/405 JSON, no fake key/password/question text in logs including tracebacks).
- `python -m pytest -q`: **74 passed** (58 existing + 16 new).
- Frontend (unchanged, sanity run): `npm test` 4/4 passed; `npm run build` succeeded.
- RAG evaluation not re-run (RAG path unchanged apart from log formatting).

**Limitations:**
- No secret-redaction filter: protection relies on not logging secrets and on library error texts verified above; a future dependency could change its messages.
- Logs are plain text, not structured JSON; no Azure Monitor/Application Insights integration yet (Azure step).
- Request paths with synthetic employee IDs (e.g. `/employees/EMP001`) are logged; acceptable for synthetic data, review before real data.
- Uvicorn's own access log is configured separately and logs query strings (e.g. `?employee_id=`).
- `POST /ingest` still rebuilds the FAISS index without authentication (known Step 1 security item, out of scope).
- 503 responses carry the request ID only in the `X-Request-ID` header, not in the JSON body (500 has both).

### Step 8 - Docker Integration Testing (Completed: 21 November 2026)

**Status:** Completed locally (Docker Engine 29.8.2, Compose v5.5.1). No Azure deployment. Not yet committed.

**Finding:** the repository contained **no** Dockerfile, compose file or `.dockerignore`, and the **PostgreSQL schema/seed was not in the repository** (`db.init_db()` assumes a separately migrated database). A minimal, additive Docker setup was created; application code and API contracts are unchanged.

**Files created/modified:**
- `Dockerfile` (backend): Python 3.12-slim, non-root user, embedding model baked in (`HF_HUB_OFFLINE=1` at runtime), `/health` HEALTHCHECK.
- `frontend/Dockerfile` + `frontend/nginx.conf` + `frontend/.dockerignore`: Vite build served by nginx; `/api/*` proxied to `backend:8000` with `/api` stripped (same as the Vite proxy, no CORS needed); Docker DNS re-resolution so a restarted backend is found again; SPA fallback.
- `docker-compose.yml`: `db` (postgres:16-alpine, named volume, no published port, `pg_isready` health), `backend` (`.env` for LLM settings, container DB values override local `PG_*`, `DOCKER_PG_PASSWORD` required, FAISS index bind-mounted **read-only**, log volume), `frontend` (127.0.0.1:8080). `depends_on: service_healthy` and `restart: unless-stopped` on all services.
- `docker/postgres/01_schema.sql`, `02_seed.sql`: read-only `pg_dump` of the local PostgreSQL (schema; data for the 6 synthetic reference tables only - no messages, tickets, feedback or escalations).
- `.dockerignore`: excludes `.env*`, `.venv`, `data/index`, `data/*.db`, logs, tests, docs, frontend.
- `.env.example`: `SIMILARITY_THRESHOLD` corrected 0.55 -> 0.65 (matches code and Step 5 guardrail tests); `DOCKER_PG_PASSWORD` documented.
- `tests/unit/test_docker_config.py`: 6 static checks (build context excludes secrets, no hardcoded secrets, read-only index mount, health/restart policy, init SQL tables and synthetic-only seed, nginx proxy rule).

**Results (isolated project `onboardai-step8`, random container DB password, volumes removed afterwards):**
- Build: both images built in 2 min 54 s (backend 879 MB, frontend 74 MB). No `.env` or secrets in images or image history.
- Startup: `docker compose up --wait` -> db, backend, frontend **healthy** in 52 s, in dependency order; init SQL executed once.
- Container DB: 10 tables, 3 employees, 45 checklist assignments.
- Integration through nginx (:8080): React app, assets and SPA fallback 200; 8 API GET endpoints 200; unknown employee 404; validation 422 string detail; Groq chat with RAG over the mounted FAISS index (`found=true`, cited section 2.1); unknown question fallback; employee-specific chat from PostgreSQL; ticket create and checklist update persisted; **18/18 checks**.
- Browser E2E (Step 6 Playwright suite, headless Chrome against :8080): **16/16 passed**.
- FAISS index: SHA-256 unchanged; `POST /ingest` fails with a safe 500 because the mount is read-only.
- Restart/persistence: backend restart (nginx re-resolved), simulated crash (SIGTERM to PID 1 -> restart count 0 -> 1, healthy), full `down`/`up` with volumes kept (init SQL not re-run): ticket, checklist change and chat history persisted; **4/4 checks** after each.
- Logs: log volume persisted (216 lines, 82 with `rid=`); 0 occurrences of the Groq key, container DB password, `gsk_`, "password", or chat question text; only tracebacks were the 2 deliberate `/ingest` attempts.
- Regression: `pytest` **80 passed** (74 + 6); frontend `npm test` 4/4, `npm run build` OK.

**Azure readiness (not implemented):** all settings come from environment variables (no endpoints or secrets in images). The LLM client is OpenAI-compatible with a configurable base URL, but variable names are Groq-specific (`GROQ_API_KEY`, `GROQ_BASE_URL`); Azure OpenAI will need either its OpenAI-compatible v1 endpoint via these variables or a small provider switch (API version, deployment name) plus Key Vault / managed identity. The `db` service would be replaced by Azure Database for PostgreSQL and the FAISS index shipped in the image or Azure storage.

**Remaining issues / limitations:**
- `requirements.txt` is unpinned (container resolved FastAPI 0.165.0 / openai 3.57.0 vs local 0.163.2 / 3.55.0) and includes dev/test tools (pytest, httpx, locust) -> larger, less reproducible image.
- Container DB is seeded from a snapshot; the original PostgreSQL migrations remain outside the repository.
- `POST /ingest` remains unauthenticated (blocked in Docker only by the read-only mount).
- No HTTPS/TLS; ports bound to 127.0.0.1 for local use only.
- Docker test scripts (integration and browser) live outside the repository and are not in CI.

### Step 9 - Documentation Finalization (Completed: 21 November 2026)

**Status:** Completed. Documentation only; no application code, PostgreSQL data or FAISS index changed. Not yet committed.

**Files updated:**
- `README.md` - rewritten (was the Day 31 draft citing OpenAI/SQLite): purpose and data notice, status table, features, Mermaid architecture diagram, technology stack, repository layout, environment-variable table (from `backend/config.py`), local setup (SQLite and PostgreSQL options, index build), Docker Compose usage, RAG workflow and guardrails, all 16 API endpoints, test commands with verified results, logging/security notes, planned Azure OpenAI migration (explicitly not implemented), known limitations.
- `docs/architecture.md` - replaced outdated Day 31 description with current component table, system and RAG decision-flow Mermaid diagrams, and local Docker deployment view; `architecture.png` labelled as superseded historical design.
- `frontend/README.md` - added dev proxy note, `npm test` / `npm run build`, Docker/nginx summary.
- `.env.example` - removed unused `BACKEND_URL` (no code reads it).

**Verification:**
- First-time setup verified in a throwaway clone of commit `0ef0717` (no `.env`): `init_db` + migrations 001-003 + `python -m backend.services.ingest` (48 chunks, identical to the existing index) + Uvicorn; `/health`, `/employees/EMP001`, checklist and history returned 200; `pytest` 80 passed. Finding documented: migration 003 needs `PYTHONPATH=.`.
- Automated consistency check: all relative links and referenced paths exist; every documented environment variable exists in `Settings` or `docker-compose.yml`; documented endpoints match the OpenAPI schema exactly (16/16); referenced `python -m` modules and npm scripts exist; no emojis; no API key, password or `gsk_` token in the documents.
- All 3 Mermaid diagrams rendered successfully with Mermaid 11.4.1 in headless Chrome.
- Regression: `pytest` 80 passed; `npm test` 4 passed.

**Remaining documentation gaps:** `docs/runbook.md` and `docs/demo_script.md` are still placeholders; `docs/test_questions.md` and `docs/test_report.md` reflect the Day 32 test set (superseded by `docs/rag_eval_report.md`); the PostgreSQL `psql -f` load path for a non-Docker database is documented but was only executed via Docker initialisation; no Azure deployment documentation can be written until Azure access exists.

### Step 10 - Final Local Testing and Release Readiness (Completed: 21 November 2026)

**Status:** Completed - local release PASS; not production-ready (no authentication, Azure not implemented). No application code changed. Full evidence: `docs/final_local_test_report.md`.

**Results (all executed 21 Nov 2026 on commit `9af56cc`, isolated Docker project with disposable volumes; real PostgreSQL not accessed; FAISS index and `docs/rag_eval_report.md` unchanged by SHA-256):**

| Check | Result |
|---|---|
| `pytest` | 80 passed |
| `npm test` / `npm run build` | 4 passed / succeeded |
| `npm run lint` | FAIL - 7 pre-existing errors (unchanged since Step 6; non-critical, unresolved) |
| Live RAG evaluation (report to temp path) | 50/50, MRR 0.971; 2 known retrieval gaps unchanged |
| Docker build + startup | 3/3 services healthy |
| API integration via nginx / browser E2E | 18/18 / 16/16 |
| Workflow sweep (3 employees, 5 policy categories with citations) | 15/15 |
| Invalid inputs and unknown employees | 20/20 |
| DB outage / recovery; live LLM outage; live retrieval failure | 5/5 + 1/1; 503; safe 500 |
| Backend restart, crash recovery, full down/up | 4/4 each |
| Secret/log scans, `npm audit` | No secrets in git, history, images or logs; 0 vulnerabilities |

**New findings (documented, not fixed - pre-Azure hardening):** `/health` is liveness-only (stays 200 while the DB is down); Swagger UI and OpenAPI schema are reachable through nginx; nginx discloses its version and sends no security headers. Existing: no authentication, unauthenticated `POST /ingest`.

**Documentation:** completed `docs/runbook.md` (start/stop, health, logs and request tracing, troubleshooting from observed errors) and `docs/demo_script.md` (10-minute walkthrough using verified questions); created `docs/final_local_test_report.md`; README documentation index and limitations updated; milestone table refreshed.

**Next Azure milestones (not started; require Azure access):**
1. **A1 - Access:** confirm subscription, roles, region and quotas with the trainer.
2. **A2 - Azure OpenAI:** create resource and chat deployment; switch `backend/services/llm.py` configuration; re-run `pytest` and `python -m scripts.rag_eval`; recalibrate thresholds.
3. **A3 - Data and secrets:** Azure Database for PostgreSQL from `docker/postgres/`; Key Vault / managed identity; no `.env` in cloud.
4. **A4 - Hosting:** Azure Container Registry + container hosting for frontend/backend; HTTPS, security headers, readiness probe, API docs disabled, `/ingest` protected.
5. **A5 - Identity:** Microsoft Entra ID sign-in and per-employee authorization before any non-demo use.
6. **A6 - Operations:** CI/CD (pytest, npm test/build, image build), Azure Monitor / Application Insights using request IDs, load tests in `tests/load/`.

### Local Improvement 1 - Frontend ESLint Errors Fixed (Completed: 21 November 2026)

**Status:** Completed. `npm run lint` now reports **0 errors, 0 warnings** (was 7 errors). No ESLint rules disabled or suppressed; no UI, API contract, backend, dependency or data changes. Not yet committed.

**Files:** `frontend/src/App.jsx`, `frontend/src/api.js`; docs: `README.md` (test table, limitations), `docs/final_local_test_report.md` (update note).

| # | Original error | Cause | Fix |
|---|---|---|---|
| 1 | `App.jsx:33` set-state-in-effect (Chat) | Effect called async `load()` that set state | `load` is a promise chain; state set only in `.then/.catch` callbacks |
| 2 | `App.jsx:71` set-state-in-effect (Checklist) | Effect called `load()`, which ran `setLoading(true)` / `setError('')` synchronously | Effect calls `fetchItems()` (state set in callbacks); initial `loading=true` plus `key={employeeId}` remount covers resets; Refresh handler resets synchronously (allowed in event handlers) |
| 3 | `App.jsx:134` set-state-in-effect (SupportCenter) | Same as #2 | Same pattern (`fetchTickets()`) |
| 4 | `App.jsx:212` set-state-in-effect (profile) | `setProfile(null)` / `setProfileError('')` on employee change | Result stored with its `employeeId`; profile/error derived during render; stale responses ignored via cleanup flag |
| 5 | `App.jsx:216` set-state-in-effect (leave/payroll/assets) | `setLoading(true)` / `setRecords({})` on page or employee change | Result stored with a request key (`employee|page`); `loading` and `records` derived during render; page-to-endpoint map moved to a module constant |
| 6 | `App.jsx:228` no-unused-vars | Unused `key` in profile filter | `([, value])` |
| 7 | `api.js:34` no-unused-vars | `payroll(id)` ignored `id` (calendar is company-wide) | `payroll()`; request unchanged |

**Verification (all executed):**
- `npm run lint` and `eslint . --max-warnings 0`: exit 0. `npm test`: 4/4. `npm run build`: succeeded (301.0 kB JS).
- Backend `pytest`: 80 passed (no backend changes).
- Browser regression (headless Chrome, Vite dev server, backend on a scratch copy of the SQLite DB): existing suite **16/16**; refactor-specific checks: Refresh buttons send exactly one request each (checklist, tickets, chat history), error then Refresh recovery, stale profile and stale leave responses ignored after fast employee switching, no uncaught page errors - **5/5**; loading texts for profile, records and checklist observed during delayed requests - **3/3** (an initial loading check failed only because the test's blocking `time.sleep` mock froze the test driver; re-verified with a non-blocking in-browser delay).
- Behaviour note: the leave/payroll/assets pages now show "Loading records..." from the first render instead of briefly showing the empty-table message.

**Remaining:** no React component test framework in the project (no new dependency added), so the refactor is covered by browser checks that live outside the repository rather than by unit tests.

### Local Improvement 2 - Email and Password Authentication (Completed: 21 November 2026)

**Status:** Completed and verified locally. Replaces the unrestricted employee selector with sign-in; every endpoint except `GET /health` and `POST /auth/login` now requires a session. No Azure, Entra ID, OAuth or LLM-provider changes. Real PostgreSQL, `data/app.db` and the FAISS index untouched. Not yet committed.

**Design:**
- Passwords: Argon2id via `argon2-cffi==25.1.0` (new, pinned dependency), library defaults t=3, m=64 MiB, p=4; minimum 12 characters; unknown emails verified against a dummy hash (no timing oracle); generic "Invalid email or password.".
- Sessions: server-side table `user_sessions`; 256-bit random token in cookie `onboardai_session` (HttpOnly, SameSite=Strict, Path=/, Secure automatically on HTTPS); only SHA-256 of the token stored; absolute TTL 8 h, idle timeout 60 min; new session on every login; logout deletes the row; password change or account disable revokes all sessions.
- CSRF: per-session random token returned by `/auth/login` and `/auth/me`, kept in browser memory, required as `X-CSRF-Token` on all authenticated POST/PATCH; login accepts JSON only.
- Rate limiting: in-process sliding window, 5 failures per email and 20 per client IP per 15 min -> 429 with `Retry-After`; `X-Forwarded-For` honoured only with `TRUST_PROXY_HEADERS=true` (set in Docker behind nginx).
- Authorization: identity from the session only; `/employees/{id}/...`, `/history`, `/chat` accept an employee ID only if it equals the session's (403 otherwise, also for unknown IDs); feedback only on own messages; legacy `/checklist` and `POST /ingest` admin-only; payroll calendar for any signed-in user.
- Accounts: `user_accounts` (email unique, Argon2 hash, employee_id unique FK, role employee/admin, active flag). No accounts are seeded; `python -m backend.manage_accounts` (dev-only, refuses `APP_ENV=production`) provisions them with hidden-prompt or named-env-var passwords.
- Schema: `backend/services/auth_schema.py` (single source), migration `backend/migrations/004_auth_tables.py` (additive, idempotent, PostgreSQL + SQLite), `docker/postgres/03_auth_schema.sql` for fresh Docker volumes; SQLite `init_db` creates the tables; PostgreSQL startup fails with a clear message if they are missing (never altered implicitly).
- Frontend: new login page (email, password with show/hide, loading state, generic errors, notices), session restore via `/auth/me` on refresh, automatic return to login on any 401, Sign out button, employee dropdown replaced by a read-only "Signed in as" card; admin accounts see an administrator page. No tokens in localStorage/sessionStorage.

**Files:** new `backend/services/auth.py`, `backend/services/auth_schema.py`, `backend/security.py`, `backend/routes/auth.py`, `backend/manage_accounts.py`, `backend/migrations/004_auth_tables.py`, `docker/postgres/03_auth_schema.sql`, `frontend/src/LoginPage.jsx`, `frontend/src/auth.js`, `frontend/src/auth.test.js`, `tests/integration/test_auth.py`; modified `backend/config.py`, `backend/main.py`, `backend/routes/{employees,chat,feedback,checklist,admin}.py`, `backend/services/db.py`, `frontend/src/{App.jsx,App.css,api.js}`, `docker-compose.yml`, `requirements.txt`, `.env.example`, tests (`conftest.py`, `test_api.py`, `test_error_handling.py`, `test_frontend_contract.py`, `test_middleware.py`, `test_docker_config.py`), docs (`README.md`, `docs/architecture.md`, `docs/runbook.md`, `docs/demo_script.md`).

**Verification (all executed 21 Nov 2026):**

| Check | Result |
|---|---|
| `python -m pytest -q` | **145 passed** (61 new in `test_auth.py`; existing tests now sign in through the real endpoint - no security bypass) |
| `npm run lint` / `npm test` / `npm run build` | 0 problems / 7 passed (3 new) / succeeded |
| Browser (headless Chrome), Docker stack via nginx | 13/13: login page, show/hide, generic errors, sign-in loading + own dashboard, HttpOnly/SameSite cookie not readable by JS, empty local/session storage, refresh persistence, workflows, RAG chat with citation + history, CSRF header on all writes, cross-employee 403 from the page, expired session -> login notice, sign out |
| Browser, Vite dev server + local backend (scratch SQLite copy) | 13/13 (same suite) |
| Docker fresh install (`onboardai-auth`, disposable volumes) | All services healthy; `03_auth_schema.sql` executed; 12 tables; 0 accounts until provisioned; stored hashes `$argon2id$v=19$m=65536,t=3,p=4` |
| Docker API checks via nginx | 20/20 (401 unauthenticated, identical errors, cookie flags, own 200 / cross 403 reads and writes, CSRF, live Groq RAG after sign-in, history, feedback, ingest roles, logout + cookie replay 401, rate limit 429, other account unaffected) |
| Docker persistence | Sessions, accounts and CSRF token valid after backend restart and after full down/up (3/3 each); init SQL not re-run |
| Log scans (Docker volume + console) | 0 occurrences of passwords, session token, CSRF token or employee emails; login events use email fingerprints |

**Known limitations:** no MFA, password reset, self-service password change or external identity provider (Entra ID out of scope); rate limiter is in-memory per process (resets on restart, not shared across workers) and a known email can be locked for up to 15 minutes by failed attempts; in Docker the backend port 8000 is also published on localhost while `X-Forwarded-For` is trusted (per-IP limit bypassable locally; per-email limit still applies); HTTPS not configured locally, so `Secure` cookies apply only once HTTPS is in place; API docs (`/docs`) remain public (they expose no data without a session); admin actions are API-only; the real local PostgreSQL needs migration 004 and account provisioning before the backend will start against it (not run, by rule).
