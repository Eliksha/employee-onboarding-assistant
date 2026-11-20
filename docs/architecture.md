# Architecture: AI Employee Onboarding Assistant

## Diagram
![Architecture](architecture.png)

## Components
React frontend | FastAPI backend + middleware | Ingestion pipeline | Embeddings | FAISS index | OpenAI LLM | SQLite | Handbook/FAQ documents

## Request flow
1. User asks a question in React.
2. `POST /chat {question}` to FastAPI.
3. Middleware validates and logs the request.
4. Question is embedded; FAISS returns top-4 chunks with scores.
5. Best score below threshold -> return fallback + escalation option.
6. Otherwise question + chunks -> LLM (answer only from context, cite source).
7. Response `{answer, sources, found}` is saved to SQLite and shown in React.

## Ingestion flow (offline)
Handbook PDF / FAQ Markdown -> extract text -> chunk (~500 tokens, overlap 50) -> embed -> store vectors + metadata (file, page, section) in FAISS.

## Checklist flow
`GET /checklist` loads tasks; `PATCH /checklist/{id}` saves a tick. SQLite only; no LLM or FAISS.

## Technology stack
| Layer | Choice | Reason |
|---|---|---|
| Frontend | React | Quick Python UI |
| Backend | FastAPI | Typed endpoints, auto docs |
| LLM + embeddings | OpenAI API | Training requirement |
| Vector store | FAISS (local) | No account needed |
| Storage | SQLite | Zero setup |
| Container / Cloud | Docker / Azure | Day 34, subject to access |
| CI/CD | GitHub Actions | Native to GitHub |
| Testing | Pytest, Locust | Unit/integration, load |

## Azure notes
No Azure access yet. Subscription, role, region and hosting service to be confirmed with the trainer. Fallback: run locally with Docker and document the blocker.
