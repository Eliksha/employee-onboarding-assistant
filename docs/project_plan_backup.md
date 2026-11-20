# Project Plan

## Milestones
| Milestone | Day | Deliverable |
|---|---|---|
| M1 Design | 31 | Charter, architecture, repo, board, synthetic data |
| M2 Backend + AI | 32 | FastAPI endpoints, embeddings, FAISS, grounded /chat, 15-question test results |
| M3 UI + middleware | 33 | React chat + checklist (migration in progress), logging, validation, error handling |
| M4 Deploy + test | 34 | Docker, Azure (or documented blocker), CI/CD, unit/integration/load tests |
| M5 Wrap-up | After | Runbook, storyboard, slides, live demo, final repo |

## Roles (solo)
Eliksha holds all roles: architecture & integration, backend, AI/LLM, frontend, DevOps & QA.

## Risks
| Risk | Impact | Mitigation |
|---|---|---|
| Missing OpenAI/Azure access | Blocks Days 32 and 34 | Confirm early; document blocker; local Docker fallback |
| Hallucinated answers | Wrong guidance | Grounding prompt, threshold, sources, fallback |
| Poor retrieval | Irrelevant answers | Tune chunk size/top-k; 15-question test set |
| Secret leak | Security incident | .gitignore, .env.example, rotate if exposed |
| Solo time overrun | Incomplete MVP | Narrow MVP, daily review, cut list |

## Dependencies
OpenAI key + model names (Day 32); synthetic data (Day 32); Docker installed (Day 34); Azure subscription/role/region (Day 34).

## Blocker log
| Date | Blocker | Who can resolve | Status |
|---|---|---|---|
| Day 31 | No Azure access yet | Trainer / lab admin | Open |
| Day 31 | OpenAI key availability | Trainer / program admin | Open - confirm |

## Decision log
| Date | Decision | Reason |
|---|---|---|
| Day 31 | FAISS instead of Pinecone | Local, no account |
| Day 31 | SQLite for history, feedback, checklist | Zero setup |
| Day 31 | Postpone login, upload page, analytics | Keep MVP achievable solo |

## OnboardAI Capstone Extension — Updated 20 November 2026

### Project
OnboardAI: RAG-Powered New Joiner Support Platform

### Implementation Decisions
- Backend-first development using FastAPI.
- React + Vite for the frontend, after backend completion.
- Azure as the target cloud platform, including Azure OpenAI.
- Groq is a temporary development integration, not the final LLM provider.
- SQLite for the current prototype; production database choice to be finalized.
- Synthetic employee information only.
- Detailed final architecture diagrams will be created after implementation.

### Backend Audit — Completed
- Verified 8 existing FastAPI route definitions.
- Reviewed the existing SQLite database implementation.
- Confirmed database location: data/app.db.
- Confirmed RAG similarity threshold: 0.65.
- Verified 4 existing database tables and 50 records:
  - checklist: 15
  - messages: 34
  - feedback: 1
  - escalations: 0
- Identified missing employee isolation, authentication, ticket management,
  agent orchestration, and secure text-to-SQL.
- No database schema or records modified during the audit.

### Upcoming Implementation Phases
1. Design employee-specific schema and authentication approach.
2. Back up SQLite and implement tested, non-destructive migrations.
3. Implement employee profile, leave, assets, and payroll endpoints.
4. Implement employee-specific checklist and ticket management.
5. Implement agent orchestration, guarded SQL tools, and RAG routing.
6. Integrate Azure OpenAI and implement security guardrails.
7. Complete backend unit, integration, and security tests.
8. Build and connect the React frontend.
9. Deploy and validate the application on Azure.
10. Finalize architecture diagrams, documentation, and demo.

### Data Protection Decisions
- Preserve all existing database records.
- Do not automatically assign legacy messages to an employee.
- Restrict personalized data access to authenticated employees.
- Keep SQL execution internal, validated, read-only, and employee-scoped.
- Protect administrative ingestion endpoints before deployment.

### Current Status
Backend audit complete. Next: database schema design and migration planning.

### Authentication and Demo Employee Selection — Decision
- No employee login or Microsoft Entra ID integration for the capstone prototype.
- Use a demo employee selector (EMP001, EMP002, etc.).
- All employee records are fictional and synthetic.
- Employee IDs are demo selectors, not verified identities.
- Personalized APIs are for local or controlled demonstrations only.
- Real employee data and public deployment require authentication and authorization.
- Existing SQLite database backed up before migration:
  data/app_backup_20261120_113654.db

### Current Status
Database backup completed. Next: implement non-destructive
employee-specific database migrations and synthetic seed data.

### Migration 001 — Completed 20 November 2026
- Created backend/migrations/001_employee_schema.py.
- Tested migration on a temporary database copy.
- Verified migration can execute twice without errors.
- Applied migration successfully to data/app.db.
- Confirmed 10 application tables exist.
- Preserved all 50 original records.
- SQLite integrity_check returned ok.
- Six new tables are currently empty.
- Next: create synthetic employee seed data and test relationships.

### Synthetic Employee Data — Completed 20 November 2026
- Created backend/migrations/002_seed_demo_data.py.
- Tested synthetic data insertion on a temporary SQLite database.
- Verified repeated execution does not create duplicate records.
- Created backup: data/app_pre_seed_20261120_115842.db.
- Seeded three fictional employees: EMP001, EMP002, EMP003.
- Added 6 leave balances, 3 IT assets and 2 payroll entries.
- Created 45 employee-specific checklist assignments.
- Preserved all 50 original records.
- Verified SQLite integrity and foreign key relationships.
- Next: implement employee-specific backend database services.
