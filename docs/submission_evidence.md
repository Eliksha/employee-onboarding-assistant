# OnboardAI - Submission Evidence

Consolidated, verified results for the final report (PDF) and presentation (PPT). Every figure below comes from a
recorded run; the source document is given for each section. Status as of **25 November 2026**, repository commit
`f69b3bc` (branch `dev`, CI run #9 passed). Continuous delivery is **implemented; runs #1-#3 stopped safely before any production change (causes fixed) and no release has completed yet** - this document
does not claim a CD release.

| | |
|---|---|
| Project | OnboardAI: RAG-Powered New Joiner Support Platform (EY GDS capstone, Generative AI for HR) |
| Live application | https://onboardai-eliksha-frontend-e4ehc5caahajdshh.southindia-01.azurewebsites.net (sign-in required) |
| Production images | `onboardai-backend` / `onboardai-frontend`, tag `78b80ee-202611241823` (deployed 25 Nov 2026) |
| LLM | Azure OpenAI, GPT-4.1 deployment (Responses API, `store=false`) |
| Data | Synthetic only (fictional company NovaTech Solutions, employees EMP001-EMP003) |

## 1. Problem, scope and success criteria

New joiners repeatedly ask HR and IT about leave, payroll, benefits, IT setup and policies; the answers are spread
across a long handbook and FAQs ([problem_statement.md](problem_statement.md)). OnboardAI answers from the approved
handbook with citations, refuses to guess, answers personal questions from the employee's own records, and gives each
signed-in employee a private onboarding workspace.

| Success criterion (problem statement) | Target | Verified result |
|---|---|---|
| In-scope questions answered correctly with a source | >= 80% | **100%**: 30/30 grounded handbook answers with correct citations (held-out set, GPT-4.1); 17/17 grounding cases (RAG evaluation) |
| Out-of-scope questions trigger the safe fallback | 100% | **100%**: 6/6 (held-out set) and 7/7 unknown-question cases (RAG evaluation) |
| Production answer latency | < 5 s | **4232 ms** for a grounded answer on Azure (production verification) |

## 2. Delivered features

| Feature | Implementation |
|---|---|
| AI Assistant (handbook Q&A) | RAG over `handbook.pdf` (canonical) and `faqs.md`; citations with section and page; cited sources only |
| Personal answers | deterministic router -> allow-listed database reads (checklist, leave, assets, tickets, profile, payroll calendar); no LLM, no generated SQL |
| Mixed questions | records part + handbook part in one answer and one saved message |
| Safety | retrieval gate (0.65, keyword-corroborated band 0.60-0.65), injection screening of retrieved text, output validation (citations, numbers, emails, secret/system-prompt leakage), refusal of other employees' data, safe fallback |
| Workspace | dashboard, onboarding checklist (15 tasks), leave and payroll, assets, support tickets, chat history |
| Feedback and escalation | rate answers; escalate to an HR/IT queue (`hr` role, status transitions, audit trail) |
| Security | Argon2id passwords, server-side sessions (HttpOnly, Secure, SameSite=Strict), CSRF tokens, login rate limiting (shared PostgreSQL table), per-employee authorization, least-privilege database roles with row-level security and a signed employee scope |

## 3. Automated testing

| Suite | Result | Date / source |
|---|---|---|
| Backend unit + integration (pytest, SQLite, LLM mocked) | **711 passed**, 0 failed (incl. the first 10 static CD security checks); the CD test file was then extended to 12 checks (12 passed), and CI run #9 ran the complete suite: passed | 25 Nov 2026, Python 3.12 Docker test image ([project_plan.md](project_plan.md), CD sections) |
| Live PostgreSQL security suite (roles, RLS, signed scope, isolation attacks, import role, migrations 007/008) | **133 passed** | 24 Nov 2026, disposable PostgreSQL 16 |
| Frontend (Node test runner, ESLint, Vite build) | **11 passed**, 0 lint problems, build OK | M5; re-run in every CI run |
| GitHub Actions CI (4 jobs: backend, PostgreSQL security, frontend, Docker build) | **passed** on runs #5 (`78b80ee`), #6 (`3c0b4df`), #7 (`df18ffd`), #8 (`6427fd7`), #9 (`f69b3bc`) | GitHub Actions |
| Held-out routing evaluation (deterministic, CI regression floor) | **62/62** | every CI run |
| Deployment-script validator (`Test-DeploymentScripts.ps1`) | 69 Azure CLI command lines, **0 failures** | 25 Nov 2026 |

## 4. AI quality evaluation (Azure OpenAI GPT-4.1)

### 4.1 RAG evaluation - [rag_eval_report.md](rag_eval_report.md) (24 Nov 2026)

| Category | Pass | Fail |
|---|---|---|
| A. Knowledge base / index availability | 6 | 0 |
| B. Retrieval relevance | 17 | 0 |
| C. Answer grounding (LLM) | 17 | 0 |
| D. Unknown-question handling (LLM) | 7 | 0 |
| E. Prompt-injection resistance (LLM) | 3 | 0 |
| **Total** | **50** | **0** |

Retrieval MRR (expected section): **0.971**. Index: 65 chunks (handbook.pdf 40, faqs.md 25), `BAAI/bge-small-en-v1.5`,
FAISS `IndexFlatIP`, top-k 4, threshold 0.65.

### 4.2 Held-out hybrid evaluation - [azure_eval_report.md](azure_eval_report.md) (24 Nov 2026)

62 held-out questions against the production images (HTTPS, App Service-like proxies, PostgreSQL 16 with TLS verify-full).

| Metric | Result |
|---|---|
| Routing accuracy (kind + intents + refusal flag) | 62/62 (100%) |
| Records answers correct (records + mixed) | 26/26 (100%) |
| Unauthorized questions refused | 8/8 (100%) |
| Answers containing another employee's data | 0 |
| Retrieval hit@k / MRR | 30/30 (100%) / 0.978 |
| Grounded handbook answers | 30/30 (100%) |
| False fallbacks on answerable questions | 0/30 |
| Citation hit / citation precision | 30/30 / 1.00 |
| Mixed answers fully correct | 10/10 (100%) |
| Out-of-scope questions answered with the fallback | 6/6 (100%) |
| Errors after retries | 0 |

## 5. Performance

| Measurement | Result | Context / source |
|---|---|---|
| Grounded GPT-4.1 answer, live production (Azure) | **4232 ms** (target < 5000 ms) | production verification, 25 Nov 2026 |
| Held-out evaluation latency, records route | p50 **55 ms**, p95 107 ms (n = 24) | production images, Azure-like stack ([azure_eval_report.md](azure_eval_report.md)) |
| Held-out evaluation latency, handbook route (GPT-4.1) | p50 **1706 ms**, p95 3040 ms, max 3385 ms (n = 28) | same |
| Held-out evaluation latency, mixed route | p50 **1546 ms**, p95 2189 ms (n = 10) | same |
| Held-out evaluation latency, all 62 questions | p50 **1250 ms**, p95 2582 ms | same |
| Load test (locust, 10 users, 60 s, records questions only) | 287 requests, **0 failures**, aggregate median 83 ms / p95 200 ms; records chat median 170 ms / p95 220 ms; ~4.9 req/s | local isolated stack, 23 Nov 2026 (historical; LLM excluded; not repeated on Azure) - [load_test_report.md](load_test_report.md) |

With n < 20 per route kind, p95 values are indicative.

## 6. Azure deployment evidence (25 November 2026)

### 6.1 Deployed infrastructure (South India)

| Component | Configuration |
|---|---|
| Frontend Web App (Linux, B1 plan) | only public endpoint; HTTPS only, TLS 1.2+, HSTS/CSP/X-Frame-Options/nosniff; proxies `/api/*` to the backend |
| Backend Web App (Linux, B1 plan) | **public network access disabled**; reachable only through a private endpoint (private DNS `privatelink.azurewebsites.net`); health check `/ready` |
| Virtual network | `appservice-subnet` (VNet integration of both apps, route all), `private-endpoint-subnet`, `postgres-subnet` |
| Azure Database for PostgreSQL Flexible Server 16 | VNet-injected, public access disabled, no firewall rules, TLS required (`require_secure_transport=on`, TLS >= 1.2) and verified by the backend (verify-full) |
| Azure Container Registry | admin user disabled; images pulled by the apps' system-assigned managed identities (AcrPull) |
| Azure OpenAI | GPT-4.1 deployment; only retrieved handbook passages and the question are sent (never employee records) |
| Hardening | SCM/FTP basic authentication disabled on both apps; FTPS disabled; database administrator password rotated after migration (unstored); the application uses least-privilege roles only |

### 6.2 Deployment steps executed

`05 discover -> 00 preflight -> 20 registry -> 30 images -> 40 App Service (harden) -> 15 network -> 10 database ->
50 settings -> 65 in-VNet migration -> 40 activation -> 45 private endpoint -> admin password rotation -> 70 verification`
(PowerShell scripts in `deploy/azure/`, dry run by default, existing resources reused).

### 6.3 Data migration (in-VNet, over an authenticated SSH tunnel)

| Result | Value |
|---|---|
| Transport | TLS 1.3, certificate and host-name verification (verify-full), inside the VNet; no public database access at any time |
| Integrity | **12/12 table fingerprints identical** (per-table row count + MD5 over all rows, `COLLATE "C"` ordering) |
| Schema | migrations 008 and 005 applied; roles, RLS and signed scope verified; application-role startup checks passed |
| Duration | 525 s (successful attempt) |
| Earlier attempts | 1: collation-dependent fingerprint mismatch -> automatic rollback, fixed with `COLLATE "C"`; 2-3: container startup backoff on the empty database -> fixed with one restart and a bounded readiness loop |
| Cleanup (verified in Azure) | temporary SSH key removed, SCM basic auth disabled again and publishing password regenerated, temporary SCM rule removed, production image restored, local key pair and dump securely deleted |

### 6.4 Production verification - `deploy/azure/70-Verify-Deployment.ps1` (25 Nov 2026): **17/17 passed**

| # | Public checks (8/8) | # | Signed-in checks (9/9) |
|---|---|---|---|
| 1 | frontend `/healthz` 200 | 9 | sign-in; cookie Secure + HttpOnly + SameSite=Strict |
| 2 | SPA 200 with HSTS, CSP self-only, X-Frame-Options DENY, nosniff | 10 | own profile readable |
| 3 | API health 200, database ok | 11 | own checklist readable |
| 4 | API docs not public (404) | 12 | another employee's data refused (403) |
| 5 | readiness details not public (404) | 13 | grounded GPT-4.1 answer citing handbook.pdf page 3 in 4232 ms |
| 6 | employee data requires sign-in (401) | 14 | out-of-scope question -> safe fallback |
| 7 | unknown account -> generic 401 | 15 | chat history readable |
| 8 | backend not usable directly (403) | 16 | sign-out |
| | | 17 | session ended (401 after sign-out) |

Additional production network checks: backend main and SCM sites return 403 from the internet; the frontend reaches
the backend only via the private endpoint (frontend `/api/health` 200 with `database: ok`).

## 7. Security evidence

| Area | Evidence |
|---|---|
| Secrets | none in the repository or images: repository scan of all tracked files against every secrets-file value and Azure identifier - 0 hits (25 Nov 2026); Trivy secret scan of both production images (all severities) - 0 |
| Image vulnerabilities | Trivy: 0 fixable HIGH/CRITICAL in both production images (24-25 Nov 2026) |
| Data isolation | session-derived identity, 403 for other employees, refusal in chat (8/8), PostgreSQL row-level security with HMAC-signed employee scope (133-test live suite) |
| Prompt injection | retrieved-text screening + output validation; 3/3 injection cases resisted (GPT-4.1) |
| Network | private database (VNet injection), backend behind private endpoint with public access disabled, frontend the only public entry |
| Identity for delivery | GitHub OIDC -> user-assigned managed identity with `AcrPush` (registry) and `Website Contributor` (two Web Apps) only; no stored Azure credential |

## 8. CI/CD

| Item | Status |
|---|---|
| CI (`.github/workflows/ci.yml`) | **operational**: every push and pull request; last 5 runs passed (#5-#9) |
| CD (`.github/workflows/cd.yml`) | **implemented and validated; first runs #1-#3 (25 Nov 2026) stopped safely before any production change; both causes - GitHub environment setup and the OIDC subject format - are fixed; no successful release yet**: manual, `main` only, CI-gated, approval environment `production` (configured by the owner: required reviewer, admin bypass disabled, `main` only), index rebuild + retrieval validation, separate Trivy vulnerability and secret scans, OIDC, immutable attempt-unique tags with digests, ARM deployment, health + configuration-drift + 8 public checks, verified automatic rollback |
| CD validation performed | actionlint + shellcheck clean; 12 static CD security tests; verification script 8/8 against production on PowerShell 7.4 and 5.1; index gate 6/6 + 17/17; Trivy and smoke checks pass on the current production images |

*To be added after the first CD release: run number, image tags and digests, verification result.*

## 9. Limitations (honest assessment)

- Single-instance B1 App Service plan: no deployment slots (a release restarts the apps briefly), no autoscaling.
- Secrets are App Service application settings (encrypted at rest); Azure Key Vault references are a planned improvement.
- Local email/password accounts only (no MFA, password reset or Entra ID); synthetic data only.
- Rule-based router: unusual phrasings may fall back to the handbook; grounding checks are lexical.
- Load test was local and records-only; no Azure load test was run.
- HR/IT escalation queue is API-only (no HR user interface); no email or ticketing integration.
- Continuous delivery has not yet performed a release.

## 10. Evidence sources

| Evidence | Location |
|---|---|
| Step-by-step progress, decisions, all verification logs | [project_plan.md](project_plan.md) |
| Architecture (diagram, network, CI/CD) | [architecture.md](architecture.md), [architecture-final.png](architecture-final.png) |
| RAG / held-out evaluations | [rag_eval_report.md](rag_eval_report.md), [azure_eval_report.md](azure_eval_report.md) |
| Load test (historical) | [load_test_report.md](load_test_report.md) |
| Azure deployment runbook and scripts | [../deploy/azure/README.md](../deploy/azure/README.md) |
| Operations runbook | [runbook.md](runbook.md) |
