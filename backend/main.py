from fastapi import FastAPI

app = FastAPI(title="Employee Onboarding Assistant")


@app.get("/health")
def health():
    """Placeholder endpoint so the environment can be verified on Day 31."""
    return {"status": "ok"}
