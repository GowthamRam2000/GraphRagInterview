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
        ParsedPage(
            page_number=1,
            text="Govern function text",
            tables=[],
            images=[],
            layout_blocks=[],
        ),
        ParsedPage(
            page_number=2,
            text="Measure function text",
            tables=[],
            images=[],
            layout_blocks=[],
        ),
    ]


def test_llamaparse_markdown_tables_and_images_are_normalized() -> None:
    response = {
        "pages": [
            {
                "page_number": 7,
                "markdown": (
                    "Lifecycle evidence.\n"
                    "<table><tr><th>Stage</th></tr><tr><td>Design</td></tr></table>\n"
                    "![AI RMF lifecycle](images/lifecycle.png)"
                ),
            }
        ]
    }

    pages = pages_from_llamaparse_response(response)

    assert pages[0].tables
    assert pages[0].tables[0]["table_id"] == "page_7_table_1"
    assert "Stage Design" in pages[0].tables[0]["summary"]
    assert pages[0].images
    assert pages[0].images[0]["caption"] == "AI RMF lifecycle"
    assert pages[0].images[0]["source_ref"] == "images/lifecycle.png"


def test_deterministic_embeddings_support_similarity_ranking() -> None:
    query = deterministic_embedding("security and resilience", 16)
    close = deterministic_embedding("security and resilience", 16)
    far = deterministic_embedding("governance documentation", 16)

    assert cosine_similarity(query, close) > cosine_similarity(query, far)
