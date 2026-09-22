import psycopg
from pgvector.psycopg import register_vector

from .config import settings


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
            CREATE INDEX IF NOT EXISTS code_chunks_path_idx
            ON code_chunks(path)
            """
        )

        conn.commit()


def clear_index():
    with get_conn() as conn:
        conn.execute("DELETE FROM code_chunks")
        conn.commit()


def insert_chunks(rows):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO code_chunks(
                    path,
                    start_line,
                    end_line,
                    content,
                    embedding
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                rows,
            )

        conn.commit()


def search_chunks(embedding, limit=6):
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
            ORDER BY embedding <=> CAST(%s AS vector)
            LIMIT %s
            """,
            (embedding, embedding, limit),
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

def get_all_chunks(limit: int = 1000):
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
            ORDER BY path, start_line
            LIMIT %s
            """,
            (limit,),
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