
import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import DEFAULT_REPOSITORY_ID, settings
from app.db import (
    init_db,
    replace_index,
    get_repositories,
    search_chunks,
    get_all_chunks,
)
from app.github import (
    GitHubDownloadError,
    download_public_repository,
    parse_github_repository,
)
from app.scanner import scan_repository
from app.embeddings import embed_texts
from app.llm import review_repository
from app.schemas import (
    ChatRequest,
    ChatResponse,
    GitHubIndexRequest,
    IndexResponse,
    RepositoryInfo,
    ReviewResponse,
    Source,
    HealthComponent,
    HealthResponse,
)


# =========================================================
# Logging
# =========================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =========================================================
# FastAPI application
# =========================================================

app = FastAPI(
    title="Codebase AI",
    version="0.8.1",
    description="AI-powered repository analysis and code review agent.",
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# Startup
# =========================================================

@app.on_event("startup")
def startup_event():
    init_db()
    logger.info("Database initialized")


# =========================================================
# Basic health
# =========================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "codebase-ai-backend",
        "version": "0.8.1",
    }


# =========================================================
# Detailed repository health
# =========================================================

@app.get("/api/health/details", response_model=HealthResponse)
def detailed_health(
    repository: str = Query(DEFAULT_REPOSITORY_ID, min_length=1, max_length=512),
):
    repository_health = HealthComponent(
        status="error",
        message="Could not verify the selected repository index.",
    )
    database_health = HealthComponent(
        status="error",
        message="Database check failed.",
    )
    pgvector_health = HealthComponent(
        status="error",
        message="pgvector check failed.",
    )

    indexed_files = 0
    indexed_chunks = 0

    try:
        from app.db import get_conn

        with get_conn() as conn:
            db_row = conn.execute(
                "SELECT current_database()"
            ).fetchone()

            database_name = db_row[0] if db_row else "unknown"

            database_health = HealthComponent(
                status="healthy",
                message=f"PostgreSQL connected: {database_name}",
            )

            vector_row = conn.execute(
                """
                SELECT extversion
                FROM pg_extension
                WHERE extname = 'vector'
                """
            ).fetchone()

            if vector_row:
                pgvector_health = HealthComponent(
                    status="healthy",
                    message=f"pgvector active: {vector_row[0]}",
                )
            else:
                pgvector_health = HealthComponent(
                    status="error",
                    message="pgvector extension is not installed.",
                )

            chunk_row = conn.execute(
                "SELECT COUNT(*) FROM code_chunks WHERE repository = %s",
                (repository,),
            ).fetchone()

            indexed_chunks = int(chunk_row[0]) if chunk_row else 0

            file_row = conn.execute(
                """
                SELECT COUNT(DISTINCT path)
                FROM code_chunks
                WHERE repository = %s
                """,
                (repository,),
            ).fetchone()

            indexed_files = int(file_row[0]) if file_row else 0
            if indexed_chunks:
                repository_health = HealthComponent(
                    status="healthy",
                    message=(
                        f"Indexed {indexed_files} files and "
                        f"{indexed_chunks} code chunks."
                    ),
                )
            else:
                repository_health = HealthComponent(
                    status="error",
                    message="No indexed code chunks for this repository.",
                )

    except Exception as exc:
        logger.exception("Detailed health database check failed")

        database_health = HealthComponent(
            status="error",
            message=f"Database error: {str(exc)}",
        )

        pgvector_health = HealthComponent(
            status="error",
            message="Could not verify pgvector.",
        )
        repository_health = HealthComponent(
            status="error",
            message="Could not verify the selected repository index.",
        )

    if settings.gemini_api_key:
        gemini_health = HealthComponent(
            status="healthy",
            message=(
                "Gemini API key is configured. "
                "Live API connectivity and quota are not tested."
            ),
        )
    else:
        gemini_health = HealthComponent(
            status="error",
            message="Gemini API key is not configured.",
        )

    components = [
        repository_health,
        database_health,
        pgvector_health,
        gemini_health,
    ]

    overall_status = (
        "degraded"
        if any(component.status == "error" for component in components)
        else "healthy"
    )

    return HealthResponse(
        status=overall_status,
        repository=repository_health,
        database=database_health,
        pgvector=pgvector_health,
        gemini=gemini_health,
        indexed_files=indexed_files,
        indexed_chunks=indexed_chunks,
        repository_root=settings.repository_root,
    )


# =========================================================
# Repository indexing
# =========================================================

