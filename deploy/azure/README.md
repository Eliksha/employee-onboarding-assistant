# OnboardAI - Azure deployment runbook

Windows PowerShell 5.1+, Azure CLI 2.91+, Docker Desktop. Every script is a **dry run** (prints the redacted `az`
commands) unless `-Execute` is passed. Secrets are read from the external secrets file only; nothing secret is printed
or written to the repository. Existing resources are **reused** (create only what is missing).

Target: South India; shared Linux App Service plan (B1); Web Apps `onboardai-eliksha-backend` and
`onboardai-eliksha-frontend`; ACR `onboardaielikshaacr` (Basic, admin disabled, TenantReuse login server); Azure
Database for PostgreSQL Flexible Server 16 (private, VNet-injected); Azure OpenAI GPT-4.1. FAISS index and handbook PDF
are bundled in the backend image.

**Status: deployed and verified on 25 November 2026** (production verification 17/17; later CD #4 release 50/51 over 3 runs). Executed order:
`05 -> 00 -> 20 -> 30 -> 40 (-HardenOnly) -> 15 -> 10 -> 50 -> 65 -> 40 -> 45 -> admin password rotation -> 70`.

Deployed network:

| Resource | Configuration |
|---|---|
| `onboardai-vnet` (10.0.0.0/16) | reused (owner-created) |
| `postgres-subnet` (10.0.1.0/24) | delegated to PostgreSQL; hosts the VNet-injected server |
| `appservice-subnet` (10.0.2.0/24) | delegated to `Microsoft.Web/serverFarms`; regional VNet integration of both apps, route all |
| `private-endpoint-subnet` (10.0.3.0/24) | backend private endpoint `onboardai-eliksha-backend-pe` (group `sites`) |
| Private DNS | PostgreSQL zone (portal) and `privatelink.azurewebsites.net` (step 45), both linked to the VNet |
| Backend | `publicNetworkAccess = Disabled`: main and SCM sites only through the private endpoint (403 from the internet) |
| Frontend | the only public endpoint; SCM default deny |
| Both apps | SCM/FTP basic auth disabled, FTPS disabled, HTTPS only, TLS 1.2+, managed-identity image pull |

## 0. Validate locally (no Azure access)

```powershell
.\deploy\azure\Test-DeploymentScripts.ps1      # syntax, dry run of every step, every az flag vs. az --help, redaction
```

## 1. Sign in and discover (read-only)

```powershell
az login
.\deploy\azure\05-Discover-Resources.ps1 -BackendApp onboardai-eliksha-backend -AcrName onboardaielikshaacr [-PgServer <name>]
# writes deploy\azure\config.psd1 (git-ignored): resource group, region, plan, ACR login server, PostgreSQL FQDN/admin, image tag
.\deploy\azure\00-Preflight.ps1 -Execute       # providers, policy assignments, ARM validate of all resource types (creates nothing)
```

Add to the secrets file before step 3/6: `AZURE_PG_ADMIN_PASSWORD` (PostgreSQL administrator).

## 2. Infrastructure (reuse or create; review the dry run first)

```powershell
.\deploy\azure\10-Provision-Database.ps1            # dry run
.\deploy\azure\10-Provision-Database.ps1 -Execute   # reuse server; require_secure_transport=on, TLS>=1.2; database onboardai
.\deploy\azure\20-Provision-Registry.ps1 -Execute   # reuse ACR; ensure admin user disabled
```

## 3. Images

```powershell
.\deploy\azure\30-Publish-Images.ps1 -BuildLocal    # build + secret scan locally
.\deploy\azure\30-Publish-Images.ps1 -Execute       # az acr login (Entra ID) + push both images (tag = commit-timestamp)
```

## 4. Web Apps

```powershell
.\deploy\azure\40-Provision-AppService.ps1 -Execute # reuse plan/backend app, create frontend app if missing; managed identity + AcrPull,
                                                    # HTTPS only, TLS 1.2, FTPS/basic auth off, Always On, health checks /ready, /healthz
```

## 5. PRIVATE database (VNet-only) and migration through the App Service SSH tunnel

The database has **no public access and no firewall rules**. Order (after the policy exception for
Microsoft.Network/privateDnsZones and privateDnsZones/virtualNetworkLinks):

```powershell
.\deploy\azure\15-Provision-Network.ps1 -Execute      # REUSES onboardai-vnet + postgres-subnet + private DNS (portal); re-delegates appservice-subnet (Microsoft.Web),
                                                      # regional VNet integration of both apps (route all)
.\deploy\azure\10-Provision-Database.ps1 -Execute     # REUSES the portal server onboardai-eliksha-db (creates only if absent); refuses public
.\deploy\azure\50-Configure-Apps.ps1 -Execute         # PG_HOST = private FQDN; no database firewall rules
.\deploy\azure\65-Migrate-Database-InVNet.ps1 -Execute
```

`65-Migrate-Database-InVNet.ps1`:
1. Local, read-only on the source: one-time ed25519 key pair (current user only), `pg_dump -Fc` (no sessions/rate-limit rows),
   restore list without RLS policies, source fingerprints.
2. Builds and pushes the TEMPORARY image `<tag>-migrate` (production image + key-only sshd + PostgreSQL client), sets
   `MIGRATION_SSH_AUTHORIZED_KEY` (public key) on the backend, switches the backend to it (maintenance 503, app not started)
   and opens `az webapp create-remote-connection` (authenticated SCM tunnel on 127.0.0.1).
3. Uploads over scp and runs `onboardai-in-vnet-migrate migrate` with the secrets on stdin: refuses a non-empty target,
   TLS verify-full, one-transaction restore, identical fingerprints, 008, 005, verify 007/008/005, app-role startup checks,
   automatic rollback to an empty database on any error.
4. Always: shreds the uploads, closes the tunnel (whole process tree), deletes the key setting, switches back to the
   PRODUCTION image (no SSH server), disables SCM basic auth again and regenerates the publishing password, removes the
   temporary SCM operator rule, deletes the local key pair and dump. Then rotate the PostgreSQL administrator password.

The CLI tunnel authenticates with publishing credentials, so `-AllowTemporaryScmBasicAuth -ScmAllowIp <operator IP>`
(owner approval) enables SCM basic auth for the migration window only, with the SCM site restricted to the operator IP.
The script stops before any Azure change if SCM basic auth is off and the switch is not given. All configuration is
applied before ONE stop/start of the backend (each settings change restarts the site), then a bounded 15-minute
readiness loop waits for the SSH server.

Production run (25 Nov 2026): attempt 4 succeeded in 525 s - TLS 1.3 verify-full, 12/12 table fingerprints identical,
008 and 005 applied, startup checks passed. Earlier attempts: a collation-dependent fingerprint (fixed with
`COLLATE "C"`; automatic rollback worked) and startup backoff of the production image on the empty database (fixed by
the single restart and the readiness loop). Cleanup verified in Azure afterwards.

Rollback of the migration: `65-Migrate-Database-InVNet.ps1 -Execute -Rollback` (empty target database; source unchanged).
SSH security: ed25519 public key only, no passwords, no root, only `appuser`, no TCP/agent/X11 forwarding (database access
through SSH is refused), sshd only in the temporary image, port 2222 only through the authenticated SCM tunnel.

Rehearsed locally (Azure-like private target, non-superuser admin, TLS required): migration 25 s, 12/12 fingerprints
identical; non-empty target refused; rollback to empty; re-migration; production image ready on the migrated database;
0 secrets in container logs, process environments or files. `60-Migrate-Database.ps1` (public firewall variant) refuses to
run against Azure and is kept for local rehearsals only.

## 6. Settings and network (run before 65; repeat after the frontend app exists)

```powershell
.\deploy\azure\50-Configure-Apps.ps1 -Execute
# backend: PG (app + reader roles, scope secret), Azure OpenAI, BACKEND_PROXY_SECRET, TRUSTED_PROXY_HOPS=3
# frontend: BACKEND_ORIGIN/HOST (discovered host name), same proxy secret
# backend access restriction: integration subnet only (service endpoint, default deny); no IP rules;
# PostgreSQL is private (no firewall rules); restart both
```

## 6b. Backend private endpoint (after the migration and step 40)

```powershell
.\deploy\azure\45-Private-Endpoint.ps1 -Execute
# removes the unused delegation of private-endpoint-subnet; private DNS zone privatelink.azurewebsites.net + VNet link;
# private endpoint (group sites) + DNS zone group; checks the connection is Approved; backend publicNetworkAccess=Disabled
az webapp restart --resource-group <rg> --name onboardai-eliksha-frontend   # nginx re-resolves the backend host (private IP)
```

Run it after step 65: the migration tunnel uses the backend's public SCM site. Rollback: set the backend's
`publicNetworkAccess` back to `Enabled` (the subnet access restriction still applies), then delete the endpoint.

## 7. Verify

```powershell
$env:VERIFY_PW = '<employee password>'
.\deploy\azure\70-Verify-Deployment.ps1 -BaseUrl https://<frontend host> -BackendUrl https://<backend host> -EmployeeEmail <email> -PasswordEnv VERIFY_PW
Remove-Item Env:VERIFY_PW
```

17 checks: 8 public (frontend health, HSTS/CSP/X-Frame-Options/nosniff, API health with database, docs and readiness
hidden, sign-in required, generic login error, backend not usable directly) and 9 signed-in (secure cookie, own data,
other employees refused, GPT-4.1 answer citing handbook.pdf p. 3 within 5 s, fallback, history, sign-out).
**Production: first release 17/17 (grounded answer 4232 ms); CD #4 release 50/51 over 3 runs (latency 5086 / 2135 / 1752 ms; the only failure was run 1's latency).**

Trusted proxy hops (rate limiting per client): after deployment, 20 failed sign-ins from one network must block that
client only, not a second client on another network. If a second client is also blocked, the hop count is too low.

## Rollback

```powershell
.\deploy\azure\90-Rollback.ps1 -PreviousTag <tag> -Execute -VerifyBaseUrl https://<frontend host>   # previous images, restart, verify
.\deploy\azure\90-Rollback.ps1 -PreviousTag <tag> -ShowDatabaseRestore -RestoreTime <UTC>            # prints PITR command (not run)
```

Database changes are additive (008); data recovery uses Azure point-in-time restore into a new server (needs approval).

## Administrator password

Rotated after the migration to a random value that was not stored; the application does not use the administrator
login. When administrator access is needed, reset it and keep the new value in the external secrets file only:
`az postgres flexible-server update --resource-group <rg> --name <server> --admin-password <new value>`.

## 8. Continuous delivery (GitHub Actions)

**Status: operational** - first successful, verified release: CD run #4 (deployed digests verified, configuration unchanged, 8/8 public checks; post-release verification 50/51 over 3 runs). Runs #1-#3 stopped safely before any production change (GitHub environment setup, OIDC subject format; both fixed). CD status history
(recorded in `docs/project_plan.md`). Workflow: [`.github/workflows/cd.yml`](../../.github/workflows/cd.yml); helper:
[`cd-release.sh`](cd-release.sh).

| Job | Runs | What it does |
|---|---|---|
| `gate` | always | main branch only; input `confirm` must be `deploy`; a successful CI run (push to main) must exist for the exact commit |
| `build` | no Azure access | rebuilds the FAISS index from `data/raw` (`python -m backend.services.ingest`), validates it (`scripts.rag_eval --no-llm`: 6 index + 17 retrieval checks), builds both images from `deploy/azure/*.Dockerfile` (the backend build re-verifies index, model and document hashes), smoke checks (non-root, no dev tools, no env/dump/db/key files; a failed check execution fails the job), two separate Trivy scans pinned by digest - vulnerabilities (fixable HIGH/CRITICAL fail) and secrets (any secret of any severity fails) - and exports the scanned images |
| `release` | environment `production` (required reviewer) | loads exactly the scanned images (image ids compared), OIDC sign-in, records the current images and a configuration snapshot (rollback point), checks production is healthy, pushes under the unique tag `<sha12>-<run id>-<run attempt>` (computed in the release attempt, never overwritten) and records digests, deploys backend then frontend (`az webapp sitecontainers update`, ARM only), bounded health checks (frontend `/healthz` 200 and `/api/health` HTTP 200 with JSON `status` ok and `database` ok, 3 consecutive), proves nothing but the image changed, runs the 8 public checks of `70-Verify-Deployment.ps1`. If anything fails **after a production image update was attempted** (including a failed or partial backend update), both apps are rolled back to the recorded images and the rollback is verified: exact previous image references, configuration identical to the pre-release snapshot, health, and the 8 public checks. A failure before any update leaves production untouched (no rollback) |

Concurrency group `onboardai-production` (no parallel releases, a running release is never cancelled). Database
migrations are not part of CD (step 65, manual, inside the VNet).

**Identity (created 25 Nov 2026):** user-assigned managed identity `onboardai-github-cd` in the resource group, federated
credential `github-production` (issuer `https://token.actions.githubusercontent.com`, subject
`repo:<owner>/<repo>:environment:production`, audience `api://AzureADTokenExchange`). Role assignments, each on one
resource only: `AcrPush` on the registry, `Website Contributor` on the backend Web App, `Website Contributor` on the
frontend Web App. No subscription, resource-group, database or network role; no client secret; the registry admin
user, SCM/FTP basic auth and publish profiles stay disabled; app settings are never read or written.

**GitHub configuration (repository Settings -> Environments -> `production`):** required reviewer (the owner), deployment
branches: `main` only. Environment variables (identifiers, not secrets): `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
`AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `AZURE_ACR_LOGIN_SERVER`, `BACKEND_APP`, `FRONTEND_APP`. Optional,
only with the owner's approval: variable `VERIFY_EMPLOYEE_EMAIL` + secret `VERIFY_EMPLOYEE_PASSWORD` for a dedicated
test account - otherwise the 9 signed-in checks are run by the owner after each release (section 7).

**Release:** Actions -> CD -> Run workflow -> branch `main`, `confirm` = `deploy` -> approve the `production`
deployment after `build` has passed. Evidence: the run's job summary (commit, tags, digests, previous images, rollback
outcome; identifiers masked).

**Rollback:** automatic on failure (both apps, re-verified). Manual, to any earlier image tag:
`.\deploy\azure\90-Rollback.ps1 -PreviousTag <tag> -Execute -VerifyBaseUrl https://<frontend host>`.

Limitations: the B1 plan has no deployment slots (each release restarts the apps briefly; no blue/green); the
registry must keep public network access for GitHub-hosted runners (Basic tier, Entra ID authentication only); health
checks cannot read the running image version, so verification is behavioural (health, public checks, configuration
snapshot); the vulnerability gate can block a release when a new fixable HIGH/CRITICAL CVE is published (rebuild picks
up base-image fixes).
