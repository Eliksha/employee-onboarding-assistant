# Project Plan

## Milestones
| Milestone | Day | Deliverable |
|---|---|---|
| M1 Design | 31 | Charter, architecture, repo, board, synthetic data |
| M2 Backend + AI | 32 | FastAPI endpoints, embeddings, FAISS, grounded /chat, 15-question test results |
| M3 UI + middleware | 33 | Streamlit chat + checklist, logging, validation, error handling |
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
