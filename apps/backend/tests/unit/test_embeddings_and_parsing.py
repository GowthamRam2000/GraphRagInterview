from types import SimpleNamespace

from app.services.embeddings import cosine_similarity, deterministic_embedding
from app.services.parsing import ParsedPage, pages_from_llamaparse_response


def test_llamaparse_response_pages_are_normalized() -> None:
    response = SimpleNamespace(
        model_dump=lambda: {
            "pages": [
                {"page_number": 1, "markdown": "Govern function text"},
                {"pageNum": 2, "text": "Measure function text"},
            ]
        }
    )

    pages = pages_from_llamaparse_response(response)

    assert pages == [
        ParsedPage(page_number=1, text="Govern function text"),
        ParsedPage(page_number=2, text="Measure function text"),
    ]


def test_deterministic_embeddings_support_similarity_ranking() -> None:
    query = deterministic_embedding("security and resilience", 16)
    close = deterministic_embedding("security and resilience", 16)
    far = deterministic_embedding("governance documentation", 16)

    assert cosine_similarity(query, close) > cosine_similarity(query, far)
