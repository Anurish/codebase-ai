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

## Repository-scoped indexing

Code chunks are isolated by a repository identifier. Existing database rows
are migrated to the default identifier, `codebase-ai`, so the current frontend
and data continue to work. Re-indexing a repository replaces only that
repository's chunks, in a single transaction.

Use the frontend's GitHub URL and branch fields to index a public repository.
The backend fetches its archive from GitHub, indexes supported source files,
and cleans up the temporary download. Repositories are listed by
`GET /api/repositories`; the active repository selector scopes Q&A and review.
The equivalent indexing request is
`POST /api/index/github` with `{"github_url":"https://github.com/owner/repo","branch":"main"}`.

The local folder can still be indexed with
`POST /api/index?repository=codebase-ai`. Chat requests accept the selected
repository identifier in their JSON body, and reviews accept it as a query
parameter (`POST /api/review?repository=...`). Only public GitHub repositories
are supported; private repositories and pull-request review remain future work.

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
