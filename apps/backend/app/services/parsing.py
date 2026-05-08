from __future__ import annotations

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


@dataclass
class ParsedPdf:
    parser: str
    pages: list[ParsedPage]


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
                return ParsedPdf(
                    parser="llamaparse",
                    pages=parse_with_llamaparse(pdf_bytes, filename, settings),
                )
            if parser == "liteparse":
                return ParsedPdf(
                    parser="liteparse",
                    pages=parse_with_liteparse(pdf_bytes, settings),
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
    response = client.parsing.parse(
        file_id=file.id,
        tier=settings.llamaparse_tier,
        version="latest",
        expand=[settings.llamaparse_result_type],
        timeout=300,
        polling_interval=1,
    )
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
                pages.append(ParsedPage(page_number=page_number_from(item, index), text=text))
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
        ParsedPage(page_number=index, text=chunk)
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
        ParsedPage(page_number=page.pageNum, text=page.text.strip())
        for page in result.pages
        if page.text.strip()
    ]
    if not pages and result.text.strip():
        pages = split_text_response(result.text)
    if not pages:
        raise PdfParseError("LiteParse returned no page text")
    return pages
