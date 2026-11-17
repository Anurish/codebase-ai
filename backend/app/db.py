import psycopg
from pgvector.psycopg import register_vector

from .config import DEFAULT_REPOSITORY_ID, settings


def get_conn():
    conn = psycopg.connect(
        settings.database_url.replace(
            "postgresql+psycopg://",
            "postgresql://",
        )
    )
    register_vector(conn)
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS code_chunks (
                id BIGSERIAL PRIMARY KEY,
                repository TEXT NOT NULL DEFAULT 'codebase-ai',
                path TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                content TEXT NOT NULL,
                embedding vector({settings.embedding_dimensions}) NOT NULL
            )
            """
        )

        conn.execute(
            """
            ALTER TABLE code_chunks
            ADD COLUMN IF NOT EXISTS repository TEXT NOT NULL
            DEFAULT 'codebase-ai'
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS code_chunks_path_idx
            ON code_chunks(path)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS code_chunks_repository_path_idx
            ON code_chunks(repository, path)
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS repositories (
                repository TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                github_url TEXT,
                branch TEXT,
                indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        conn.execute(
            """
            INSERT INTO repositories(repository, name)
            VALUES (%s, %s)
            ON CONFLICT (repository) DO NOTHING
            """,
            (DEFAULT_REPOSITORY_ID, DEFAULT_REPOSITORY_ID),
        )

        conn.commit()


def replace_index(
    repository: str,
    rows,
    name: str,
    github_url: str | None = None,
    branch: str | None = None,
):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM code_chunks WHERE repository = %s",
            (repository,),
        )

        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO code_chunks(
                    repository,
                    path,
                    start_line,
                    end_line,
                    content,
                    embedding
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [(repository, *row) for row in rows],
            )

        conn.execute(
            """
            INSERT INTO repositories(
                repository,
                name,
                github_url,
                branch,
                indexed_at
            )
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (repository) DO UPDATE SET
                name = EXCLUDED.name,
                github_url = EXCLUDED.github_url,
                branch = EXCLUDED.branch,
                indexed_at = NOW()
            """,
            (repository, name, github_url, branch),
        )

        conn.commit()


def get_repositories():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                repositories.repository,
                repositories.name,
                repositories.github_url,
                repositories.branch,
                COUNT(code_chunks.id) AS chunks,
                COUNT(DISTINCT code_chunks.path) AS files
            FROM repositories
            LEFT JOIN code_chunks
                ON code_chunks.repository = repositories.repository
            GROUP BY
                repositories.repository,
                repositories.name,
                repositories.github_url,
                repositories.branch,
                repositories.indexed_at
            ORDER BY repositories.indexed_at DESC, repositories.name
            """
        ).fetchall()

    return [
        {
            "repository": row[0],
            "name": row[1],
            "github_url": row[2],
            "branch": row[3],
            "chunks": int(row[4]),
            "files": int(row[5]),
        }
        for row in rows
    ]


def search_chunks(embedding, repository: str, limit=6):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                path,
                start_line,
                end_line,
                content,
                1 - (
                    embedding <=> CAST(%s AS vector)
                ) AS score
            FROM code_chunks
            WHERE repository = %s
            ORDER BY embedding <=> CAST(%s AS vector)
            LIMIT %s
            """,
            (embedding, repository, embedding, limit),
        ).fetchall()

    return [
        {
            "path": row[0],
            "start_line": row[1],
            "end_line": row[2],
            "content": row[3],
            "score": float(row[4]),
        }
        for row in rows
    ]

def get_all_chunks(repository: str, limit: int = 1000):
    """
    Return all indexed repository chunks for full repository review.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                path,
                start_line,
                end_line,
                content
            FROM code_chunks
            WHERE repository = %s
            ORDER BY path, start_line
            LIMIT %s
            """,
            (repository, limit),
        ).fetchall()

    return [
        {
            "id": row[0],
            "path": row[1],
            "start_line": row[2],
            "end_line": row[3],
            "content": row[4],
        }
        for row in rows
    ]