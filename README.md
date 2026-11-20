# Employee Onboarding Assistant

## Problem
New joiners struggle to find approved onboarding information (leave, payroll, benefits, IT setup) and depend on HR/IT for routine answers.

## Proposed solution
A document-grounded AI assistant that answers onboarding questions from an approved handbook, shows sources, offers an onboarding checklist and escalates to HR/IT when it cannot answer.

## Planned stack
- Frontend: React + Vite
- Backend: FastAPI
- LLM: approved OpenAI API access
- Retrieval: embeddings + FAISS (subject to validation)
- Storage: SQLite
- Deployment: Docker + Azure (subject to access) | CI/CD: GitHub Actions

## Data
Synthetic handbook, FAQs and checklist for a fictional company (NovaTech Solutions) in `data/raw/`. No real employee data.

## Setup (local)
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then add your real values locally
uvicorn backend.main:app --reload   # check http://localhost:8000/health
```

## Team
Eliksha - sole developer (architecture, backend, AI, frontend, DevOps/QA)

## Project status
Day 31: Project setup and architecture. Azure deployment pending access approval.
