# OnboardAI â€” Project Plan

**Project:** OnboardAI: RAG-Powered New Joiner Support Platform  
**Domain:** Generative AI for Human Resources  
**Team member:** Eliksha Maheshwari  
**Location:** Pune  
**Mentor:** Kanishka Vatsa  
**Last updated:** 24 November 2026  

**Status:** Phase 1 (security hardening) ACTIVATED. **Azure deployment COMPLETED and VERIFIED in production (25 November 2026, 17/17 checks) - see "Azure Deployment - Completed and Verified" at the end of this file.** Phase 2 - Hybrid SQL + RAG Orchestration Steps 2A and 2B IMPLEMENTED, MANUALLY VERIFIED and committed. Phase 3 architecture completion audit done (23 November 2026). M3 (engineering baseline and automated evaluation) committed. M4 (CSV import role, schema dictionary, canonical PDF RAG with versioned index, routing fixes) approved. M5 (feedback and escalation from chat, migration 007 data integrity, API docs restriction, nginx security headers) implemented and verified on disposable databases, a clone of the live database and isolated containers; **M4 + M5 committed and pushed to `dev` (`cde4538`; all four GitHub CI checks passed) and ACTIVATED on the local Docker stack (23 November 2026)** - see "M4 + M5 Local Activation" at the end of this file. Pending: handbook page-citation check and employee-level authorization check on the activated stack.

## 1. Milestones

| Milestone | Planned day | Deliverable | Current status |
|---|---|---|---|
| M1 â€” Design | 31 | Charter, architecture, repository, synthetic data | Completed for local prototype |
| M2 â€” Backend + AI | 32 | FastAPI, RAG, FAISS, employee data APIs, orchestration | Completed locally (RAG eval 50/50, guardrails); Azure OpenAI migration pending |
| M3 â€” UI + Middleware | 33 | React dashboard, chat, checklist, support center, validation | Completed; browser E2E 16/16 |
| M4 â€” Deploy + Test | 34 | Docker, Azure deployment, CI/CD, unit/integration/load/security tests | Docker + local testing completed (Step 10); CI (4 GitHub checks passing) and local load test completed (M3); M4 + M5 local activation completed (23 Nov 2026, `cde4538`); Azure deployment completed and verified in production (25 Nov 2026, 17/17); CD pending |
| M5 â€” Wrap-up | After | Runbook, architecture diagrams, storyboard, slides, demo, final repository | Runbook, architecture, demo script, final test report done; slides pending |

## 2. Scope and Technology Decisions

- **Backend:** Python, FastAPI, explicit deterministic agent orchestrator.
- **AI:** Retrieval-augmented generation over onboarding/policy content, using embeddings and FAISS. Azure OpenAI is the **target** LLM service; Groq was used temporarily during development and must be replaced before Azure completion.
- **Frontend:** React + Vite, connected to the FastAPI backend.
- **Persistence:** PostgreSQL 16 (Docker stack and local development); SQLite remains only for the automated test suite and legacy local runs. Least-privilege database roles and row-level security are implemented (Phase 1 hardening, end of this file) and activated on the running database (23 November 2026); the data-integrity constraints of migration 007 are also applied (M5).
- **Cloud target:** Azure only for the final solution. Production persistence, hosting, identity, secrets management, and monitoring require configuration and validation.
- **Data:** Synthetic fictional employees only (EMP001, EMP002, EMP003). The original employee selector was replaced by sign-in; the employee is always taken from the session.
- **Authentication:** Implemented locally (21-22 Nov 2026): email/password with Argon2id hashing, server-side sessions in an HttpOnly cookie with absolute and idle expiry, CSRF tokens on all writes, per-email and per-IP login rate limiting, `employee`/`admin` roles. Every employee route serves only the signed-in employee's own records. Not implemented: MFA, password reset, external identity provider (Microsoft Entra ID is a possible later change), persistent rate limiting, HTTPS.

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

1. **Security readiness:** Local authentication, authorization, CSRF and RBAC are implemented and tested; least-privilege PostgreSQL roles with row-level security are implemented and activated (23 November 2026). Remaining: decide the identity approach for Azure, HTTPS, secret storage (Key Vault / managed identity), persistent login rate limiting, Docker owner password rotation.
2. **[ON HOLD] Azure OpenAI integration:** Replace temporary Groq usage; configure model deployments and environment variables securely; verify RAG answer quality, grounding, and fallback behavior.
3. **[ON HOLD] Azure infrastructure:** Confirm subscription, permissions, region, quotas, resource availability, deployment architecture, and production database choice.
4. **Container and deployment validation:** Verify Docker build/run, configure frontend/backend hosting, HTTPS, CORS, health checks, and environment separation.
5. **Operational controls:** Add structured logging with minimal PII, monitoring, alerts, backup/restore and rollback procedures.
6. **Quality assurance:** Add targeted API integration, authorization, failure-path, security, and load tests; record evidence and known limitations.
7. **CI/CD:** Add automated checks and deployment pipeline, with secrets excluded from source control.
8. **Final deliverables:** Update architecture diagrams, README, deployment/runbook, demo script, slides, and submission package.
9. **Post-activation checks on the live local stack (pending):** handbook page-citation verification and employee-level authorization testing (see "M4 + M5 Local Activation").

## 5. Roles

Solo project: Eliksha Maheshwari handles architecture/integration, backend, AI/LLM, frontend, DevOps, QA, and documentation.

## 6. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Azure access, quota, or model deployment unavailable | Blocks cloud integration/deployment | Confirm subscription, region, roles, and quotas before provisioning; document blocker |
| Weak identity controls if exposed publicly | Unauthorized access with real data | Local auth, RBAC, CSRF and own-employee checks implemented and tested; add HTTPS, MFA/identity provider and managed secrets before public or real-data use |
| Over-privileged database access | Full database compromise through any SQL flaw | Least-privilege app/reader roles, read-only SQL-agent transactions, timeouts, row limits, RLS (Phase 1 hardening); activated on the live database 23 Nov 2026 |
| Hallucinated or unsupported policy answers | Incorrect onboarding guidance | Ground responses in retrieved sources; abstain/escalate when evidence is insufficient; evaluate against test set |
| Weak retrieval | Irrelevant answers | Evaluate chunking, similarity threshold, top-k, and source coverage |
| Secret exposure | Credential compromise | Use environment/secret stores; rotate exposed keys; enable scanning; avoid committing `.env` |
| Database choice for Azure not final | Reliability/performance concerns | PostgreSQL 16 used locally; choose and test managed Azure PostgreSQL before production |
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
| 21 Nov 2026 | Local email/password authentication replaces the employee selector | Server-side identity and authorization before any shared use |
| 23 Nov 2026 | Least-privilege PostgreSQL roles, read-only SQL-agent path and RLS before any LLM-generated SQL; keep approved query tools | Phase 1 of the hybrid SQL + RAG plan |

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

**Next:** M4 + M5 are committed (`cde4538`) and activated locally (see "M4 + M5 Local Activation" at the end of this file). Pre-Azure remediation of the three HIGH audit findings (S1 backups ignored, S2 fail closed on privileged database roles, D3 tested backup/restore) implemented and verified, not committed; S2 takes effect on the next backend rebuild (see "Pre-Azure Remediation" at the end of this file). Azure OpenAI (GPT-4.1, Responses API) integrated, evaluated (RAG 50/50, held-out 100%) and active on the local stack, replacing Groq; not committed (see "Azure OpenAI Integration" at the end of this file). Remaining local checks: handbook page-citation verification and employee-level authorization testing on the activated stack; optional migration 006 for CSV import. Azure milestones (A1 onward) remain ON HOLD.

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


### Docker Integration - Manual Verification (Completed: 22 November 2026)

**Status:** Completed for the checks below (manually verified by the project owner). No application code changed.

| # | Check | Result |
|---|---|---|
| 1 | Docker Compose built and started PostgreSQL, FastAPI and React | Completed |
| 2 | All three containers reported healthy status | Completed |
| 3 | Employee authentication through `http://localhost:8080` | Completed |
| 4 | RAG chatbot answered an onboarding-related question | Completed |
| 5 | Onboarding checklist: task completion persisted after page refresh | Completed |
| 6 | Port mapping: backend on host port 8001, frontend on 8080, to avoid conflicts with local development servers (configurable via `BACKEND_PORT` / `FRONTEND_PORT`) | Completed |

**Outstanding items:**
- **Security - Deferred â€” required before deployment or sharing the environment:** rotate the Docker PostgreSQL password (`DOCKER_PG_PASSWORD`) because the original value was exposed. Reason for deferral: the current password is used only for a local demonstration with synthetic data. The value must not be recorded in this document or the repository.
- Complete the remaining Docker feature verification (other workspace features not covered above).
- Add database-aware health checks (the current `/health` endpoint is liveness-only and stays healthy while PostgreSQL is unavailable).


### Local Improvement 3 - Database-Aware Health Checks (Completed: 22 November 2026)

**Status:** Completed and verified. Resolves the outstanding item "Add database-aware health checks" from the Docker manual verification. Authentication, RAG, checklist and employee endpoints unchanged. No `.env` change, no volumes deleted, no Azure services. Not yet committed.

**Implementation:**
- `GET /health` (public) now runs a lightweight `SELECT 1` against the configured database: HTTP 200 `{"status":"ok","database":"ok"}` when reachable, HTTP 503 `{"status":"unavailable","database":"unavailable","detail":"Service unavailable: the database is not reachable."}` otherwise; `Cache-Control: no-store`.
- `backend/services/db.py` `check_database()`: PostgreSQL via the existing `postgres_connection()` configuration with `connect_timeout` and `statement_timeout` of `HEALTH_DB_TIMEOUT_SECONDS` (default 3); SQLite opened read-only (never creates a file). Failures log only `health check: database unavailable (<error type>)` - no host, user, password or error text in logs or responses.
- `backend/services/postgres.py`: `postgres_connection(connect_timeout=10)` parameter added; all other callers keep the 10-second default.
- Docker: the existing `HEALTHCHECK` already requires HTTP 200 from `/health`, so no Dockerfile change was needed; timeouts nest correctly (DB probe 3 s < request 4 s < Docker check 5 s). A database outage now marks the backend container `unhealthy` (Docker does not restart it; it returns to `healthy` when the database recovers).
- Docs: `README.md` and `docs/runbook.md` statements that `/health` was liveness-only corrected; `.env.example` documents `HEALTH_DB_TIMEOUT_SECONDS`.

**Verification (executed 22 Nov 2026):**

| Check | Result |
|---|---|
| `tests/unit/test_health.py` (rewritten) | 10 passed: SQLite healthy / missing (503, no file created), public access, PostgreSQL healthy with 3 s connect + statement timeout, PostgreSQL failures (OperationalError, timeout) -> 503 without leaking host/user/password, isolation guard -> 503, default timeout preserved for other callers, invalid backend -> unavailable, Docker HEALTHCHECK timeout nesting |
| Full backend suite `python -m pytest -q` | **154 passed** (145 previously + 9 net new) |
| Docker configuration | `test_docker_config.py` 7 passed; `docker compose config --quiet` valid |
| Live Docker (isolated project `onboardai-health`, ports 8102/8182) | DB up: 200 direct and via nginx, container healthy. DB stopped: 503 in ~3.3 s (direct and via nginx), container `unhealthy`, restart count 0. DB restarted: container `healthy`, 200. Logs show only `database unavailable (OperationalError)`; 0 occurrences of the DB password |

**Outstanding:**
- The running local stack (`employee-onboarding-assistant`, ports 8001/8080) still uses the previous backend image; rebuild it (`docker compose up -d --build`) to get the new `/health` behaviour.
- The isolated test stack was stopped and its images removed; its volumes `onboardai-health_pgdata` and `onboardai-health_logs` were kept (no volumes deleted) and can be removed manually when no longer needed.
- Password rotation for the Docker PostgreSQL database remains deferred (see the Docker manual verification section).


### Final Local Docker and Security Verification (Completed: 22 November 2026)

**Status:** PASS - local development phase ready to close. One genuine defect was found and fixed (session idle refresh). No Azure services, no `.env` or credential changes, no Docker volumes deleted, main Docker application not stopped or modified. Not yet committed.

**Verification environments**
- **Main stack** (`employee-onboarding-assistant`, frontend 8080, backend 8001): non-invasive checks only - no logins with real accounts, no data writes.
- **Isolated stack** (`onboardai-final`, ports 8103/8183, own PostgreSQL volume): synthetic accounts for EMP001-EMP003 and an admin with random per-run passwords; used for all authenticated, write, restart and outage checks. Session expiry was verified on a temporary one-off backend container (port 8104) with `SESSION_IDLE_MINUTES=1`, `SESSION_TTL_MINUTES=2` sharing the isolated database; removed afterwards.

**Automated results (executed 22 Nov 2026)**

