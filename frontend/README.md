# OnboardAI — Frontend

React + Vite frontend for OnboardAI: RAG-Powered New Joiner Support Platform.

## Features

- Employee dashboard and demo employee selector
- AI Assistant with employee-specific chat history
- Interactive onboarding checklist
- Leave balances and payroll calendar
- IT asset information
- Support ticket creation and history

## Local Development

### Prerequisites

- Node.js and npm
- Running OnboardAI FastAPI backend

### Start the Backend

From the project root:

python -m uvicorn backend.main:app --reload --port 8000

### Start the Frontend

From the frontend directory:

npm install
npm run dev

Open http://localhost:5173. The Vite dev server proxies `/api/*` to `http://127.0.0.1:8000` (see `vite.config.js`).

### Test and Build

npm test          # helper tests with the Node test runner
npm run build     # production build in dist/

### Docker

`Dockerfile` builds the app and serves it with nginx; `nginx.conf` proxies `/api/*` to the `backend` service, matching the dev proxy. Start the full stack from the project root with Docker Compose (see the root README).

## Important Notes

- The employee selector is for synthetic demo data only.
- The selector does not provide authentication or authorization.
- Backend API endpoints must be available for employee features.
- Azure is the target deployment platform.
- Groq is a temporary development LLM integration.
