# Problem Statement: AI Employee Onboarding Assistant

## Users
- Primary: new joiners in their first 90 days
- Secondary: HR and IT support teams (content owners, escalation receivers)

## Business problem
New joiners repeatedly ask HR and IT about leave, payroll, benefits, IT setup and company policies. Information is spread across a long handbook and FAQ sheets, so people search manually or wait for replies. This costs support time, delays productivity and can produce inconsistent answers.

## Proposed solution
A RAG-based chatbot that answers onboarding questions from an approved handbook with source references, shows an onboarding checklist and escalates to HR/IT when the documents do not contain the answer.

## Scope (MVP)
1. Question input and answer display
2. Retrieval of relevant handbook passages (embeddings + FAISS)
3. Grounded answer generation with an LLM
4. Source display, safe fallback and escalate-to-HR/IT option
5. Onboarding checklist (Day 1 / Week 1 / Month 1)

## Out of scope
Login/SSO, HRMS or email integration, admin upload page, multilingual support, analytics, automated approvals, legal/medical interpretation, real employee data.

## Success criteria
- At least 80% of in-scope test questions answered correctly with a source
- 100% of out-of-scope questions trigger the safe fallback
- Typical response time under 5 seconds
- Containerized, deployed (or documented blocker + local run), CI passing, test results recorded

## Assumptions and constraints
Synthetic data only (fictional company NovaTech Solutions); single user; local FAISS index; OpenAI API; four-day build window; solo developer.

## Safety note
Output is decision support. Unanswered or sensitive questions are escalated to a human (HR/IT); the assistant never approves or changes anything.
