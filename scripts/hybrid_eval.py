"""M3 - held-out evaluation of OnboardAI hybrid chat (routing, records, handbook, mixed, refusals, latency).

Dataset: tests/eval/heldout_questions.json (written separately from the router tests; not used for tuning).

Modes
  --routing-only        Deterministic: routing accuracy only (no database, index, embeddings or LLM). Used in CI.
  (default) in-process  Isolated, freshly seeded SQLite copy in a temp directory + the real FAISS index
                        (read-only) + local embeddings + the configured LLM (Groq). Never touches PostgreSQL.
  --base-url URL        HTTP against an ISOLATED backend (never the live stack): logs in as the session
                        employee (password from the env var named by --password-env) and calls POST /chat.
                        Ground truth comes from the REST endpoints, so the chat path is checked independently.

Metrics (per question, aggregated by category and route kind)
  routing   kind + records intents (+ refusal flag for unauthorized questions) match the label
  records   every expected value from the ground-truth records appears in the records part
  refusal   unauthorized questions get the refusal text; leak = another employee's marker in any answer
  handbook  retrieval hit@k / MRR of an expected section for the text actually sent to retrieval;
            grounded = not a fallback and contains an answer key; citation hit / precision of returned
            handbook sources against the expected sections
  fallback  out-of-scope questions return the standard fallback with no handbook sources
  latency   wall-clock per question (in-process: orchestrator call; HTTP: request), p50/p95 per kind

Usage
  python -m scripts.hybrid_eval --routing-only
  python -m scripts.hybrid_eval --report docs/hybrid_eval_report.md
  python -m scripts.hybrid_eval --base-url http://127.0.0.1:8301 --email <email> --password-env EVAL_PW
"""
import argparse
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "tests" / "eval" / "heldout_questions.json"
CATEGORIES = ("records", "handbook", "mixed", "ambiguous", "unauthorized", "out_of_scope")
HANDBOOK_SPLIT = "\n\nFrom the handbook:\n"
RECORD_FILES = {"Your records", "Company records"}