def index_repository_path(
    root: str,
    repository: str,
    name: str,
    github_url: str | None = None,
    branch: str | None = None,
) -> IndexResponse:
    file_count, chunks = scan_repository(root)

    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="No supported source chunks found in repository.",
        )

    logger.info("Generating embeddings for %s chunks", len(chunks))
    vectors = embed_texts(
        [chunk["content"] for chunk in chunks],
        task_type="RETRIEVAL_DOCUMENT",
    )

    if len(vectors) != len(chunks):
        raise RuntimeError(
            f"Embedding count mismatch: received {len(vectors)} "
            f"vectors for {len(chunks)} chunks."
        )

    rows = [
        (
            chunk["path"],
            chunk["start_line"],
            chunk["end_line"],
            chunk["content"],
            vector,
        )
        for chunk, vector in zip(chunks, vectors)
    ]

    replace_index(
        repository,
        rows,
        name=name,
        github_url=github_url,
        branch=branch,
    )

    logger.info(
        "Indexing completed: %s files, %s chunks for %s",
        file_count,
        len(chunks),
        repository,
    )
    return IndexResponse(
        files=file_count,
        chunks=len(chunks),
        repository=repository,
        name=name,
        github_url=github_url,
        branch=branch,
    )


@app.get("/api/repositories", response_model=list[RepositoryInfo])
def list_repositories():
    try:
        return get_repositories()
    except Exception as exc:
        logger.exception("Repository list retrieval failed")
        raise HTTPException(
            status_code=500,
            detail=f"Could not retrieve repositories: {exc}",
        ) from exc


