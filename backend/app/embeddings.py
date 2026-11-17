
import logging
import time

from google import genai
from google.genai import types

from .config import settings


logger = logging.getLogger(__name__)

client = None

# Keep requests small to reduce token-per-minute spikes.
BATCH_SIZE = 5
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 5


def get_client():
    """Build the Gemini client on demand so imports stay test-friendly."""

    global client

    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    if client is None:
        client = genai.Client(api_key=settings.gemini_api_key)

    return client


def embed_texts(texts: list[str], task_type: str):
    """
    Generate embeddings in small batches.

    Retries temporary quota and service errors with exponential
    backoff. Returns vectors in the same order as the input texts.
    """

    if not texts:
        return []

    normalized_texts = []
    for text in texts:
        if text is None:
            raise ValueError("Embedding text cannot be None.")
        normalized = str(text).strip()
        if not normalized:
            raise ValueError("Embedding text cannot be empty.")
        normalized_texts.append(normalized)

    all_embeddings = []
    gemini_client = get_client()

    for start in range(0, len(normalized_texts), BATCH_SIZE):
        batch = normalized_texts[start:start + BATCH_SIZE]

        for attempt in range(MAX_RETRIES):
            try:
                result = gemini_client.models.embed_content(
                    model=settings.embedding_model,
                    contents=batch,
                    config=types.EmbedContentConfig(
                        task_type=task_type,
                        output_dimensionality=settings.embedding_dimensions,
                    ),
                )

                if not result.embeddings:
                    raise RuntimeError(
                        "Gemini returned no embeddings for a non-empty batch."
                    )

                batch_embeddings = [
                    embedding.values
                    for embedding in result.embeddings
                ]

                if len(batch_embeddings) != len(batch):
                    raise RuntimeError(
                        "Gemini returned a different number of embeddings "
                        "than the number of input texts."
                    )

                all_embeddings.extend(batch_embeddings)

                logger.info(
                    "Embedded batch %s-%s of %s",
                    start + 1,
                    start + len(batch),
                    len(normalized_texts),
                )

                # Small pause between successful requests.
                if start + BATCH_SIZE < len(normalized_texts):
                    time.sleep(2)

                break

            except Exception as exc:
                error_text = str(exc).upper()

                is_temporary = any(
                    marker in error_text
                    for marker in (
                        "429",
                        "RESOURCE_EXHAUSTED",
                        "503",
                        "UNAVAILABLE",
                        "500",
                        "INTERNAL",
                        "RATE LIMIT",
                    )
                )

                if not is_temporary or attempt == MAX_RETRIES - 1:
                    logger.exception(
                        "Embedding batch failed at input %s-%s",
                        start + 1,
                        start + len(batch),
                    )
                    raise

                delay = INITIAL_RETRY_DELAY * (2 ** attempt)

                logger.warning(
                    "Temporary Gemini embedding error. "
                    "Retrying batch in %s seconds (attempt %s/%s): %s",
                    delay,
                    attempt + 1,
                    MAX_RETRIES,
                    exc,
                )

                time.sleep(delay)

    return all_embeddings


def embed_query(text: str):
    if text is None:
        raise ValueError("Embedding query text cannot be None.")

    cleaned_text = str(text).strip()
    if not cleaned_text:
        raise ValueError("Embedding query text cannot be empty.")

    embeddings = embed_texts(
        [cleaned_text],
        task_type="RETRIEVAL_QUERY",
    )

    if not embeddings:
        raise RuntimeError("Gemini returned no embedding for the query.")

    return embeddings[0]
