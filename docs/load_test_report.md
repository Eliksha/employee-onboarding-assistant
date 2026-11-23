# Load Test Report (M3, re-run in M4)

Date: 2026-11-23 | Latest run: M4 working tree on commit `7e2e866` (PDF index mounted read-only) | Tool: locust 2.47.0 (`tests/load/locustfile.py`)

## Environment

| Item | Value |
|---|---|
| Runner | `bash tests/load/run_isolated_load_test.sh` (Git Bash on Windows Server 2022) |
| Host | 8 CPUs, 16 GB RAM, Docker Engine 29.8.2 (linux/amd64 VM); locust ran on the same host |
| Backend | Image built from the working tree (`onboardai-backend:m3-isolated`, Python 3.12, pinned requirements, PDF index mounted read-only via `INDEX_SRC`), one uvicorn process, as `onboardai_app` + `onboardai_reader` with the signed employee scope and row-level security |
| Database | Temporary PostgreSQL 16 (`postgres:16-alpine`) seeded only from `docker/postgres` (synthetic data); migration 005 applied with random credentials |
| Isolation | Own network, containers and image, all removed afterwards; the running Docker stack and its data were not used |
| Load profile | 10 users, spawn rate 2 users/s, 60 s, think time 1-3 s per user; each user signs in once (synthetic EMP001 account) |
| Task mix (weights) | records chat 3, checklist 3, leave balances 2, payroll calendar 1, history 1, health 1 |

Handbook (LLM) questions are excluded on purpose: they would measure the external Groq service and its rate limits, not this application. Records chat still exercises routing, the reader role, scope signing, RLS and one chat-history write per request. Handbook latency is measured separately in `docs/hybrid_eval_report.md`.

## Results - M4 re-run (locust CSV, `loadtest_stats.csv`)

| Endpoint | Requests | Failures | Median ms | p95 ms | p99 ms | Max ms | Req/s |
|---|---|---|---|---|---|---|---|
| POST /auth/login | 10 | 0 | 210 | 290 | 290 | 289 | 0.17 |
| POST /chat (records) | 88 | 0 | 170 | 220 | 240 | 237 | 1.49 |
| GET /employees/[id]/checklist | 63 | 0 | 81 | 100 | 130 | 135 | 1.07 |
| GET /employees/[id]/leave-balances | 55 | 0 | 78 | 97 | 100 | 100 | 0.93 |
| GET /employees/payroll/calendar | 29 | 0 | 41 | 66 | 81 | 81 | 0.49 |
| GET /health | 25 | 0 | 18 | 29 | 43 | 43 | 0.42 |
| GET /history?limit=20 | 17 | 0 | 69 | 96 | 96 | 96 | 0.29 |
|  **All requests** | 287 | 0 | 83 | 200 | 250 | 289 | 4.87 |

M3 run (same profile, Markdown index): 281 requests, 0 failures, aggregate median 81 ms / p95 200 ms, records chat median 170 ms / p95 210 ms. M4 run: 287 requests, 0 failures, aggregate median 83 ms / p95 200 ms, records chat median 170 ms / p95 220 ms - no measurable change.

Additional observations (M4 run): 0 failed requests, 0 HTTP 5xx responses and 0 tracebacks in the backend log; 0 occurrences of any generated password, scope secret or login password in the backend log; an in-container index rebuild was refused by the read-only mount and the active index version stayed unchanged.

## Interpretation and limitations

- At about 5 requests/s from 10 concurrent users the stack showed no errors; records chat had a 170 ms median and 210 ms p95; every endpoint's p95 was at or below 350 ms.
- This is a small smoke-level load test, not a capacity test: one run, one host, client and server sharing the same machine, short duration, synthetic data and a single test account.
- Not measured: higher concurrency, sustained load, LLM-backed questions under load, multiple backend workers, or behaviour behind nginx.
- Reproduce: `bash tests/load/run_isolated_load_test.sh loadtest-output` (results in `loadtest-output/`, git-ignored). Tunables: `USERS`, `SPAWN_RATE`, `DURATION`, `PORT`.
