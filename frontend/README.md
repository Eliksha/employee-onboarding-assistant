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

Open http://localhost:5173.

## Important Notes

- The employee selector is for synthetic demo data only.
- The selector does not provide authentication or authorization.
- Backend API endpoints must be available for employee features.
- Azure is the target deployment platform.
- Groq is a temporary development LLM integration.
