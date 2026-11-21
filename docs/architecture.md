# Architecture: OnboardAI

Current architecture of the local implementation (21 November 2026). Azure components are planned, not implemented.

## System overview

```mermaid
flowchart LR
    user["Browser"] --> fe["React SPA<br/>(Vite dev server or nginx in Docker)"]
    fe -->|"/api/* same origin"| api["FastAPI backend<br/>middleware: request ID, logging, safe errors"]
    api --> orch{"Orchestrator<br/>intent router"}
    orch -->|"personal data intent"| edb[("PostgreSQL 16<br/>or SQLite")]
    orch -->|"policy question"| rag["RAG pipeline"]
    rag --> emb["fastembed<br/>BAAI/bge-small-en-v1.5"]
    rag --> idx[("FAISS index<br/>data/index")]
    rag --> guard["Guardrails"]
    guard --> llm["LLM API<br/>Groq (temporary)<br/>Azure OpenAI (planned)"]
    api -->|"chat history, tickets, checklist"| edb
    raw["data/raw<br/>handbook.md, faqs.md"] -->|"ingest"| idx
```

## RAG decision flow

```mermaid
flowchart TD
    q["Question"] --> route{"Personal data intent?"}
    route -->|"yes"| dbq["Approved DB query<br/>formatted answer, no LLM"]
    route -->|"no"| ret["Retrieve top 4 passages<br/>(cosine similarity)"]
    ret --> gate{"Top score >= 0.65?"}
    gate -->|"yes"| gen["LLM call<br/>passages in untrusted_context"]
    gate -->|"no"| band{"Score >= 0.60 and<br/>keyword match?"}
    band -->|"yes"| gen
    band -->|"no"| fb["Fallback answer<br/>with HR/IT contacts"]
    gen --> nf{"NOT_FOUND?"}
    nf -->|"yes"| fb
    nf -->|"no"| val{"Valid citation, supported<br/>numbers/emails, no leaks?"}
    val -->|"no"| fb
    val -->|"yes"| ans["Answer + cited sources only"]
```

## Components

| Component | Location | Responsibility |
|---|---|---|
| Frontend | `frontend/src/` | Dashboard, AI Assistant, checklist, leave and payroll, assets, support tickets |
| API and middleware | `backend/main.py`, `backend/routes/`, `backend/middleware/` | Endpoints, validation, request IDs, logging, safe JSON errors |
| Orchestrator | `backend/services/orchestrator.py`, `employee_query_router.py` | Route personal questions to approved DB functions, others to RAG |
| Ingestion | `backend/services/ingest.py` | Section-aware chunking (350 words, 40 overlap), embedding, FAISS index |
| Retrieval | `backend/services/retriever.py`, `embeddings.py` | Local embeddings, top-k search |
| Guardrails | `backend/services/guardrails.py` | Retrieval gate, context sanitising, output validation, cited-source mapping |
| LLM client | `backend/services/llm.py` | OpenAI-compatible client (Groq temporarily), grounded system prompt |
| Persistence | `backend/services/db.py`, `employee_db.py` | Chat history, tickets, checklist, employee data (PostgreSQL or SQLite) |
| Containers | `Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml` | Local frontend + backend + PostgreSQL stack |

## Deployment view (local Docker Compose)

- `frontend`: nginx on 127.0.0.1:8080, serves the build, proxies `/api/*` to `backend:8000`.
- `backend`: FastAPI on 127.0.0.1:8000, embedding model inside the image, FAISS index mounted read-only, logs on a named volume.
- `db`: PostgreSQL 16, named volume, initialised from `docker/postgres/`, not published to the host.
- Startup order via health checks; `restart: unless-stopped`.

## Planned Azure target (not implemented)

Azure OpenAI replaces Groq; hosting, managed PostgreSQL, secret storage (Key Vault / managed identity) and identity (for example Microsoft Entra ID) are to be confirmed once Azure access is available. See the migration section in the root [README](../README.md).

## Historical design

[architecture.png](architecture.png) shows the initial Day 31 design (Streamlit frontend, OpenAI, SQLite). It is superseded by the diagrams above and kept for reference only.
