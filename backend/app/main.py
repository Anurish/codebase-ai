from pathlib import Path
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import (
    init_db,
    clear_index,
    insert_chunks,
    search_chunks,
    get_all_chunks,
)
from app.scanner import scan_repository
from app.embeddings import embed_texts
from app.graph import answer_question
from app.llm import review_repository
from app.schemas import (
    ChatRequest,
    ChatResponse,
    IndexResponse,
    ReviewResponse,
    Source,
    HealthComponent,
    HealthResponse,
)


# ---------------------------------------------------------
# Logging
# ---------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# FastAPI
# ---------------------------------------------------------

app = FastAPI(
    title="Codebase AI",
    version="0.8.0",
    description="AI-powered repository analysis and code review agent.",
)


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# Startup
# ---------------------------------------------------------

@app.on_event("startup")
def startup_event():
    init_db()
    logger.info("Database initialized")


# ---------------------------------------------------------
# Basic Health
# ---------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "codebase-ai-backend",
        "version": "0.8.0",
    }


# ---------------------------------------------------------
# Detailed Repository Health
# ---------------------------------------------------------

@app.get(
    "/api/health/details",
    response_model=HealthResponse,
)
def detailed_health():
    """
    Detailed health information for:

    - Repository
    - PostgreSQL
    - pgvector
    - Gemini configuration
    - Indexed files
    - Indexed chunks
    """

    # -----------------------------
    # Repository check
    # -----------------------------

    repository_path = Path(settings.repository_root)

    if repository_path.exists() and repository_path.is_dir():
        repository_health = HealthComponent(
            status="healthy",
            message="Repository directory is available.",
        )
    else:
        repository_health = HealthComponent(
            status="error",
            message="Repository directory is not available.",
        )

    # Defaults
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

    # -----------------------------
    # Database + pgvector
    # -----------------------------

    try:
        from app.db import get_conn

        with get_conn() as conn:

            # PostgreSQL
            db_row = conn.execute(
                "SELECT current_database()"
            ).fetchone()

            database_name = db_row[0] if db_row else "unknown"

            database_health = HealthComponent(
                status="healthy",
                message=f"PostgreSQL connected: {database_name}",
            )

            # pgvector
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

            # Indexed chunks
            chunk_row = conn.execute(
                """
                SELECT COUNT(*)
                FROM code_chunks
                """
            ).fetchone()

            indexed_chunks = int(chunk_row[0]) if chunk_row else 0

            # Indexed files
            file_row = conn.execute(
                """
                SELECT COUNT(DISTINCT path)
                FROM code_chunks
                """
            ).fetchone()

            indexed_files = int(file_row[0]) if file_row else 0

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

    # -----------------------------
    # Gemini configuration
    # -----------------------------

    if settings.gemini_api_key:
        gemini_health = HealthComponent(
            status="healthy",
            message="Gemini API key is configured.",
        )
    else:
        gemini_health = HealthComponent(
            status="error",
            message="Gemini API key is not configured.",
        )

    # -----------------------------
    # Overall status
    # -----------------------------

    components = [
        repository_health,
        database_health,
        pgvector_health,
        gemini_health,
    ]

    if any(component.status == "error" for component in components):
        overall_status = "degraded"
    else:
        overall_status = "healthy"

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


# ---------------------------------------------------------
# Index Repository
# ---------------------------------------------------------

@app.post(
    "/api/index",
    response_model=IndexResponse,
)
def index_repository():

    try:
        logger.info("Starting repository indexing")

        files = scan_repository(settings.repository_root)

        if not files:
            raise HTTPException(
                status_code=400,
                detail="No supported source files found in repository.",
            )

        clear_index()

        contents = [
            {
                "path": item["path"],
                "content": item["content"],
                "start_line": item["start_line"],
                "end_line": item["end_line"],
            }
            for item in files
        ]

        texts = [
            item["content"]
            for item in contents
        ]

        logger.info(
            "Generating embeddings for %s chunks",
            len(texts),
        )

        vectors = embed_texts(
            texts,
            task_type="RETRIEVAL_DOCUMENT",
        )

        rows = []

        for item, vector in zip(contents, vectors):
            rows.append(
                {
                    "path": item["path"],
                    "start_line": item["start_line"],
                    "end_line": item["end_line"],
                    "content": item["content"],
                    "embedding": vector,
                }
            )

        insert_chunks(rows)

        indexed_files = len(
            set(item["path"] for item in contents)
        )

        indexed_chunks = len(rows)

        logger.info(
            "Repository indexing completed: %s files, %s chunks",
            indexed_files,
            indexed_chunks,
        )

        return IndexResponse(
            files=indexed_files,
            chunks=indexed_chunks,
        )

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("Repository indexing failed")

        raise HTTPException(
            status_code=500,
            detail=f"Repository indexing failed: {str(exc)}",
        )


# ---------------------------------------------------------
# Chat / Q&A
# ---------------------------------------------------------

