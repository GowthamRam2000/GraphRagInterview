from __future__ import annotations

import hashlib
import math

from app.core.config import Settings, get_settings


def embed_texts(
    texts: list[str],
    *,
    task_type: str | None = None,
    settings: Settings | None = None,
) -> list[list[float]]:
    settings = settings or get_settings()
    clean_texts = [text.strip() for text in texts]
    if not clean_texts:
        return []
    if settings.embedding_provider == "gemini_api" and settings.gemini_api_key:
        return embed_with_gemini(clean_texts, task_type=task_type, settings=settings)
    return [deterministic_embedding(text, settings.embedding_dimension) for text in clean_texts]


def embed_query(text: str, settings: Settings | None = None) -> list[float]:
    settings = settings or get_settings()
    return embed_texts(
        [text],
        task_type="RETRIEVAL_QUERY",
        settings=settings,
    )[0]


def embed_with_gemini(
    texts: list[str],
    *,
    task_type: str | None,
    settings: Settings,
) -> list[list[float]]:
    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)
    embeddings: list[list[float]] = []
    for text in texts:
        response = client.models.embed_content(
            model=settings.embedding_model,
            contents=[text],
            config={
                "task_type": task_type or settings.embedding_task_type,
                "output_dimensionality": settings.embedding_dimension,
            },
        )
        embeddings.append(list(response.embeddings[0].values))
    return embeddings


def deterministic_embedding(text: str, dimension: int) -> list[float]:
    values: list[float] = []
    seed = text.encode("utf-8")
    counter = 0
    while len(values) < dimension:
        digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        values.extend((byte / 127.5) - 1.0 for byte in digest)
        counter += 1
    return normalize(values[:dimension])


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        vector_norm(left) * vector_norm(right)
    )


def normalize(values: list[float]) -> list[float]:
    norm = vector_norm(values)
    if norm == 0:
        return values
    return [value / norm for value in values]


def vector_norm(values: list[float]) -> float:
    return math.sqrt(sum(value * value for value in values)) or 1.0