# ---------------------------------------------------------------- dataset
def load_dataset(path=DATASET):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def percentile(values, pct):
    """Nearest-rank percentile (no interpolation); None for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


# ---------------------------------------------------------------- routing (deterministic)
def routing_result(item):
    from backend.services.employee_query_router import route

    r = route(item["question"])
    expected_intents = tuple(item.get("expected_intents", ()))
    refusal_expected = bool(item.get("expect_refusal"))
    ok = (r.kind == item["expected_kind"] and r.sql_intents == expected_intents
          and r.third_party == refusal_expected)
    return {"kind": r.kind, "intents": list(r.sql_intents), "third_party": r.third_party,
            "ambiguous": r.ambiguous, "policy_question": r.policy_question, "routing_ok": ok}


def routing_metrics(rows):
    by_cat = {}
    for row in rows:
        by_cat.setdefault(row["category"], []).append(row["routing_ok"])
    kinds = ("records", "handbook", "mixed")
    confusion = {e: {p: 0 for p in kinds} for e in kinds}
    for row in rows:
        confusion[row["expected_kind"]][row["kind"]] += 1
    unauthorized = [r for r in rows if r["category"] == "unauthorized"]
    flagged = [r for r in rows if r["third_party"]]
    return {
        "n": len(rows),
        "accuracy": sum(r["routing_ok"] for r in rows) / len(rows),
        "by_category": {c: (sum(v), len(v)) for c, v in by_cat.items()},
        "confusion": confusion,
        "third_party_recall": (sum(r["third_party"] for r in unauthorized) / len(unauthorized)) if unauthorized else None,
        "third_party_false_positives": sum(1 for r in flagged if r["category"] != "unauthorized"),
    }


# ---------------------------------------------------------------- grading helpers (pure; unit-tested)
def split_answer(answer, kind):
    """(records_part, handbook_part) of an answer for the given route kind."""
    if kind == "mixed" and HANDBOOK_SPLIT in answer:
        head, tail = answer.split(HANDBOOK_SPLIT, 1)
        return head, tail
    return (answer, "") if kind == "records" else ("", answer)


def _days(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"


def expected_record_values(intent, truth, today=None):
    """Strings that must appear in a correct records answer, derived from ground-truth rows."""
    data = truth[intent]
    if intent == "checklist":
        done = sum(1 for i in data if i["done"])
        return [f"{done} of {len(data)}"] if data else ["No onboarding checklist items"]
    if intent == "leave_balances":
        return [f"{r['leave_type']}: {_days(r['available_days'])} days" for r in data] or ["No leave balance records"]
    if intent == "assets":
        return [r["asset_name"] for r in data] or ["No assigned assets"]
    if intent == "tickets":
        return [f"Ticket #{r['ticket_id']}" for r in data] or ["You have no support tickets"]
    if intent == "profile":
        return [str(data["department"]), str(data["joining_date"])[:10]]
    if intent == "payroll":
        today = (today or date.today()).isoformat()
        upcoming = sorted(str(r["payment_date"])[:10] for r in data if str(r["payment_date"])[:10] >= today)
        return [upcoming[0]] if upcoming else ["No upcoming payroll date"]
    raise ValueError(intent)


def section_matches(section, expected_sections):
    return any(s.lower() in section.lower() for s in expected_sections)


def grade(item, route_row, response, truth, fallback_text, refusal_text, markers):
    """Grade one answer. `response` = {answer, sources, error}; returns a dict of booleans/None."""
    answer = response.get("answer") or ""
    sources = response.get("sources") or []
    handbook_sources = [s for s in sources if s.get("file") not in RECORD_FILES]
    records_part, handbook_part = split_answer(answer, route_row["kind"])
    g = {"error": response.get("error"),
         "leak": any(m.lower() in answer.lower() for m in markers)}
    if response.get("error"):
        return g

    if item.get("expect_refusal"):
        g["refusal_ok"] = refusal_text in answer
    elif item.get("expected_intents"):
        needed = [v for intent in item["expected_intents"] for v in expected_record_values(intent, truth)]
        g["records_ok"] = bool(records_part) and all(v in records_part for v in needed)

    if item.get("expect_fallback"):
        g["fallback_ok"] = handbook_part.strip() == fallback_text.strip() and not handbook_sources
    elif item.get("answer_keys"):
        is_fallback = handbook_part.strip() == fallback_text.strip()
        g["false_fallback"] = is_fallback
        g["grounded"] = (not is_fallback) and any(k.lower() in handbook_part.lower() for k in item["answer_keys"])
        g["citation_hit"] = any(section_matches(s["section"], item["sections"]) for s in handbook_sources)
        g["citation_precision"] = (sum(section_matches(s["section"], item["sections"]) for s in handbook_sources)
                                   / len(handbook_sources)) if handbook_sources else None
    if item["category"] == "mixed":
        g["mixed_ok"] = bool(g.get("records_ok")) and bool(g.get("grounded")) and bool(g.get("citation_hit"))
    return g


# ---------------------------------------------------------------- environments
class InProcess:
    """Isolated seeded SQLite copy + real index + configured LLM. Nothing outside the temp dir is written."""

    label = "in-process (isolated seeded SQLite copy, active FAISS index version read-only, local embeddings)"

    def __init__(self, employee):
        os.environ["DB_BACKEND"] = "sqlite"
        from backend.config import settings
        from backend.services import db

        self.tmp = Path(tempfile.mkdtemp(prefix="onboardai-eval-"))
        settings.db_backend, settings.db_path = "sqlite", self.tmp / "eval.db"
        settings.log_dir = self.tmp / "logs"
        from backend.services import ingest

        try:
            self.index_version = ingest.load_active()[0]
        except ingest.IndexUnavailable as exc:
            raise SystemExit(f"{exc}; build it first (python -m backend.services.ingest)")
        db.init_db()
        for name, call in (("001_employee_schema.py", lambda m: m.migrate(settings.db_path)),
                           ("002_seed_demo_data.py", lambda m: m.seed_demo_data(settings.db_path)),
                           ("003_employee_chat_history.py", lambda m: m.migrate(settings.db_path)),
                           ("004_auth_tables.py", lambda m: m.migrate())):
            call(_load_migration(name))
        self.employee = employee

    def truth(self):
        from backend.services import employee_db as e

        return {"checklist": e.get_employee_checklist(self.employee), "leave_balances": e.get_leave_balances(self.employee),
                "assets": e.get_employee_assets(self.employee), "tickets": e.get_employee_tickets(self.employee),
                "profile": e.get_employee(self.employee), "payroll": e.get_payroll_calendar()}

    def ask(self, question):
        from backend.services import llm, orchestrator

        start = time.perf_counter()
        try:
            r = orchestrator.answer_question(question, employee_id=self.employee)
            return {"answer": r["answer"], "sources": r["sources"]}, time.perf_counter() - start
        except llm.LLMUnavailable:
            return {"error": "llm_unavailable"}, time.perf_counter() - start

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class Http:
    label = "HTTP against an isolated backend"

    def __init__(self, base_url, email, password, employee):
        import httpx

        self.base, self.employee = base_url.rstrip("/"), employee
        self.client = httpx.Client(base_url=self.base, timeout=90)
        r = self.client.post("/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        self.client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        self.label = f"HTTP against an isolated backend ({self.base})"

    def truth(self):
        g = lambda p: self.client.get(p).raise_for_status().json()  # noqa: E731
        e = self.employee
        return {"checklist": g(f"/employees/{e}/checklist"), "leave_balances": g(f"/employees/{e}/leave-balances"),
                "assets": g(f"/employees/{e}/assets"), "tickets": g(f"/employees/{e}/tickets"),
                "profile": g(f"/employees/{e}"), "payroll": g("/employees/payroll/calendar")}

    def ask(self, question):
        start = time.perf_counter()
        r = self.client.post("/chat", json={"question": question})
        elapsed = time.perf_counter() - start
        if r.status_code != 200:
            return {"error": f"http_{r.status_code}"}, elapsed
        body = r.json()
        return {"answer": body["answer"], "sources": body["sources"]}, elapsed

    def close(self):
        self.client.close()


def _load_migration(filename):
    import importlib.util

    path = ROOT / "backend" / "migrations" / filename
    spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def retrieval_rank(query, sections, k):
    from backend.services import retriever

    for i, hit in enumerate(retriever.search(query, k), 1):
        if section_matches(hit["section"], sections):
            return i
    return None


# ---------------------------------------------------------------- run + report
def _mean(values):
    values = [v for v in values if v is not None]
    return (sum(values) / len(values)) if values else None


def _rate(rows, key):
    values = [r["grade"].get(key) for r in rows if r["grade"].get(key) is not None]
    return (sum(bool(v) for v in values), len(values))


def run(args):
    data = load_dataset(args.dataset)
    items = data["questions"]
    rows = []
    for item in items:
        rows.append({**{k: item[k] for k in ("id", "category", "question", "expected_kind")},
                     "expected_intents": item.get("expected_intents", []), **routing_result(item)})
    summary = {"routing": routing_metrics(rows), "n": len(rows)}
    if args.routing_only:
        return data, rows, summary, "routing only (deterministic)", None

    from backend.config import settings
    from backend.services import orchestrator, rag

    env = (Http(args.base_url, args.email, os.environ[args.password_env], data["session_employee"])
           if args.base_url else InProcess(data["session_employee"]))
    try:
        truth = env.truth()
        for row, item in zip(rows, items):
            if item.get("sections"):
                row["retrieval_rank"] = retrieval_rank(row["policy_question"] or item["question"], item["sections"],
                                                       settings.top_k)
            response, elapsed = env.ask(item["question"])
            attempts = 1
            while response.get("error") in ("llm_unavailable", "http_503") and attempts < 3:
                time.sleep(args.delay * 4 * attempts)
                response, elapsed = env.ask(item["question"])
                attempts += 1
            row.update(latency_ms=round(elapsed * 1000, 1), attempts=attempts, answer=response.get("answer", ""),
                       sources=response.get("sources", []),
                       grade=grade(item, row, response, truth, rag.FALLBACK, orchestrator.THIRD_PARTY_REFUSAL,
                                   data["other_employee_markers"]))
            if row["kind"] != "records":
                time.sleep(args.delay)
    finally:
        env.close()
    summary.update(_aggregate(rows))
    return data, rows, summary, env.label, settings.model_name


def _aggregate(rows):
    ranks = [r.get("retrieval_rank") for r in rows if "retrieval_rank" in r]
    lat = {}
    for r in rows:
        if r["grade"].get("error"):
            continue
        lat.setdefault(r["kind"], []).append(r["latency_ms"])
        lat.setdefault("all", []).append(r["latency_ms"])
    return {
        "records": _rate(rows, "records_ok"),
        "refusal": _rate(rows, "refusal_ok"),
        "leaks": sum(1 for r in rows if r["grade"].get("leak")),
        "grounded": _rate(rows, "grounded"),
        "false_fallback": _rate(rows, "false_fallback"),
        "citation_hit": _rate(rows, "citation_hit"),
        "citation_precision": _mean([r["grade"].get("citation_precision") for r in rows]),
        "fallback": _rate(rows, "fallback_ok"),
        "mixed": _rate(rows, "mixed_ok"),
        "errors": sum(1 for r in rows if r["grade"].get("error")),
        "retrieval_hit": (sum(1 for x in ranks if x), len(ranks)),
        "retrieval_mrr": _mean([1 / x if x else 0.0 for x in ranks]),
        "latency": {k: {"n": len(v), "p50": percentile(v, 50), "p95": percentile(v, 95), "max": max(v)}
                    for k, v in lat.items()},
    }


def _fmt_rate(pair):
    ok, n = pair
    return f"{ok}/{n} ({ok / n:.0%})" if n else "n/a"


def _git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def render(data, rows, summary, env_label, model):
    rt = summary["routing"]
    lines = [
        "# Hybrid Chat Evaluation Report (M3)", "",
        f"Date: {date.today().isoformat()} | Commit: `{_git_commit()}` (plus uncommitted changes) | "
        f"Python {platform.python_version()} on {platform.system()}", "",
        f"Environment: {env_label}" + (f" | LLM: `{model}` via Groq (temporary)" if model else ""), "",
        f"Dataset: `tests/eval/heldout_questions.json` - {summary['n']} held-out questions, session employee "
        f"{data['session_employee']}. Generated by `python -m scripts.hybrid_eval`. Expectations for records come "
        "from the database at run time; handbook answer keys are verbatim knowledge-base text.", "",
        "## Summary", "",
        "| Metric | Result |", "|---|---|",
        f"| Routing accuracy (kind + intents + refusal flag) | {_fmt_rate((sum(r['routing_ok'] for r in rows), len(rows)))} |",
        f"| Third-party detection recall (unauthorized questions flagged) | "
        f"{rt['third_party_recall']:.0%} |" if rt["third_party_recall"] is not None else "| Third-party recall | n/a |",
        f"| Third-party false positives (other categories) | {rt['third_party_false_positives']} |",
    ]
    if "records" in summary:
        s = summary
        lines += [
            f"| Records answers correct (records + mixed) | {_fmt_rate(s['records'])} |",
            f"| Unauthorized questions refused | {_fmt_rate(s['refusal'])} |",
            f"| Answers containing another employee's data marker | {s['leaks']} |",
            f"| Retrieval hit@k of an expected section (query actually sent) | {_fmt_rate(s['retrieval_hit'])} |",
            f"| Retrieval MRR | {s['retrieval_mrr']:.3f} |",
            f"| Grounded handbook answers (answer key present, not a fallback) | {_fmt_rate(s['grounded'])} |",
            f"| False fallbacks on answerable questions | {_fmt_rate(s['false_fallback'])} |",
            f"| Citation hit (a returned handbook source is an expected section) | {_fmt_rate(s['citation_hit'])} |",
            "| Citation precision (mean share of returned handbook sources that are expected) | "
            + (f"{s['citation_precision']:.2f} |" if s['citation_precision'] is not None else "n/a |"),
            f"| Mixed answers fully correct (records + grounded + cited) | {_fmt_rate(s['mixed'])} |",
            f"| Out-of-scope questions answered with the fallback | {_fmt_rate(s['fallback'])} |",
            f"| Errors after retries (LLM unavailable / HTTP errors) | {s['errors']} |",
        ]
    lines += ["", "## Routing by category", "", "| Category | Correct |", "|---|---|"]
    lines += [f"| {c} | {ok}/{n} |" for c, (ok, n) in sorted(rt["by_category"].items())]
    lines += ["", "Route-kind confusion (rows = expected, columns = predicted):", "",
              "| expected \\ predicted | records | handbook | mixed |", "|---|---|---|---|"]
    lines += [f"| {e} | " + " | ".join(str(rt["confusion"][e][p]) for p in ("records", "handbook", "mixed")) + " |"
              for e in ("records", "handbook", "mixed")]
    if "latency" in summary:
        lines += ["", "## Latency (successful answers, milliseconds, nearest-rank percentiles)", "",
                  "| Route kind | n | p50 | p95 | max |", "|---|---|---|---|---|"]
        for k in ("records", "handbook", "mixed", "all"):
            v = summary["latency"].get(k)
            if v:
                lines.append(f"| {k} | {v['n']} | {v['p50']:.0f} | {v['p95']:.0f} | {v['max']:.0f} |")
        lines += ["", "With n < 20 per kind, p95 is close to the maximum; treat it as indicative."]
    lines += ["", "## Per-question results", "",
              "| ID | Category | Question | Route | Routing | Result | Latency ms |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        g = r.get("grade", {})
        result = ", ".join(f"{k}={'yes' if v is True else 'no' if v is False else (f'{v:.2f}' if isinstance(v, float) else v)}"
                           for k, v in g.items() if v is not None and k != "leak") or "-"
        if g.get("leak"):
            result += ", LEAK"
        route = r["kind"] + (f":{','.join(r['intents'])}" if r["intents"] else "") + (" (refused)" if r["third_party"] else "")
        lines.append(f"| {r['id']} | {r['category']} | {r['question']} | {route} | "
                     f"{'ok' if r['routing_ok'] else 'MISS'} | {result} | {r.get('latency_ms', '-')} |")
    lines += ["", "## Method and limitations", "",
              "- The held-out set was written before measurement and was not used to change the router; misses are reported, not fixed, in M3.",
              "- Grading is lexical: an answer key must appear verbatim (case-insensitive). Paraphrased correct answers can be counted as not grounded; unsupported paraphrased claims are not detected.",
              "- Records correctness requires every expected value (for example all leave types) to appear in the records part.",
              "- Leak detection checks other employees' names, emails and asset names from the synthetic seed; it cannot prove the absence of every possible leak (database RLS is the primary control and is tested separately).",
              "- One run, one model, temperature 0; LLM answers can still vary between runs. Transient LLM errors are retried up to twice and reported.",
              "- In-process latency excludes HTTP, nginx and PostgreSQL; use --base-url against an isolated stack for end-to-end latency."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--dataset", default=str(DATASET))
    p.add_argument("--routing-only", action="store_true")
    p.add_argument("--base-url")
    p.add_argument("--email")
    p.add_argument("--password-env", default="EVAL_PASSWORD")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between LLM-using questions")
    p.add_argument("--report", help="write a Markdown report to this path")
    p.add_argument("--json", help="write raw results to this path")
    p.add_argument("--min-routing-accuracy", type=float, help="exit 1 if routing accuracy is below this value")
    args = p.parse_args(argv)

    data, rows, summary, env_label, model = run(args)
    report = render(data, rows, summary, env_label, model)
    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, default=str), encoding="utf-8")
    print(report.split("## Per-question results")[0])
    accuracy = summary["routing"]["accuracy"]
    if args.min_routing_accuracy is not None and accuracy < args.min_routing_accuracy:
        print(f"Routing accuracy {accuracy:.3f} is below the minimum {args.min_routing_accuracy:.3f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