@app.post(
    "/api/chat",
    response_model=ChatResponse,
)
def chat(request: ChatRequest):

    try:
        result = answer_question(
            question=request.question,
            repository=request.repository,
        )

        return result

    except Exception as exc:
        logger.exception("Chat request failed")

        raise HTTPException(
            status_code=500,
            detail=f"Chat failed: {str(exc)}",
        )


# ---------------------------------------------------------
# Convert DB chunks to review sources
# ---------------------------------------------------------

def format_review_sources(rows):
    """
    Convert database chunks into the Source structure
    expected by the review pipeline.
    """

    sources = []

    for row in rows:

        sources.append(
            {
                "file": row["path"],
                "path": row["path"],
                "lines": (
                    f'{row["start_line"]}-'
                    f'{row["end_line"]}'
                ),
                "score": "1.0000",
                "content": row["content"],
            }
        )

    return sources


# ---------------------------------------------------------
# Full Repository Review Sources
# ---------------------------------------------------------

def get_full_repository_review_sources():
    """
    Retrieve every indexed repository chunk.

    Keeps both the original database line fields and the
    formatted source fields so the review pipeline can use
    either representation.
    """

    rows = get_all_chunks(limit=1000)

    sources = []

    for row in rows:
        sources.append(
            {
                "id": row["id"],
                "file": row["path"],
                "path": row["path"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "lines": (
                    f'{row["start_line"]}-'
                    f'{row["end_line"]}'
                ),
                "score": "1.0000",
                "content": row["content"],
            }
        )

    file_count = len(
        set(source["path"] for source in sources)
    )

    logger.info(
        "Full repository review: %s chunks across %s files",
        len(sources),
        file_count,
    )

    return sources


# ---------------------------------------------------------
# Legacy Diverse Review Retrieval
# ---------------------------------------------------------

def get_diverse_review_sources():
    """
    Semantic review retrieval.

    Kept as a fallback/reference implementation.

    The current /api/review endpoint uses the full repository
    review function above.
    """

    review_queries = [

        # Security
        (
            "security vulnerabilities authentication authorization "
            "credentials secrets API keys tokens passwords "
            "injection XSS CSRF"
        ),

        # Bugs / correctness
        (
            "bugs correctness exceptions error handling failure states "
            "invalid input null values race conditions unsafe operations"
        ),

        # Performance
        (
            "performance database queries SQL vector search API calls "
            "external requests network latency caching expensive operations"
        ),

        # Code quality
        (
            "code quality maintainability architecture code smells "
            "duplicated code coupling separation of concerns configuration"
        ),

        # FastAPI
        (
            "FastAPI backend routes middleware request validation "
            "response handling dependency injection"
        ),

        # Frontend
        (
            "Next.js React frontend state management fetch API "
            "error handling components security"
        ),

        # PostgreSQL
        (
            "PostgreSQL database transactions connections queries "
            "pgvector embeddings persistence"
        ),

        # LangGraph / AI
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

    # Sort strongest candidates first
    sorted_candidates = sorted(
        candidates.values(),
        key=lambda item: float(item["score"]),
        reverse=True,
    )

    # Maximum two chunks from one file
    MAX_CHUNKS_PER_FILE = 2
    MAX_REVIEW_CHUNKS = 20

    selected = []
    per_file_count = {}

    # First pass: diversity
    for item in sorted_candidates:

        path = item["path"]

        count = per_file_count.get(path, 0)

        if count >= MAX_CHUNKS_PER_FILE:
            continue

        selected.append(item)
        per_file_count[path] = count + 1

        if len(selected) >= MAX_REVIEW_CHUNKS:
            break

    # Second pass: fill remaining slots
    if len(selected) < MAX_REVIEW_CHUNKS:

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

            if len(selected) >= MAX_REVIEW_CHUNKS:
                break

    logger.info(
        "Diverse review retrieval: %s unique candidates, "
        "%s selected chunks across %s files",
        len(sorted_candidates),
        len(selected),
        len(set(item["path"] for item in selected)),
    )

    return format_review_sources(selected)


# ---------------------------------------------------------
# Repository Code Review
# ---------------------------------------------------------

@app.post(
    "/api/review",
    response_model=ReviewResponse,
)
def review():

    try:

        logger.info(
            "Starting full repository code review"
        )

        # -------------------------------------------------
        # IMPORTANT:
        # Full repository coverage.
        # Previously this used get_diverse_review_sources(),
        # which selected only 20 semantic chunks.
        # -------------------------------------------------

        sources = get_full_repository_review_sources()

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

        # -------------------------------------------------
        # Convert sources to Pydantic Source models
        # -------------------------------------------------

        formatted_sources = []

        for source in sources:

            formatted_sources.append(
                Source(
                    file=source["file"],
                    path=source["path"],
                    lines=source["lines"],
                    score=str(source["score"]),
                    content=source["content"],
                )
            )

        # -------------------------------------------------
        # Return structured review
        # -------------------------------------------------

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

        logger.exception(
            "Repository review failed"
        )

        raise HTTPException(
            status_code=500,
            detail=f"Repository review failed: {str(exc)}",
        )