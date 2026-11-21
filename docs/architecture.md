# Architecture: OnboardAI

Current architecture of the local implementation (21 November 2026), including local email/password authentication. Azure components are planned, not implemented.

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
    api --> sec["Security dependencies<br/>session, CSRF, own-employee, admin role"]
    sec --> edb
    raw["data/raw<br/>handbook.md, faqs.md"] -->|"ingest"| idx
```

## Authentication and request authorization

```mermaid
sequenceDiagram
    participant B as Browser (React)
    participant N as nginx / Vite proxy
    participant A as FastAPI
    participant D as Database
    B->>N: POST /api/auth/login {email, password}
    N->>A: POST /auth/login
    A->>A: rate-limit check (email, client IP)
    A->>D: load account by email
    A->>A: Argon2id verify (dummy hash if unknown)
    A->>D: insert session (SHA-256 of token, CSRF token, expiry)
    A-->>B: Set-Cookie onboardai_session (HttpOnly, SameSite=Strict) + {user, csrf_token}
    B->>A: GET /api/employees/EMP001 (cookie)
    A->>D: resolve session hash, check expiry and idle timeout
    A->>A: path employee == session employee? (else 403)
    A-->>B: 200 own profile
    B->>A: PATCH /api/employees/EMP001/checklist/1 (cookie + X-CSRF-Token)
    A->>A: CSRF token == session token? (else 403)
    A-->>B: 200 updated item
    B->>A: POST /api/auth/logout (cookie + X-CSRF-Token)
    A->>D: delete session
    A-->>B: cookie cleared
```

- Identity always comes from the server-side session; employee IDs in requests are only compared against it.
- Session tokens are 256-bit random values; only their SHA-256 hash is stored. Sessions expire after `SESSION_TTL_MINUTES` (8 h) or `SESSION_IDLE_MINUTES` (60 min) of inactivity.
- Roles: `employee` (own records only) and `admin` (`/ingest`, legacy checklist; no employee data unless linked).

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
| Frontend | `frontend/src/` | Login page, dashboard, AI Assistant, checklist, leave and payroll, assets, support tickets; CSRF token kept in memory |
| API and middleware | `backend/main.py`, `backend/routes/`, `backend/middleware/` | Endpoints, validation, request IDs, logging, safe JSON errors |
| Orchestrator | `backend/services/orchestrator.py`, `employee_query_router.py` | Route personal questions to approved DB functions, others to RAG |
| Ingestion | `backend/services/ingest.py` | Section-aware chunking (350 words, 40 overlap), embedding, FAISS index |
| Retrieval | `backend/services/retriever.py`, `embeddings.py` | Local embeddings, top-k search |
| Guardrails | `backend/services/guardrails.py` | Retrieval gate, context sanitising, output validation, cited-source mapping |
| LLM client | `backend/services/llm.py` | OpenAI-compatible client (Groq temporarily), grounded system prompt |
| Authentication | `backend/services/auth.py`, `auth_schema.py`, `backend/security.py`, `backend/routes/auth.py`, `backend/manage_accounts.py` | Argon2id passwords, server-side sessions, CSRF, login rate limiting, authorization dependencies, dev account provisioning |
| Persistence | `backend/services/db.py`, `employee_db.py` | Chat history, tickets, checklist, employee data, accounts and sessions (PostgreSQL or SQLite) |
| Containers | `Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml` | Local frontend + backend + PostgreSQL stack |

## Deployment view (local Docker Compose)

- `frontend`: nginx on 127.0.0.1:8080, serves the build, proxies `/api/*` to `backend:8000`.
- `backend`: FastAPI on 127.0.0.1:8000, embedding model inside the image, FAISS index mounted read-only, logs on a named volume.
- `db`: PostgreSQL 16, named volume, initialised from `docker/postgres/` (schema, synthetic data, authentication tables; no accounts), not published to the host.
- The backend trusts `X-Forwarded-For`/`-Proto` from nginx (`TRUST_PROXY_HEADERS=true`) for login rate limiting and the cookie `Secure` flag.
- Startup order via health checks; `restart: unless-stopped`.

## Planned Azure target (not implemented)

Azure OpenAI replaces Groq; hosting, managed PostgreSQL, HTTPS and secret storage (Key Vault / managed identity) are to be confirmed once Azure access is available. Local email/password authentication is implemented; an external identity provider (for example Microsoft Entra ID) is a possible later change, not current scope. See the migration section in the root [README](../README.md).

## Historical design

[architecture.png](architecture.png) shows the initial Day 31 design (Streamlit frontend, OpenAI, SQLite). It is superseded by the diagrams above and kept for reference only.
