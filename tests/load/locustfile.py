"""Small, reproducible load test for OnboardAI (M3). Run ONLY against an isolated stack.

Scenario: signed-in employees use the dashboard and ask records questions in chat.
Handbook (LLM) questions are deliberately excluded: they would measure the external LLM provider's
rate limits and cost, not this application. Records chat exercises routing, the read-only reader role,
the signed employee scope, row-level security and chat-history writes.

Environment:
  LOADTEST_EMAIL, LOADTEST_PASSWORD   synthetic test account on the isolated stack
  LOADTEST_EMPLOYEE                   its employee ID (default EMP001)

Usage (see tests/load/run_isolated_load_test.sh, which creates and removes the isolated stack):
  locust -f tests/load/locustfile.py --headless -u 10 -r 2 -t 60s --host http://127.0.0.1:8301 --csv out/loadtest
"""
import os
import random

from locust import HttpUser, between, task

EMPLOYEE = os.environ.get("LOADTEST_EMPLOYEE", "EMP001")
RECORDS_QUESTIONS = (
    "What is my onboarding status?",
    "How many casual leaves do I have left?",
    "Which laptop do I have?",
    "When is the next payroll date?",
    "Which onboarding tasks are still pending?",
)


class Employee(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        r = self.client.post("/auth/login", json={"email": os.environ["LOADTEST_EMAIL"],
                                                  "password": os.environ["LOADTEST_PASSWORD"]}, name="/auth/login")
        r.raise_for_status()
        self.client.headers["X-CSRF-Token"] = r.json()["csrf_token"]

    @task(1)
    def health(self):
        self.client.get("/health")

    @task(3)
    def checklist(self):
        self.client.get(f"/employees/{EMPLOYEE}/checklist", name="/employees/[id]/checklist")

    @task(2)
    def leave(self):
        self.client.get(f"/employees/{EMPLOYEE}/leave-balances", name="/employees/[id]/leave-balances")

    @task(1)
    def payroll(self):
        self.client.get("/employees/payroll/calendar")

    @task(1)
    def history(self):
        self.client.get("/history", params={"limit": 20})

    @task(3)
    def chat_records(self):
        with self.client.post("/chat", json={"question": random.choice(RECORDS_QUESTIONS)},
                              name="/chat (records)", catch_response=True) as r:
            if r.status_code != 200 or not r.json().get("sources"):
                r.failure(f"unexpected chat response {r.status_code}")
