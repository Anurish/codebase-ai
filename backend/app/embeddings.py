from google import genai
from google.genai import types

from .config import settings


client = genai.Client(api_key=settings.gemini_api_key)


def embed_texts(texts: list[str], task_type: str):
    result = client.models.embed_content(
        model=settings.embedding_model,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=settings.embedding_dimensions,
        ),
    )

    return [embedding.values for embedding in result.embeddings]


def embed_query(text: str):
    return embed_texts([text], "RETRIEVAL_QUERY")[0]