@app.post("/api/index", response_model=IndexResponse)
def index_repository(
    repository: str = Query(DEFAULT_REPOSITORY_ID, min_length=1, max_length=512),
):
    try:
        logger.info("Starting local repository indexing for %s", repository)
        return index_repository_path(
            settings.repository_root,
            repository,
            name=repository,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Repository indexing failed")
        raise HTTPException(
            status_code=500,
            detail=f"Repository indexing failed: {str(exc)}",
        )


@app.post("/api/index/github", response_model=IndexResponse)
def index_github_repository(request: GitHubIndexRequest):
    try:
        owner, repository_name, github_url, repository_id = (
            parse_github_repository(request.github_url, request.branch)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info(
        "Starting public GitHub repository indexing: %s branch %s",
        github_url,
        request.branch,
    )

    try:
        with download_public_repository(
            owner,
            repository_name,
            request.branch,
        ) as repository_path:
            return index_repository_path(
                str(repository_path),
                repository_id,
                name=f"{repository_name} ({request.branch})",
                github_url=github_url,
                branch=request.branch,
            )
    except HTTPException:
        raise
    except GitHubDownloadError as exc:
        logger.warning("GitHub repository indexing failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("GitHub repository indexing failed")
        raise HTTPException(
            status_code=500,
            detail=f"GitHub repository indexing failed: {exc}",
        ) from exc


# =========================================================
# Chat / Q&A using LangGraph
# =========================================================

@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    try:
        from app.graph import code_graph

        result = code_graph.invoke(
            {
                "question": request.question,
                "repository": request.repository,
            }
        )

        sources = result.get("sources", [])

        formatted_sources = [
            Source(
                file=source["path"],
                path=source["path"],
                lines=(
                    f'{source["start_line"]}-'
                    f'{source["end_line"]}'
                ),
                score=str(source["score"]),
                content=source["content"],
            )
            for source in sources
        ]

        return ChatResponse(
            answer=result["answer"],
            sources=formatted_sources,
        )

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("Chat request failed")

        raise HTTPException(
            status_code=500,
            detail=f"Chat failed: {str(exc)}",
        )


# =========================================================
# Format review sources
# =========================================================

def format_review_sources(rows):
    """Convert indexed chunks into the review source format."""

    sources = []

    for row in rows:
        sources.append(
            {
                "file": row["path"],
                "path": row["path"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "lines": (
                    f'{row["start_line"]}-'
                    f'{row["end_line"]}'
                ),
                "score": str(row.get("score", "1.0000")),
                "content": row["content"],
            }
        )

    return sources


# =========================================================
# Full repository review sources
# =========================================================

def get_full_repository_review_sources(repository: str):
    """Retrieve every currently indexed chunk for review."""

    rows = get_all_chunks(repository=repository, limit=1000)
    sources = format_review_sources(rows)

    file_count = len(
        {source["path"] for source in sources}
    )

    logger.info(
        "Full repository review: %s chunks across %s files",
        len(sources),
        file_count,
    )

    return sources


# =========================================================
# Semantic review retrieval (fallback)
# =========================================================

def get_diverse_review_sources(repository: str):
    """Retrieve diverse, semantically relevant review chunks."""

    review_queries = [
        (
            "security vulnerabilities authentication authorization "
            "credentials secrets API keys tokens passwords injection XSS CSRF"
        ),
        (
            "bugs correctness exceptions error handling failure states "
            "invalid input null values race conditions unsafe operations"
        ),
        (
            "performance database queries SQL vector search API calls "
            "external requests network latency caching expensive operations"
        ),
        (
            "code quality maintainability architecture code smells "
            "duplicated code coupling separation of concerns configuration"
        ),
        (
            "FastAPI backend routes middleware request validation "
            "response handling dependency injection"
        ),
        (
            "Next.js React frontend state management fetch API "
            "error handling components security"
        ),
        (
            "PostgreSQL database transactions connections queries "
            "pgvector embeddings persistence"
        ),
        (
            "LangGraph workflow retrieval embeddings LLM generation "
            "prompts orchestration"
        ),
    ]

    candidates = {}

    for query in review_queries:
        try:
            query_vector = embed_texts(
                [query],
                task_type="RETRIEVAL_QUERY",
            )[0]

            results = search_chunks(
                query_vector,
                repository=repository,
                limit=8,
            )

            for result in results:
                key = (
                    f'{result["path"]}:'
                    f'{result["start_line"]}:'
                    f'{result["end_line"]}'
                )

                existing = candidates.get(key)

                if (
                    existing is None
                    or float(result["score"])
                    > float(existing["score"])
                ):
                    candidates[key] = result

        except Exception:
            logger.exception(
                "Review retrieval failed for query: %s",
                query,
            )

    sorted_candidates = sorted(
        candidates.values(),
        key=lambda item: float(item["score"]),
        reverse=True,
    )

    max_chunks_per_file = 2
    max_review_chunks = 20

    selected = []
    per_file_count = {}

    # First pass: prioritize file diversity.
    for item in sorted_candidates:
        path = item["path"]

        if per_file_count.get(path, 0) >= max_chunks_per_file:
            continue

        selected.append(item)
        per_file_count[path] = per_file_count.get(path, 0) + 1

        if len(selected) >= max_review_chunks:
            break

    # Second pass: fill remaining slots.
    if len(selected) < max_review_chunks:
        selected_keys = {
            (
                item["path"],
                item["start_line"],
                item["end_line"],
            )
            for item in selected
        }

        for item in sorted_candidates:
            key = (
                item["path"],
                item["start_line"],
                item["end_line"],
            )

            if key in selected_keys:
                continue

            selected.append(item)

            if len(selected) >= max_review_chunks:
                break

    logger.info(
        "Diverse review retrieval: %s candidates, %s selected chunks "
        "across %s files",
        len(sorted_candidates),
        len(selected),
        len({item["path"] for item in selected}),
    )

    return format_review_sources(selected)


# =========================================================
# Repository code review
# =========================================================

@app.post("/api/review", response_model=ReviewResponse)
def review(
    repository: str = Query(DEFAULT_REPOSITORY_ID, min_length=1, max_length=512),
):
    try:
        logger.info("Starting full repository code review for %s", repository)

        # Review all indexed chunks, not only the semantic top 20.
        sources = get_full_repository_review_sources(repository)

        if not sources:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No indexed repository chunks found. "
                    "Run /api/index first."
                ),
            )

        logger.info(
            "Sending %s chunks to AI reviewer",
            len(sources),
        )

        result = review_repository(sources)

        formatted_sources = [
            Source(
                file=source["file"],
                path=source["path"],
                lines=source["lines"],
                score=str(source["score"]),
                content=source["content"],
            )
            for source in sources
        ]

        return ReviewResponse(
            findings=result.get("findings", []),
            summary=result.get(
                "summary",
                {
                    "critical": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "informational": 0,
                    "potential": 0,
                },
            ),
            overall_review=result.get(
                "overall_review",
                "Repository review completed.",
            ),
            sources=formatted_sources,
            reviewed_chunks=len(sources),
        )

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("Repository review failed")

        raise HTTPException(
            status_code=500,
            detail=f"Repository review failed: {str(exc)}",
        )