| Check | Result |
|---|---|
| Backend `python -m pytest -q` | **189 passed** (154 before: +34 new isolation/security tests, +1 session regression test) |
| Security-focused subset (auth, isolation, error handling, health, guardrails) | 141 passed (before the regression test was added) |
| Frontend `npm test` / ESLint `--max-warnings 0` / `npm run build` | 7 passed / 0 errors, 0 warnings / succeeded |
| `docker compose config --quiet`; `test_docker_config.py` | valid; 7 passed |
| Main stack (non-invasive, API via nginx) | 4/4: `/health` 200 `database: ok`; all 17 protected routes 401 without a session; invalid requests safe 4xx; unknown email generic 401 |
| Isolated stack - headless Chrome (Playwright, scripted) | 13/13: login page, password toggle, generic invalid-credential errors, sign-in, HttpOnly/SameSite cookie not readable by JS and no browser storage, refresh persistence, leave/assets/checklist (persisted after refresh, then restored)/ticket, RAG chat with citation + history, CSRF header on all writes, cross-employee and CSRF-less requests 403 from the page, expired session -> login, sign out |
| Isolated stack - API via nginx | 17/17 (re-run 17/17 on the fixed image): unauthenticated sweep, invalid requests, login and cookie flags, identical invalid-credential errors, own profile retrieval, EMP001 <-> EMP002 read/write isolation in both directions, checklist isolation, live Groq RAG with cited source, chat history isolation, feedback own 200 / cross 403, CSRF (missing or other session's token) 403, RBAC (employee 403 on admin routes, admin 403 on employee data, admin authorized for ingest/legacy checklist), no hashes/tokens/passwords in responses, logout + replayed cookie 401, rate limit 429 with `Retry-After` |
| Isolated stack - backend restart | 4/4: checklist change, server-side session and chat history persisted |
| Isolated stack - database outage | DB stopped: `/api/health` 503 in ~3.4 s, backend container `unhealthy` (not restarted); DB started: healthy, 200 |
| Live session expiry (one-off backend) | Initially 2/3 (defect below); after the fix **3/3**: idle session rejected after > 60 s; active session valid until, and rejected after, the 2-minute absolute lifetime |
| Log scans | Isolated stack (855 lines): 0 occurrences of account passwords, DB password, API key, session or CSRF token, emails or hashes. Main stack (523 lines): 0 key-like tokens, hashes, `password=`, cookies, CSRF tokens or emails |

**Manually verified results** (by the project owner, earlier on 22 Nov 2026 - recorded in "Docker Integration - Manual Verification"): Docker build/health, employee login at `http://localhost:8080`, chatbot answer, checklist persistence after refresh, logout. No additional manual browser verification was performed in this step; the browser checks above are automated.

**Security review**
- Hardcoded credentials: none in tracked code (only fake `gsk_FAKE...` keys inside tests). `.env` not tracked and never in git history; only `.env.example` is tracked.
- SQL: all queries use bound parameters; no f-string, `.format` or `%` SQL (now enforced by `test_backend_sql_uses_bound_parameters_only`).
- Endpoints: 19 routes; only `GET /health` and `POST /auth/login` are public (route-inventory tests); all employee routes enforce own-employee authorization; writes require CSRF; admin routes require the admin role.
- Sessions: random 256-bit tokens, only SHA-256 stored, rotation on login, server-side invalidation on logout/password change/disable, absolute and idle expiry (fixed below).
- Cross-employee leakage: none found (profile, leave, assets, checklist, tickets, chat, history, feedback tested in both directions).

**Fix implemented**
- `backend/services/auth.py` (`resolve_session`): `last_seen_at` was refreshed at most every 60 s, so with an idle timeout of 60 s or less an active user was signed out (with the default 60-minute timeout an active session could end up to ~1 minute early). It is now refreshed after `min(60 s, idle timeout / 2)`, so active sessions never time out while writes stay limited. Regression test `test_active_session_survives_short_idle_timeout` fails on the old code and passes on the fix.

**Files changed in this step:** `backend/services/auth.py` (fix), `tests/integration/test_auth.py` (regression test), `tests/integration/test_isolation_security.py` (new, 34 tests), `docs/project_plan.md`.

**Remaining limitations / follow-ups**
- The running main stack still uses the backend image built before the session fix; rebuild it (`docker compose up -d --build backend`) to apply it.
- The main stack currently has one provisioned employee account; EMP002 isolation was therefore verified on the isolated stack with synthetic accounts, not on the main stack.
- Docker test volumes kept as instructed: `onboardai-final_pgdata`, `onboardai-final_logs`, `onboardai-health_pgdata`, `onboardai-health_logs` (remove manually when no longer needed).
- Unchanged known limitations: Docker PostgreSQL password rotation deferred (required before deployment or sharing); no MFA, password reset or external identity provider; in-memory login rate limiter (per process, resets on restart, possible 15-minute nuisance lockout); no HTTPS locally; public API docs; backend port also published on localhost while `X-Forwarded-For` is trusted.

**Local development phase:** ready to close. Next phase: Azure (A1 access confirmation onward), not started.


---

## Phase 1 - Hybrid SQL + RAG Architecture Audit (23 November 2026)

**Scope:** read-only audit of the code against the planned hybrid architecture. No application code, databases, credentials or Docker containers were changed. The live container database was inspected via `docker exec ... psql` with `default_transaction_read_only=on`. `python -m pytest -q`: **189 passed** (SQLite fixtures, LLM mocked). Status labels: **Implemented / Partial / Missing / Not Verified**.

### A1. Planned vs actual architecture

```
PLANNED                                         ACTUAL (code as of 23 Nov 2026)
React -> API Gateway -> FastAPI                 React -> nginx /api reverse proxy -> FastAPI
  -> Orchestrator -> Intent classification        -> orchestrator.answer_question -> regex classify_employee_query
Path A: CSV -> PostgreSQL -> schema dictionary  Path A: hard-coded seed SQL/Python -> PostgreSQL (or SQLite)
        -> text-to-SQL / approved tools                 -> 5 allow-listed parameterised functions (no schema dictionary)
        -> shared LLM generator                         -> Python string templates (NO LLM)
Path B: PDF -> chunk -> embed -> FAISS          Path B: Markdown (PDF only if no same-name .md) -> chunk -> fastembed -> FAISS
        -> retrieve -> shared LLM generator             -> retrieve -> gate -> Groq LLM -> guardrails -> cited sources
Mixed: both paths -> one grounded answer        Mixed: not supported (exactly one path per question)
LLM: Azure OpenAI                               LLM: Groq (OpenAI-compatible client), no Azure code path
```

| # | Planned component | Status | Evidence |
|---|---|---|---|
| 1 | React frontend | Implemented | `frontend/src/App.jsx`, `frontend/src/api.js` |
| 2 | API Gateway | Partial | `frontend/nginx.conf` strips `/api` and proxies to `backend:8000`; no managed gateway (rate limiting, auth offload, quotas) |
| 3 | FastAPI backend | Implemented | `backend/main.py` (6 routers + `/health`) |
| 4 | Orchestration layer | Partial | `backend/services/orchestrator.py::answer_question` - single if/else dispatch, no multi-tool plan |
| 5 | Intent classification | Partial | `backend/services/employee_query_router.py::classify_employee_query` - regex only, 5 intents, verified misroutes (A6) |
| 6 | PostgreSQL as system of record | Implemented | Docker forces `DB_BACKEND=postgresql` (`docker-compose.yml`); `docker/postgres/01_schema.sql` matches the live DB |
| 7 | CSV import into PostgreSQL | Missing | no `.csv` files, no `COPY`/csv code anywhere; data comes from `docker/postgres/02_seed.sql` and `backend/migrations/002_seed_demo_data.py` (hard-coded tuples) |
| 8 | Schema dictionary (tables, columns, types, relations) | Missing | no metadata module or file; nothing passes schema information to an LLM |
| 9 | Safe text-to-SQL **or** approved query tools | Implemented (approved-tools option) | `employee_query_router.py::execute_employee_query` allow-list -> fixed bound-parameter queries in `employee_db.py`; no text-to-SQL exists |
| 10 | Employee-specific retrieval | Implemented | employee ID taken from the session: `routes/chat.py::chat` -> `security.py::assert_own_employee` |
| 11 | SQL results -> shared LLM generator | Missing | `orchestrator.py::_format_employee_answer` builds text from templates; `llm.generate_answer` is never called on Path A |
| 12 | PDF ingestion | Partial | `ingest.py::_read_pdf` exists, but `load_chunks` skips a PDF when a same-stem `.md` exists; the current index has **0 PDF chunks** (48 chunks: `handbook.md` 23, `faqs.md` 25) |
| 13 | Text extraction + chunking | Implemented | `ingest.py::chunk_markdown_handbook` (heading-aware, 350 words / 40 overlap), `chunk_faqs`, `_split_long` |
| 14 | Embedding generation | Implemented | `embeddings.py::embed_texts` (fastembed `BAAI/bge-small-en-v1.5`, L2-normalised) |
| 15 | FAISS vector storage | Implemented | `ingest.py::build_index` -> `IndexFlatIP`; `data/index/faiss.index` + `chunks.json` |
| 16 | Similarity search + source references | Implemented | `retriever.py::search`; `guardrails.py::retrieval_gate`, `validate_answer`, `map_citation`; API returns `{file, section, score}` for cited chunks only (`rag.py`) |
| 17 | RAG evidence -> LLM generator | Implemented (RAG-only, not shared) | `rag.py::answer_question` -> `llm.py::generate_answer` (system prompt is handbook-specific) |
| 18 | Mixed queries (both paths, one answer) | Missing | `orchestrator.answer_question` returns from exactly one branch |
| 19 | Azure OpenAI provider | Missing | `config.py` has only `groq_api_key` / `groq_base_url`; `llm.py::_client` builds `OpenAI(base_url=groq)`; no `AzureOpenAI`, endpoint, deployment or API-version settings |

### A2. PostgreSQL inventory (live Docker database `onboardai`, verified read-only)

All dates/timestamps outside the auth tables are stored as `text`. Row counts are from the live DB on 23 Nov 2026.

| Table | Columns (SQL type, nullability / default) | PK | FKs / unique | Purpose | Rows |
|---|---|---|---|---|---|
| `employees` | employee_id text NN; name text NN; email text NN; department text NN; joining_date text NN; location text NN | employee_id | UNIQUE(email) | **Employee data** (profile) | 3 |
| `leave_balances` | id integer identity; employee_id text NN; leave_type text NN; available_days double precision NN default 0, CHECK >= 0 | id | employee_id -> employees; UNIQUE(employee_id, leave_type) | **Leave balances** | 6 |
| `assets` | asset_id text NN; employee_id text NN; asset_type text NN; asset_name text NN; status text NN default 'assigned' | asset_id | employee_id -> employees | **IT assets** | 3 |
| `payroll_calendar` | id integer identity; payroll_month text NN; payment_date text NN; status text NN default 'scheduled' | id | UNIQUE(payroll_month) | **Payroll** (company-wide pay dates only; no per-employee payroll) | 2 |
| `checklist` | id integer NN; phase text; task text; done integer (legacy global flag) | id | - | **Onboarding task catalogue** | 15 |
| `checklist_assignments` | employee_id text NN; checklist_id integer NN; done integer NN default 0, CHECK in (0,1) | (employee_id, checklist_id) | employee_id -> employees; checklist_id -> checklist | **Per-employee onboarding tasks** | 45 |
| `tickets` | ticket_id integer identity; employee_id text NN; category text NN; subject text NN; description text NN; status text NN default 'open'; created_at text NN default now; updated_at text NN default now | ticket_id | employee_id -> employees | **Support tickets** | 0 |
| `escalations` | id integer identity; question text; contact_pref text; status text; created_at text | id | **none** (no employee_id column) | HR/IT escalations (simulated; not called by the frontend) | 0 |
| `messages` | id integer identity; question text; answer text; found integer; sources text (JSON string); created_at text; employee_id text | id | **no FK** on employee_id; index (employee_id, id DESC) | **Chat history** | 1 |
| `feedback` | id integer identity; message_id integer; rating text; comment text; created_at text | id | **no FK** on message_id | **Feedback** | 0 |
| `user_accounts` | id integer identity; email text NN; password_hash text NN; employee_id text; role text NN default 'employee' CHECK in (employee, admin); is_active integer NN default 1; created_at bigint NN; updated_at bigint NN | id | UNIQUE(email), UNIQUE(employee_id), employee_id -> employees; CHECK admin or employee_id not null | **Authentication** | 1 |
| `user_sessions` | token_hash text NN; user_id integer NN; csrf_token text NN; created_at bigint NN; last_seen_at bigint NN; expires_at bigint NN | token_hash | user_id -> user_accounts ON DELETE CASCADE | **Authentication (sessions)** | 0 |

Data not present at all: designation/job title, manager, team, per-employee payroll/salary/payslips, task due dates/owners, asset serial numbers/issue dates.

### A3. Ingestion status

| Item | Status | Evidence |
|---|---|---|
| CSV -> PostgreSQL | **Missing** | No CSV files or loader. Seeding = `docker/postgres/02_seed.sql` (pg_dump INSERTs run by `docker-entrypoint-initdb.d`) and the SQLite-only `backend/migrations/001-004_*.py` |
| PDF -> FAISS | **Partial** | `ingest.py::load_chunks` uses `handbook.md`; `handbook.pdf` is ignored because `handbook.md` exists. PDF chunks would get `section="PDF text"` and no page numbers, so their citations would be weak |
| Re-index | Implemented / Not Verified in Docker | `POST /ingest` (`routes/admin.py::reindex`, admin + CSRF). In Docker `data/index` is mounted `:ro`, so a rebuild there would likely fail. Not executed, because it writes |
| Source references | Implemented | file + section + score for cited chunks only (`guardrails.map_citation`, `rag.py`) |

### A4. SQL agent verification

| Check | Status | Evidence |
|---|---|---|
| Uses schema metadata | **Missing** | no schema dictionary; queries are hand-written in `employee_db.py` |
| Generates SQL from text | **Missing** (by design today) | no LLM-generated SQL anywhere |
| Only approved operations | Implemented | `execute_employee_query` allow-list of 5 functions; an unknown intent raises `ValueError` |
| Bound parameters only | Implemented | all queries bind parameters (`?` -> `%s`); enforced by `test_backend_sql_uses_bound_parameters_only` |
| Read-only execution | **Partial** | `employee_db._connection(readonly=True)` is enforced only for SQLite (`?mode=ro`); on PostgreSQL it opens a normal read-write transaction |
| Least-privilege DB role | **Missing** | the app connects as `onboardai`, which is a PostgreSQL **superuser** (`rolsuper = t`, verified live) |
| Statement timeout / row limit | **Missing** | none on app queries (only the `/health` probe sets `statement_timeout`) |
| Coverage of data | Partial | intents: leave_balances, assets, checklist, tickets, profile. `payroll_calendar` is reachable only via `GET /employees/payroll/calendar`, not via chat. `profile` matches "designation", but no such column exists |

### A5. RAG pipeline verification

| Step | Status | Evidence |
|---|---|---|
| Load + extract | Partial | Markdown first, PDF only as a fallback (`ingest.load_chunks`, `_read_pdf`) |
| Chunk | Implemented | heading-aware chunks with overlap (`chunk_markdown_handbook`, `_split_long`), FAQ Q/A chunks |
| Embed | Implemented | `embeddings.embed_texts` (local fastembed, no API key) |
| Store | Implemented | FAISS `IndexFlatIP` (cosine on normalised vectors) |
| Retrieve | Implemented | `retriever.search`, top_k = 4 |
| Evidence gate | Implemented | `guardrails.retrieval_gate` (0.65 threshold + 0.05 borderline band that needs keyword corroboration) |
| Grounded generation | Implemented | `llm.generate_answer` (temperature 0, `<untrusted_context>` wrapping, `sanitize_passage`) |
| Output validation | Implemented | `guardrails.validate_answer` (NOT_FOUND, leak check, citation validity, unsupported numbers/emails) |
| Citations | Implemented | cited chunks only, as `{file, section, score}` |
| Evaluation | Implemented earlier, Not Verified now | `scripts/rag_eval.py`, `docs/rag_eval_report.md` (50/50 recorded). Not re-run in this audit because it needs live Groq calls |

### A6. Orchestration and routing verification

**Onboarding question trace - "How many leaves do I have left?"**
1. `frontend/src/api.js` -> `POST /api/chat` -> nginx strips `/api` (`frontend/nginx.conf`).
2. `backend/routes/chat.py::chat`: `csrf_protected` resolves the session (`security.py::current_session` -> `services/auth.py::resolve_session`), `assert_own_employee` pins `employee_id` to the session's employee, and `employee_db.get_employee` checks that the employee exists.
3. `services/orchestrator.py::answer_question` -> `employee_query_router.classify_employee_query` returns `"leave_balances"`.
4. `employee_query_router.execute_employee_query` -> `employee_db.get_leave_balances` (`SELECT leave_type, available_days FROM leave_balances WHERE employee_id = %s`).
5. `orchestrator._format_employee_answer` builds a bullet list (no LLM).
6. `db.save_employee_message` writes to `messages`; the response is `{message_id, answer, sources: [], found: true}`.

**Policy question trace - "What is the leave policy?"**
1-2. Same as above.
3. `classify_employee_query` returns `None` (policy patterns) -> `rag.answer_question`.
4. `retriever.search` -> `embeddings.embed_texts` -> FAISS `IndexFlatIP.search` over `data/index/faiss.index` / `chunks.json`.
5. `guardrails.retrieval_gate`. If it passes: `llm.generate_answer` (Groq) -> `guardrails.validate_answer` -> cited sources. If it fails: the fixed `FALLBACK` text.
6. `db.save_employee_message`; the response includes the cited `sources`.

**Classifier probe results (run directly against `classify_employee_query`):**

| Question | Result | Correct? |
|---|---|---|
| How many leaves do I have left? | leave_balances | yes |
| How many casual leaves do I have left? | None (RAG) | **no** - the policy pattern `(casual/sick/earned/annual) leave` takes priority over the personal intent |
| What is my sick leave balance? | None (RAG) | **no** - same cause |
| What is the leave policy? | None (RAG) | yes |
| When is the next payroll date? | None (RAG) | **no** - no payroll intent; the DB table is unused by chat |
| What is my designation? | profile | routed, but the answer cannot contain a designation (no column) |
| Who is my manager? | None (RAG) | **no** - no data and no intent |
| What is the laptop policy and which laptop do I have? | None (RAG only) | **no** - mixed question; the personal part is dropped |
| Can I carry forward my remaining leaves and how many do I have? | leave_balances (DB only) | **no** - mixed question; the policy part is dropped |

| Check | Status | Evidence |
|---|---|---|
| Intent classification | Partial | regex, first match wins, policy patterns checked first |
| Mixed queries | **Missing** | single-branch return in `orchestrator.answer_question` |
| Shared LLM answer generator for SQL + RAG | **Missing** | Path A never calls the LLM; `llm.generate_answer` accepts only handbook passages and uses a handbook-only prompt |

### A7. Alignment estimate: about 63%

**Method:** the target architecture was split into the 19 components in table A1. Each was scored from code evidence (not from earlier docs) as Implemented = 1, Partial = 0.5, Missing = 0, all weighted equally.

- Implemented (10): components 1, 3, 6, 9, 10, 13, 14, 15, 16, 17
- Partial (4): components 2, 4, 5, 12
- Missing (5): components 7, 8, 11, 18, 19
- Score = (10 x 1 + 4 x 0.5) / 19 = **12 / 19 = 63%**

By area: **Path B (RAG, components 12-17) 5.5 / 6 = 92%**; **Path A (SQL, components 6-11) 3 / 6 = 50%**; **platform, routing and provider (components 1-5, 18, 19) 3.5 / 7 = 50%**. The RAG half is close to target. The gaps are concentrated in the structured-data path, the shared generator, mixed routing and Azure OpenAI. Equal weighting slightly flatters the result, because the missing items (schema dictionary, shared generator, mixed routing) are the core of the "hybrid" design.

### A8. Gaps, security concerns and unnecessary components

**Security concerns**
- S1 (High) The app DB role `onboardai` is a PostgreSQL superuser (`POSTGRES_USER` in `docker-compose.yml`). Replace it with a least-privilege app role, plus a separate `SELECT`-only role, before any text-to-SQL.
- S2 (High, before text-to-SQL) "Read-only" employee queries are not read-only on PostgreSQL (`employee_db._connection`). Needs `SET TRANSACTION READ ONLY` (or `default_transaction_read_only`), a `statement_timeout` and a row limit.
- S3 (High, future) Once SQL results go to the LLM, `tickets.subject` and `tickets.description` are user-written text. Treat them as untrusted data (the same `<untrusted_context>` handling as RAG) and pass only the session employee's rows.
- S4 (Medium) No FK on `messages.employee_id` or `feedback.message_id`; `escalations` has no `employee_id`, so escalations cannot be attributed to anyone.
- S5 (Known, unchanged) In-memory login rate limiter; Docker PG password rotation deferred; public API docs; backend port published on localhost while proxy headers are trusted.

**Functional gaps**
- G1 No CSV import. G2 No schema dictionary. G3 Path A results do not go through the LLM. G4 No mixed-query support. G5 No Azure OpenAI client or config. G6 The regex classifier misroutes personal leave-type questions and has no payroll intent. G7 The handbook PDF is not indexed, and PDF chunks lack page metadata. G8 Dates are stored as `text`, which blocks reliable date filtering in SQL. G9 The schema lacks fields that users' questions imply: designation, manager and per-employee payroll.

**Unnecessary / legacy components (candidates for removal after review)**
- Dual SQLite + PostgreSQL code paths: `_postgres()` / `_execute` duplicated in `services/db.py` and `services/employee_db.py`; the SQLite-only `backend/migrations/001-004`; the `data/app*.db` backups.
- Legacy global chat and checklist: `db.save_message` (rows without employee_id), `db.recent_messages` and `db.message_exists` (both unused), `routes/checklist.py` and the `checklist.done` column (superseded by `checklist_assignments`).
- `postgres.check_postgres_connection` (unused); the `escalations` table and `/escalate` route (not used by the frontend, overlaps `tickets`).
- `locust` in `requirements.txt` with an empty `tests/load/`; the committed `frontend/dist/`.
- Stale statements earlier in this plan (Section 2 "Prototype persistence: SQLite", "Authentication: Not implemented") no longer match the code.

### A9. Missing features ranked by priority

| Priority | Feature | Why |
|---|---|---|
| P1 | Least-privilege DB roles plus enforced read-only, timeouts and row limits for Path A | prerequisite for any LLM-driven SQL |
| P1 | Azure OpenAI provider (config + client), with Groq kept only as a local fallback | the stated target provider |
| P1 | Shared response generator that takes typed evidence (SQL rows + RAG passages) | core of the hybrid design |
| P2 | Intent classifier v2 that returns a set of intents (`sql`, `rag`, `both`) and fixes the leave-type and payroll questions | enables mixed queries; fixes the verified misroutes |
| P2 | Mixed-query orchestration (run both paths, merge evidence, one grounded answer with SQL and document citations) | planned behaviour |
| P2 | Schema dictionary (generated from `information_schema` plus curated descriptions and relationships) | grounding for tool selection and any text-to-SQL |
| P3 | CSV import pipeline into PostgreSQL (validated, idempotent upserts) | planned data source |
| P3 | PDF ingestion as a first-class source, with page numbers in citations | planned Path B input |
| P3 | Optional constrained text-to-SQL (SELECT-only, allow-listed tables, validator, read-only role), only if approved tools prove insufficient | flexibility; highest risk |
| P4 | Schema clean-up: proper date types, FKs on messages/feedback, drop legacy columns/tables, optional new fields (designation, manager) | data quality |
| P4 | Remove the SQLite path and legacy endpoints | maintenance |

### A10. Exact files requiring changes

| Change | Files |
|---|---|
| Azure OpenAI provider | `backend/config.py`, `backend/services/llm.py`, `.env.example`, `docker-compose.yml` (env only), LLM mocks in `tests/unit` and `tests/integration` |
| Shared generator + typed evidence | `backend/services/llm.py`, `backend/services/orchestrator.py`, `backend/services/rag.py`, `backend/services/guardrails.py` (also check numbers against SQL evidence), `backend/schemas/models.py` (source type for DB evidence) |
| Classifier v2 + mixed routing | `backend/services/employee_query_router.py`, `backend/services/orchestrator.py`, new `tests/unit/test_intent_router.py` |
| SQL safety | `backend/services/employee_db.py`, `backend/services/postgres.py`, new `docker/postgres/04_roles.sql`, `docker-compose.yml` |
| Schema dictionary | new `backend/services/schema_dictionary.py` (plus a curated `data/schema_dictionary.json` or `.yaml`) |
| CSV import | new `scripts/import_csv.py` (or `backend/services/csv_import.py`), new synthetic `data/csv/*.csv` |
| PDF ingestion | `backend/services/ingest.py`, `backend/services/retriever.py`, `tests/unit/test_ingest.py`, `docker-compose.yml` (index mount for re-indexing) |
| Payroll in chat | `backend/services/employee_query_router.py`, `backend/services/orchestrator.py` |
| Schema clean-up / legacy removal | `docker/postgres/01_schema.sql` + a new migration SQL, `backend/services/db.py`, `backend/routes/checklist.py`, `backend/routes/feedback.py`, `backend/main.py`, `requirements.txt` |
| Frontend (DB-evidence citations) | `frontend/src/App.jsx`, `frontend/src/format.js` |
| Docs | `docs/architecture.md`, `docs/architecture.png`, `README.md`, this file |

### A11. Recommended implementation order

1. **Safety baseline:** least-privilege PostgreSQL roles, read-only transactions, statement timeout and row limit for Path A; write the tests first.
2. **Azure OpenAI provider** behind a provider setting (Groq kept only as a local fallback); verify with `scripts/rag_eval.py`.
3. **Shared response generator** that accepts `{type: sql|document, ...}` evidence; route Path A results through it with guardrails (number/email checks against SQL rows; untrusted-text wrapping).
4. **Classifier v2 + mixed queries:** multi-intent output, fix the verified misroutes, add a payroll intent, run both paths when needed; add a routing test table.
5. **Schema dictionary** generated from `information_schema` plus curated descriptions; use it for tool descriptions (and later for any text-to-SQL).
6. **CSV import** into PostgreSQL with validation and idempotent upserts.
7. **PDF-first ingestion** with page-level citations; rebuild the index.
8. **Optional constrained text-to-SQL**, only if the approved tools are insufficient.
9. **Clean-up:** remove the SQLite path and legacy tables/routes, fix date types and FKs; update the architecture docs.
10. **Then** the Azure deployment milestones (A1 onward).

**Status:** audit complete; no implementation started. Awaiting owner review before any code change or Azure work.


---

## Phase 1 - PostgreSQL Security Hardening (23 November 2026)

**Status:** code complete and verified; **not applied to the running database.** The live Docker database was only inspected (read-only session): the backend still connects as `onboardai` (superuser) and no table has row-level security. Applying migration 005 and switching the backend to the new roles are approval steps (below). Nothing committed or pushed; no Azure resources.

### What changed in code

| Requirement | Implementation | Evidence |
|---|---|---|
| 1. No superuser for the app | New `onboardai_app` role: SELECT on application tables, INSERT only where the app inserts, UPDATE only on the exact columns it updates, DELETE only on `user_sessions`; NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOBYPASSRLS/NOINHERIT; role-level `statement_timeout=15s` | `backend/services/db_roles.py` (`APP_PRIVILEGES`), `backend/migrations/005_least_privilege_roles.py` |
| 2. App features preserved | Grant map derived from every SQL statement in `auth.py`, `db.py`, `employee_db.py`; a test fails if a used statement is not granted or a granted privilege is unused | `tests/unit/test_db_roles.py`; live: `test_application_flows_work_with_app_and_reader_roles`; Docker e2e 15/15 |
| 3. Separate read-only role/connection | New `onboardai_reader` role (SELECT on 7 employee-facing tables; no access to accounts, sessions, chat history, feedback, escalations) and `postgres_readonly_connection()` using `PG_READER_USER` | `backend/services/postgres.py`, `backend/config.py` |
| 4. Read-only transactions | Reader role default `default_transaction_read_only=on`; every read-only connection also sets it in libpq options plus `BEGIN READ ONLY`, and is always rolled back; SQLite: `mode=ro` + `PRAGMA query_only` | `postgres.py`, `readonly_query.py` |
| 5. Timeouts and row limits | `SQL_AGENT_STATEMENT_TIMEOUT_MS` (5000) and `SQL_AGENT_MAX_ROWS` (200, a ceiling callers cannot raise) on every read-only query; server-side cursor fetches at most limit + 1 rows; `PG_STATEMENT_TIMEOUT_MS` (10000) on app connections; timeouts return HTTP 503 with no SQL in the response or logs | `readonly_query.fetch_readonly`, `middleware/__init__.py` |
| 6. Server-side employee isolation | Unchanged session-based route checks, plus row-level security for the reader role on employees, leave_balances, assets, checklist_assignments, tickets. **Superseded by the pre-activation fixes (next section):** the policy now requires an HMAC-signed, connection-bound, expiring employee scope verified in the database, not a plain session setting | `db_roles.py` (`RLS_TABLES`), `employee_scope.py`, `employee_db.py` |
| Statement guard (SQL agent) | **Superseded (next section):** the regex guard was replaced by PostgreSQL-parser validation with allow-listed syntax, tables, functions and casts | `readonly_query.py` |
| 7. Parameterised SQL preserved | All queries still bound; role names/identifiers composed with `psycopg2.sql.Identifier`; passwords sent SCRAM-hashed (`encrypt_password`), never in plaintext SQL | `test_backend_sql_uses_bound_parameters_only` still passes |
| Startup guard | Development: warning when connected as superuser or without a reader role. `APP_ENV=production`: refuses to start | `db.enforce_role_policy` |
| Docker | Backend can opt in via `DOCKER_PG_APP_USER/PASSWORD`, `DOCKER_PG_READER_USER/PASSWORD`; defaults are unchanged (`onboardai`) so the running stack is unaffected | `docker-compose.yml` (validated with `docker compose config`) |

### Database roles and permissions (as verified on a disposable PostgreSQL 16)

| Table | onboardai_app | onboardai_reader (RLS = own employee only) |
|---|---|---|
| employees | SELECT | SELECT (RLS) |
| leave_balances, assets | SELECT | SELECT (RLS) |
| payroll_calendar | SELECT | SELECT |
| checklist | SELECT, UPDATE(done) | SELECT |
| checklist_assignments | SELECT, UPDATE(done) | SELECT (RLS) |
| tickets | SELECT, INSERT | SELECT (RLS) |
| messages, feedback, escalations | SELECT, INSERT | none |
| user_accounts | SELECT, INSERT, UPDATE(password_hash, employee_id, role, is_active, updated_at) | none |
| user_sessions | SELECT, INSERT, UPDATE(last_seen_at), DELETE | none |
| Role defaults (this DB) | statement_timeout 15s, idle-in-transaction 60s, 20 connections | read-only default, statement_timeout 5s, idle-in-transaction 10s, 10 connections |

Also: `REVOKE TEMPORARY ON DATABASE ... FROM PUBLIC`, `REVOKE CREATE ON SCHEMA public FROM PUBLIC`. Schema migrations continue to run as the owner.

### Verification (executed 23 November 2026)

| Check | Result |
|---|---|
| Backend `python -m pytest -q` | **243 passed, 28 skipped** (was 189; +54 new unit tests; the 28 skips are the live-PostgreSQL tests, which need a disposable server) |
| Live PostgreSQL role tests (`tests/integration/test_postgres_roles.py`, disposable `postgres:16-alpine`, real schema/seed/auth SQL, provisioned twice for idempotency) | **28 passed** - app flows (auth, sessions, chat history, feedback, escalation, checklist, tickets); 15 forbidden app statements (DDL, TRUNCATE, DELETE, ungranted columns, CREATE ROLE, disabling RLS) and self-escalation denied; reader denied on 5 sensitive tables, writes denied even after turning read-only off, no TEMP tables; RLS limits every secured table to the scoped employee and returns nothing without a scope; timeout (200 ms) cancels a long query; row limit; guard blocks scope escape; CLI dry run/verify print no secrets |
| Docker end-to-end (test-tagged image, disposable DB mirroring the stack's superuser owner) | migration CLI dry run executes nothing (64 statements planned), `--apply` 63 statements, re-apply idempotent, `--verify` 0 problems; account provisioned as the app role; backend running as `onboardai_app` + `onboardai_reader`: **15/15** HTTP checks (health, login, own data, cross-employee 403, payroll, checklist write + read-back, ticket write + read, chat employee path, live RAG chat with sources, history, feedback, logout); no least-privilege warnings; 0 secrets in logs. Test containers, network and image removed |
| Frontend `npm test` / ESLint `--max-warnings 0` / `npm run build` | 7 passed / 0 errors, 0 warnings / succeeded (no `dist` changes) |
| `docker compose config --quiet`; `tests/unit/test_docker_config.py` | valid; 7 passed |
| Live stack database (read-only inspection) | unchanged: `onboardai` superuser, no RLS; main stack containers healthy throughout |

One defect was found and fixed during verification: `python backend/migrations/005_least_privilege_roles.py` failed inside the container with `No module named 'backend'`. The script now adds the project root to `sys.path` when run directly.

### Migration steps requiring approval (not executed)

Full commands: [runbook section 9](runbook.md#9-database-roles-least-privilege).
1. Rebuild the backend image (`docker compose build backend`); this also picks up the earlier session fix. It does not touch the database volume.
2. Choose two new random passwords (16+ characters) in environment variables. No existing password is changed.
3. Run `005_least_privilege_roles.py --verify`, then the dry run, then `--apply` (one transaction, verified before commit). This creates the roles and grants, revokes TEMPORARY/CREATE from PUBLIC, and enables RLS with policies. The owner bypasses RLS, so the current backend keeps working.
4. **Credential switch:** set `DOCKER_PG_APP_*` / `DOCKER_PG_READER_*` and recreate only the backend (`docker compose up -d --no-deps backend`).
5. Rollback: unset those variables and recreate the backend. Roles and policies can stay in place.

### Outstanding risks

- The live database is unchanged until steps 3-4 are approved; until then the running backend is still a superuser connection (startup now logs this).
- ~~The RLS scope is a session setting~~ - **fixed** (F1, next section): the scope is HMAC-signed and verified in the database.
- ~~The statement guard is regex-based~~ - **fixed** (F2, next section): PostgreSQL-parser validation with allow-lists.
- Without `PG_READER_USER`, read-only queries fall back to the app credentials: still READ ONLY and limited, but without the privilege boundary or RLS.
- PUBLIC keeps EXECUTE on built-in functions (e.g. `pg_sleep`); bounded by statement timeouts.
- The app role can read `user_accounts.password_hash` (required for login).
- Fresh Docker volumes do not create the roles automatically; run migration 005 after first start.
- Row-limit truncation is logged but not signalled to API clients (current tables have at most 15 rows per employee).
- SQLite (tests/legacy) has no role separation or RLS.
- Unchanged from before: in-memory login rate limiter; Docker owner password rotation deferred; no HTTPS locally.

### Audit status updates

S1 (superuser app role): **Implemented in code, pending apply.** S2 (read-only, timeouts, row limits): **Implemented.** A4 "Least-privilege DB role", "Read-only execution" and "Statement timeout / row limit": **Implemented** (code), live apply pending.

### Files

- New: `backend/services/readonly_query.py`, `backend/services/db_roles.py`, `backend/migrations/005_least_privilege_roles.py`, `tests/unit/test_readonly_query.py`, `tests/unit/test_db_roles.py`, `tests/integration/test_postgres_roles.py`
- Modified: `backend/config.py`, `backend/services/postgres.py`, `backend/services/employee_db.py`, `backend/services/db.py`, `backend/middleware/__init__.py`, `docker-compose.yml`, `.env.example`, `docs/runbook.md`, `docs/architecture.md`, `docs/project_plan.md`

**Next:** see "Phase 1 - Pre-activation Security Fixes" below; then owner approval of the migration steps.


---

## Phase 1 - Pre-activation Security Fixes (23 November 2026)

**Status:** fixed and verified on temporary databases only; **migration 005 is still NOT applied to the running database.** Nothing committed or pushed.

### Findings from the pre-activation verification

| # | Finding | Severity | Status |
|---|---|---|---|
| F1 | The reader role could impersonate another employee. Row-level security compared `employee_id` to the plain session setting `app.current_employee`, which any session can change with `SET`, `SET LOCAL` or `set_config()` | High (exploitable with reader credentials or any arbitrary-SQL path) | **Fixed** |
| F2 | The regex statement guard could be bypassed with a quoted identifier (`SELECT "set_config"(...)`), letting a query reach F1 through the backend's guarded path | High (for any future LLM-generated SQL) | **Fixed** |

Neither finding was reachable through the application as deployed: all queries are hard-coded and nothing user-supplied runs as SQL.

### Fix 1 - PostgreSQL parser + strict allow-list validation (`backend/services/readonly_query.py`)

- Statements are parsed with **pglast 7.24** (libpg_query, PostgreSQL's own parser) and must be exactly one `SelectStmt`.
- Every node of the syntax tree must be an allow-listed type. Tables must be the reader's seven tables (or CTE names), unqualified or `public`. Functions must be on a list of pure aggregate, string, number and date helpers, unqualified or `pg_catalog`. Cast types must be allow-listed.
- Rejected, among others: `SET`/`RESET`/`DO`/`CALL`/`COPY`/`EXPLAIN`; multiple statements; `set_config` and `current_setting` in every spelling the server accepts (plain, quoted, schema-qualified, Unicode-escaped, `UESCAPE`, inside subqueries, CTEs, `WHERE`, `LATERAL`); functions in `FROM`; data-modifying CTEs; `SELECT INTO`; `FOR UPDATE/SHARE`; catalog, `information_schema` and private schemas; `reg*` casts; `?` placeholders inside literals.
- The text that is validated is the text that runs: placeholder count must match the parameters, and `%` is escaped for the driver.

### Fix 2 - Database-enforced, HMAC-signed employee scope (`backend/services/employee_scope.py`, migration 005)

- Reader policies now use `employee_id = (SELECT onboardai_rls.current_employee())`.
- `current_employee()` is `SECURITY DEFINER` (owner) with `search_path = pg_catalog, pg_temp`. It returns the employee only if `app.scope_sig` equals HMAC-SHA256(key, `v1:<employee>:<connection id>:<expiry>`). The connection id is `pg_backend_pid()` plus `backend_start`, so a signature cannot be replayed from another connection. Expiry is checked against the server clock, with a 60-second lifetime and a maximum of 600 seconds. Malformed values return NULL, which means no rows.
- The key is stored as HMAC inner/outer padded keys in `onboardai_private.scope_key`. Only the owner can use the schema: no USAGE for PUBLIC, the app role or the reader role, and no SELECT on the table. The function source in `pg_proc` contains no key material. The reader has USAGE on `onboardai_rls` and EXECUTE on the two functions only; the app role and PUBLIC have neither.
- Backend: `PG_SCOPE_SECRET` (32+ characters, same value given to migration 005 as `ONBOARDAI_SCOPE_SECRET`). Each read-only transaction fetches its connection id, signs, and sets the three settings transaction-locally. Wrong or missing secret means no rows. The backend refuses to start when `PG_READER_USER` is set without a valid secret.
- Migration 005: creates the private and verifier schemas, the key table and the functions; stores the key once (never replaced without `--rotate-scope-secret`; a mismatching secret only produces a note); creates or updates the reader policies; `--verify` checks the key, privileges, `SECURITY DEFINER`, pinned search path, EXECUTE grants, and that the policies use the verifier (and, given the secret, that it matches).

### Security test results (temporary PostgreSQL 16 only)

| Test | Result |
|---|---|
| Reader `SET app.current_employee` / `SET LOCAL` / `set_config` (session and local) | **PASS** - 0 rows (was a bypass) |
| Reader quoted `"set_config"`, `pg_catalog.set_config`, Unicode-escaped, `UESCAPE` (direct SQL) | **PASS** - 0 rows |
| Forged settings: random, all-zero, non-hex or expired signatures | **PASS** - 0 rows |
| Tampering with a valid EMP001 scope (change employee or expiry) | **PASS** - access revoked (0 rows), never widened |
| Replay of a valid EMP002 signature from another connection (session- and transaction-level) | **PASS** - 0 rows; control: valid on its own connection only |
| Signature made with a wrong secret; expired; beyond the maximum lifetime | **PASS** - 0 rows |
| Scope survives only its transaction | **PASS** |
| Reader/app reading or updating the key, creating objects in the private schema, replacing or overloading the verifier, `ALTER FUNCTION`, `ALTER POLICY`, `pg_temp` functions | **PASS** - all denied |
| Key material in catalogs (`pg_proc` source) | **PASS** - none |
| Malicious SQL through the backend path **with the validator skipped** (quoted `set_config` + read, MATERIALIZED CTE, `LATERAL`, `WHERE set_config(...)`, explicit EMP002 filters, UNION over all employee tables) | **PASS** - no EMP002 rows (database-enforced) |
| Same malicious SQL through `fetch_readonly` | **PASS** - rejected by the parser |
| Parser validation unit tests (67 statements: 12 allowed, 55 malicious) | **PASS** |
| SQL HMAC formula equals Python `hmac` | **PASS** |
| EMP001 vs EMP002 on every tested path: data-layer functions, SQL-agent queries (unfiltered, `= EMP002`, `<> EMP001`), scope-less connection, raw reader SQL, 13 HTTP cross-employee checks | **PASS** - EMP001 never received an EMP002 record |
| App role: disable RLS, drop/alter/create policies, BYPASSRLS, `SET ROLE`, functions in `public`, write other employees' leave/tickets/messages, grant reader access to accounts | **PASS** - all denied or no effect |
| Wrong backend secret | **PASS** - fails closed (no rows, no error leak) |
| Clone of live data: old image before migration / old image after migration / new image as owner / new image as app + reader roles | **PASS** - 26/26 HTTP checks in each of the four states |
| Migration on the clone: verify before (exit 1), dry run (nothing created), `--apply` (75 statements, one transaction), re-apply (idempotent), verify after (0 problems), data unchanged, no secrets in output or logs | **PASS** |
| Clone attack script (direct DB, validator-skipped and guarded paths, escalation, app role) | **PASS** - 43 blocked, 0 bypasses |
| `python -m pytest -q` | **PASS** - 300 passed, 77 skipped (the live-PostgreSQL tests) |
| `tests/integration/test_postgres_roles.py` on a disposable PostgreSQL 16 | **PASS** - 77 passed |
| Frontend `npm test` / ESLint `--max-warnings 0` / `npm run build`; `docker compose config` | **PASS** - 7/7, 0 warnings, built (no `dist` changes), valid |
| Container image: pglast installs on Python 3.12 (Linux) | **PASS** |

The live stack database was only read (`pg_dump` for the clone); all temporary containers, the network and the test image were removed; the main stack stayed healthy.

### Activation steps (unchanged order; still require approval)

As in [runbook section 9](runbook.md#9-database-roles-least-privilege), with one addition: generate `ONBOARDAI_SCOPE_SECRET` (32+ characters), pass it to the migration, and set `DOCKER_PG_SCOPE_SECRET` to the same value before recreating the backend.

### Remaining risks (after the fixes)

- Migration 005 is still not applied; the running backend remains a superuser connection until activation.
- The scope secret is a new credential. If it leaks together with the reader password, an attacker with database network access could sign any employee's scope. The database port is not published outside Docker.
- The app role intentionally reads all employees' rows; per-employee isolation for normal API traffic is enforced by the session-based route checks (tested), not by the database.
- The verifier's owner must be a superuser or a member of `pg_read_all_stats` (true for the Docker owner); provisioning refuses otherwise.
- Signature comparison in SQL is not constant-time; with HMAC over a per-connection message, a remote timing attack is not practical.
- pglast's grammar is PostgreSQL 17's, which is a superset of the 16 server; constructs that 16 does not support fail at execution, never bypass validation.
- Row-limit truncation is logged but not signalled to API clients.
- Unchanged: in-memory login rate limiter, Docker owner password rotation deferred, no HTTPS locally.

### Files (this step)

- New: `backend/services/employee_scope.py`
- Modified: `backend/services/readonly_query.py` (parser validator), `backend/services/postgres.py` (signed scope), `backend/services/db_roles.py` (private key, verifier, policies, verify), `backend/migrations/005_least_privilege_roles.py` (scope secret, `--rotate-scope-secret`), `backend/services/db.py` (startup check), `backend/config.py` (`PG_SCOPE_SECRET`), `requirements.txt` (`pglast==7.24`), `docker-compose.yml` (`DOCKER_PG_SCOPE_SECRET`), `.env.example`, `tests/unit/test_readonly_query.py`, `tests/integration/test_postgres_roles.py`, `docs/runbook.md`, `docs/architecture.md`, `docs/project_plan.md`

**Phase 1 readiness:** security fixes complete; activation status is tracked in the next section.


---

## Phase 1 - Activation Status (23 November 2026)

**Status: ACTIVATED (23 November 2026).** Preflight passed, the owner gave final confirmation, migration 005 was applied and the backend switched to the least-privilege roles. The preflight record below describes the state before activation; the activation result is at the end of this section.

### Preflight results

| Check | Result | Evidence |
|---|---|---|
| 1. Running Docker database healthy | **PASS** | db, backend and frontend containers healthy; `pg_isready` accepting connections; `/api/health` 200 `database: ok`; PostgreSQL 16.16, 8.3 MB; no other client sessions |
| 2. Usable backup exists | **PASS** (created during preflight) | None existed for the Docker PostgreSQL database (only SQLite files from 20 Nov). Created `onboardai_local_backups/postgres_docker/onboardai_pre_phase1_20261123_121605.dump` outside the repository (pg_dump custom format, 23,699 bytes, SHA-256 `a144332004654d81dfe0cbdc2031e54097bc74e9a364c60a5c19c5142c0b1657`). Restored into a throwaway container with `pg_restore --exit-on-error`: all 12 tables and every row count match live. Restoring needs a fresh `postgres:16` container with `POSTGRES_USER=onboardai`. The file contains one account's password hash: keep it local |
| 3. Role passwords and scope secret configured securely | **PASS** (after owner decision) | Initially none were set anywhere. Owner chose a locked file outside the repository: `<secrets-file>` (outside the repository), ACL owner FullControl only, inheritance disabled, not in git. Holds the existing `DOCKER_PG_PASSWORD` (copied from the running container's configuration, unchanged, consistent with the backend), new app and reader passwords (43 characters each), new scope secret (64 characters), and `BACKEND_PORT=8001` / `FRONTEND_PORT=8080` so a recreate keeps the current ports. No value was displayed or logged. Runbook section 9 documents the file |
| 4a. Runbook step 1: `docker compose build backend` | **PASS** | Image rebuilt; the running backend container is still on its original image (not recreated) |
| 4b. `--verify` on the live database | **PASS** (expected exit 1) | Problems are exactly `role onboardai_app does not exist`, `role onboardai_reader does not exist` |
| 4c. Dry run on the live database | **PASS** | Exit 0; 75 statements planned, identical to the preview on the verified backup restore; no errors or notes; nothing created; 0 secret values in output |
| 5. Unexpected errors | **None** | Only cosmetic: Windows PowerShell 5.1 shows compose progress lines as `NativeCommandError` (exit codes 0/1 as expected; 0 Python errors); one-off containers removed |

### Changes `--apply` will make (one transaction, verified before commit)

- **Roles:** create `onboardai_app` and `onboardai_reader` (LOGIN, no superuser/createdb/createrole/replication/bypassrls, SCRAM passwords); defaults for this database (app: statement_timeout 15 s, idle-in-transaction 60 s; reader: read-only by default, statement_timeout 5 s, idle-in-transaction 10 s); connection limits 20 and 10.
- **Database and schema hardening:** `REVOKE TEMPORARY ON DATABASE onboardai FROM PUBLIC`; `REVOKE CREATE ON SCHEMA public FROM PUBLIC`; CONNECT and USAGE on `public` for both roles.
- **Grants:** 23 privilege grants on the 12 application tables and 5 identity sequences for the app role; SELECT on 7 tables for the reader (as listed in runbook section 9).
- **New objects:** schema `onboardai_private` with table `scope_key` (1 row: the HMAC padded keys; owner-only); schema `onboardai_rls` with `connection_id()` and the SECURITY DEFINER `current_employee()` (EXECUTE for the reader only).
- **Row-level security:** enabled on employees, leave_balances, assets, checklist_assignments and tickets, with 10 policies (app: all rows; reader: signed employee scope).
- **Not changed:** any table data, the `onboardai` owner role and its password, other tables, the running containers. The owner bypasses row-level security, so the current backend keeps working (tested: state B, 26/26).
- **Locking:** enabling RLS briefly takes exclusive locks on the 5 tables inside one short transaction (about 1 s measured on the clone).

### After `--apply` (runbook step 4, part of the approved activation)

Add the switch variables to the secrets file and recreate only the backend (`docker compose --env-file ... up -d --no-deps backend`). This is a few seconds of backend restart on the new image as `onboardai_app` + `onboardai_reader` with the scope secret. Sessions are server-side in the database, so signed-in users stay signed in. Then: health, login, isolation and live verification checks. Rollback is in runbook section 9.

### Activation result (23 November 2026, after the owner's final confirmation)

**Status: ACTIVATED.** Migration 005 is applied to the live Docker database and the backend runs as `onboardai_app` + `onboardai_reader` with the signed employee scope.

| Step | Result |
|---|---|
| Gate: health immediately before apply | `/api/health` 200 `database: ok`; 0 active sessions |
| Runbook step 3: `--apply` | Exit 0: "Migration 005 applied: 75 statements, roles onboardai_app and onboardai_reader verified" (one transaction, verified before commit); 0 secret values in output |
| `--verify` (with scope secret) | Exit 0, 0 problems; RLS on all 5 employee tables; stored key matches the secret; verifier SECURITY DEFINER with pinned search path; key unreachable by app, reader and PUBLIC; verifier executable by the reader only |
| Gate: old backend (owner) after apply | Healthy; protected routes 401; data unchanged |
| Runbook step 4: credential switch | Switch variables added to the locked secrets file (owner-only ACL kept); `docker compose --env-file ... up -d --no-deps backend` recreated only the backend on the new image; healthy after 12 s; `PG_USER=onboardai_app`, `PG_READER_USER=onboardai_reader`, scope secret set; port 127.0.0.1:8001 unchanged; db and frontend containers not restarted |
| HTTP checks (via nginx, non-invasive) | `/api/health` 200; backend `:8001/health` 200; 5 protected routes 401 without a session; wrong-password login 401 |
| In-container live checks (backend's own configuration; read-only, attacks denied or rolled back) | **37/37 PASS**: app connects as non-superuser `onboardai_app`; reader is read-only by default; startup policy reports no issues; EMP001 profile, leave, 15-item checklist and payroll read through the signed scope; unfiltered SQL-agent queries on all 5 employee tables return only EMP001; explicit EMP002 filter and scope-less reads return nothing; validator rejects quoted `set_config`, `SET`, `user_accounts`, signing key; reader `SET LOCAL`, `set_config`, quoted `set_config`, forged signature and replayed EMP002 signature give no EMP002 rows; reader cannot read the key or accounts, write, replace the verifier or `SET ROLE`; app role cannot disable RLS, alter policies, read the key, call the verifier, gain BYPASSRLS, `SET ROLE`, delete or run DDL |
| Backend log since the switch | 0 tracebacks; no least-privilege warnings; no secrets |
| Live data | Unchanged: 1 account, 9 completed checklist items, 1 message, 0 tickets, 0 feedback, 0 escalations |

**Not performed (by design, non-invasive):** sign-in with the real account and data writes on the live stack. App-role writes (checklist, tickets, chat history, feedback, sessions) were verified on the clone with the identical plan (26/26 in state D). **Recommended owner check:** sign in at http://localhost:8080, toggle a checklist item, ask the assistant one question.

**Rollback (if ever needed):** remove the `# Runbook step 4` block from `<secrets-file>` and run `docker compose --env-file <file> up -d --no-deps backend`; the backend returns to the owner account. Full database restore: the pre-activation backup above.

**Operating note:** from now on run compose commands with `--env-file <path-to-secrets-file>` (runbook section 9). Without it, compose cannot interpolate `DOCKER_PG_PASSWORD`, and a recreate would not use the least-privilege roles.

**Remaining risks:** the existing `DOCKER_PG_PASSWORD` is weak (11 characters) and its rotation is still deferred; the secrets file and the backup are plaintext on disk (owner-only ACL; also keep the values in a password manager); the backup contains one password hash; in-memory login rate limiter; no HTTPS locally.


---

## Phase 2 - Hybrid SQL + RAG Orchestration: Step 1 Investigation (23 November 2026)

**Azure integration and deployment: ON HOLD** (owner decision, 23 November 2026). Milestones A1-A6, Azure OpenAI migration, Azure hosting and CI/CD deployment are paused; Groq remains the LLM provider. Work focuses exclusively on Phase 2.

**Scope of this step:** read-only investigation. No application code, migrations, databases or containers changed; nothing committed. Proposed changes below await owner approval.

### Request path (verified in code)

1. `frontend/src/api.js` `chat()` -> `POST /api/chat {employee_id, question}` -> nginx -> `backend/routes/chat.py::chat`.
2. Authentication context: `security.csrf_protected` -> `auth.resolve_session` (server-side session cookie + CSRF header). `assert_own_employee` replaces any request `employee_id` with the session's employee (403 on mismatch); admin accounts have `employee_id = None`.
3. `services/orchestrator.py::answer_question` -> `employee_query_router.classify_employee_query(question)`, which returns **one** intent or `None`.
4. Intent -> `execute_employee_query` (allow-list of 5 functions in `employee_db.py`) -> `readonly_query.fetch_readonly` (pglast validation, reader role, READ ONLY, timeout, row limit, HMAC-signed employee scope enforced by RLS) -> `_format_employee_answer` (deterministic text, **no LLM**) -> `db.save_employee_message`.
5. `None` -> `rag.answer_question`: `retriever.search` (FAISS) -> `guardrails.retrieval_gate` -> `llm.generate_answer` (Groq; handbook-only prompt) -> `guardrails.validate_answer` (citations must be `[Handbook n]`/`[FAQ]`) -> fallback text if anything fails -> saves the message itself.
6. Response contract `ChatResponse {message_id, answer, sources: [{file, section, score}], found}`; the frontend `formatSources` renders any `{file, section}` pair, so new source kinds need no frontend change.

### Root cause: onboarding-status misrouting

`classify_employee_query` (`backend/services/employee_query_router.py`) matches the `checklist` intent only with `(my|onboarding) ... (checklist|tasks?|progress)` or `(pending|completed) ... (tasks?|checklist)`. **"status" is not in either keyword list**, so "What is my onboarding status?" returns `None` and falls through to handbook RAG. There are **no unit tests for the classifier**, so the gap was never caught.

Classifier probe (executed against the current code):

| Question | Routed to | Expected |
|---|---|---|
| What is my onboarding status? | RAG | checklist (SQL) |
| How far along am I with onboarding? / Am I done with onboarding? | RAG | checklist (SQL) |
| What do I still need to complete? / What tasks are left for me? / How many tasks have I completed? | RAG | checklist (SQL) |
| What is my onboarding progress? / Which onboarding tasks are still pending? / Show my checklist | checklist | checklist (correct) |
| How many casual leaves do I have left? / What is my sick leave balance? | RAG | leave_balances (the leave-type "policy" pattern is checked first and wins) |
| When is the next payroll date? / When is my next salary payment? | RAG | payroll calendar (no payroll intent exists) |
| What is the leave policy and how many leaves do I have left? | RAG only | SQL + RAG (mixed) |
| Which laptop do I have and what is the laptop policy? | RAG only | SQL + RAG (mixed) |
| What is the dress code? | RAG | RAG (correct) |

### Data supporting onboarding status (live database, read-only)

- `checklist(id integer PK, phase text, task text, done integer)` - 15 tasks: Day 1 (4), Week 1 (6), Month 1 (5). `checklist.done` is a legacy global flag (all 0, used only by the admin `/checklist` route).
- `checklist_assignments(employee_id text, checklist_id integer, done integer 0/1; PK (employee_id, checklist_id); FKs to employees and checklist)` - 15 per employee; current progress EMP001 4/15, EMP002 3/15, EMP003 0/15.
- `employee_db.get_employee_checklist(employee_id)` already returns `{id, phase, task, done}` for the session employee through the reader role + signed scope. **Onboarding status needs no new SQL**, only routing and formatting. No due dates or task owners exist (status can be "x of y, by phase, pending items", not "overdue").

### Safeguards in place (to preserve)

- Identity from the server-side session only; request `employee_id` must match (403); admins have no employee workspace.
- SQL path: allow-listed functions only (no LLM-generated SQL); every read through `fetch_readonly` (PostgreSQL-parser validation, reader role, READ ONLY, 5 s timeout, 200-row cap) with an HMAC-signed, connection-bound scope verified by RLS (Phase 1, activated).
- RAG path: retrieval gate, untrusted-context wrapping, output validation (citations, unsupported numbers/emails, leak check), fallback text.
- Gap found: `guardrails.leak_reasons` checks `groq_api_key` and `pg_password` but not the new `pg_reader_password` / `pg_scope_secret`.

### Mixed SQL + RAG support

**Not supported.** `orchestrator.answer_question` returns from exactly one branch; `rag.answer_question` persists its own message, so two parts cannot be combined into one saved message; the LLM prompt and `guardrails.citations()` accept only handbook/FAQ evidence.

### Proposed changes (smallest safe set; awaiting approval)

**Step 2A - routing fix and onboarding status (fixes the reported bug)**

| File / function | Change |
|---|---|
| `employee_query_router.py` | Add `route(question) -> Route(sql_intents: tuple, needs_policy: bool)`. Onboarding vocabulary (status, progress, pending, remaining, left, completed, done, how far, still need) -> `checklist`. A personal marker (my, I, me, do I have, left, remaining, balance) beats the leave-type policy pattern. New `payroll` intent (next payroll / pay date / salary payment date). Policy cues (policy, rules, allowed, can I, eligible, how do I, process) -> `needs_policy`. Keep `classify_employee_query` as a compatible wrapper |
| `employee_query_router.execute_employee_query` | Add `payroll` -> existing `employee_db.get_payroll_calendar` (company-wide, no scope). The allow-list stays closed; no new SQL |
| `orchestrator._format_employee_answer` | Checklist answer leads with a status summary ("4 of 15 onboarding tasks completed (27%)", per-phase counts, pending tasks first); payroll formatter |
| `guardrails.leak_reasons` | Also check `pg_reader_password` and `pg_scope_secret` |

**Step 2B - mixed queries (deterministic composition, no new LLM surface)**

| File / function | Change |
|---|---|
| `rag.py` | Split `answer_question` into `answer_policy(question) -> result` (no persistence) plus the existing wrapper (unchanged behaviour for RAG-only questions) |
| `orchestrator.answer_question` | When `route` has SQL intents **and** `needs_policy`: run the SQL tool(s) (same allow-list and session scope) and the RAG pipeline, then return one answer ("From your records: ... / From the handbook: ..."), sources = `{file: "Your records", section: <tool label>, score: 1.0}` + the cited handbook sources, `found` if either part was found, **one** saved message. If the LLM is unavailable, return the records part with a note for the policy part (no 503 when data is available) |
| Unchanged | `ChatRequest`/`ChatResponse`, routes, frontend, database, migrations, Phase 1 security modules |

**Step 2C - optional, separate approval later:** shared LLM synthesis over typed evidence (SQL rows wrapped as untrusted data, because ticket subjects and descriptions are user-written; `[Your records]` citations validated by guardrails; numbers checked against SQL rows), and LLM tool selection or text-to-SQL backed by a schema dictionary. Deferred because it adds prompt-injection surface; 2A/2B deliver the hybrid behaviour with existing grounded components.

### Tests required

- **Unit - routing table** (new `tests/unit/test_intent_router.py`): every probe question above plus negatives (pure policy questions stay RAG; "Show EMP002's checklist" still uses the session employee). Includes the regression case "What is my onboarding status?" -> checklist.
- **Unit - formatting:** onboarding status (all pending / partial / all done / empty), payroll, leave types.
- **Unit - orchestration:** mixed query returns both parts and both source kinds and saves one message; RAG fallback keeps the SQL part; LLM unavailable keeps the SQL part; admin without employee gets the policy part plus a note; SQL-only and RAG-only paths unchanged (existing tests).
- **Unit - guardrails:** leak check covers reader password and scope secret.
- **Integration (`/chat` via TestClient):** EMP001 onboarding status returns EMP001's checklist only; mixed question; cross-employee and CSRF behaviour unchanged; `ChatResponse` contract and history unchanged.
- **Existing suites:** full backend (300), live-PostgreSQL role/attack suite (77) on a disposable server, frontend tests/lint/build.
- **Clone verification:** HTTP checks on a clone of the live data with the least-privilege roles (as in Phase 1), before any change to the running stack.


---

## Phase 2 - Hybrid SQL + RAG Orchestration: Steps 2A and 2B Implemented (23 November 2026)

**Status: IMPLEMENTED AND MANUALLY VERIFIED.** Approved by the owner on 23 November 2026; validated on a temporary clone (the running stack was not modified during that validation), then deployed by the owner to the local Docker stack (backend image rebuilt and backend container recreated at 14:26-14:35 IST; still running as `onboardai_app` with the reader role and signed scope; no migration or database change). Not yet committed. Azure integration and deployment remain **ON HOLD**; Groq remains the LLM provider.

### What changed

| File | Change |
|---|---|
| `backend/services/employee_query_router.py` | New deterministic `route(question) -> Route`: clause splitting at new questions only, per-clause precedence P1-P5 (topic state cue > policy cue > first-person + personal topic > ambiguous topic > general), topic inheritance for follow-up clauses, third-party detection, leave-type focus. `classify_employee_query` kept as a wrapper. Closed allow-list resolved by name at call time; new `payroll` intent via `execute_company_query` (existing `get_payroll_calendar`). No new SQL |
| `backend/services/orchestrator.py` | Records-only, handbook-only and mixed flows; one saved message per chat in every flow; checklist status summary ("You have completed 4 of 15 onboarding tasks (27%); 11 pending", per-phase counts, pending first), leave-type focus, payroll next date, whole-number day display; source labels `Your records` / `Company records`; safe notes for third-party requests, accounts without an employee workspace and handbook failures |
| `backend/services/rag.py` | `answer_policy()` (no persistence) split from `answer_question()` (unchanged behaviour: same pipeline, saves once) |
| `backend/services/guardrails.py` | Leak check also covers `pg_reader_password` and `pg_scope_secret` |
| Docs | `docs/architecture.md` (new "Hybrid chat routing" section, diagrams, components), `README.md` (routing and response steps) |
| Unchanged | `ChatRequest`/`ChatResponse`, routes, authentication, CSRF, frontend code, database schema, migrations, Phase 1 security modules |

### Routing examples (verified)

| Question | Route | Answer source |
|---|---|---|
| What is my onboarding status? | records: checklist (P1) | Your records > Onboarding checklist |
| How far along am I with onboarding? / What do I still need to complete? | records: checklist | Your records |
| How many casual leaves do I have left? | records: leave_balances (P1 beats leave-type wording) | "Casual Leave: 8 days available." + all balances |
| How many casual leaves do I get in a year? | handbook (P2) | handbook.md |
| How many casual leaves? | handbook (P4 ambiguous -> safe default) | handbook.md |
| When is the next payroll date? | records: payroll | Company records > Payroll calendar |
| When is my salary credited? | handbook (payroll is company-wide; rule question) | handbook.md |
| What is the leave policy and how many do I have left? | mixed: leave_balances + handbook("what is the leave policy") | Your records + handbook.md |
| Which laptop do I have and what is the laptop policy? | mixed: assets + handbook | Your records + handbook.md |
| What is my onboarding status? Also, what is the dress code? | mixed: checklist + handbook | Your records + handbook.md |
| Show EMP002's checklist / How many leaves does Meera have left? | records clause with third party -> refused, no query | none |
| What is the dress code? | handbook (P5) | handbook.md |

### Fallbacks

Missing records -> "No ... records were found." (never invented). Weak handbook evidence or rejected LLM answer -> standard fallback text. Mixed question with LLM unavailable or retrieval error -> records part plus "I could not check the handbook right now ..." (HTTP 200). Handbook-only question with LLM unavailable -> HTTP 503 as before, nothing saved. Database timeout -> HTTP 503 (Phase 1), nothing saved. Admin (no employee) -> note instead of personal records; payroll calendar and handbook part still answered.

### Test results

| Suite | Result |
|---|---|
| 2A gate: full backend suite after Step 2A | 409 passed, 77 skipped (live-PostgreSQL suite, run separately below) |
| Full backend suite after Step 2B (final) | **445 passed**, 77 skipped (300 existing + 145 new: routing table and precedence 91, orchestration/formatting 36, `/chat` integration 13, guardrails leak 5) |
| Live-PostgreSQL role/attack suite on a disposable server | **77 passed** |
| Phase 1 adversarial DB attacks on the clone | **43 blocked, 0 bypasses** |
| Clone HTTP checks, Phase 2 image as `onboardai_app` + `onboardai_reader` + signed scope, real Groq | **23/23 passed** |
| Clone HTTP checks, same image with an invalid Groq key (LLM outage) | **5/5 passed** |
| Backend logs on the clone | 0 tracebacks, 0 secrets, 0 question text, no least-privilege warnings |
| Frontend `npm test` / `npm run lint` / `npm run build` | 8/8 (1 new source-label test) / 0 problems / built |
| Live stack during validation | Unchanged (containers, image, data: messages/completed/tickets/accounts 3/7/0/1 before and after) |

Clone method: temporary PostgreSQL 16 container; live data copied with read-only `pg_dump` (signing-key table data excluded); throw-away role passwords and scope secret via migration 005 `--apply --reset-passwords --rotate-scope-secret`; clone-only test passwords; Phase 2 image built under a separate tag; all temporary containers, network and the test image removed afterwards.

### Remaining limitations

- Rule-based vocabulary: unusual phrasings can still fall to the handbook (safe default) and new topics need new terms; covered by the regression table, which should grow with real questions.
- Third-party detection covers employee IDs, possessives, "does/has/is <name> ...", colleague/manager/their; other phrasings that name a person are not detected. Data exposure is still impossible (reads use only the session employee under RLS), but such an answer would show the user's own records.
- Mixed answers are composed, not synthesised: two sections rather than one blended paragraph (Step 2C, separate approval).
- Records-only answers are not LLM-validated (they are produced from rows, not generated). A database timeout still fails the whole mixed request (503) rather than returning only the handbook part.
- Retrieval failure in a handbook-only question remains a safe HTTP 500 (existing contract and test).
- Ticket subjects are user-written text and are echoed in ticket answers (unchanged behaviour; not sent to the LLM).

### Manual verification (owner, 23 November 2026)

Performed in the browser against the local Docker stack (frontend http://localhost:8080) after the backend rebuild. All passed:

| Scenario | Result |
|---|---|
| Onboarding status and pending tasks ("What is my onboarding status?") | PASS - status summary from the employee's own checklist |
| Employee-specific leave balances | PASS |
| Payroll calendar retrieval | PASS |
| Mixed SQL + RAG leave-policy question | PASS - "From your records" and "From the handbook" sections with separate sources |
| Cross-employee access refusal | PASS - refused, no other employee's data shown |

Azure integration and deployment remain **ON HOLD**; Groq remains the temporary LLM provider. The limitations listed above remain open and are accepted for the local release.

### Version control readiness (23 November 2026)

Review of all uncommitted changes (Phase 1 least-privilege roles, signed employee scope and read-only SQL path; Phase 2A/2B routing and orchestration; documentation):

- 18 modified and 10 new files, all intended. No migration is outstanding: migration 005 is already applied to the live database and is committed as code for reproducibility.
- Secret scan: the real values of every key, password and scope secret in `.env` and the external secrets file were searched for in the diff and all new files - **none found**. `.env.example` and `docker-compose.yml` contain only placeholders and variable references.
- Not in the repository / ignored: `.env`, `data/*.db` (including backups), `data/index/*`, `logs/`, `frontend/dist/`, `node_modules/`, caches. The database backup (`onboardai_local_backups/`) and the secrets file (`<secrets-file>`) are outside the repository. Temporary validation scripts stayed in the session scratch directory.
- `git diff --check`: clean after two whitespace fixes (trailing spaces in this file, blank line at end of `backend/services/db_roles.py`).
- Tests at commit time: backend 445 passed (+77 live-PostgreSQL tests passed on a disposable server), frontend 8/8, lint clean.


---

## Phase 3 - Architecture Completion Audit (23 November 2026)

**Scope:** read-only audit of code, configuration, database structure, tests and documentation at commit `99d1c30` (branch `dev`, in sync with `origin/dev`). Only this file was changed. No application code, database, Docker container or Git history was modified. **Azure integration and deployment remain ON HOLD**; Groq remains the temporary LLM provider.

**Evidence sources:** source files and tests (cited inline); read-only checks of `data/index` (FAISS `ntotal` and chunk metadata) and `data/raw/handbook.pdf` (text extraction only); `curl` of the running stack (`/api/docs`, `/api/openapi.json`, `/api/checklist` without a session); request timings read from the running backend's log file (no question text is logged). The full test suite was not re-run: the last full run at `99d1c30` was 445 passed + 77 live-PostgreSQL tests.

**Requirement sources:** no EY capstone requirement document exists in the repository. The sources available are `docs/problem_statement.md` (project-authored MVP scope and success criteria), the milestone table in section 1 of this file, and the hybrid architecture described in the Phase 1 audit (A1). Mandatory capstone requirements are therefore marked **UNVERIFIED** below.

### P3-A. Architecture completion matrix

Status: **COMPLETE** = implemented with sufficient evidence; **PARTIAL** = implemented but missing required behaviour or validation; **MISSING** = no implementation found.

| # | Component | Status | Existing implementation | Evidence | Missing work | Priority |
|---|---|---|---|---|---|---|
| 1 | CSV -> PostgreSQL ingestion | MISSING | Data comes from hard-coded seeds | `docker/postgres/02_seed.sql`, `backend/migrations/002_seed_demo_data.py`; no `.csv` file and no CSV/`COPY` code in the repository | Validated, idempotent, transactional importer with dry run and error report | P1 |
| 2 | PostgreSQL schema and integrity | PARTIAL | 12 tables, PKs, FKs on employee tables, CHECK constraints, UNIQUE (employee_id, leave_type) | `docker/postgres/01_schema.sql`, `03_auth_schema.sql`, `tests/unit/test_docker_config.py` | No FK on `messages.employee_id` or `feedback.message_id`; `escalations` has no `employee_id`; dates stored as `text` | P1 (FKs), P2 (date types) |
| 3 | Schema dictionary | MISSING | Table/column inventory exists only as documentation (Phase 1 audit A2) | No metadata module; `information_schema` used only for table-existence checks (`db.py::init_db`, migration 004) | Curated machine-readable dictionary (tables, columns, types, keys, relationships, descriptions, allowed reader tables), with a test that it matches the live schema | P1 |
| 4 | SQL access layer (approved tools) | COMPLETE | Closed allow-list of 6 read operations, bound parameters, read-only reader role, pglast validation, timeout, 200-row cap, signed scope + RLS | `employee_query_router.py::ALLOWED_OPERATIONS`, `COMPANY_OPERATIONS`, `execute_employee_query`; `readonly_query.py::assert_select_only`, `fetch_readonly`; `employee_scope.py`; `tests/unit/test_readonly_query.py` (103), `tests/integration/test_postgres_roles.py` (77) | - | - |
| 5 | Constrained text-to-SQL agent | MISSING (by design) | Safety infrastructure for it already exists (validator, reader role, RLS) | No LLM-generated SQL anywhere | Only if the requirement is confirmed; never unrestricted | P2 (requirement UNVERIFIED) |
| 6 | PDF ingestion | PARTIAL | `_read_pdf` (pypdf) exists | `ingest.py::load_chunks` skips a PDF when a same-name `.md` exists; current index has **0 PDF chunks** (48 chunks: `faqs.md` 25, `handbook.md` 23); `handbook.pdf` has 3 pages of extractable text (5,158 characters, so no OCR needed) | PDF as a first-class source with page numbers and section detection; duplicate-document handling; tests on a real PDF | P1 |
| 7 | OCR fallback | MISSING | - | No OCR code or dependency | Not needed for the current text-based PDF; optional | P2 |
| 8 | Chunking and metadata | PARTIAL | Heading-aware Markdown chunks (350 words, 40 overlap), FAQ Q/A chunks, source + section | `ingest.py::chunk_markdown_handbook`, `chunk_faqs`, `_split_long`; `tests/unit/test_ingest.py` (3) | Page numbers, document hash/version; PDF chunks would be labelled only "PDF text" | P1 (with #6) |
| 9 | Embeddings | COMPLETE | fastembed `BAAI/bge-small-en-v1.5`, normalised, baked into the image | `embeddings.py::embed_texts`, `Dockerfile`; rag_eval A05 | - | - |
| 10 | FAISS index lifecycle | PARTIAL | `IndexFlatIP` built and saved; lazy load; admin `POST /ingest` | `ingest.py::build_index`, `retriever.py::_ensure_loaded`, `routes/admin.py::reindex`; `tests/unit/test_retriever.py` (1) | Non-atomic write (index then JSON; a failure leaves them out of sync); no vector/metadata count check on load; the request path builds the index if it is missing; in Docker `data/index` is mounted `:ro`, so `POST /ingest` cannot work there (not executed in this audit) | P1 |
| 11 | Document-level access restrictions | MISSING (not required today) | All documents are company-wide policy | - | Needed only if restricted documents are added | P2 |
| 12 | RAG retrieval, grounding and guardrails | COMPLETE | Evidence gate (0.65 + corroborated 0.60-0.65 band), untrusted-context wrapping, NOT_FOUND rule, citation/number/email/leak validation, fallback | `guardrails.py`, `rag.py::answer_policy`, `llm.py::generate_answer`; `tests/unit/test_guardrails.py` (25); `docs/rag_eval_report.md` | Grounding check is lexical: paraphrased unsupported claims could pass (documented) | P2 |
| 13 | Citations with page references | PARTIAL | Cited sources as file + section (+ score); records labelled `Your records` / `Company records` | `guardrails.py::map_citation`, `orchestrator.py::RECORD_LABELS`, `frontend/src/format.js::formatSources` | No page numbers (blocked by #6) | P1 (with #6) |
| 14 | Conflicting policy information | MISSING | - | No conflict detection; one synthetic handbook, so no conflicts exist today | Only relevant with multiple document versions; document-version metadata covers it | P2 |
| 15 | LLM provider and failure handling | PARTIAL | Groq through the OpenAI client, 30 s timeout, 2 retries, `LLMUnavailable` -> 503 (handbook-only) or records + note (mixed) | `llm.py::_client`, `routes/chat.py::chat`, `orchestrator.py::_policy_part`; tests in `test_error_handling.py`, `test_hybrid_chat.py` | Azure OpenAI provider (**ON HOLD**) | P1, ON HOLD |
| 16 | Intent routing (SQL / RAG / mixed) | COMPLETE | Deterministic clause router with precedence rules P1-P5, ambiguity default, topic inheritance, third-party refusal | `employee_query_router.py::route`, `classify_clause`; `tests/unit/test_intent_router.py` (91) | Accuracy never measured on a held-out question set (see P3-E) | P1 (measurement) |
| 17 | Hybrid orchestration | COMPLETE | Records-only, handbook-only and mixed flows; one saved message per chat; partial-failure handling | `orchestrator.py::answer_question`, `_records_part`, `_policy_part`; `tests/unit/test_orchestrator.py` (36), `tests/integration/test_hybrid_chat.py` (13); clone checks 23/23 + 5/5; owner manual verification | Shared LLM synthesis (step 2C) not built: answers are composed in two sections | P2 (requirement UNVERIFIED) |
| 18 | Chat history persistence | COMPLETE | Exactly one row per chat, per employee, history endpoint | `db.save_employee_message`, `routes/chat.py::history`; persistence-count tests in `test_hybrid_chat.py` | FK on `messages.employee_id` (see #2) | P1 (with #2) |
| 19 | Authentication and sessions | COMPLETE | Argon2id, server-side hashed session tokens, absolute and idle expiry, rate limiting, generic errors | `services/auth.py`, `security.py`, `routes/auth.py`; `tests/integration/test_auth.py` (62) | In-memory rate limiter; no MFA or password reset (out of MVP scope) | P2 |
| 20 | Authorization, CSRF and employee isolation | COMPLETE | Session-derived employee, 403 on mismatch, admin role, CSRF on all writes; DB-level RLS with signed scope | `security.py::assert_own_employee`, `csrf_protected`, `require_admin_write`; `tests/integration/test_isolation_security.py` (34), `test_postgres_roles.py` | - | - |
| 21 | Secrets and configuration | PARTIAL | `.env` git-ignored; owner-only secrets file outside the repo; no secrets in images; leak checks | `docker-compose.yml`, `.env.example`, `tests/unit/test_docker_config.py`; secrets file per runbook section 9 | Weak 11-character owner DB password (rotation deferred); public `/api/docs` and `/api/openapi.json` (verified 200); no HTTP security headers in `frontend/nginx.conf` | P1 (password rotation), P2 (rest) |
| 22 | API, validation and error handling | COMPLETE | Pydantic models, readable 422s, safe 500 JSON with request ID, 503 for LLM and DB timeouts | `schemas/models.py`, `middleware/__init__.py`; `tests/integration/test_error_handling.py` (16), `test_middleware.py` (3) | - | - |
| 23 | Logging, audit trail and monitoring | PARTIAL | Request-ID logs with timings, rotating file log, route kind logged without question text | `logging_config.py`, `middleware/__init__.py::RequestLoggingMiddleware`, `orchestrator.py` (`chat route` line) | No metrics endpoint or dashboard, no audit log for security events beyond login logs, no alerting | P2 (Azure monitoring is ON HOLD) |
| 24 | Health checks | COMPLETE | `/health` checks the DB; Docker health checks with dependency ordering | `main.py::health`, `Dockerfile` `HEALTHCHECK`, `docker-compose.yml`; `tests/unit/test_health.py` (10) | Does not report index or LLM readiness (by design: public endpoint) | P2 |
| 25 | DB connection management | PARTIAL | Connection timeouts and statement timeouts | `postgres.py::postgres_connection`, `postgres_readonly_connection` | A new connection per query (no pool); scoped reads add signing round trips; adequate at capstone scale | P2 |
| 26 | React frontend | PARTIAL | Login, dashboard, chat with sources, checklist toggle, leave/payroll, assets, support tickets | `frontend/src/App.jsx` (313 lines, single file), `LoginPage.jsx`, `api.js`; `pages/`, `components/`, `services/`, `layouts/` are empty | No feedback (thumbs) UI and no escalate action in chat, although the API exists (`/feedback`, `/escalate`) and the fallback text tells users to "use the escalate option"; escalation is possible only through the Support Center ticket form | P1 |
| 27 | Feedback and escalation backend | PARTIAL | `POST /feedback` (owner check), `POST /escalate` (simulated) | `routes/feedback.py` | Escalations are not linked to an employee; `/escalate` overlaps tickets | P1 (with #26) |
| 28 | Docker packaging | COMPLETE | Non-root image, baked embedding model, health checks, localhost-only ports, opt-in least-privilege roles | `Dockerfile`, `docker-compose.yml`, `frontend/Dockerfile`, `frontend/nginx.conf`; `tests/unit/test_docker_config.py` (7) | Re-index path in Docker (see #10) | P1 (with #10) |
| 29 | CI/CD | MISSING | - | `.github/workflows/` contains only `.gitkeep` | Pipeline for pytest, frontend test/lint/build and image build (deployment ON HOLD) | P1 |
| 30 | Dependency management | PARTIAL | 3 of 16 requirements pinned | `requirements.txt` (fastapi, openai, faiss-cpu, fastembed etc. unpinned; pytest, httpx, locust in the runtime image) | Pin versions; split runtime and test requirements | P1 |
| 31 | Automated tests | PARTIAL | 445 backend + 77 live-PostgreSQL + 8 frontend tests | test files listed above | Thin ingestion/retrieval tests (4); no load tests (`tests/load/` empty); no browser E2E in the repository | P1 |
| 32 | Evaluation metrics | PARTIAL | RAG evaluation harness | `scripts/rag_eval.py`, `docs/rag_eval_report.md` (20 Nov 2026) | Not re-run after Phases 1-2; no routing, mixed-answer, latency or fallback-rate metrics (see P3-E) | P1 |
| 33 | Azure deployment | MISSING | - | - | **ON HOLD** (documented blocker) | ON HOLD |

### P3-B. Gap analysis

**P0 - Critical: none found.** No security vulnerability, data-isolation failure or data-corruption path was found in the current code. Employee isolation is enforced twice (session authorization and database RLS with a signed scope) and covered by automated and manual tests.

**P1 - Important**

| ID | Finding | Impact | Smallest safe correction |
|---|---|---|---|
| G1 | No CSV -> PostgreSQL import (#1) | Documented architecture input missing; data changes need hand-written SQL | Admin CLI importer `scripts/import_csv.py`: per-file schema validation, all-or-nothing transaction, upsert on natural keys (idempotent), dry run by default, row-level error report. It must **not** run as `onboardai_app`, which is (correctly) SELECT-only on the reference tables since Phase 1 (`db_roles.APP_PRIVILEGES`); use a dedicated import role or the owner account through the migration-005 admin pattern (owner decision) |
| G2 | No schema dictionary (#3) | SQL path not self-describing; prerequisite for any future text-to-SQL; docs drift | `backend/services/schema_dictionary.py` (curated descriptions) + test comparing it with `01_schema.sql`/SQLite DDL and `db_roles.READER_TABLES` |
| G3 | PDF not indexed, no page citations (#6, #8, #13) | The project brief describes PDF RAG, but retrieval actually runs on `handbook.md`; answers are equivalent today because both files hold the same content, but the PDF path is untested | Page-aware PDF chunking (page + heading detection), PDF preferred or both with de-duplication by content hash, `page` in sources, re-run rag_eval |
| G4 | Fragile index lifecycle (#10, #28) | A failed rebuild can leave the index and metadata out of sync; `/ingest` cannot work in Docker; the first request may try to build an index | Write to temporary files then atomic rename; check `ntotal == len(chunks)` on load; never build on the request path; document a host-side rebuild command (or a writable index volume) |
| G5 | Feedback and escalation not usable from the UI (#26, #27) | MVP item 4 ("escalate-to-HR/IT option") only reachable through the ticket form; the fallback text points to a non-existent button | Thumbs up/down and "Escalate" actions on each answer using the existing endpoints; escalation creates a ticket for the session employee (or `/escalate` stores `employee_id`) |
| G6 | Missing FKs and escalation attribution (#2, #18, #27) | Orphaned feedback/messages possible; escalations cannot be traced | Migration 006: FKs `messages.employee_id -> employees`, `feedback.message_id -> messages`, nullable `escalations.employee_id`; pre-check for orphan rows; update `db_roles` grant map |
| G7 | No CI (#29) | Problem statement success criterion "CI passing" unmet; regressions rely on manual runs | GitHub Actions: backend pytest (SQLite), live-PostgreSQL suite against a service container, `npm test/lint/build`, `docker build` (no push, no deployment) |
| G8 | Unpinned dependencies (#30) | Non-reproducible builds; test tools shipped in the runtime image | Pin from the current working environment; `requirements-dev.txt` for pytest/httpx/locust |
| G9 | Evaluation not current (#16, #32) | Success criteria (80% in-scope accuracy, 100% out-of-scope fallback, < 5 s) not re-measured after Phases 1-2; routing accuracy never measured | Extend `scripts/rag_eval.py` with a held-out labelled routing set, mixed questions, latency and fallback/error rates; record results |
| G10 | Weak owner DB password (#21) | Owner account protected by an 11-character password (local only, not published) | Rotate per runbook section 9 (owner action, no code change) |

**P2 - Optional**

| ID | Finding | Smallest safe correction |
|---|---|---|
| O1 | Public API docs and schema; no security headers | Disable docs when `APP_ENV=production`; add CSP / X-Frame-Options / X-Content-Type-Options / Referrer-Policy in nginx |
| O2 | Shared LLM synthesis for mixed answers (step 2C) | Only if required; typed evidence, records as untrusted data, numbers validated against rows |
| O3 | Constrained text-to-SQL | Only if confirmed mandatory; reuse `assert_select_only`, reader role, RLS and the schema dictionary |
| O4 | Dates stored as text | Migration to `date`/`timestamptz` when date filtering is needed |
| O5 | Connection pooling; persistent rate limiting; MFA/password reset | Production hardening (Azure phase) |
| O6 | OCR, document-level ACLs, conflict detection | Only when scanned or restricted documents exist |
| O7 | Third-party detection is pattern-based | Extend patterns from real questions; no data exposure possible (RLS) |
| O8 | Single-file `App.jsx`; legacy SQLite path, `/checklist` route, `checklist.done`, unused helpers | Refactor/remove after the core milestones |
| O9 | Monitoring/metrics/alerting | Azure Monitor / Application Insights when Azure resumes (ON HOLD) |

### P3-C. Requirements traceability

| Requirement | Source | Category | Status |
|---|---|---|---|
| RAG chatbot over approved handbook with source references | `docs/problem_statement.md` MVP 1-4 | 2. Project-documented (mandatory status UNVERIFIED) | COMPLETE (Markdown source) |
| Safe fallback and escalate-to-HR/IT option | problem statement MVP 4 | 2 | PARTIAL - fallback complete; escalation only via ticket form (G5) |
| Onboarding checklist Day 1 / Week 1 / Month 1 | problem statement MVP 5 | 2 | COMPLETE (per employee, persisted) |
| >= 80% in-scope correct with source; 100% out-of-scope fallback | problem statement success criteria | 2 | Measured 20 Nov 2026 before Phases 1-2 (see P3-E); re-measurement needed (G9) |
| Typical response < 5 s | problem statement | 2 | Indicative only (8 chats, see P3-E); not formally measured |
| Containerised; deployed or documented blocker + local run; CI passing; test results recorded | problem statement | 2 | Containerised COMPLETE; deployment = documented blocker (Azure ON HOLD); **CI MISSING** (G7) |
| Docker, Azure deployment, CI/CD, unit/integration/load/security tests; runbook, diagrams, slides, demo | section 1 milestones M4-M5 | 1. Likely programme requirements - **UNVERIFIED** (no EY document in repo) | Docker/tests/runbook/diagrams/demo done; load tests, CI/CD, slides missing; Azure ON HOLD |
| CSV -> PostgreSQL; schema dictionary; text-to-SQL **or** approved tools; PDF -> FAISS; shared generator; mixed queries; Azure OpenAI | Hybrid architecture (Phase 1 audit A1) | 2. Project architecture | Approved tools, mixed queries COMPLETE; CSV, schema dictionary MISSING; PDF PARTIAL; shared generator not built (O2); Azure ON HOLD |
| Authentication, least-privilege DB, signed scope, RLS | Phase 1 decisions | 3. Engineering improvements (beyond MVP: login was out of scope in the problem statement) | COMPLETE |
| Pinned deps, atomic index, FKs, security headers, eval metrics | This audit | 3 | Proposed |
| LLM synthesis, text-to-SQL, OCR, ACLs, pooling, MFA, UI refactor | This audit | 4. Optional | Deferred |

Note: the problem statement lists "admin upload page" and "Login/SSO" as out of scope, so CSV/PDF ingestion can remain CLI/admin-API driven without an upload UI.

### P3-D. Security and reliability risks

| Risk | Type | Severity | Status |
|---|---|---|---|
| Cross-employee data access | Security | - | Mitigated (session authz + RLS + signed scope; 77 + 43 attack checks) |
| SQL injection / unsafe SQL | Security | - | Mitigated (bound parameters, allow-list, pglast validator, read-only reader role) |
| Prompt injection / leakage | Security | Low | Mitigated (untrusted-context wrapping, NOT_FOUND rule, leak check incl. Phase 1 secrets); lexical grounding limits remain |
| Weak owner DB password | Security | Medium (local) | Open (G10) |
| Public API docs, missing security headers | Hardening | Low | Open (O1) |
| Index/metadata desync on failed rebuild; Docker re-index impossible | Reliability | Medium | Open (G4) |
| Unpinned dependencies, no CI | Reliability | Medium | Open (G7, G8) |
| Orphan rows (no FKs) | Data integrity | Low | Open (G6) |
| LLM outage | Reliability | - | Handled (503 for handbook-only; records preserved for mixed) |
| In-memory rate limiter, connection-per-query | Scalability | Low (single instance) | Accepted for local release (O5) |

### P3-E. Metrics: measured vs proposed

**Measured (do not extrapolate):**
- RAG evaluation 20 Nov 2026 (`docs/rag_eval_report.md`, Groq `qwen/qwen3.8-27b`, same 48-chunk index): index checks 6/6, retrieval relevance 17/17 (MRR 0.971 for the expected section), answer grounding 17/17, unknown-question fallback 7/7, prompt injection 3/3. Taken **before** Phases 1-2; not re-run since.
- Day 32 question set (`docs/test_report.md`): 15/15 auto-checked.
- Routing: 91 router unit tests pass. These are design-time regression cases written with the router, **not** an unbiased accuracy measurement.
- `/chat` latency from the running backend's request log (23 Nov 2026, manual testing, mixed backend versions, all kinds pooled): n = 8 successful chats, min 84 ms, median 164 ms, p90 1,888 ms, max 2,704 ms. Indicative only (tiny sample, not split by route kind).

**Proposed (not yet measured):** intent/routing accuracy and macro-F1 on a held-out labelled set (records / handbook / mixed, plus third-party refusals); SQL routing accuracy per intent; retrieval hit@k and MRR re-run on the current stack; answer groundedness and citation correctness for handbook and mixed answers; end-to-end latency p50/p95 per route kind; fallback rate on in-scope questions (target low) and out-of-scope questions (target 100%); error rate (5xx) under a small load test.

### P3-F. Accelerated implementation roadmap

Three milestones complete the core architecture; everything else is deferred. Recommended order: M3 first, because CI, pinned dependencies and the evaluation harness protect and measure M4 and M5.

**M3 - Engineering and evaluation baseline** (Complexity: **Low-Medium**)
- Objective: reproducible builds, automated regression on every push, measured baseline metrics.
- Reuse: existing pytest suites, `scripts/rag_eval.py`, `tests/integration/test_postgres_roles.py` (disposable-server pattern), `tests/load/` (empty) with `locust` (already a dependency).
- Implement: pin `requirements.txt` from the working environment and add `requirements-dev.txt`; GitHub Actions workflow (backend pytest, live-PostgreSQL suite with a `postgres:16` service container, frontend `npm ci`/test/lint/build, `docker build` without push); extend `rag_eval` with a held-out labelled routing set (about 60 questions, written separately from the router tests), mixed-answer checks, latency p50/p95 per route kind and fallback/error rates; a small locust scenario (local only).
- Affected files: `requirements.txt`, new `requirements-dev.txt`, `Dockerfile` (runtime requirements only), new `.github/workflows/ci.yml`, `scripts/rag_eval.py`, new `tests/eval/routing_set.json` (or similar), `tests/load/locustfile.py`, `docs/rag_eval_report.md`.
- Security: CI uses no real secrets (LLM mocked; live LLM evaluation runs locally only); throw-away PostgreSQL passwords generated per job.
- Acceptance: CI green on `dev`; image builds with pinned versions; evaluation report records the measured metrics above with dates and model.
- Tests: CI runs all existing suites; evaluation script unit tests (`tests/unit/test_rag_eval.py` extended).
- Manual: one local `python -m scripts.rag_eval` with Groq; review the report.
- Migrations: none. Docker rebuild: yes (pinned dependencies; verify on a clone first). Blocking: GitHub Actions availability on the repository.

**M4 - Data and document ingestion completion** (Complexity: **Medium-High**)
- Objective: CSV -> PostgreSQL import, schema dictionary, page-aware PDF ingestion and a robust index lifecycle.
- Reuse: the migration-005 admin-connection pattern (`PG_ADMIN_*`), `employee_db` table shapes, `db_roles.READER_TABLES`, `ingest.py` chunkers, `embeddings.py`, `rag_eval`.
- Implement: `scripts/import_csv.py` (employees, leave balances, assets, checklist assignments, payroll calendar; header/type/FK validation, dry run by default, single transaction, upsert on natural keys, row-level error report, no deletes unless explicitly requested); synthetic `data/csv/*.csv` matching the current seed; `backend/services/schema_dictionary.py` with a consistency test; PDF chunking by page and heading with `page` metadata, content-hash de-duplication between `handbook.pdf` and `handbook.md` (one canonical source, chosen explicitly), atomic index write, count check on load, no index build on the request path, documented host-side rebuild (`python -m backend.services.ingest`) plus backend restart; `page` shown in sources (`format.js`).
- Affected files: new `scripts/import_csv.py`, `data/csv/`, new `backend/services/schema_dictionary.py`, `backend/services/ingest.py`, `retriever.py`, `guardrails.py::map_citation` (page-aware citations), `rag.py` (source fields), `frontend/src/format.js`, `docs/runbook.md`, tests.
- Security: the running application's roles are **not** widened (`onboardai_app` stays SELECT-only on reference tables). Recommended: a dedicated `onboardai_importer` role (INSERT/UPDATE on `employees`, `leave_balances`, `assets`, `checklist_assignments`, `payroll_calendar` only; no DELETE, no auth tables, no BYPASSRLS; RLS policy for it), used only by the manual CLI, with credentials from the external secrets file. Alternative: run the CLI with the owner account like migration 005. CSV values are bound parameters; no secrets in CSVs; PDF text stays wrapped as untrusted context.
- Acceptance: importing the same CSVs twice yields identical tables (idempotent); invalid rows are reported and nothing is committed; schema dictionary test passes; index contains PDF chunks with page numbers; rag_eval retrieval and grounding at least as good as the M3 baseline; citations show the page.
- Tests: importer unit tests (valid, duplicate, bad header, bad type, unknown employee FK, partial failure rollback); live-PostgreSQL importer tests (import role succeeds; app and reader roles are still denied writes); ingestion tests on the real PDF (page metadata, de-duplication, atomic write, count mismatch detection); `ChatResponse` contract test with the new optional source field.
- Manual: dry-run import on a clone; rebuild the index on the host; ask 5 policy questions and check page citations.
- Migrations: **yes if the dedicated import role is chosen** (role + grants + RLS policy, through the `db_roles` plan/verify pattern; no table changes); none if the owner-run option is chosen. Docker rebuild: yes (backend + frontend); index rebuild on the host. Blocking: owner decisions on (a) import role vs owner-run CLI, (b) the canonical handbook source (PDF vs Markdown), (c) an optional `page` field on `ChatResponse.sources` items (additive, backward-compatible).

**M5 - User workflow completion and data integrity** (Complexity: **Medium**)
- Objective: feedback and escalation usable from chat; referential integrity; low-risk hardening.
- Reuse: `/feedback` and ticket endpoints, `security.py` dependencies, migration 005 pattern (dry run / verify / apply, clone validation).
- Implement: thumbs up/down and "Escalate to HR/IT" on each answer (escalation creates a ticket for the session employee with the question as description, or `/escalate` gains `employee_id`); fallback text aligned with the UI; migration 006 (FKs on `messages.employee_id` and `feedback.message_id`, `escalations.employee_id`, orphan pre-check, grant map update); disable `/docs` and `/openapi.json` outside development; nginx security headers.
- Affected files: `frontend/src/App.jsx`, `frontend/src/api.js`, `backend/routes/feedback.py`, `backend/services/db.py`, `docker/postgres/01_schema.sql`, new `backend/migrations/006_integrity_constraints.py`, `backend/services/db_roles.py`, `backend/main.py`, `frontend/nginx.conf`, `rag.py::FALLBACK`, docs.
- Security: escalation and feedback stay CSRF-protected and owner-checked; FKs must not break RLS policies; migration validated on a clone with a backup first.
- Acceptance: a user can rate and escalate any answer; escalations are attributable; no orphan rows possible; docs endpoints return 404 in the Docker profile; security headers present; all suites green in CI.
- Tests: route tests for feedback/escalation ownership and CSRF; migration dry-run/apply/verify tests (SQLite + live PostgreSQL); header and docs-disabled tests; frontend unit tests for the new actions.
- Manual: browser check of rate/escalate flows for EMP001 and EMP002; verify that EMP002 cannot see EMP001's escalation ticket.
- Migrations: **yes (006)**, with backup and clone validation. Docker rebuild: yes (backend + frontend). Blocking: none.

**Deferred / ON HOLD (separate approval):** Azure OpenAI provider and Azure deployment (ON HOLD); owner DB password rotation (owner action, can happen any time); LLM synthesis of mixed answers (2C); constrained text-to-SQL (only if the requirement is confirmed); OCR; document ACLs; date-type migration; connection pooling; persistent rate limiting; MFA/password reset; frontend refactor; SQLite/legacy removal; monitoring.

### P3-G. Components that should remain unchanged

Authentication, sessions, CSRF and authorization (`auth.py`, `security.py`); Phase 1 database security (`db_roles.py`, migration 005, `employee_scope.py`, `readonly_query.py`, RLS policies); the deterministic router and orchestrator contracts (`employee_query_router.route`, `orchestrator.answer_question`); RAG guardrails and evidence gate (`guardrails.py`); the `ChatResponse` contract (additive optional fields only); Docker topology and the least-privilege compose variables; the external secrets file process.

### P3-H. Development workflow for approved milestones

1. Audit the existing implementation before coding. 2. Reuse verified components. 3. Implement related changes together. 4. Run targeted tests during development. 5. Run the full regression and security suites at milestone completion. 6. Validate risky changes (migrations, ingestion, image changes) on a temporary clone. 7. Focused manual verification before release. 8. Update documentation and this file. 9. One consolidated milestone report with the changed-file list and a recommended commit message; **all Git staging, commits and pushes are performed by the owner**.

### P3-I. Status of this audit

No application code, database records or schema, Docker containers or Git history were modified; no migration was run; no dependency was added. Only `docs/project_plan.md` was updated (this section, the status line and the next-step line). Implementation of M3-M5 awaits owner approval.


---

## M3 - Engineering Baseline and Automated Evaluation (23 November 2026)

**Status: IMPLEMENTED AND VERIFIED LOCALLY; CI NOT YET RUN ON GITHUB.** Approved by the owner on 23 November 2026. The GitHub Actions workflow has not run yet: it runs after the owner pushes. Its four jobs were executed with the same commands in equivalent clean local containers (results below). The running Docker stack and live PostgreSQL data were not modified (live messages/completed/tickets/accounts 8/7/0/1 before and after; the 5 messages added since the Phase 2 check were written at 14:36-14:40 IST during the owner's manual testing, before M3 started). Azure remains **ON HOLD**. Nothing committed.

### Delivered

| Scope item | Implementation |
|---|---|
| Pinned dependencies | `requirements.txt` = 14 runtime packages pinned to the set in the verified Docker image (Python 3.12); `requirements-dev.txt` = runtime + pytest, httpx, locust (pinned). `requests` removed as a direct dependency (unused; still installed via fastembed). Local venv aligned; `pip check` clean. The runtime image no longer contains pytest/locust (846 MB vs 916 MB) |
| CI | `.github/workflows/ci.yml`: `backend-tests` (Python 3.12, pinned install, index built from `data/raw`, full suite, fails on any skip, held-out routing eval), `postgres-security-tests` (disposable `postgres:16-alpine`, per-job random masked password, 77-test suite, fails on skips), `frontend` (Node 24, `npm ci`/test/lint/build), `docker-build` (compose config, backend + frontend image builds, pip check, import smoke test, no dev tools in image, non-root uid). `permissions: contents: read`; only official `actions/*`; no secrets, no push, no deployment |
| Held-out dataset | `tests/eval/heldout_questions.json`: 62 questions (16 records, 16 handbook, 10 mixed, 6 ambiguous, 8 unauthorized, 6 out-of-scope), written before measurement and not used to tune the router; handbook keys/sections verbatim from `data/raw`; records expectations computed from the database at run time |
| Evaluation | `scripts/hybrid_eval.py`: `--routing-only` (deterministic, CI), in-process mode (isolated seeded SQLite copy + real index + Groq), `--base-url` HTTP mode (ground truth from REST endpoints). Metrics: routing accuracy and confusion, third-party recall/false positives, records correctness, refusals, leak markers, retrieval hit@k/MRR on the text actually sent to retrieval, groundedness, false fallbacks, citation hit/precision, mixed correctness, out-of-scope fallback, errors, latency p50/p95 per route kind |
| Load test | `tests/load/locustfile.py` + `tests/load/run_isolated_load_test.sh` (throw-away image, synthetic-seed PostgreSQL, migration 005 with random secrets, least-privilege backend, synthetic login; everything removed on exit) |
| Tests | `tests/unit/test_hybrid_eval.py` (18): dataset integrity (verbatim KB keys, real sections, absent out-of-scope terms, no reuse of router/rag_eval questions), grading logic, percentile, routing regression floor (>= measured 0.967, no third-party false positives) |
| Docs | `docs/hybrid_eval_report.md` (generated), `docs/load_test_report.md`, README (install, testing, CI, limitations, documentation), this section; `.gitattributes` (`*.sh` keeps LF), `.gitignore` (`loadtest-output/`) |

### Measured results (23 November 2026; one run each; Groq `qwen/qwen3.8-27b`)

| Metric | Result |
|---|---|
| Routing accuracy, held-out (kind + intents + refusal flag) | **60/62 (96.8%)**; records 16/16, handbook 16/16, ambiguous 6/6, out-of-scope 6/6, mixed 9/10, unauthorized 7/8 |
| Third-party detection | recall 7/8; 0 false positives |
| Records answers correct (records + mixed) | 25/26 |
| Unauthorized questions refused | 7/8; **0** answers containing another employee's data marker |
| Retrieval hit@4 / MRR (query actually sent) | 27/30 / 0.861 |
| Grounded handbook answers / false fallbacks | 26/30 / 4/30 |
| Citation hit / precision | 26/30 / 1.00 |
| Mixed answers fully correct | 7/10 |
| Out-of-scope fallback | 6/6 |
| Errors after retries | 0 |
| End-to-end latency, HTTP, PostgreSQL + least-privilege roles (p50 / p95 ms) | records 152 / 238 (n=24); handbook 374 / 2,443 (n=29); mixed 478 / 804 (n=9); all 329 / 1,440 |
| Load test (10 users, 60 s, records chat + REST) | 281 requests (CSV), **0 failures**, aggregate median 81 ms / p95 200 ms, records chat median 170 ms / p95 210 ms, about 4.8 req/s; 0 5xx, 0 secrets in logs |

The in-process run reproduced every quality metric and the same five failing questions. Against the problem-statement criteria: in-scope handbook answers 26/30 (87%, target >= 80%), out-of-scope fallback 6/6 (target 100%), end-to-end p95 1.4 s overall and 2.4 s for handbook answers (target "typically < 5 s").

**Failing questions (reported, not fixed in M3):** M10 "How many sick days do I have left ..." - "sick days" is not leave vocabulary, records part dropped. U04 "Which laptop is assigned to Meera?" - third party not detected; shows the user's own laptop (no data leak). M01 / M06 - the policy clause sent to retrieval is a pronoun-only fragment ("apply for it", "carry them forward"), so the handbook part falls back although the router inherited the topic for classification. H14 "Is a cab provided if I stay late at work?" - retrieval miss (expected section not in the top 4).

### Verification

| Check | Result |
|---|---|
| Backend suite, local Python 3.14 with pinned versions | 463 passed (+77 PostgreSQL tests skipped locally, run below) |
| CI `backend-tests` equivalent (clean `python:3.12-slim`, snapshot of tracked + new files only, no `.env`, index built from `data/raw`) | 463 passed, **0 skipped**; routing 60/62 |
| CI `postgres-security-tests` equivalent (disposable `postgres:16-alpine`, random password) | 77 passed, 0 skipped |
| CI `frontend` equivalent (clean `node:24-alpine`) | npm ci ok; 8/8 tests; lint clean; build ok |
| CI `docker-build` equivalent | compose config ok; both images built; pip check clean; import ok; no pytest/locust in image; uid 10001 |
| Workflow file | Parsed (4 jobs, read-only permissions, triggers push/PR/dispatch). `actionlint` was not run: the attempt was blocked by the local permission policy |

### Remaining risks and limitations

- CI has not run on GitHub yet; runner differences (network to Hugging Face for the model download, action versions) can still fail the first run.
- Transitive dependencies are not locked; only direct dependencies are pinned.
- The evaluation is one run on a 62-question set with lexical grading; LLM answers can vary between runs; p95 values with n < 30 are indicative.
- The load test is smoke-level (one host, client and server on the same machine, no LLM questions, one account).
- The router and retrieval findings above remain open for a later approved milestone.

### Manual verification for the owner

1. `pip install -r requirements-dev.txt`, then `python -m pytest -q` (expect 463 passed, 77 skipped without a PostgreSQL DSN).
2. `python -m scripts.hybrid_eval --routing-only` (expect 60/62).
3. Optional: `WITH_EVAL=1 bash tests/load/run_isolated_load_test.sh loadtest-output` (about 4 minutes; uses Groq for the evaluation part; removes everything it creates).
4. After pushing: open the repository's Actions tab and confirm all four jobs pass; only then record CI as green.


---

## M4 - Data Architecture Completion and Hybrid Answer Quality (23 November 2026)

**Status: IMPLEMENTED AND VERIFIED IN ISOLATED ENVIRONMENTS; NOT ACTIVATED ON THE RUNNING STACK; NOT COMMITTED.** Built on commit `7e2e866`. The running Docker stack, live PostgreSQL data (messages/completed/tickets/accounts 8/7/0/1 before and after) and the production index `data/index` (legacy flat files, unchanged) were not modified. Activation needs owner approval (steps below). Azure remains **ON HOLD**; Groq remains the temporary LLM.

### Part A - CSV ingestion, import role, schema dictionary

| Component | Implementation |
|---|---|
| Import role | Migration 006 (`backend/migrations/006_import_role.py`; plan/verify in `db_roles.build_import_plan` / `verify_import_role`): `onboardai_importer`, LOGIN, no superuser/createrole/createdb/bypassrls/replication, connection limit 2, statement timeout 60 s. SELECT + INSERT + column-level UPDATE on employees, leave_balances, assets, payroll_calendar, checklist; SELECT + INSERT only on checklist_assignments; own RLS policy; no access to auth, chat, feedback, escalation, ticket tables or the signing-key schemas. Resets only its own grants; the app and reader roles are unchanged (verified) |
| CSV import | `backend/services/csv_import.py` + `scripts/import_csv.py`: six files in FK order; exact headers, typed/allowed-value validation, duplicate keys and emails within a file, FKs against file set + database, email ownership; every file validated before any write; dry run by default; one transaction (any validation or database error -> nothing written); idempotent upserts on natural keys (insert / update changed columns / unchanged); never deletes ("not in file" counted only); assignments insert-only (progress preserved); identifiers validated against the schema dictionary and quoted, all values bound. CLI connects only as the import role (refuses superuser, BYPASSRLS, app and reader roles) |
| Synthetic data | `data/csv/*.csv` generated from `docker/postgres/02_seed.sql`; importing them into a seeded database reports every row unchanged (SQLite and PostgreSQL) |
| Schema dictionary | `backend/services/schema_dictionary.json` (12 tables: description, columns with PostgreSQL type/nullability/description, PK, unique, FKs with ON DELETE, personal-data/sensitive/RLS/reader/import flags; 7 relationships) + `schema_dictionary.py` (`load`, `relationships`, `introspect`, `diff`) + `scripts/schema_dictionary.py --check`. Validated against a disposable PostgreSQL catalog in the CI PostgreSQL job; consistency with `db_roles` and the import specs unit-tested. Security schemas deliberately not described |

### Part B - Actual PDF RAG

| Component | Implementation |
|---|---|
| Canonical source | `handbook.pdf`; same-stem `handbook.md` skipped as a derived copy; `faqs.md` indexed; byte-identical documents indexed once (manifest lists documents and skip reasons) |
| Extraction and chunks | pypdf text per page; numbered headings accepted only in sequence (1., 2., 2.1 ...); one chunk per section and page with `page` metadata (section 6 heading on page 2, text on page 3 -> page 3); same section labels as before, so citations and the evaluation set are unchanged |
| Retrieval quality | Small-to-big: overlapping 2-sentence windows are embedded; the retriever returns each parent section once with the full section text as context |
| Index lifecycle | `versions/<id>/` (index, chunks, manifest) + atomic `ACTIVE` pointer; validation before activation (counts, dimension, manifest, self-search); failed builds remove their temp dir and keep the previous version; newest 3 versions kept; legacy flat files still load; the request path never builds or writes; the retriever hot-reloads a new ACTIVE version and keeps the last good version if a new one is broken; `POST /ingest` returns 409 on a read-only mount |
| Citations / API | `Source.page` optional; `/chat` uses `response_model_exclude_none`, so records sources and older answers are unchanged (no `page: null`); history keeps pages; frontend shows "(p. N)" |
| Docker | Verified: isolated backend container with the PDF index mounted `:ro` answered with page citations; an in-container rebuild was refused (OSError) and the active version stayed unchanged |

### Part C - M3 evaluation failures (general fixes; held-out set unchanged, `git diff` empty)

| Failure | Fix |
|---|---|
| M10 "sick days" | Leave vocabulary: `(casual/sick/earned/annual/paid/personal/privilege) day(s)` |
| U04 "assigned to Meera" | Third-party patterns: "assigned/issued/allocated/given/belongs to <someone>" and capitalised names after for/of/to/does/did/has/is/about/with (domain-word allow-list) |
| M01, M06 pronoun follow-ups | A follow-up clause with only a pronoun reference is sent to retrieval with the previous clause's topic words ("can i carry them forward (earned leaves)") |
| H14 cab question | Small-to-big retrieval windows (no question-specific rules); retrieval comparison over 49 answerable cases: expected section in top 4 and gate passed 44 -> 47, out-of-scope/unknown gate behaviour unchanged (9/13 reach the LLM, which answers NOT_FOUND, as before) |

### Evaluation - before (M3) / after (M4), same 62 held-out questions, HTTP end-to-end on PostgreSQL with least-privilege roles

| Metric | M3 | M4 |
|---|---|---|
| Routing accuracy | 60/62 | **62/62** |
| Records correct / unauthorized refused / leak markers | 25/26 / 7/8 / 0 | **26/26 / 8/8 / 0** |
| Retrieval hit@4 / MRR | 27/30 / 0.861 | **30/30 / 0.978** |
| Grounded / false fallbacks / citation hit / precision | 26/30 / 4 / 26/30 / 1.00 | **30/30 / 0 / 30/30 / 1.00** (all handbook citations from handbook.pdf with a page) |
| Mixed fully correct / out-of-scope fallback | 7/10 / 6/6 | **10/10** / 6/6 |
| Latency p50/p95 ms (records, handbook, mixed) | 152/238, 374/2,443, 478/804 | 160/188, 425/3,496, 443/2,452 |

Answer-quality regressions: none (fixed H14, M01, M06, M10, U04). Latency: handbook/mixed p95 higher (n = 28/10; p95 is essentially the slowest single Groq call; p50 +51 / -35 ms) - observed, attributed to LLM response-time variance, not investigated further. In-process run: identical quality metrics. Load test (10 users, 60 s): 287 requests, 0 failures, median 83 ms / p95 200 ms (M3: 281, 0, 81 / 200).

### Verification

| Suite | Result |
|---|---|
| Backend, CI-equivalent clean Python 3.12 container (index built from the PDF) | **516 passed, 0 skipped** |
| Backend, local Python 3.14 (scratch PDF index) | 516 passed (+105 PostgreSQL tests skipped locally, run below) |
| PostgreSQL suites on a disposable server (77 role + 28 M4: import role grants and denials, app/reader gained no writes, dry run, apply, repeat, rollback on invalid data and on a database error, isolation after import, CLI refusals, schema dictionary vs catalog) | **105 passed, 0 skipped** |
| Frontend test / lint / build | 9/9 / clean / built |
| Held-out evaluation (HTTP + in-process) | see table above |
| Isolated stack: read-only index, page citations, load test, secrets in logs | rebuild refused, unchanged; pages present; 0 failures; 0 secrets |

New tests: `test_csv_import.py` (29), `test_schema_dictionary.py` (4), `test_pdf_index.py` (19), `test_postgres_m4.py` (28), plus page-citation tests in `test_hybrid_chat.py` and `format.test.js`. Changed tests: five chat tests use the new `indexed_env` fixture (the request path no longer builds an index); `test_rag_eval.py` checks the active index version.

### Activation (owner approval required; nothing below has been run on the live stack)

**Update 23 November 2026:** steps 1-3 completed as part of the M4 + M5 local activation (versioned index, 65 chunks); step 4 (migration 006) not reported as run; step 5 (page-citation check) still pending - see "M4 + M5 Local Activation".

1. Backup (runbook section 9 pattern).
2. Rebuild the index on the host: `python -m backend.services.ingest` (adds `data/index/versions/` + `ACTIVE`; the legacy flat files stay for rollback; the running pre-M4 backend ignores them).
3. Rebuild and recreate only the backend: `docker compose --env-file <secrets file> up -d --build --no-deps backend`.
4. Optional, for CSV import: add `ONBOARDAI_IMPORT_DB_PASSWORD` to the secrets file, run migration 006 (dry run, `--apply`, `--verify`; runbook section 10), then `scripts.import_csv` dry run before any `--apply`.
5. Manual check: sign in, ask "Is a cab provided if I stay late at work?" (expect a `handbook.pdf` citation with "(p. 3)") and one mixed question.
Rollback: delete `data/index/ACTIVE` (legacy index) and/or rebuild the backend from the previous commit; migration 006 rollback in runbook section 10.

### Remaining gaps

- Routing is rule-based: new phrasings and names written in lower case (for example "for meera") are not recognised as third parties (data still cannot leak: RLS scopes every read to the session employee).
- Grounding checks remain lexical; the evaluation is one run on 62 questions.
- Local development needs `python -m backend.services.ingest` once (the index format changed); until then `test_rag_eval.py::test_active_index_exists_and_matches_raw_documents` fails locally against the legacy index.
- Dates are still stored as text; no FKs on messages/feedback; escalation attribution and the feedback/escalation UI remain for M5.
- CSV import is a CLI (no upload UI, by MVP scope); scripts are not in the image (mounted or run on the host).


---

## M5 - User Workflow Completion and Data Integrity (23 November 2026)

**Status (update 23 November 2026): COMMITTED (`cde4538`, `dev`, CI 4/4 passed) and ACTIVATED locally - see "M4 + M5 Local Activation" below.** Original status at implementation: **IMPLEMENTED AND VERIFIED (unit, integration, disposable PostgreSQL, clone of the live database, isolated containers); NOT ACTIVATED; NOT COMMITTED.** Baseline: the approved M4 working tree on commit `7e2e866`. Live PostgreSQL (messages/feedback/escalations/completed/accounts 8/0/0/7/1 before and after), the running containers and the active index were not changed. Azure remains **ON HOLD**.

### Implemented

| Area | Change |
|---|---|
| Chat feedback and escalation | Every answer has Helpful / Not helpful (existing `POST /feedback`) and "Escalate to HR/IT" (existing `POST /escalate`, now with an optional `message_id`). Ownership checks as for feedback (403 other employee, 404 unknown); escalating the same answer twice returns the existing escalation; escalations record the session employee (`NULL` for admins). `GET /history` items gain optional `feedback` (latest rating) and `escalated` fields, so the UI shows state after reload. The fallback text now points to the button. Free-text escalations (`{question}` only) still work unchanged |
| Migration 007 | `backend/services/db_integrity.py` + `backend/migrations/007_data_integrity.py` (dry run default, `--verify`, `--apply` in one transaction, owner only, idempotent): `escalations.employee_id` / `message_id`; FKs messages.employee_id -> employees, feedback.message_id -> messages (CASCADE), escalations.employee_id -> employees, escalations.message_id -> messages (SET NULL); feedback.message_id NOT NULL; CHECKs on feedback.rating, messages.found, escalations.status; 3 indexes. Refuses (no changes) while invalid rows exist; never deletes or rewrites data. Fresh installs: `docker/postgres/04_integrity.sql` (tested to match). SQLite gets the columns at startup |
| Startup safety | The M5 backend refuses to start on PostgreSQL until migration 007 is applied (clear message) |
| Schema dictionary | Updated to the M5 schema (11 relationships; escalations personal data); validated against both a fresh install and a migrated pre-M5 database |
| API documentation | `/docs`, `/redoc`, `/openapi.json` only when `APP_ENV=development` or `API_DOCS=true`; `docker-compose.yml` sets `API_DOCS: "false"`; nginx returns 404 for `/api/docs|redoc|openapi.json` |
| nginx security headers | CSP (`default-src 'self'`, scripts self only, styles self + Google Fonts + inline, fonts gstatic, `frame-ancestors 'none'`, `object-src 'none'`, `base-uri`/`form-action` self), nosniff, X-Frame-Options DENY, Referrer-Policy no-referrer, Permissions-Policy, COOP same-origin, `server_tokens off`; on every response including `/api` |
| Unchanged | Authentication, sessions, CSRF, employee isolation, RLS and signed scope, approved query functions, router/orchestrator/RAG, PDF index, `ChatResponse` contract (additive fields only) |

### Verification

| Check | Result |
|---|---|
| Backend suite, CI-equivalent clean Python 3.12 container (PDF index built fresh) | **545 passed, 0 skipped** (516 M4 + 27 new M5 tests + 2 new frontend-contract route cases) |
| PostgreSQL suites on a disposable server (77 roles + 28 M4 + 20 M5) | **125 passed, 0 skipped** |
| Frontend test / lint / build | 11/11 / clean / built |
| Held-out routing | 62/62 (router unchanged) |
| Clone of the live database (pg_dump, signing key excluded): deployed (M4) image before 007 | 5/5 (login, chat, feedback, free-text escalation, cross-employee 403) |
| Clone: M5 image before 007 | refused to start with the migration-007 message |
| Clone: migration 007 | verify exit 1 -> dry run (no constraints created) -> apply 13 statements, verified -> verify exit 0 -> re-run "nothing to do"; existing rows 9/1/1 with identical checksum; schema dictionary matches; 005 roles/RLS verify clean |
| Clone: deployed (M4) image after 007 (backward compatibility) | 5/5 |
| Clone: M5 backend (`API_DOCS=false`) + M5 frontend (nginx) | 19/19 - feedback, escalate own answer, idempotent, cross-employee 403, CSRF 403, history state, PDF page citation, security headers on pages and `/api`, docs 404 via nginx and directly, SPA assets same-origin; 0 tracebacks, 0 secrets in logs |

New tests: `test_feedback_escalation.py` (10), `test_m5_hardening.py` (17), `test_postgres_m5.py` (20), 2 frontend tests. Changed tests: `test_frontend_contract.py` expects 15 frontend API calls (was 13: +feedback, +escalate); the PostgreSQL fixtures of `test_postgres_roles.py` and `test_postgres_m4.py` build the full fresh-install schema (01-04); `test_schema_dictionary.py` expects 11 relationships.

### Activation (owner approval required; order matters)

1. Backup (runbook section 9).
2. Migration 007 (runbook section 11): `--verify` (exit 1), dry run, `--apply`, `--verify` (exit 0). Safe with the running M4 backend.
3. If M4 is not active yet: rebuild the index on the host (`python -m backend.services.ingest`, M4 step).
4. Rebuild and recreate backend and frontend: `docker compose --env-file <secrets file> up -d --build --no-deps backend frontend`.
5. Manual check in the browser: rate an answer, escalate it (button changes to "Escalated to HR/IT", reload keeps the state), sign in as another employee and confirm the history is separate; `http://localhost:8080/api/docs` returns 404; DevTools shows no CSP violations (fonts load).

**Rollback:** recreate backend/frontend from the M4 images (they work with 007 applied). Constraint removal only if required (runbook section 11); full return via the backup.

### Remaining risks

- The CSP keeps `style-src 'unsafe-inline'` (React style attributes) and allows Google Fonts; a self-hosted font would allow removing the external origins.
- Escalations are stored, not delivered (no email/ticket integration); no reviewer UI for feedback or escalations.
- Browser-level CSP behaviour was checked through headers and same-origin assets, not with a headless browser in this run; the manual step 5 covers it.
- Dates are still stored as text; `messages`/`feedback` have no RLS (only the app role can read them; the reader cannot).

---

## M4 + M5 Local Activation (23 November 2026)

**Status: COMPLETED on the local Docker stack.** Azure deployment remains **PENDING / ON HOLD**. Results below are as reported by the owner after running the activation; this file records them, it did not run them.

### Completed

| Item | Result |
|---|---|
| Version control | M4 + M5 committed and pushed to `dev` (`cde4538`) |
| CI | All four GitHub CI checks passed (backend tests, PostgreSQL security tests, frontend, Docker build) |
| Migration 007 (data integrity) | Applied successfully, 13 statements |
| Post-migration verification | Zero problems; zero orphaned or invalid records |
| Search index | Versioned FAISS index generated successfully, 65 chunks |
| Containers | Updated backend and frontend images built and activated; backend, frontend and PostgreSQL containers healthy |
| Manual functional checks | PASS: login, employee status queries, checklist lookup, sick-leave balance lookup, feedback, escalation |

### Still pending

| Item | Status | Existing evidence |
|---|---|---|
| Handbook citation verification on the activated stack (e.g. "Is a cab provided if I stay late at work?" -> `handbook.pdf` with "(p. 3)") | **PENDING** | Automated and isolated only: held-out evaluation citation hit 30/30 with pages (M4); page citation present in the M5 isolated-container check (19/19). Not yet confirmed manually on the live local stack |
| Employee-level authorization testing on the activated stack (second employee: separate history, cross-employee access refused) | **PENDING** | Automated and isolated only: 125 PostgreSQL role/RLS/isolation tests, cross-employee 403 tests in the backend suite, cross-employee 403 on the clone of the live database. Not yet confirmed manually on the live local stack |
| Browser CSP check (no CSP violations in DevTools, fonts load) and `/api/docs` returning 404 | Not reported | Headers and 404s verified in isolated containers (M5) |
| Migration 006 (CSV import role) | Optional; not reported as run | Verified on disposable PostgreSQL and the clone (M4) |
| Azure deployment (A1 onward) | **PENDING / ON HOLD** | - |

Rollback procedures are unchanged: M5 section above and runbook section 11 (migration 007), M4 section and runbook section 10 (index pointer, migration 006).

---

## Pre-Azure Remediation - HIGH Audit Findings S1, S2, D3 (23 November 2026)

**Status: IMPLEMENTED AND VERIFIED; NOT COMMITTED.** Source: read-only pre-Azure readiness audit (23 November 2026; CONDITIONAL GO, no critical findings). Live PostgreSQL was only read (pg_dump, SELECT); its data and the running containers were not changed. Azure remains **ON HOLD**.

| Finding | Change | Evidence |
|---|---|---|
| S1 - database dumps could be committed (repository is public) | `.gitignore` and `.dockerignore`: `backups/`, `*.dump`. Existing dumps not moved, changed or opened | `git check-ignore` matches both existing dumps and a new one; `git status` shows no `backups/` entry |
| S2 - app could run as the PostgreSQL superuser | `db.enforce_role_policy` refuses a superuser **or BYPASSRLS** application role in every environment (startup reads `rolsuper, rolbypassrls`; unknown attributes also refused). `ALLOW_PRIVILEGED_DB_CONNECTION=true` is a local-development escape hatch honoured only with `APP_ENV=development`; `docker-compose.yml` pins it to `false`. Migrations, `manage_accounts`, CSV import unchanged (they never call the startup check) | 23 new unit tests (`tests/unit/test_privileged_db_connection.py`: all environments, both flags, override ignored outside development, no credentials in the message, startup path, compose pin); live PostgreSQL test (`test_postgres_m5.py`): superuser refused, development override accepted, override ignored in production. Rebuilt image on the restored copy: owner refused, override + `APP_ENV=production` refused, `onboardai_app` starts. Live backend already uses `onboardai_app` (not superuser, not BYPASSRLS) |
| D3 - no PostgreSQL backup/restore procedure | `docs/runbook.md` section 12: PowerShell 5.1-safe backup (`pg_dump -Fc -f` in the container + `docker compose cp`; no `>` redirection), archive check, isolated restore test on an internal Docker network, recovery rules (new project/volume only, same scope secret, never into the active database) | See below |

**Backup and restore results (actually executed):**

| Check | Result |
|---|---|
| Existing `backups/onboardai_pre_m5.dump` | **Not a valid archive** (UTF-16 byte-order mark: written through PowerShell `>`). Kept unchanged; documented as unusable |
| Existing `backups/onboardai_pre_m5_valid.dump` | Valid custom archive (13 tables incl. signing key); restored into a disposable server: exit 0; signing key and account password hashes identical to live; pre-M5 schema (8/0/0 rows, no 007 constraints) as expected |
| New backup with the documented PowerShell commands (`backups/onboardai_20261123_181908.dump`, 44,501 bytes) | Archive listing: 13 `TABLE DATA` entries incl. `onboardai_private.scope_key`, `user_accounts`, `user_sessions` |
| Restore of the new backup (disposable server, internal network) | `pg_restore --exit-on-error` exit 0; **13/13 tables identical to live** (row count + content checksum, values not printed); migration 005 `--verify` with the real scope secret exit 0 (`key_matches_secret: true`; app/reader cannot reach the key); migration 007 `--verify` exit 0; app role startup OK; RLS-scoped reads EMP001 15 rows = live, 0 cross-employee rows |
| Cleanup / live | Disposable containers, network and test image removed; live stack healthy, row counts unchanged |

**Tests:** backend suite **568 passed** (545 + 23 new); PostgreSQL suites on a disposable server **125 passed**; `docker compose config` valid.

**Behaviour change to note:** on a brand-new Docker database the backend no longer starts as the owner; provision the roles with migration 005 first (README / runbook section 9). The Phase 1 rollback "switch back to the owner account" is superseded (runbook section 9).

**Activation (owner):** rebuild the backend with the secrets file (`docker compose --env-file <secrets file> up -d --build --no-deps backend`); it must start as `onboardai_app`. Store backups outside the repository or keep them in the ignored `backups/` folder with owner-only access.

---

## Azure OpenAI Integration - GPT-4.1 replaces Groq (24 November 2026)

**Status: IMPLEMENTED, EVALUATED AND ACTIVATED on the local Docker stack (backend rebuilt with the external secrets file); NOT COMMITTED.** Baseline: commit `445ffce`. Azure OpenAI is the only LLM provider. Azure hosting, managed PostgreSQL, HTTPS and Key Vault remain pending; no new Azure resources were created. Live PostgreSQL records (14/0/1/7/1 messages/feedback/escalations/completed tasks/accounts before and after), both Docker volumes and the read-only FAISS index were preserved; a verified backup was taken before the rebuild (`backups/onboardai_20261124_094429.dump`, 13 tables).

### Implemented

| Area | Change |
|---|---|
| LLM client | `backend/services/llm.py`: OpenAI Python SDK (pinned 3.57.0, unchanged) against the resource's v1 endpoint, **Responses API** (`client.responses.create`): `model` = deployment `gpt-4.1`, system prompt as `instructions`, retrieved passages wrapped as untrusted context in `input`, `temperature=0`, `max_output_tokens=600`, **`store=False`**; no dated api-version. Endpoint normalised to `https://<resource>/openai/v1/` (https only; no credentials, query or deployment paths) |
| Failure handling | 30 s timeout, 2 SDK retries; missing/invalid configuration -> `LLMUnavailable` before any request (chat 503; mixed questions keep the records part); provider errors -> type + HTTP status only (no key, endpoint or body); Azure content filter on the prompt (HTTP 400 `content_filter`) and incomplete responses -> standard fallback |
| Indirect prompt-injection screen (E01) | `guardrails.screen_passages`: sentences in retrieved text that address the AI system (override the rules, reveal prompt/keys/credentials, "reply only with", role/instruction markers) are removed before the prompt is built; the remaining policy text of the passage is kept, a passage left without content is dropped (cannot be cited). Applied in `rag.answer_policy` (before the retrieval gate) and again in `llm.generate_answer`. Logged as counts only. Zero false positives on all 78 knowledge-base texts (raw Markdown, PDF pages, PDF chunks, index chunks and contexts); the index is never modified. Azure content filters stay enabled |
| Configuration | `AZURE_OPENAI_ENDPOINT` (alias `AZURE_OPENAI_BASE_URL`), `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_KEY`, `LLM_TIMEOUT_SECONDS`/`LLM_MAX_RETRIES`/`LLM_MAX_OUTPUT_TOKENS`; Groq settings removed; `docker-compose.yml` passes the Azure values from the external secrets file (`--env-file`) |
| Guardrails / evaluation | Leak check covers `azure_openai_api_key` and OpenAI-style key shapes; `rag_eval`, `hybrid_eval`, `run_test_questions` report the Azure deployment |
| Unchanged | FAISS retrieval and versioned index, canonical PDF and page citations, PostgreSQL and migrations, hybrid SQL + RAG orchestration (employee records never reach the LLM), authentication, RBAC, CSRF, RLS, checklist/status/leave, chat history, feedback, escalation |

### Verification (24 November 2026)

| Check | Result |
|---|---|
| Backend suite (local venv) | **624 passed** (568 + 24 `test_azure_llm.py` + 32 `test_injection_screen.py`); 7 existing tests moved from Groq to Azure fakes; 2 prompt-construction tests updated because the injected passage is now removed before the prompt (they still assert that retrieved text never enters the system instructions and that forged wrapper tags are neutralised, and now also that the injected instruction is absent) |
| PostgreSQL suites (disposable server) / frontend | **125 passed** / 11/11 tests, lint clean, build OK |
| RAG evaluation, Azure GPT-4.1 (`docs/rag_eval_report.md`) | **50/50**: index 6/6, retrieval 17/17 (MRR 0.971), grounding 17/17, unknown questions 7/7, prompt injection **3/3** (E01 was FAIL before the screen: Azure's content filter rejected the poisoned prompt, HTTP 400 `content_filter`; now the instruction is removed and the salary question is answered from [Handbook 3]) |
| Held-out evaluation, Azure GPT-4.1 (`docs/azure_eval_report.md`) | routing 62/62; records 26/26; unauthorized refused 8/8, 0 leak markers; retrieval hit 30/30 (MRR 0.978); grounded 30/30, 0 false fallbacks; citation hit 30/30, precision 1.00; mixed 10/10; out-of-scope fallback 6/6; 0 errors. Latency p50/p95/max ms: records 108/157/219, handbook 1,369/2,322/2,510, mixed 1,525/2,202/2,202 |
| Inside the rebuilt backend container (live stack) | 11/11: Azure settings present; app role `onboardai_app` (not superuser/BYPASSRLS); real GPT-4.1 request 3.0 s; cab question -> `handbook.pdf` p. 3; out-of-scope -> fallback; E01 passes; forced 0.001 s timeout -> `APITimeoutError` after 1.6 s including 2 retries; invalid key -> `AuthenticationError (HTTP 401)` 0.3 s; unknown deployment -> `NotFoundError (HTTP 404)` 0.4 s; missing key -> fail closed without a request; no key in any message |
| Functional, through nginx, on a temporary clone of the live database with the rebuilt images (live records untouched) | **27/27**: unauthenticated 401; generic invalid-login 401; HttpOnly/SameSite=Strict cookie; checklist read, CSRF-less update 403, update with CSRF; onboarding status and sick-leave balance match the records; EMP001 -> EMP002 data and history 403; third-party question refused; grounded policy answer with p. 3; out-of-scope fallback; mixed answer; feedback; escalation (idempotent); cross-employee feedback/escalation 403; history state; security headers; docs 404; backend with an invalid Azure key -> 503 generic message and mixed answers keep the records part |
| Logs | Live backend and clone backends: 0 tracebacks, 0 secrets, 0 endpoint mentions; failures logged as `Azure OpenAI request failed: AuthenticationError (HTTP 401)` |
| Containers (live) | backend, frontend, db healthy; `/` 200, `/api/health` 200, `/api/docs` 404, unauthenticated `/api/employees/EMP001` 401 |

### Rollback

Rebuild the backend from `445ffce` with the previous `.env` (Groq); no database or index change is involved. Backup: `backups/onboardai_20261124_094429.dump` (runbook section 12).

### Remaining limitations

- The injection screen is pattern-based: it removes known instruction shapes; a novel paraphrase could pass it, in which case the system prompt, Azure's content filter (which blocks such prompts and yields the fallback) and output validation (citations, numbers, e-mails, leak check) remain. The current knowledge base is synthetic and contains no such text.
- Authenticated functional checks ran on a clone with the rebuilt images, not with the owner's live account (no live records or accounts were created); a short manual browser check on the live stack remains advisable.
- API-key authentication from a local secrets file; Key Vault / managed identity (Entra ID) pending with Azure hosting. Synthetic handbook text and user questions are sent to Azure; `store=False` disables stored responses.
- Evaluation is a single run (62 + 50 questions); GitHub CI has not run on these changes yet (not pushed).

## Deployment Readiness and Audit Closure - CHECKPOINT (24 November 2026, paused for VM logout)

**Status: IN PROGRESS, NOT COMMITTED.** Baseline commit `78b80ee` (CI green). Mentor corrected to **Kanishka Vatsa**. The Azure team reports that the required resource types are now enabled; **no Azure resource has been provisioned and no Azure CLI command has been executed**. The live local Docker stack, its database volume, records and the active FAISS index were not changed (read only with `pg_dump` / `SELECT`); it still runs the `78b80ee` images.

### Implemented in this batch (working tree)

| Area | Change |
|---|---|
| PostgreSQL TLS | `PG_SSLMODE` / `PG_SSLROOTCERT` for the app, migrations and CSV import; `APP_ENV=production` refuses to start unless `verify-full` (certificate chain and host name) |
| Connection pool | `backend/services/postgres.py`: bounded pool per credential set (`PG_POOL_MAX_SIZE`=5), wait timeout -> 503, pre-ping of idle connections, maximum lifetime, discard after connection errors, reset on return (ROLLBACK + DISCARD ALL); the signed employee scope is transaction-local and never survives into the next lease |
| Startup integrity (audit D2) | Full migration-007 schema check, migration-008 check and TLS check at startup (once per configuration) |
| Readiness (audit R2) | `GET /ready`: database, migrations, FAISS index, embedding model, required configuration (ok/unavailable only); `/health` unchanged |
| HR/IT escalation queue (audit F6) | The problem statement names HR/IT as escalation receivers, so: new `hr` role, `GET/PATCH /hr/escalations` (HR only, CSRF, no-store), workflow open -> in_progress -> resolved -> closed with notes, audit trail of creation, every view and every change (`escalation_events`), privacy (only the escalated question/answer and employee name/ID), employee chat shows the HR status; React HR queue view. Delivery is in-app only (no e-mail or ticketing integration) |
| Migration 008 | `backend/migrations/008_hr_escalation_queue.py` + `docker/postgres/05_hr_queue.sql` (identical, test-enforced), additive only. **Order on an existing database: backup -> 008 --apply -> 008 --verify**, then rebuild the backend image (the new backend refuses to start without 008) |
| Shared login rate limit (audit S10) | `login_failures` table (SHA-256 keys, pruned), shared by all workers and instances; in-memory limiter bounded |
| Trusted proxies | `TRUSTED_PROXY_HOPS` (with port stripping); `BACKEND_PROXY_SECRET` header required by the backend except on `/health` and `/ready` |
| Prompt injection (audit S6) and failures | Wrapper tags neutralised in the question too; database outages -> 503 + Retry-After without details |
| CSP / fonts | Fonts bundled (`@fontsource` 5.3.0); CSP is `'self'` only (Google origins removed) |
| Non-superuser provisioning (Azure) | Migration 005 no longer needs superuser or `pg_read_all_stats`: inherited membership in the reader role for the verifier owner; ALTER ROLE only for attributes that differ |
| Azure images | `deploy/azure/backend.Dockerfile` (PDF, ACTIVE index version and embedding model baked in and verified at build; read-only; production defaults; OS upgrades); `deploy/azure/frontend.Dockerfile` (Alpine nginx package, envsubst entrypoint, HSTS, HTTPS upstream with SNI and certificate verification, proxy key); allow-list `.dockerignore` files |
| Azure automation | `deploy/azure/`: module, `00-Preflight` (incl. an ARM *validate* policy check), `10-Provision-Database`, `20-Provision-Registry`, `30-Publish-Images`, `40-Provision-AppService`, `50-Configure-Apps`, `60-Migrate-Database`, `config.example.psd1`; every script is a dry run unless `-Execute` |

### Verified results (24 November 2026, Docker Python, synthetic or cloned data)

| Check | Result |
|---|---|
| Backend suite (Docker, Python 3.12) | **696 passed** |
| Live PostgreSQL suites (disposable server) | **133 passed** with the pool off; pool on: 6 of 7 runs 133/133, 1 run had 1 statement-timeout failure (**open item**) |
| Frontend | 13/13 tests, lint clean, build OK |
| Migration rehearsal (`60-Migrate-Database.ps1 -Execute -SkipFirewall`) against an Azure-like PostgreSQL 16 (non-superuser administrator, TLS required) | Passed in 47 s: 12/12 data fingerprints identical (incl. Argon2 hashes and the scope key), 005/007/008 verified, scope key matches the secret. Two real defects found and fixed on the way (008 statement splitter; 005 superuser assumption) |
| TLS negative tests | IP instead of host name, untrusted CA, plaintext: all refused; production with `require` refused at startup |
| Production images end to end (App Service-like proxies, HTTPS) | **32/32**: authentication, Secure cookies, checklist/CSRF, status, leave, isolation, GPT-4.1 citations (p. 3), fallback, mixed, injection, feedback, escalation, HR queue workflow and audit, headers/HSTS/CSP, proxy key, rate limit through 3 hops with spoofed X-Forwarded-For ignored; a second client is unaffected |
| In-container Azure OpenAI | 11/11 (real GPT-4.1 2.5 s; timeout 1.8 s incl. retries; 401/404 sanitised; fail closed) |
| Restart recovery | Database restart under load: 5 of 76 requests got 503 during ~2.3 s, then automatic recovery; session kept; no tracebacks |
| Backup/restore drill (non-superuser, TLS) | Dump 56 KB in 5 s, restore 8 s with roles and policies, fingerprints identical |
| Performance (backend capped at 1 vCPU, approximating P0v3) | Idle 278 MiB backend / 11 MiB frontend. Records path, 10 users: 56 req/s, p50 176 ms, p95 270 ms, 0 errors, peak 342 MiB. Handbook (GPT-4.1), 5 users: p50 2.4 s, p95 4.0 s, 20/20 HTTP 200 (6 safe fallbacks: 4 questions not in the handbook, 2 inconsistent on a borderline question). Startup to ready: backend 7-11 s, frontend 3-4 s. **P0v3 (1 vCPU / 4 GB) fits both apps for demo load** |
| Images | Backend 847 MB, frontend 27.6 MB. Trivy: backend 0 fixable HIGH/CRITICAL (53 without a Debian fix), frontend 0 HIGH/CRITICAL |
| Dependency / source scans | pip-audit 0, npm audit 0; bandit 0 high, 5 medium = reviewed false positives (allow-listed identifiers, parameterised values) |
| Logs | No API key, endpoint, proxy secret or traceback |

### Open items / remaining tasks (resume here)

1. Investigate the intermittent pool-enabled PostgreSQL test failure (statement timeout, 1 of 7 runs).
2. Write `70-Verify-Deployment.ps1`, `90-Rollback.ps1`, `Test-DeploymentScripts.ps1` (parse all scripts, dry-run every step, check every `az` flag against `az ... --help`) and `deploy/azure/README.md` (deployment runbook).
3. Re-run the RAG (50) and held-out (62) evaluations on Azure GPT-4.1 against this code.
4. Documentation: README, architecture (plus Azure, RAG, hybrid routing, security and escalation diagrams), runbook (section 14: migration 008 activation; Azure), demo script and storyboard, superseded banners, audit closure matrix, requirement traceability (only `docs/problem_statement.md` and the milestone table are in the repository; the original assessment brief is not available), presentation content, submission checklist, packaging without secrets or dumps.
5. Optional: the same OS-package hardening for the local stack Dockerfiles.
6. Live local stack activation (needs owner approval): backup -> 008 --apply -> rebuild backend and frontend.
7. Azure provisioning and deployment (needs owner approval): run the scripts in order with `-Execute`.

### How to resume after logout

- All changes are saved in the working tree (uncommitted, nothing staged).
- Rehearsal tooling (no secrets) is copied to `onboardai_local_backups/rehearsal_tooling_20261124/` outside the repository; throwaway containers, the simulation network, test accounts and certificates were removed.
- Docker test runner: build `onboardai-test:local` from `rehearsal_tooling_20261124/test-runner.Dockerfile` (FROM the local backend image plus `requirements-dev.txt`), then run pytest with the repository mounted read-only at `/src` (PostgreSQL suites need `ONBOARDAI_PG_TEST_ADMIN_DSN` and a disposable server).
- Production images: `docker build -f deploy/azure/backend.Dockerfile -t onboardai-backend:azure-local .` (same for `frontend.Dockerfile`).

## Deployment-Critical Completion (24 November 2026, deadline 8 PM IST)

**Status: deployment-critical work COMPLETE and validated locally; NOT COMMITTED; nothing provisioned or deployed in Azure.** The owner reports existing resources: backend Web App `onboardai-eliksha-backend`, a Linux P0v3 plan, ACR `onboardaielikshaacr` (Basic, TenantReuse, admin disabled), Azure OpenAI GPT-4.1, region South India; PostgreSQL and the remaining infrastructure are being provisioned by the owner. **Blocker for discovery: the Azure CLI on the VM is not signed in (`az login` required).** The live local stack is unchanged (still `78b80ee` images).

### 1. Intermittent PostgreSQL timeout - root cause and fix

Root cause: a defect in the new test `test_session_settings_are_reset_between_leases` (tests/integration/test_postgres_m6.py) - it set `statement_timeout = 1` (1 ms) and then ran two more statements, which were cancelled whenever they took longer than 1 ms on a busy machine. It was the only 1 ms timeout in the code base; product code was not involved. Fix: a distinctive safe value (`'7s'`); the test still proves that the pooled session is reset to the configured 10 s. Re-run: **133/133 in all 4 runs** (pool on x3, pool off x1) on a disposable PostgreSQL 16.

### 2. Deployment scripts - completed and validated

| Script | Purpose / change |
|---|---|
| `05-Discover-Resources.ps1` (new) | Read-only discovery -> git-ignored `config.psd1`: resource group, region, **actual plan name and SKU** (from the backend app), **ACR login server** (TenantReuse/DNL registries have a hashed host name - image names now use it), PostgreSQL server, **FQDN** and admin login, frontend app presence, image tag (commit + timestamp) |
| `10`, `20`, `40` | Now **reuse** existing resources (create only if missing) and always apply the security configuration (TLS, admin user off, managed identity + AcrPull, HTTPS only, TLS 1.2, FTPS/basic auth off, health checks) |
| `50`, `60` | Use the discovered PostgreSQL FQDN and backend host name |
| `70-Verify-Deployment.ps1` (new) | 16 HTTPS checks + direct-backend refusal; Windows PowerShell 5.1 compatible |
| `90-Rollback.ps1` (new) | Previous image tag for both apps (tag existence checked), restart, verify; prints (never runs) the point-in-time-restore command |
| `Test-DeploymentScripts.ps1` (new) | Parser check of all scripts, dry run of every step, every `az` flag checked against the installed CLI help, redaction check |
| `README.md` (new) | Deployment runbook (order, commands, rollback) |

Validation: `Test-DeploymentScripts.ps1` - 12/12 scripts parse, 8/8 steps dry-run, **43/43 distinct az command lines valid against Azure CLI 2.91**, no secret in any output. It found **4 real defects, all fixed**: `firewall-rule create/delete` used the old `--name <server> --rule-name` syntax (2.91: `--server-name <server> --name <rule>`), and `flexible-server db create/show` used `--database-name` (2.91: `--name`). `70-Verify-Deployment.ps1` against the production images in the Azure-like simulation: **16/16** (handbook answer 1.7 s). `60-Migrate-Database.ps1` second rehearsal: passed, 12/12 fingerprints identical.

### 3. Evaluations (Azure GPT-4.1, this code)

| Evaluation | Result |
|---|---|
| RAG evaluation (`docs/rag_eval_report.md`, Docker) | **50/50**: index 6/6, retrieval 17/17, grounding 17/17, unknown 7/7, prompt injection 3/3 |
| Held-out (`docs/azure_eval_report.md`), end to end over HTTPS on the **production images** against the Azure-like PostgreSQL (TLS verify-full) | routing 62/62; records 26/26; unauthorized 8/8, 0 leaks; retrieval 30/30 (MRR 0.978); grounded 30/30, 0 false fallbacks; citations 30/30, precision 1.00; mixed 10/10; out-of-scope 6/6; 0 errors. Latency p50/p95 ms: records 55/107, handbook 1,706/3,040, mixed 1,546/2,189 |
| Backend suite (Docker) | 696 passed (unchanged code since) |

### 4. Local activation - prepared, awaiting owner approval (not executed)

Order (the running backend image predates migration 008, so the new images are built first; building does not touch running containers):
1. Tag the current images for rollback: `docker tag employee-onboarding-assistant-backend:latest employee-onboarding-assistant-backend:pre-008` (same for frontend).
2. Backup (runbook section 12): `pg_dump -Fc -f` inside the db container, `docker compose cp` to `backups\`, `pg_restore -l` check.
3. `docker compose --env-file <secrets> build backend frontend`.
4. `docker compose --env-file <secrets> run --rm --no-deps -e PG_ADMIN_USER=onboardai -e PG_ADMIN_PASSWORD backend python backend/migrations/008_hr_escalation_queue.py --apply`, then `--verify`; 007 and 005 `--verify`.
5. `docker compose --env-file <secrets> up -d --no-deps --wait backend frontend`; checks: `/api/health`, `/ready` inside the container, record counts unchanged.
Rollback: retag `pre-008` images and `up -d` (008 is additive; the old code ignores the new tables).

### Next (after deployment)

Presentation, detailed documentation, storyboard, submission packaging and Blob Storage integration are deferred until after a successful deployment (owner decision).

## Local Activation of Migration 008 + Azure Discovery (24 November 2026, owner-approved)

**Status: local stack ACTIVATED on the new images; Azure deployment BLOCKED (PostgreSQL by policy).** Nothing committed or staged; no Azure resource created or modified.

### Local activation (approved by the owner)

| Step | Result |
|---|---|
| Before | live counts messages/feedback/escalations/completed tasks/accounts/tickets = 18/0/1/7/1/0 |
| Rollback images | `employee-onboarding-assistant-backend:pre-008` (cc84ac32d175), `...-frontend:pre-008` (65fac941e7e9) |
| Backup | `backups/onboardai_pre008_20261124_171502.dump` (44.6 KB, `pg_dump -Fc -f` in the container + `docker cp`); `pg_restore -l`: 13 table-data entries; full restore into a throwaway server: counts identical (18/0/1/7/1/0) |
| Build | `docker compose build backend frontend` (177 s; running containers untouched) |
| Migration 008 | dry run, then `--apply`: 13 DDL statements + 10 grants, verified; `008 --verify`, `007 --verify`, `005 --verify` (`key_matches_secret: true`, no problems) all clean; counts unchanged |
| Restart | `up -d --no-deps --wait backend frontend` (29 s): all three containers healthy on the new images (backend 2c9603385f4a, frontend b818bb469aea) |
| Public smoke | `/ready` all 5 components ok; `/` 200, `/api/health` 200, `/api/docs` and `/api/openapi.json` 404, `/api/employees/EMP001` and `/api/hr/escalations` 401 unauthenticated, generic login error, CSP self-only + X-Frame-Options + nosniff; backend log 0 errors |
| Authenticated smoke (new local images against a throwaway clone of the live database incl. 008; live records untouched) | **27/27** (auth, CSRF, checklist, status, leave, isolation, GPT-4.1 citation p. 3, fallback, mixed, feedback, escalation, history, headers, docs 404, invalid Azure key -> 503 and records part kept); logs: 0 tracebacks, 0 secrets |
| After | live counts 18/0/1/7/1 unchanged (one expected `login_failures` row from the wrong-password smoke test, expires after 15 minutes) |

Rollback (if needed): `docker tag ...:pre-008 ...:latest` for both images, `docker compose --env-file <secrets> up -d --no-deps backend frontend`; 008 is additive and ignored by the old code. Minor difference noted: the local nginx still serves `/api/ready` (the Azure template hides it); localhost-only, low risk.

### Azure discovery (read-only, config dir `%USERPROFILE%\.azure-onboardai`)

| Resource | Discovered |
|---|---|
| Resource group / region | `<resource-group>`, South India |
| App Service plan | `<app-service-plan>`, P0v3, Linux, 1 app |
| Backend Web App | `onboardai-eliksha-backend`, host **`<backend-host>.azurewebsites.net`** (unique default host name, not `<name>.azurewebsites.net`), HTTPS only, **sitecontainers model**, no VNet integration, public access enabled |
| Frontend Web App | not present yet |
| ACR | `onboardaielikshaacr`, Basic, admin disabled, login server **`<acr-login-server>`** (TenantReuse hash) |
| PostgreSQL / VNet / private DNS | none exist |
| Other | Log Analytics, Application Insights, AI Foundry account `<azure-openai-resource>` (Azure OpenAI) |

**Root cause of the PostgreSQL failure (activity log, 11:40 UTC):** the portal deployment was rejected at validation by Azure Policy **"Sandbox: Allowed resource types"**: the private DNS zone `onboardai-eliksha-db.private.postgres.database.azure.com` (Microsoft.Network/privateDnsZones) and a second generated resource `smcxxjkqtwy5w` (type not shown in the log) are not allowed. The sandbox account cannot read the policy's allowed-type list (AuthorizationFailed). A validate-only probe showed that **Azure Container Instances are not authorised** for this account; the probe was then interrupted because the token now requires **MFA re-authentication** (AADSTS50076).

### Script changes from the discovery

- `Set-WebAppImage` (module): the backend uses the App Service **sitecontainers** model, so images are set with `az webapp sitecontainers update/create` (main container, target port, system-assigned identity for ACR pulls); classic apps still use `config container set`. Used by 40 and 90.
- Validator now also checks the commands that only run against existing resources (sitecontainers, identity, role assignment, ACR update, firewall cleanup, PITR): **0 failures**.

### Remaining deployment blockers

1. **Azure Policy**: private PostgreSQL needs Microsoft.Network/privateDnsZones and privateDnsZones/virtualNetworkLinks (and, for VNet integration, Microsoft.Network/virtualNetworks with delegated subnets) to be allowed; identify the type of `smcxxjkqtwy5w`. Owner/Azure team action.
2. **MFA re-authentication** of `%USERPROFILE%\.azure-onboardai` (`az login` with the claims challenge). Owner action.
3. **Migration path inside the VNet** (no public database access): ACI is not authorised. Options for the owner to decide: (a) migrate through the backend Web App once it has VNet integration, using the App Service SSH tunnel (`az webapp create-remote-connection`) into the backend container - requires adding an SSH server and PostgreSQL client tools to the backend image (Microsoft-documented pattern, reachable only through the authenticated SCM tunnel); (b) start the Azure database fresh from the repository schema/seed (`docker/postgres/01-05`) plus roles (005) run from inside the VNet by the backend image at deployment, and re-create the owner account - no local data transfer (local chat history and the one escalation are not migrated).
4. Backend VNet integration (delegated subnet) and the frontend Web App: after the policy exception, with owner approval.

## Private PostgreSQL + SSH-Based In-VNet Migration (24 November 2026)

**Decision (owner): private PostgreSQL connectivity only - no public database access, no temporary public firewall rules; migration Option A (App Service SSH tunnel) to preserve all existing data.** Confirmed by the owner from the Activity Log: the sandbox policy denies `Microsoft.Network/privateDnsZones` and `Microsoft.Network/privateDnsZones/virtualNetworkLinks` (`smcxxjkqtwy5w` = the VNet link). Nothing was created or modified in Azure; nothing staged or committed.

### Prepared and validated without the policy update

| Item | Result |
|---|---|
| `deploy/azure/migration/` (temporary migration image) | `migration.Dockerfile` = production backend image + OpenSSH server + PostgreSQL client + `onboardai-in-vnet-migrate`; `sshd_config`: port 2222, **ed25519 public key only**, no passwords, no keyboard-interactive, **no root**, `AllowUsers appuser`, no TCP/agent/stream/X11 forwarding, no tunnels; fresh host key per start; `appuser` password locked; application NOT started (maintenance responder: 200 for the App Service start-up probe, 503 for everything else); no secret baked in or stored |
| `in-vnet-migrate.sh` (runs inside the container, i.e. inside the VNet) | secrets only on stdin (strict KEY=VALUE allow-list, BOM/CRLF-safe, values may contain '='); TLS verify-full; **refuses a non-empty target**; one-transaction restore (pg_restore 17 renders SQL, the 17-only `transaction_timeout` setting is dropped for the 16 server); fingerprint comparison; 008 then 005 (scope key kept); verify 007/008/005; application-role startup checks; **automatic rollback to an empty database on any error**; uploads shredded |
| `65-Migrate-Database-InVNet.ps1` | one-time key pair (current-user ACL) -> dump/list/fingerprints (source read-only) -> build/push `<tag>-migrate` -> set `MIGRATION_SSH_AUTHORIZED_KEY` -> switch backend to the migration image -> `az webapp create-remote-connection` (127.0.0.1) -> scp + migrate -> **finally always**: shred uploads, close tunnel, delete the key setting, switch back to the PRODUCTION image (no SSH server), delete local key and dump; prints the PostgreSQL admin-password rotation command (needs approval). `-Rollback` empties the target through the same path |
| `15-Provision-Network.ps1` (new) | VNet, `snet-postgres` (delegated to PostgreSQL), `snet-app` (delegated to App Service), private DNS zone `<server>.private.postgres.database.azure.com` + VNet link, backend regional VNet integration with route-all; reuse-aware |
| `10-Provision-Database.ps1` | creates the server **private only** (`--vnet/--subnet/--private-dns-zone`, no `--public-access`); refuses to reuse a server with public access |
| `50-Configure-Apps.ps1` | no database firewall rules at all; refuses a public server; warns if the backend lacks VNet integration |
| `60-Migrate-Database.ps1` | firewall code removed; refuses to run against Azure (local rehearsal only) |
| Validator (`Test-DeploymentScripts.ps1`) | 14/14 scripts parse, 10/10 steps dry-run, **55/55 az command lines + 17 conditional commands valid against Azure CLI 2.91**, no secret in any output, new rule: **no database firewall rule and no `--public-access` in any step** - 0 failures |
| Backend suite (Docker) | **701 passed** (+5 static security tests of the migration tooling: key-only sshd, entrypoint, no SSH/DB client in production images, refusal/rollback/TLS in the migration script, no public database in any script) |

### Local rehearsal of the SSH migration (Azure-like private target: PostgreSQL 16, TLS required, non-superuser admin)

| Check | Result |
|---|---|
| SSH access | password login refused; root refused (even with the right key); a different key refused; the one-time key for `appuser` accepted; stdio/TCP forwarding to the database refused ("administratively prohibited") |
| Migration via `65 -SkipAzure` (container port on 127.0.0.1 standing in for the SCM tunnel) | **passed in 25 s**: TLS 1.3 verify-full, one-transaction restore, **12/12 fingerprints identical** (incl. Argon2 hashes and the scope key), 008 + 005 (82 statements, scope key matches), verification clean, app-role startup checks passed, uploads shredded, local key/dump deleted |
| Safety | second migration against the populated target **refused** (14 tables untouched); 0 files left in the upload directory; **0 secret values** in container logs, process environments or the env file |
| Rollback | `-Rollback`: database recreated empty, application roles removed; re-migration afterwards succeeded |
| Production image on the migrated database | `/ready` 200 (database, schema, index, model, configuration ok); no SSH server in the production container |
| Defects found and fixed during the rehearsal | parent directory permissions of the maintenance responder; PowerShell 5.1 stderr-as-error and UTF-8 BOM on stdin; PowerShell comma/plus precedence in the secrets list (values were concatenated - refused safely); IFS parsing that would strip a trailing '=' from secrets; pg_restore 17 vs server 16 (`transaction_timeout`). In every failure the script failed closed, printed no secret and ran its cleanup/rollback |

### Remaining blockers / owner actions

1. Policy exception for `Microsoft.Network/privateDnsZones` and `Microsoft.Network/privateDnsZones/virtualNetworkLinks` (Azure team).
2. MFA re-authentication of `%USERPROFILE%\.azure-onboardai` (owner).
3. Add `AZURE_PG_ADMIN_PASSWORD` to the secrets file (owner; the file is never modified by these scripts).
4. Approvals, in order: 15 (network + VNet integration) -> 10 (private server) -> 30 (push images) -> 40 (frontend app, image settings) -> 50 (settings) -> 65 (migration) -> admin password rotation -> 70 (verify).

## Azure Deployment - Images Published, App Services Hardened (24 November 2026)

**Status:** the private PostgreSQL deployment failed again on the same two policy denials (`Microsoft.Network/privateDnsZones`, `privateDnsZones/virtualNetworkLinks`). The owner created both Web Apps (system-assigned identities, AcrPull verified) and re-authenticated the CLI. Everything that does not depend on PostgreSQL or private networking is done. Approved and executed by the owner's decision: **ACR push** and **App Service hardening**. Deferred by the owner: frontend container deployment. No resource was created, no public database access exists, nothing staged or committed.

### Discovery (read-only, `%USERPROFILE%\.azure-onboardai`)

Resource group `<resource-group>` (southindia); plan `<app-service-plan>` (P0v3); backend `<backend-host>.azurewebsites.net`; frontend `<frontend-host>.azurewebsites.net`; both apps use the **sitecontainers** model with a placeholder main container (`appsvc/staticsite`, port 80, anonymous pull); ACR login server `<acr-login-server>`; no PostgreSQL/VNet. Both apps share the plan's outbound IP addresses: an IP-based access restriction on the backend cannot distinguish our frontend from other apps on the same stamp, so the **proxy-key header** (BACKEND_PROXY_SECRET) is the effective frontend-to-backend control (IP restriction = defence in depth).

### Executed (approved)

| Action | Result |
|---|---|
| Production images (step 30, build + secret scan) | `onboardai-backend` and `onboardai-frontend`, tag **`78b80ee-202611241823`** (code = 78b80ee + this batch's working tree); index 65 chunks + embedding model + PDF verified at build; secret scan clean (credentials/endpoints); Trivy **0 fixable HIGH/CRITICAL** both images; backend runs as appuser, no SSH server, no DB client, 0 secret-named environment variables baked in |
| ACR push (`az acr login`, Entra ID) | backend digest `sha256:adbb53ceb9b622225b0823ce0aedb905b8f348b1be66b11c3405ba497711c1e8`, frontend digest `sha256:a26b2cfd5c00307e85d5cc6e677ed3e0132f7cd0a6910327dc964f14c5aa7584`; registry now lists exactly these tags |
| App Service hardening (step 40 `-HardenOnly`, both apps) | verified: FTPS Disabled, basic-auth publishing off (FTP and SCM), HTTP/2 on, TLS 1.2, HTTPS only, Always On, ARR affinity off, ACR pulls via managed identity, container logging on; identity/AcrPull only checked; images and health checks untouched |

### Script fixes from this round

* `05-Discover-Resources.ps1`: generated `config.psd1` was not a valid data file (PowerShell ',' vs '+' precedence put the header comment and `@{` on one line); fixed; region normalised to lowercase.
* `Initialize-Deployment`: now **fails closed** when the configuration cannot be parsed (before, a parse error left an empty configuration and produced an empty image tag); per-step `-NotNeeded` keys (steps 30 and 40 `-HardenOnly` do not need the PostgreSQL values) while every other placeholder still blocks `-Execute`.
* `30-Publish-Images.ps1`: the image secret scan matched role names (`onboardai_app`, `onboardai_reader`) from the secrets file - a false positive (identifiers present in the code by design); the scan now checks credential and endpoint values only. Messages show the real registry and dry-run status.
* `40-Provision-AppService.ps1`: `-HardenOnly` mode (settings only, creates nothing, no image change).
* Validator: also checks that every `.psd1` parses; **0 failures**.

### Remaining deployment steps (each needs approval)

| # | Step | Depends on | Estimate |
|---|---|---|---|
| 1 | Policy exception for private DNS zones + VNet links | Azure team | external |
| 2 | `AZURE_PG_ADMIN_PASSWORD` in the secrets file | owner | 2 min |
| 3 | `15-Provision-Network.ps1 -Execute` (VNet, delegated subnets, private DNS + link, backend VNet integration) | 1 | 5-10 min |
| 4 | Private PostgreSQL (owner, or `10-Provision-Database.ps1 -Execute`), then `05-Discover-Resources.ps1 -PgServer <name>` | 3 | 10-15 min (server creation) |
| 5 | `50-Configure-Apps.ps1 -Execute` (app settings incl. private PG_HOST, proxy secret; frontend settings; backend access restriction) | 4 | 5 min |
| 6 | `65-Migrate-Database-InVNet.ps1 -Execute` (temporary migration image, SSH tunnel, restore, verify, switch back) - if the Entra-authenticated SCM tunnel is refused with basic auth disabled, temporarily allow SCM basic auth for the migration window only (approval) | 5 | 15-20 min |
| 7 | `40-Provision-AppService.ps1 -Execute` (production images on both apps, health checks /ready and /healthz) | 6 | 10 min (pull + start) |
| 8 | PostgreSQL admin password rotation; `70-Verify-Deployment.ps1` (16 checks + direct-backend refusal); trusted-proxy-hops check | 7 | 10 min |

**Revised estimate after the policy exception: about 60-75 minutes** of execution, mostly Azure provisioning, image pull and container start-up.

## Deployment Readiness - Fast-Track Checks (24 November 2026)

**Status: deployment preparation COMPLETE; waiting for the private DNS policy exception.** No Azure provisioning, no production container activation, nothing staged or committed.

| Check | Result |
|---|---|
| ACR digests vs build records | backend tag `78b80ee-202611241823` -> `sha256:adbb53ceb9b622225b0823ce0aedb905b8f348b1be66b11c3405ba497711c1e8`, frontend -> `sha256:a26b2cfd5c00307e85d5cc6e677ed3e0132f7cd0a6910327dc964f14c5aa7584`: **identical** to the digests recorded at push; the untagged manifests are the platform image and BuildKit attestation of each index |
| Source consistency | no image input (backend, data, frontend sources, Dockerfiles, nginx files, entrypoint) changed after the respective build: no rebuild needed |
| SSH tunnel with SCM basic auth disabled | `az webapp create-remote-connection` (CLI 2.91) authenticates with the app's **publishing credentials** (HTTP Basic, `begin_list_publishing_credentials`): it is refused while SCM basic auth is disabled. Browser SSH (Entra) uses the fixed root password, which the key-only sshd rejects by design. Decision: `65 -AllowTemporaryScmBasicAuth` (approval) enables **SCM-only** basic auth for the migration window; cleanup always disables it and regenerates the publishing password. FTP basic auth stays off. Live tunnel test deferred to the migration |
| Private backend networking | IP restrictions/secret headers are NOT used as isolation: both apps get regional VNet integration in `snet-app` (route-all), `snet-app` gets the `Microsoft.Web` service endpoint, the backend admits **only that subnet** (default deny; SCM site keeps its own Entra-protected access). `50-Configure-Apps.ps1` refuses to run unless this restriction exists and no IP allow rule remains; the proxy-key header stays as an extra layer |
| Validator | 61 az command lines + conditional commands valid against CLI 2.91; no secrets; no database firewall/public access: **0 failures** |

### Mandatory Azure permissions (policy "Sandbox: Allowed resource types" + RBAC)

* Resource types: `Microsoft.Network/privateDnsZones`, `Microsoft.Network/privateDnsZones/virtualNetworkLinks` (**currently denied - the only known blocker**); `Microsoft.Network/virtualNetworks` (+ subnets, delegations, service endpoints); `Microsoft.DBforPostgreSQL/flexibleServers`; App Service regional VNet integration (`Microsoft.Web/sites/networkConfig` / `virtualNetworkConnections`) - not yet exercised, confirm with the Azure team.
* RBAC on the resource group: `Microsoft.Network/virtualNetworks/subnets/join/action` (VNet integration, PostgreSQL injection), write on `Microsoft.Web/sites/basicPublishingCredentialsPolicies` (temporary SCM basic auth), `Microsoft.Web/sites/newpassword/action`.
* Not usable under the current policy: backend private endpoint (needs `privatelink.azurewebsites.net`, a private DNS zone); container instances (not authorised).

### Ordered execution (after the exception; each step needs approval)

```powershell
$env:AZURE_CONFIG_DIR = "$env:USERPROFILE\.azure-onboardai"
.\deploy\azure\00-Preflight.ps1 -Execute                                   # ARM validate: policy now allows all types
.\deploy\azure\15-Provision-Network.ps1 -Execute                           # VNet, subnets, private DNS + link, both apps integrated, backend subnet-only
.\deploy\azure\10-Provision-Database.ps1 -Execute                          # PRIVATE PostgreSQL 16 (or reuse the owner's server)
.\deploy\azure\05-Discover-Resources.ps1 -PgServer <server-name>           # refresh config.psd1 (PgHost, PgAdminUser)
.\deploy\azure\50-Configure-Apps.ps1 -Execute                              # app settings (private PG_HOST, proxy secret); isolation check
.\deploy\azure\65-Migrate-Database-InVNet.ps1 -Execute -AllowTemporaryScmBasicAuth   # SSH migration; backend back on production image
.\deploy\azure\40-Provision-AppService.ps1 -Execute                        # production images on both apps + health checks
az postgres flexible-server update --resource-group <rg> --name <server> --admin-password <new>   # rotate admin password
$env:VERIFY_PW = '<employee password>'; .\deploy\azure\70-Verify-Deployment.ps1 -BaseUrl https://<frontend-host>.azurewebsites.net -BackendUrl https://<backend-host>.azurewebsites.net -EmployeeEmail <email> -PasswordEnv VERIFY_PW
```

Rollback: `90-Rollback.ps1 -PreviousTag <tag> -Execute`; migration rollback `65-Migrate-Database-InVNet.ps1 -Execute -Rollback`.

**Revised estimate after the exception: about 60-75 minutes** (PostgreSQL creation 10-15, migration 15-20, image pull/start 10, verification 10).

## Azure Deployment - Portal PostgreSQL Reuse and Readiness (25 November 2026)

**Status: permissions verified; owner-created private resources discovered and wired into the scripts; waiting for approvals and `AZURE_PG_ADMIN_PASSWORD`.** Nothing created or modified in Azure by these scripts in this stage; nothing staged or committed (HEAD `3c0b4df` committed by the owner).

| Item | Result |
|---|---|
| Permissions | validate-only ARM deployment of VNet + delegated subnets + service endpoint, private DNS zone + VNet link, private PostgreSQL 16, App Service VNet integration: **Succeeded** (policy and RBAC allow every type) |
| Owner-created (portal) resources, reused | VNet `onboardai-vnet` 10.0.0.0/16; `postgres-subnet` 10.0.1.0/24 (in use by the server); server `onboardai-eliksha-db` (Ready, PostgreSQL 16, B1ms, **public access Disabled**, admin `onboardai_admin`); private DNS zone `onboardai-eliksha-db.private.postgres.database.azure.com` linked to the VNet (Completed); `appservice-subnet` 10.0.2.0/24 and `private-endpoint-subnet` 10.0.3.0/24 |
| Finding | `appservice-subnet` is **delegated to PostgreSQL**, not `Microsoft.Web/serverFarms`, and unused: step 15 re-delegates it (and adds the `Microsoft.Web` service endpoint) - needs approval; it refuses if the subnet is in use. `private-endpoint-subnet` is left unchanged (not used by this design) |
| App Service plan | SKU is now **B1** (was P0v3); supports VNet integration, Always On, health checks; 1 core as in the load test (backend peak ~340 MiB of 1.75 GB) |
| Images | published `78b80ee-202611241823` reused (content = commit `3c0b4df` image inputs; digests unchanged); migration image `...-78b80ee-202611241823-migrate` built locally and checked (key-only sshd, PostgreSQL client), **not pushed** |
| Secrets file | all required values present except **`AZURE_PG_ADMIN_PASSWORD` (missing; owner to add the portal admin password)** |
| Scripts updated | 15 reuses VNet/PostgreSQL subnet/DNS (never creates them), reuses `appservice-subnet`, verifies the DNS link from the server; 05 records the intended server, admin and network names and accepts `-ImageTag`; config template/local config use the actual names; validator: placeholder-safe, **0 failures** |
| Private backend ingress | unchanged design: both apps VNet-integrated in `appservice-subnet` (route all), backend admits only that subnet (default deny); SCM basic auth stays disabled unless separately approved |

### Ordered next steps (each needs approval)

1. `15-Provision-Network.ps1 -Execute` - re-delegate `appservice-subnet` + service endpoint, VNet integration of both apps, backend subnet-only ingress.
2. `10-Provision-Database.ps1 -Execute` - reuses the server: `require_secure_transport=on`, TLS >= 1.2, database `onboardai`.
3. `50-Configure-Apps.ps1 -Execute` - app settings (secrets via temporary file, private PG_HOST, proxy secret); isolation check.
4. `65-Migrate-Database-InVNet.ps1 -Execute` - pushes the migration image, SSH migration; **needs `AZURE_PG_ADMIN_PASSWORD`; SCM basic auth only with a separate approval (`-AllowTemporaryScmBasicAuth`)**.
5. `40-Provision-AppService.ps1 -Execute` - production images + health checks; then admin password rotation and `70-Verify-Deployment.ps1`.

## Azure Deployment - Stages 1-3 Executed (25 November 2026, owner-approved: network, database configuration, app settings)

| Stage | Result (verified read-only afterwards) |
|---|---|
| 15 Network | `appservice-subnet` (10.0.2.0/24, unused) re-delegated from PostgreSQL to `Microsoft.Web/serverFarms` + service endpoint `Microsoft.Web` (Succeeded); both Web Apps VNet-integrated into it with route-all; backend access restrictions: one Allow rule for `appservice-subnet` (priority 100), default **Deny**, SCM site restricted separately (not inheriting); direct public request to the backend -> **403**. Private DNS zone linked to `onboardai-vnet` (Completed). A false positive of the in-use guard (PowerShell `@($null).Count` = 1) stopped the first run before any change; fixed |
| 10 Database (existing portal server) | `require_secure_transport=on`, `ssl_min_protocol_version=TLSv1.2`, database `onboardai` created; public network access **Disabled**; **0 firewall rules** |
| 50 Settings | backend: PG_HOST = server FQDN (resolves to the private address through the linked private zone inside the VNet), PG_PORT 5432, PG_DATABASE onboardai, PG_USER onboardai_app, PG_READER_USER onboardai_reader, WEBSITES_PORT 8000, TRUSTED_PROXY_HOPS 3, Azure OpenAI deployment gpt-4.1; every secret equals the secrets-file value (compared, not printed); frontend: BACKEND_ORIGIN/HOST = discovered backend host, WEBSITES_PORT 80; proxy secret (48 chars) identical on both apps; temporary settings files deleted; isolation check passed; both apps restarted (still placeholder containers) |

**Ingress as configured (accurate description):** the backend keeps its public endpoint (public DNS name) but only admits traffic from `appservice-subnet` through the `Microsoft.Web` service endpoint (default deny; anything else gets 403), plus the proxy-key header. This is **service-endpoint access restriction, not private-endpoint isolation**. Full private-endpoint isolation would additionally need a backend private endpoint (`privatelink.azurewebsites.net` zone - now allowed by policy - and a non-delegated subnet), public network access disabled on the backend, and the frontend resolving the private address; this needs an owner decision before production activation. The SCM site of the backend is not IP-restricted (needed for the migration tunnel) and requires authentication (Entra; basic auth disabled).

**Private database connectivity:** control plane verified (server private, DNS zone linked, backend integrated in the VNet with route-all). Data-plane connectivity (DNS resolution to the private address + TLS verify-full connection) is verified from inside the VNet by the first step of the migration (`onboardai-in-vnet-migrate`: "TLS version" check) - our containers are not running in the backend yet.

**Step 65 status:** prepared (migration image built locally, dry run against the real resources). Added a fail-fast pre-check: with SCM basic auth disabled and no `-AllowTemporaryScmBasicAuth`, it stops before any Azure change. Blockers: `AZURE_PG_ADMIN_PASSWORD` not yet in the secrets file; separate approval for temporary SCM basic auth. Validator: 0 failures.

---

## Azure Deployment - Stages 4-7 Executed (25 Nov 2026)

### Step 65 - in-VNet database migration (SSH over the SCM tunnel)
| Attempt | Result | Root cause | Fix |
|---|---|---|---|
| 1 | Rolled back automatically | Fingerprint mismatch with equal row counts: collation differs (Alpine/musl source vs Azure glibc en_US) | Fingerprints ordered with `COLLATE "C"` |
| 2 | SSH kex reset | Production image crash-looped on the empty database (startup backoff ~4.5 min); SCM/basic-auth changes applied after the restart caused more restarts | All configuration first, then ONE stop/start |
| 3 | Readiness window expired | Same as 2 (diagnosed from ARM container logs) | Bounded 15-minute readiness loop, tunnel restarted if it exits |
| 4 | **SUCCEEDED** (525 s) | Final local `Remove-Item` failed: `az` is a .cmd wrapper, its python child kept `tunnel.err` open | Cleanup now kills the tunnel process TREE and retries the delete (bounded) |

Attempt 4: TLS 1.3 verify-full inside the VNet; 12/12 table fingerprints identical; migrations 005/008 applied;
scope key matched; application-role startup checks passed. No duplicate migration was started.

Cleanup verified in Azure: SCM and FTP basic auth `false`, publishing password regenerated, temporary
`migration-operator` SCM rule removed (SCM default Deny, no allow rules), `MIGRATION_SSH_AUTHORIZED_KEY` deleted,
backend back on the production image; leftover tunnel process stopped; local work directory (key pair, dump)
overwritten and deleted.

### Step 40 - production activation
Both apps on `78b80ee-202611241823` (managed identity pull), HTTPS only, TLS 1.2+, FTPS disabled, basic auth
disabled, health checks `/ready` (backend) and `/healthz` (frontend). `/api/health` via the frontend:
`{"status":"ok","database":"ok"}`.

### Step 45 - backend private endpoint
* `private-endpoint-subnet` (10.0.3.0/24): unused PostgreSQL delegation removed; PE network policies disabled.
* Private DNS zone `privatelink.azurewebsites.net` + VNet link `onboardai-vnet-webapps`.
* Private endpoint `onboardai-eliksha-backend-pe` (10.0.3.4): Succeeded / Approved; DNS zone group `default`
  (A records for the main and SCM host names).
* Backend `publicNetworkAccess = Disabled`. Main and SCM sites return 403 from the internet; the frontend
  (VNet-integrated, route-all) reaches the backend only through the private endpoint (frontend restarted so nginx
  re-resolves the backend host).
* Bug found and fixed: `az network private-endpoint dns-zone-group show` returns `{}` with exit 0 when the group is
  missing, so the first run skipped creating it; the group was created and the script now checks for a real object.

### Database administrator password rotation
Rotated to a 40-character random value that was never printed or stored (temporary file overwritten and deleted).
The application uses only `onboardai_app` (verified: no app setting references the admin login), so it was not
affected. The old `AZURE_PG_ADMIN_PASSWORD` in the external secrets file is now INVALID; the owner resets it when admin
access is needed (`az postgres flexible-server update ... --admin-password`) and stores it in the secrets file.

### Step 70 - verification
Public checks 8/8 PASS: frontend health, HSTS/CSP/X-Frame-Options/nosniff, API health with database ok, API docs and
readiness details not public, sign-in required, generic login error, backend not usable directly.
Signed-in checks (cookie flags, own data, cross-employee refusal, grounded GPT-4.1 answer, fallback, history,
sign-out) need an employee password and are run by the owner:
`$env:VERIFY_PW = '<password>'; .\deploy\azure\70-Verify-Deployment.ps1 -BaseUrl <frontend> -BackendUrl <backend> -EmployeeEmail <email> -PasswordEnv VERIFY_PW`

### Final posture
| Component | State |
|---|---|
| PostgreSQL 16 | Private (VNet-injected), public access Disabled, TLS verify-full, no firewall rules |
| Backend | Public network access Disabled; reachable only via private endpoint; SCM/FTP basic auth off |
| Frontend | Public HTTPS entry point; SCM/FTP basic auth off |
| Validator | `Test-DeploymentScripts.ps1`: 0 failures |

---

## Azure Deployment - Completed and Verified (25 Nov 2026)

**Result: SUCCESS.** Final authenticated production verification (`deploy/azure/70-Verify-Deployment.ps1`, run by the
owner with an employee account): **17/17 checks passed**.

| Group | Result | Checks |
|---|---|---|
| Public | 8/8 | frontend health; HSTS, CSP self-only, X-Frame-Options DENY, nosniff; API health with database ok; API docs not public; readiness details not public; employee data requires sign-in; generic login error; backend not usable directly |
| Authenticated | 9/9 | sign-in with Secure/HttpOnly/SameSite=Strict cookie; own profile; own checklist; another employee's data refused; grounded GPT-4.1 answer citing handbook.pdf page 3; out-of-scope safe fallback; chat history; sign-out; session terminated |
| Latency | PASS | live RAG answer 4232 ms (target < 5000 ms) |

Deployed state (unchanged since verification): frontend Web App is the only public endpoint; backend Web App public
network access Disabled, reachable only via its private endpoint; PostgreSQL Flexible Server 16 private (VNet-injected,
no firewall rules, TLS verified); images `78b80ee-202611241823` from ACR via managed identity; SCM/FTP basic auth
disabled on both apps; database administrator password rotated (unstored).

Documentation updated: `README.md` (status, Azure deployment section, limitations), `docs/architecture.md` (deployed
Azure network diagram and configuration table), `deploy/azure/README.md` (actual network, executed order, step 45,
migration cleanup, 17-check verification, admin password), `docs/runbook.md` (pointer to the Azure runbook).

Milestone M4 (Deploy + Test): Azure deployment DONE. Remaining (outside the deployed system): commit and push of the
deployment scripts and documentation; continuous deployment; Key Vault references for secrets.

---

## Submission Cleanup (A1-A13) and CD Feasibility (25 Nov 2026)

**Scope:** owner-approved priorities 1-4 of the read-only audit at commit `df18ffd` (CI run #7 passed). B1-B4 deferred;
C1-C8 not implemented. No runtime application logic, database schema, migration, record, backup, Azure resource or
production image was changed; no image was rebuilt or redeployed.

### Changes
| ID | File(s) | Change |
|---|---|---|
| A1-A5 | `README.md` | Rate limiting (shared `login_failures` table on PostgreSQL), CSP (self-only fonts), HR/IT escalation queue, migrations 005-008 (PostgreSQL), evaluation rows now show current GPT-4.1 results (RAG 50/50, held-out 62/62) with Groq runs labelled historical |
| README review | `README.md` | Status rows for CI and CD (CD not implemented); repository layout (deploy/azure, migrations); configuration table completed (rate-limit store, reader role, TLS, pool, proxy key/hops, API docs); ingestion description (canonical PDF, 2-sentence windows, 65 chunks); `hr` role, `/ready` and `/hr/escalations` endpoints; production security summary; CI run #7 and 17/17 production verification; test counts 701 / 133 |
| A6 | `frontend/README.md` | Sign-in instead of the removed "employee selector"; Azure build and GPT-4.1 statements replace "Azure is the target" / "Groq is temporary" |
| A7 | `docs/runbook.md` | Rollback no longer points to the Groq commit; Azure rollback via `90-Rollback.ps1` |
| A8 | `tests/load/run_isolated_load_test.sh` | Usage comment: Azure OpenAI settings instead of a Groq key |
| A9 | `docs/final_local_test_report.md`, `docs/test_report.md`, `docs/hybrid_eval_report.md`, `docs/load_test_report.md` | One-line "historical report" note under each title (Groq-era evidence kept unchanged), linking the current Azure results |
| A10 | `.env.example` | 23 more settings documented as commented entries showing the code defaults (no credentials; behaviour unchanged when copied) |
| A11 | `scripts/hybrid_eval.py`, `scripts/rag_eval.py` | Unused `statistics` / `json` imports removed |
| A12 | `tests/integration/test_auth.py`, `tests/unit/test_rag_eval.py`, `tests/integration/test_frontend_contract.py` | Unused `re` / `json` / `TestClient` imports removed (no test removed or changed) |
| A13 | 8 `.gitkeep` files (`.github/workflows`, `backend/{middleware,routes,schemas,services}`, `tests/{integration,load,unit}`) | Deleted; `data/index/.gitkeep` kept (re-included by `.gitignore`) |

Image note: `backend/` and `frontend/` are build contexts, so the `.gitkeep` deletions and `frontend/README.md` change the
inputs of a FUTURE image build (no runtime effect; `frontend/README.md` stays in the build stage only). The running
images (`78b80ee-202611241823`) are unaffected.

### Verification
| Check | Result | Baseline |
|---|---|---|
| Backend suite (Docker test image, Python 3.12, repo read-only) | **701 passed**, 133 skipped (live-PostgreSQL suites without a disposable server) | 701 passed - no regression |
| Live PostgreSQL suites | not re-run: no PostgreSQL test or runtime file changed | 133 passed (24 Nov) |
| Frontend | not re-run: only `frontend/README.md` changed | 11 passed, lint clean, build OK |
| `Test-DeploymentScripts.ps1` | 69 az command lines, **0 failures** | 0 failures |
| `docker compose config --quiet` | valid | valid |
| Secret scan (all 181 tracked text files x 16 secret/identifier values) | **0 hits**; generic credential patterns: only the fake token in `tests/unit/test_rag_eval.py` | 0 hits |

### CD feasibility (read-only; nothing created)
* **Permissions:** the operator account has the custom role "Resource Group Admin1 (No Delete)" on the resource group,
  including `Microsoft.ManagedIdentity/userAssignedIdentities/*`, `Microsoft.Authorization/roleAssignments/*`,
  `Microsoft.Web/*`, `Microsoft.ContainerRegistry/*`; no `roleDefinitions/write` (built-in roles only). The tenant allows
  users to create app registrations. **No permission blocker.**
* **OIDC:** user-assigned managed identity in the resource group with a federated credential for
  `repo:<owner>/<repo>:environment:production` (GitHub environment with required reviewer); `azure/login` with client,
  tenant and subscription IDs as non-secret variables; no client secret, no publish profile, SCM basic auth stays off.
* **Least privilege:** `AcrPush` on the registry; `Website Contributor` on the two Web Apps only; no database,
  network, Key Vault or resource-group role.
* **Publishing:** ACR Basic with public network access (required for GitHub-hosted runners; Basic has no firewall);
  build both images with `deploy/azure/*.Dockerfile`, immutable commit-SHA tags, the existing secret scan before push.
  The backend image bundles the FAISS index, which is git-ignored: the pipeline must build it from `data/raw`
  (as CI does) and validate it.
* **Deployment:** ARM only - `az webapp sitecontainers update` (main container image, managed-identity pull) + restart,
  backend first, then frontend. The backend SCM site is private and is not needed.
* **Health and rollback:** poll the public frontend `/healthz` and `/api/health` (proves frontend -> private endpoint
  -> backend -> private PostgreSQL) plus the 70-Verify public checks; on failure re-point both apps to the previous tag
  (`90-Rollback.ps1` logic) and re-verify.
* **Networking:** GitHub-hosted runners need only the ARM API, ACR and the public frontend; backend private endpoint,
  disabled backend public access and the private database are unchanged. Database migrations stay manual
  (in-VNet procedure, step 65) - a runner must never reach the database.
* **Constraints:** B1 plan has no deployment slots (brief restart per deploy, no blue/green); signed-in verification
  needs a dedicated test account password as a GitHub environment secret (or public checks only); sandbox subscription
  lifetime.
