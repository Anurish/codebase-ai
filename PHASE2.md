# Phase 2 — Backend Foundation

## Architecture

Next.js frontend
        |
        v
FastAPI
        |
        v
LangGraph
   retrieve -> analyze
        |
        v
PostgreSQL + pgvector

## Run

1. Copy `backend/.env.example` to `backend/.env`.
2. Set `OPENAI_API_KEY`.
3. From project root run:

```bash
docker compose up --build
```

4. Check:

http://localhost:8000/health

## Current status

This phase proves the backend/API/LangGraph/database plumbing. The retrieval node is intentionally a stub.

Next implementation:
- repository scanner
- Tree-sitter parsing
- code-aware chunking
- embeddings
- pgvector persistence
- retrieval
- LLM analysis
- source/line citations
