# Codebase AI — Phase 1 + Phase 2

Combined project for an AI-powered codebase reviewer and codebase Q&A system.

## Phase 1 — Frontend

- Next.js + React
- Dark premium UI
- Codebase Q&A
- Suggested questions
- Source-file panel
- Code preview
- Responsive layout
- Mock responses

Run:

```bash
npm install
npm run dev
```

Open http://localhost:3000

## Phase 2 — Backend Foundation

- FastAPI
- LangGraph
- PostgreSQL + pgvector
- OpenAI configuration
- `/health`
- `/api/chat`

Create:

```text
backend/.env
```

from:

```text
backend/.env.example
```

Set your API key and run:

```bash
docker compose up --build
```

Backend health:

http://localhost:8000/health

## Important

The current LangGraph retrieval node is a placeholder. The next phase will connect the system to an actual repository and implement indexing, Tree-sitter parsing, embeddings, vector retrieval, and real file/line citations.
