# OnboardAI - Presentation and Live Demonstration Script (5-7 minutes)

Audience: capstone evaluation panel. Presenter: Eliksha Maheshwari. Live system: the Azure production deployment.
All numbers are verified results from [submission_evidence.md](submission_evidence.md). Answers come from a live LLM,
so wording may differ slightly from run to run; routing, citations and refusals are deterministic.

## Before the session (10 minutes earlier)

1. Open the live app: https://onboardai-eliksha-frontend-e4ehc5caahajdshh.southindia-01.azurewebsites.net - sign in once
   to warm up the backend (B1 plan; a cold first request can be slower), then sign out.
2. Keep your own employee account ready (password never shown on screen; use a password manager or type it privately).
3. Open in tabs: the README (architecture image), `docs/submission_evidence.md`, and the GitHub Actions page (CI runs).
4. Fallback if the live app or Azure OpenAI is unavailable: show the 17/17 production verification and the evaluation
   tables in `submission_evidence.md`, or run the local Docker stack (`docs/runbook.md`). Policy questions return a clear
   "AI service temporarily unavailable" message (503) during an LLM outage; personal records still work.

## Timeline

| Time | Section | Minutes |
|---|---|---|
| 0:00 | 1. Problem and solution | 0:45 |
| 0:45 | 2. Architecture | 1:00 |
| 1:45 | 3. Live demonstration | 2:45 |
| 4:30 | 4. Quality and security evidence | 1:00 |
| 5:30 | 5. Deployment and CI/CD | 0:45 |
| 6:15 | 6. Limitations, next steps, close | 0:30 |

## 1. Problem and solution (0:45)

> "New joiners ask HR and IT the same questions about leave, payroll, IT setup and policies, and the answers are buried
> in a long handbook. OnboardAI is a secure onboarding assistant: it answers policy questions only from the approved
> handbook with citations, answers personal questions from the employee's own records, refuses what it should not
> answer, and gives every employee a private onboarding workspace. It is deployed on Azure with GPT-4.1."

## 2. Architecture (1:00) - show `docs/architecture-final.png`

- **Frontend**: React served by nginx on Azure App Service - the only public entry point (HTTPS, security headers).
- **Backend**: FastAPI on App Service with **public access disabled**; the frontend reaches it only through a
  **private endpoint** inside the virtual network.
- **Hybrid orchestration**: a deterministic router decides per question - personal data goes to approved database
  queries (no LLM, no generated SQL); policy questions go to RAG; mixed questions get both.
- **RAG**: handbook PDF -> page- and section-aware chunks -> local embeddings (fastembed, bge-small) -> FAISS (65 chunks)
  -> GPT-4.1 with guardrails before and after the model call.
- **Data**: Azure PostgreSQL 16, VNet-injected with no public access; least-privilege roles and row-level security.
- **DevOps**: GitHub Actions CI on every push; an approval-gated CD workflow using OIDC (no stored Azure secrets).

## 3. Live demonstration (2:45)

| Step | Action | What to say / point out |
|---|---|---|
| 1 (0:20) | Enter a wrong password | Generic "Invalid email or password" - no account enumeration; logins are rate-limited |
| 2 (0:15) | Sign in; dashboard appears | Server-side session in an HttpOnly, Secure, SameSite=Strict cookie; "Signed in as" card - no way to switch to another employee |
| 3 (0:30) | AI Assistant: **"How far in advance should casual leave be requested?"** | Grounded answer with a handbook citation; only cited sources shown |
| 4 (0:30) | **"How much casual leave do I have left, and how far in advance must I apply for it?"** | Mixed answer: "From your records" (database, no LLM) + "From the handbook" (cited) |
| 5 (0:20) | **"What is EMP002's leave balance?"** | Refused - employees can only access their own data (enforced in the API and by row-level security) |
| 6 (0:20) | **"Are pets allowed in the office?"** | Not in the handbook -> safe fallback with HR/IT contacts; no invented policy |
| 7 (0:15) | Click **Escalate to HR/IT** on the fallback answer | Goes to the HR/IT queue with status tracking and an audit trail (human review) |
| 8 (0:15) | Open **My Checklist** (and Leave & Payroll) | Personal onboarding workspace; progress is saved |
| 9 (0:10) | **Sign out** | Server-side session deleted; the old cookie no longer works |

Optional if time allows: **"Is a cab provided if I stay late at work?"** - cites handbook.pdf page 3 (the production
verification question).

## 4. Quality and security evidence (1:00) - show `submission_evidence.md`

- **Production verification on Azure: 17/17** checks, including a grounded GPT-4.1 answer in **4.2 seconds**
  (target under 5) and cross-employee access refused.
