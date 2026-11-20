# OnboardAI â€” Project Plan

**Project:** OnboardAI: RAG-Powered New Joiner Support Platform  
**Domain:** Generative AI for Human Resources  
**Team member:** Eliksha Maheshwari  
**Location:** Pune  
**Mentor:** Shankhalika Sarkar  
**Last updated:** 20 November 2026

## 1. Milestones

| Milestone | Planned day | Deliverable | Current status |
|---|---|---|---|
| M1 â€” Design | 31 | Charter, architecture, repository, synthetic data | Completed for local prototype |
| M2 â€” Backend + AI | 32 | FastAPI, RAG, FAISS, employee data APIs, orchestration | Implemented locally; Azure OpenAI migration pending |
| M3 â€” UI + Middleware | 33 | React dashboard, chat, checklist, support center, validation | Implemented and manually tested |
| M4 â€” Deploy + Test | 34 | Docker, Azure deployment, CI/CD, unit/integration/load/security tests | Local automated/API checks passed; deployment and remaining tests pending |
| M5 â€” Wrap-up | After | Runbook, architecture diagrams, storyboard, slides, demo, final repository | Pending |

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

**Step 71 â€” Azure readiness audit:** inspect the current Docker configuration, environment-variable references, Azure integration points, and available Azure permissions **without provisioning or changing cloud resources**. Record the findings here before implementation.

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
