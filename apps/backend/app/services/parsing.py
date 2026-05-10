from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from app.core.config import Settings, get_settings


class PdfParseError(RuntimeError):
    pass


@dataclass
class ParsedPage:
    page_number: int
    text: str
    tables: list[dict] | None = None
    images: list[dict] | None = None
    layout_blocks: list[dict] | None = None


@dataclass
class ParsedPdf:
    parser: str
    pages: list[ParsedPage]
    metadata: dict | None = None


def parse_pdf_bytes(
    pdf_bytes: bytes,
    filename: str,
    settings: Settings | None = None,
) -> ParsedPdf:
    settings = settings or get_settings()
    errors: list[str] = []
    parsers = [settings.parser_primary, settings.parser_fallback]
    for parser in parsers:
        try:
            if parser == "llamaparse":
                pages = parse_with_llamaparse(pdf_bytes, filename, settings)
                return ParsedPdf(
                    parser="llamaparse",
                    pages=pages,
                    metadata={
                        "tier": settings.llamaparse_tier,
                        "result_type": settings.llamaparse_result_type,
                        "image_extraction": ["screenshot", "embedded", "layout"],
                    },
                )
            if parser == "liteparse":
                pages = parse_with_liteparse(pdf_bytes, settings)
                return ParsedPdf(
                    parser="liteparse",
                    pages=pages,
                    metadata={
                        "ocr_enabled": settings.liteparse_ocr_enabled,
                        "dpi": settings.liteparse_dpi,
                    },
                )
        except Exception as exc:
            errors.append(f"{parser}: {type(exc).__name__}: {exc}")

    raise PdfParseError("PDF parsing failed through configured parsers: " + "; ".join(errors))


def parse_with_llamaparse(
    pdf_bytes: bytes,
    filename: str,
    settings: Settings,
) -> list[ParsedPage]:
    if not settings.llama_cloud_api_key:
        raise PdfParseError("LLAMA_CLOUD_API_KEY is not configured")

    from llama_cloud import LlamaCloud

    client = LlamaCloud(api_key=settings.llama_cloud_api_key, timeout=300)
    file = client.files.create(
        file=(filename, BytesIO(pdf_bytes), "application/pdf"),
        purpose="parse",
    )
    parse_kwargs = {
        "file_id": file.id,
        "tier": settings.llamaparse_tier,
        "version": "latest",
        "expand": [settings.llamaparse_result_type],
        "images_to_save": ["screenshot", "embedded", "layout"],
        "timeout": 300,
        "polling_interval": 1,
    }
    try:
        response = client.parsing.parse(**parse_kwargs)
    except TypeError:
        parse_kwargs.pop("images_to_save", None)
        response = client.parsing.parse(**parse_kwargs)
    pages = pages_from_llamaparse_response(response)
    if not pages:
        raise PdfParseError("LlamaParse returned no page text")
    return pages


def pages_from_llamaparse_response(response: Any) -> list[ParsedPage]:
    payload = response.model_dump() if hasattr(response, "model_dump") else response
    pages = pages_from_payload(payload)
    if pages:
        return pages
    text = first_text_value(payload)
    return split_text_response(text)


def pages_from_payload(payload: Any) -> list[ParsedPage]:
    if isinstance(payload, list):
        pages: list[ParsedPage] = []
        for index, item in enumerate(payload, start=1):
            text = first_text_value(item)
            if text:
                pages.append(
                    ParsedPage(
                        page_number=page_number_from(item, index),
                        text=text,
                        tables=table_payloads_from_item(item, text),
                        images=image_payloads_from_item(item, text),
                        layout_blocks=layout_blocks_from_item(item),
                    )
                )
        return pages
    if not isinstance(payload, dict):
        return []

    candidate = payload.get("pages") or payload.get("documents") or payload.get("result")
    if candidate is not None:
        pages = pages_from_payload(candidate)
        if pages:
            return pages
    for value in payload.values():
        pages = pages_from_payload(value)
        if pages:
            return pages
    return []


