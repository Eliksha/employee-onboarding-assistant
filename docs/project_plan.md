# OnboardAI — Project Plan

**Project:** OnboardAI: RAG-Powered New Joiner Support Platform  
**Domain:** Generative AI for Human Resources  
**Team member:** Eliksha Maheshwari  
**Location:** Pune  
**Mentor:** Shankhalika Sarkar  
**Last updated:** 20 November 2026

## 1. Milestones

| Milestone | Planned day | Deliverable | Current status |
|---|---|---|---|
| M1 — Design | 31 | Charter, architecture, repository, synthetic data | Completed for local prototype |
| M2 — Backend + AI | 32 | FastAPI, RAG, FAISS, employee data APIs, orchestration | Implemented locally; Azure OpenAI migration pending |
| M3 — UI + Middleware | 33 | React dashboard, chat, checklist, support center, validation | Implemented and manually tested |
| M4 — Deploy + Test | 34 | Docker, Azure deployment, CI/CD, unit/integration/load/security tests | Local automated/API checks passed; deployment and remaining tests pending |
| M5 — Wrap-up | After | Runbook, architecture diagrams, storyboard, slides, demo, final repository | Pending |

## 2. Scope and Technology Decisions

- **Backend:** Python, FastAPI, explicit deterministic agent orchestrator.
- **AI:** Retrieval-augmented generation over onboarding/policy content, using embeddings and FAISS. Azure OpenAI is the **target** LLM service; Groq was used temporarily during development and must be replaced before Azure completion.
- **Frontend:** React + Vite, connected to the FastAPI backend.
- **Prototype persistence:** SQLite at `data/app.db`.
- **Cloud target:** Azure only for the final solution. Production persistence, hosting, identity, secrets management, and monitoring require configuration and validation.
- **Data:** Synthetic fictional employees only; demo selectors EMP001, EMP002, EMP003.
- **Authentication:** Not implemented in the demo. An employee selector is **not** an authentication or authorization mechanism. Do not expose employee-specific APIs with real data or deploy them publicly without proper identity and access controls.

## 3. Implementation Progress

### Completed — Backend and data

- Reviewed existing FastAPI routes and SQLite tables; backed up the database before migrations.
- Applied non-destructive employee-specific migrations and synthetic seed data; preserved legacy records.
- Added employee profile, leave balance, IT asset, payroll calendar, checklist, and support ticket endpoints.
- Added employee-scoped chat history and request routing between employee information and policy/RAG responses.
- Implemented explicit Python orchestration for the local prototype.
- Added checklist updates via `PATCH /employees/{employee_id}/checklist/{item_id}`.
- Added support ticket creation via `POST /employees/{employee_id}/tickets`.

### Completed — Frontend

- React/Vite OnboardAI dashboard and employee demo selector.
- AI Assistant with employee-specific chat history.
- Leave & Payroll and My Assets views.
- Interactive checklist: mark complete/incomplete, persist changes, show progress and errors.
- Support Center: create tickets, show feedback, and refresh employee-specific ticket history.

### Completed — Verification (20 November 2026)

| Verification | Observed result | Scope |
|---|---|---|
| `python -m pytest -q` | **16 passed in 6.25 s** | Existing automated test suite |
| Live HTTP GET checks | **5/5 returned 200** | EMP001 profile, leave balances, checklist, assets, tickets |
| Employee-ID consistency | **6/6 checks; 0 mismatches** | Checklist and ticket API records for EMP001–EMP003 |
| SQLite schema inspection | Expected application tables present | `data/app.db` |
| SQLite checklist persistence | **45 assignments**, including `done=0` and `done=1` | `checklist_assignments` |
| SQLite support ticket persistence | **1 ticket** for EMP001, category IT, status `open` | `tickets` |
| UI acceptance checks | Checklist and support tickets reported working | Local React/FastAPI integration |

**Interpretation:** These checks support local functional correctness and employee-ID consistency. They do **not** demonstrate production-grade authorization, penetration testing, load readiness, or successful Azure deployment.

## 4. Remaining Work — Prioritized

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
| 20 Nov 2026 | Use synthetic demo employees EMP001–EMP003 | Enable employee-specific feature testing |
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

**Step 71 — Azure readiness audit:** inspect the current Docker configuration, environment-variable references, Azure integration points, and available Azure permissions **without provisioning or changing cloud resources**. Record the findings here before implementation.

### PostgreSQL Dependency Update � 20 November 2026

- Added `psycopg2-binary==2.9.13` to `requirements.txt`.
- Verified that version 2.9.13 is installed in the local Python virtual environment.
- Purpose: Ensure PostgreSQL connectivity dependencies are included in fresh installations and future deployment environments.
- Existing application functionality and database records remain unchanged by this dependency update.


### PostgreSQL Configuration Documentation � 20 November 2026

- Added DB_BACKEND and PG_* connection variables to .env.example.
- Documented PostgreSQL 16 as the intended database backend.
- Preserved SQLite as an available local fallback.
- No changes made to the private .env file or existing database records.
- Database credentials must remain outside version control.

### Frontend Asset Cleanup � 20 November 2026

- Removed unused frontend assets: hero.png, react.svg, vite.svg, and icons.svg.
- Confirmed no references to these filenames in frontend source or configuration files before removal.
- Retained favicon.svg for future browser icon configuration.
- No application logic, API routes, or database functionality was modified.

### Documentation Cleanup � 20 November 2026

- Removed the redundant project_plan_backup.md from the active repository.
- Retained docs/project_plan.md as the authoritative project plan.
- Preserved historical project decisions through existing backups and Git history.
- No application functionality or database records were modified.

### Frontend Documentation Cleanup � 20 November 2026

- Replaced the default React/Vite README with OnboardAI-specific frontend documentation.
- Removed outdated README_ONBOARDAI.txt.
- Preserved Vite, ESLint, and favicon configuration files.
- No application logic, API endpoints, or database records were modified.

### Backend Test Verification � 20 November 2026

- Executed automated tests with DB_BACKEND=sqlite.
- Result: 16 tests passed in 5.74 seconds.
- No test failures.
- PostgreSQL was not used for this test run.