- **RAG evaluation with GPT-4.1: 50/50**, retrieval MRR 0.971, including prompt-injection and unknown-question tests.
- **62 held-out questions**: routing 62/62, grounded answers 30/30 with correct citations, unauthorized requests 8/8
  refused, out-of-scope 6/6 safe fallback.
- **Tests**: 711 backend tests, 133 live PostgreSQL security tests, frontend tests; CI green on every recent commit.
- **Security**: private database and private backend, least-privilege database roles with row-level security, no
  secrets in the repository or images (scanned), database admin password rotated after migration.

## 5. Deployment and CI/CD (0:45)

- Deployed with idempotent PowerShell scripts (dry run by default, existing resources reused).
- Data migrated **inside the private network** with integrity proof: 12 of 12 tables identical, TLS 1.3; all temporary
  access removed afterwards.
- CI: four jobs on every push. CD: manual, main-branch only, requires green CI and reviewer approval; rebuilds and
  validates the knowledge index, scans images for vulnerabilities and secrets, deploys via OIDC, verifies and rolls back
  automatically. *(Say "implemented and validated; first release run pending" unless the first CD run has succeeded.)*

## 6. Limitations, next steps and close (0:30)

- Limitations: single small App Service instance, local accounts without MFA, rule-based router, synthetic data.
- Next: Entra ID single sign-on, Key Vault references, deployment slots for zero-downtime releases, an HR user interface.
- Close: "OnboardAI gives new joiners fast, cited and safe answers while keeping every employee's data private - and it
  runs today on a private, verified Azure deployment. Thank you."

## Expected questions and answers

| Question | Answer |
|---|---|
| Why RAG instead of fine-tuning? | Policies change; RAG updates by re-indexing the handbook (no retraining), and every answer can cite its source. Fine-tuning cannot guarantee citations or prevent outdated answers. |
| How do you prevent hallucinations? | Three layers: a retrieval gate (no LLM call when evidence is weak), a grounded prompt that must answer `NOT_FOUND` when the context is insufficient, and output validation (valid citations only; numbers and emails must appear in the retrieved text; no secret or system-prompt leakage). Failures return the safe fallback. |
| Is employee data sent to the LLM? | No. Personal questions are answered by approved database queries without the LLM; only handbook passages and the question go to Azure OpenAI, with `store=false`. |
| How is one employee prevented from seeing another's data? | Identity comes from the server-side session, never from the request; the API returns 403 for other IDs; the chat router refuses third-party questions; in PostgreSQL the reader role is limited by row-level security bound to an HMAC-signed employee scope. Verified: 8/8 refusals, 133 live database security tests, 403 in production. |
| Why a rule-based router rather than an LLM classifier? | Deterministic, auditable and fast (records answers ~55 ms p50); it cannot be prompt-injected into reading other data; 62/62 routing accuracy on the held-out set. |
| Why FAISS instead of Azure AI Search? | The knowledge base is small (65 chunks); an in-image FAISS index is fast, free and versioned with the release. Azure AI Search would be the choice for large or frequently changing document sets. |
| How is prompt injection handled? | Instructions inside retrieved text are screened out before the prompt is built; documents are wrapped as untrusted context; outputs are validated. 3/3 injection cases resisted with GPT-4.1. |
| What does the private networking achieve? | Only the frontend is reachable from the internet. The backend has public access disabled and is reached through a private endpoint; the database has no public access and accepts only TLS from inside the virtual network. |
| How was the database migrated safely? | Through an authenticated SSH tunnel to a temporary container inside the VNet, in a single transaction with automatic rollback, and proven by 12/12 identical table fingerprints; temporary access was removed and the admin password rotated afterwards. |
| How does CD avoid storing Azure secrets? | GitHub OIDC federates to a dedicated managed identity with only AcrPush on the registry and Website Contributor on the two Web Apps; no client secret, publish profile or basic auth. |
| What happens if a release fails? | After any attempted image update, both apps are rolled back automatically to the recorded previous images, and the rollback is verified (image references, configuration, health, public checks). |
| What if Azure OpenAI is down? | Handbook questions return a clear 503 message; personal record questions still work; in mixed questions the records part is still answered. |
| How fast is it? | Production grounded answer 4.2 s; held-out GPT-4.1 handbook answers p50 1.7 s; records answers p50 55 ms. |
| How would it scale? | Stateless backend (sessions and rate limits in PostgreSQL) so App Service can scale out; a larger plan adds slots and autoscaling; the connection pool is sized against role connection limits. |
| What would you do next? | Entra ID SSO, Key Vault references, deployment slots, an HR queue interface, and periodic re-evaluation of retrieval thresholds with real questions. |