def first_text_value(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, dict):
        for key in ("markdown", "md", "text", "content", "page_text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def page_number_from(payload: Any, fallback: int) -> int:
    if not isinstance(payload, dict):
        return fallback
    value = payload.get("page_number") or payload.get("pageNum") or payload.get("page")
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def split_text_response(text: str, max_chars: int = 1800) -> list[ParsedPage]:
    clean = text.strip()
    if not clean:
        return []
    chunks = [clean[index : index + max_chars].strip() for index in range(0, len(clean), max_chars)]
    return [
        ParsedPage(
            page_number=index,
            text=chunk,
            tables=extract_tables_from_markdown(chunk, index),
            images=extract_images_from_markdown(chunk, index),
            layout_blocks=[],
        )
        for index, chunk in enumerate(chunks, start=1)
    ]


def parse_with_liteparse(pdf_bytes: bytes, settings: Settings) -> list[ParsedPage]:
    from liteparse import LiteParse

    result = LiteParse().parse(
        pdf_bytes,
        ocr_enabled=settings.liteparse_ocr_enabled,
        dpi=settings.liteparse_dpi,
        timeout=300,
    )
    pages = [
        ParsedPage(
            page_number=page.pageNum,
            text=page.text.strip(),
            tables=extract_tables_from_markdown(page.text.strip(), page.pageNum),
            images=extract_images_from_markdown(page.text.strip(), page.pageNum),
            layout_blocks=[],
        )
        for page in result.pages
        if page.text.strip()
    ]
    if not pages and result.text.strip():
        pages = split_text_response(result.text)
    if not pages:
        raise PdfParseError("LiteParse returned no page text")
    return pages


def table_payloads_from_item(item: Any, text: str) -> list[dict]:
    explicit = []
    if isinstance(item, dict):
        for key in ("tables", "table", "structured_tables"):
            value = item.get(key)
            if isinstance(value, list):
                explicit.extend(value)
    extracted = extract_tables_from_markdown(text, page_number_from(item, 1))
    normalized = []
    for index, table in enumerate([*explicit, *extracted], start=1):
        if isinstance(table, dict):
            markdown = table.get("markdown") or table.get("html") or table.get("text") or str(table)
            normalized.append(
                {
                    "table_id": str(table.get("table_id") or table.get("id") or f"table_{index}"),
                    "markdown": markdown,
                    "summary": summarize_table(markdown),
                    "metadata": {
                        key: value
                        for key, value in table.items()
                        if key not in {"markdown", "html", "text"}
                    },
                }
            )
        elif isinstance(table, str):
            normalized.append(
                {
                    "table_id": f"table_{index}",
                    "markdown": table,
                    "summary": summarize_table(table),
                    "metadata": {},
                }
            )
    return normalized


def image_payloads_from_item(item: Any, text: str) -> list[dict]:
    explicit = []
    if isinstance(item, dict):
        for key in ("images", "image", "figures"):
            value = item.get(key)
            if isinstance(value, list):
                explicit.extend(value)
    extracted = extract_images_from_markdown(text, page_number_from(item, 1))
    normalized = []
    for index, image in enumerate([*explicit, *extracted], start=1):
        if isinstance(image, dict):
            caption = (
                image.get("caption")
                or image.get("alt")
                or image.get("description")
                or image.get("text")
                or f"Image {index}"
            )
            normalized.append(
                {
                    "image_id": str(image.get("image_id") or image.get("id") or f"image_{index}"),
                    "caption": str(caption),
                    "source_ref": (
                        image.get("source_ref")
                        or image.get("path")
                        or image.get("url")
                        or image.get("name")
                    ),
                    "image_data": (
                        image.get("image_data") or image.get("data") or image.get("base64")
                    ),
                    "mime_type": image.get("mime_type") or image.get("content_type"),
                    "extension": image.get("extension") or image.get("ext"),
                    "metadata": {
                        key: value
                        for key, value in image.items()
                        if key
                        not in {
                            "caption",
                            "alt",
                            "description",
                            "text",
                            "path",
                            "url",
                            "name",
                            "source_ref",
                            "image_data",
                            "data",
                            "base64",
                            "mime_type",
                            "content_type",
                            "extension",
                            "ext",
                        }
                    },
                }
            )
        elif isinstance(image, str):
            normalized.append(
                {
                    "image_id": f"image_{index}",
                    "caption": image,
                    "source_ref": None,
                    "metadata": {},
                }
            )
    return normalized


def layout_blocks_from_item(item: Any) -> list[dict]:
    if not isinstance(item, dict):
        return []
    for key in ("layout", "layout_blocks", "blocks", "items"):
        value = item.get(key)
        if isinstance(value, list):
            return [block for block in value if isinstance(block, dict)]
    return []


def extract_tables_from_markdown(text: str, page_number: int) -> list[dict]:
    tables: list[dict] = []
    for index, match in enumerate(
        re.finditer(r"<table\b.*?</table>", text, flags=re.IGNORECASE | re.DOTALL),
        start=1,
    ):
        markdown = match.group(0).strip()
        tables.append(
            {
                "table_id": f"page_{page_number}_table_{index}",
                "markdown": markdown,
                "summary": summarize_table(markdown),
                "metadata": {"source": "markdown_html_table"},
            }
        )
    return tables


def extract_images_from_markdown(text: str, page_number: int) -> list[dict]:
    images: list[dict] = []
    pattern = r"!\[(?P<alt>[^\]]*)\]\((?P<ref>[^)]+)\)"
    for index, match in enumerate(re.finditer(pattern, text), start=1):
        alt = match.group("alt").strip()
        source_ref = match.group("ref").strip()
        images.append(
            {
                "image_id": f"page_{page_number}_image_{index}",
                "caption": alt or f"Image reference {source_ref}",
                "source_ref": source_ref,
                "metadata": {"source": "markdown_image"},
            }
        )
    return images


def summarize_table(markdown: str, max_chars: int = 360) -> str:
    text = re.sub(r"<[^>]+>", " ", markdown)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "Extracted table."
    return text[: max_chars - 1].rstrip() + ("..." if len(text) >= max_chars else "")
