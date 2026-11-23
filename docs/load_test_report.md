# Load Test Report (M3)

Date: 2026-11-23 | Commit: `6481b86` plus uncommitted M3 changes | Tool: locust 2.47.0 (`tests/load/locustfile.py`)

## Environment

| Item | Value |
|---|---|
| Runner | `bash tests/load/run_isolated_load_test.sh` (Git Bash on Windows Server 2022) |
| Host | 8 CPUs, 16 GB RAM, Docker Engine 29.8.2 (linux/amd64 VM); locust ran on the same host |
| Backend | Image built from the working tree (`onboardai-backend:m3-isolated`, Python 3.12, pinned requirements), one uvicorn process, as `onboardai_app` + `onboardai_reader` with the signed employee scope and row-level security |
| Database | Temporary PostgreSQL 16 (`postgres:16-alpine`) seeded only from `docker/postgres` (synthetic data); migration 005 applied with random credentials |
| Isolation | Own network, containers and image, all removed afterwards; the running Docker stack and its data were not used |
| Load profile | 10 users, spawn rate 2 users/s, 60 s, think time 1-3 s per user; each user signs in once (synthetic EMP001 account) |
| Task mix (weights) | records chat 3, checklist 3, leave balances 2, payroll calendar 1, history 1, health 1 |

Handbook (LLM) questions are excluded on purpose: they would measure the external Groq service and its rate limits, not this application. Records chat still exercises routing, the reader role, scope signing, RLS and one chat-history write per request. Handbook latency is measured separately in `docs/hybrid_eval_report.md`.

## Results (locust CSV, `loadtest_stats.csv`)

| Endpoint | Requests | Failures | Median ms | p95 ms | p99 ms | Max ms | Req/s |
|---|---|---|---|---|---|---|---|
| POST /auth/login | 10 | 0 | 240 | 350 | 350 | 354 | 0.17 |
| POST /chat (records) | 70 | 0 | 170 | 210 | 270 | 267 | 1.21 |
| GET /employees/[id]/checklist | 70 | 0 | 78 | 100 | 210 | 213 | 1.21 |
| GET /employees/[id]/leave-balances | 48 | 0 | 80 | 110 | 130 | 129 | 0.83 |
| GET /employees/payroll/calendar | 25 | 0 | 39 | 56 | 68 | 68 | 0.43 |
| GET /health | 24 | 0 | 19 | 26 | 28 | 28 | 0.41 |
| GET /history?limit=20 | 34 | 0 | 72 | 87 | 90 | 90 | 0.59 |
|  **All requests** | 281 | 0 | 81 | 200 | 270 | 354 | 4.84 |

Percentiles are locust's approximations. The console summary printed at shutdown counted 284 requests (also 0 failures); the CSV above (281) was written a moment earlier, before the last in-flight requests completed.

Additional observations from the same run:
- 0 failed requests, 0 HTTP 5xx responses and 0 tracebacks in the backend log.
- 0 occurrences of any generated password, scope secret or login password in the backend log.
- Container resources after the run: backend about 0.2% CPU and 275 MiB, database about 37 MiB (idle snapshots before and after; peak usage during the run was not sampled).

## Interpretation and limitations

- At about 5 requests/s from 10 concurrent users the stack showed no errors; records chat had a 170 ms median and 210 ms p95; every endpoint's p95 was at or below 350 ms.
- This is a small smoke-level load test, not a capacity test: one run, one host, client and server sharing the same machine, short duration, synthetic data and a single test account.
- Not measured: higher concurrency, sustained load, LLM-backed questions under load, multiple backend workers, or behaviour behind nginx.
- Reproduce: `bash tests/load/run_isolated_load_test.sh loadtest-output` (results in `loadtest-output/`, git-ignored). Tunables: `USERS`, `SPAWN_RATE`, `DURATION`, `PORT`.
