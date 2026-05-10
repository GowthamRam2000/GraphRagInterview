from __future__ import annotations

import re
from base64 import b64decode
from collections import Counter, defaultdict

from app.core.config import get_settings
from app.models.schemas import (
    DocumentSummary,
    FinalizeDocumentRequest,
    IngestionStatus,
    OntologyObjectType,
    OntologyRelationship,
    OntologyResponse,
    PageStatus,
    UploadUrlRequest,
    UploadUrlResponse,
)
from app.rag.ontology_extractor import ExtractedObject, ExtractedOntology, extract_ontology_for_page
from app.services.artifacts import (
    ArtifactManifest,
    StoredArtifact,
    upload_image_asset,
    upload_image_metadata,
    upload_page_markdown,
    upload_table_json,
)
from app.services.embeddings import embed_texts
from app.services.parsing import (
    ParsedPage,
    ParsedPdf,
    extract_images_from_markdown,
    extract_tables_from_markdown,
)
from app.services.store import (
    STORE,
    DocumentRecord,
    EntityRecord,
    EvidenceRecord,
    ImageRecord,
    PageRecord,
    RelationshipRecord,
    TableRecord,
    hydrate_store,
    new_id,
    persist_document_state,
)

ENTITY_PATTERN = re.compile(r"\b(?:[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+){0,4})\b")
STOP_ENTITIES = {"The", "A", "An", "This", "That", "It"}


def create_upload(request: UploadUrlRequest) -> UploadUrlResponse:
    hydrate_store()
    settings = get_settings()
    document_id = new_id("doc")
    gcs_uri = f"gs://{settings.gcs_bucket_raw}/raw/{document_id}/{request.filename}"
    upload_url = f"local-upload://{document_id}/{request.filename}"
    STORE.documents[document_id] = DocumentRecord(
        document_id=document_id,
        filename=request.filename,
        status="upload_url_created",
        upload_url=upload_url,
        gcs_uri=gcs_uri,
    )
    persist_document_state(document_id)
    return UploadUrlResponse(
        document_id=document_id,
        upload_url=upload_url,
        gcs_uri=gcs_uri,
        status="upload_url_created",
    )


def list_documents() -> list[DocumentSummary]:
    hydrate_store()
    return [
        DocumentSummary(
            document_id=document.document_id,
            filename=document.filename,
            title=document.title,
            status=document.status,
            page_count=len(document.pages),
        )
        for document in sorted(STORE.documents.values(), key=lambda item: item.created_at)
    ]


def get_document_or_none(document_id: str) -> DocumentRecord | None:
    hydrate_store()
    return STORE.documents.get(document_id)


def finalize_document(document_id: str, request: FinalizeDocumentRequest) -> IngestionStatus | None:
    pages = [
        ParsedPage(
            page_number=index,
            text=text,
            tables=extract_tables_from_markdown(text, index),
            images=extract_images_from_markdown(text, index),
            layout_blocks=[],
        )
        for index, text in enumerate(
            request.pages or split_text_into_pages(request.text or ""),
            start=1,
        )
    ]
    parsed = ParsedPdf(
        parser="manual",
        pages=pages
        or [
            ParsedPage(
                page_number=1,
                text="No extractable text was provided for this document.",
            )
        ],
        metadata={"source": "finalize_endpoint", "legacy_text_only": True},
    )
    return finalize_parsed_document(
        document_id,
        parsed,
        title=request.title,
        raw_pdf_gcs_uri=None,
        legacy_text_only=True,
    )


def finalize_parsed_document(
    document_id: str,
    parsed: ParsedPdf,
    title: str | None = None,
    raw_pdf_gcs_uri: str | None = None,
    legacy_text_only: bool = False,
) -> IngestionStatus | None:
    hydrate_store()
    document = STORE.documents.get(document_id)
    if document is None:
        return None

    pages = parsed.pages or [
        ParsedPage(page_number=1, text="No extractable text was provided for this document.")
    ]
    settings = get_settings()
    manifest = ArtifactManifest(raw_pdf_gcs_uri=raw_pdf_gcs_uri or document.raw_pdf_gcs_uri)

    document.title = title or document.filename
    if raw_pdf_gcs_uri:
        document.raw_pdf_gcs_uri = raw_pdf_gcs_uri
        document.gcs_uri = raw_pdf_gcs_uri
    document.parser_metadata = {
        "parser": parsed.parser,
        **(parsed.metadata or {}),
    }
    document.legacy_text_only = legacy_text_only
    document.pages.clear()
    document.status = "processing"
    remove_existing_document_graph(document_id)

    previous_entity_id: str | None = None
    for index, parsed_page in enumerate(pages, start=1):
        page_number = parsed_page.page_number or index
        page_text = parsed_page.text
        tables = normalize_tables(document_id, page_number, parsed_page.tables or [], manifest)
        images = normalize_images(document_id, page_number, parsed_page.images or [], manifest)
        page_artifact = upload_page_markdown(document_id, page_number, page_text, settings)
        if page_artifact.error:
            manifest.errors.append(f"page {page_number}: {page_artifact.error}")
        if page_artifact.stored:
            manifest.page_markdown_uris[page_number] = page_artifact.uri

        fallback_entities = extract_entities(page_text)
        ontology = extract_ontology_for_page(
            page_text=page_text,
            page_number=page_number,
            fallback_names=fallback_entities,
            tables=[table_to_simple_dict(table) for table in tables],
            images=[image_to_simple_dict(image) for image in images],
        )
        entities = unique_ontology_objects(ontology, fallback_entities)
        page_entity_names = [item.name for item in entities]
        text_evidence_ids = create_text_evidence(
            document_id=document_id,
            page_number=page_number,
            page_text=page_text,
            entities=page_entity_names,
            page_artifact_uri=page_artifact.uri if page_artifact.stored else None,
            ontology=ontology,
        )
        primary_evidence_id = text_evidence_ids[0]

        page_entity_ids: list[str] = []
        for extracted in entities:
            entity_id = stable_entity_id(document_id, extracted.name)
            entity = STORE.entities.setdefault(
                entity_id,
                EntityRecord(
                    entity_id=entity_id,
                    document_id=document_id,
                    name=extracted.name,
                    label=extracted.label,
                    confidence=extracted.confidence,
                    properties=extracted.properties,
                ),
            )
            entity.label = extracted.label
            entity.confidence = max(entity.confidence, extracted.confidence)
            entity.properties.update(extracted.properties)
            entity.page_numbers.add(page_number)
            entity.evidence_ids.update(text_evidence_ids)
            page_entity_ids.append(entity_id)

        for relationship in ontology.relationships:
            source_id = stable_entity_id(document_id, relationship.source)
            target_id = stable_entity_id(document_id, relationship.target)
            if source_id in STORE.entities and target_id in STORE.entities:
                STORE.relationships.append(
                    RelationshipRecord(
                        source_entity_id=source_id,
                        relationship_type=relationship.relationship_type,
                        target_entity_id=target_id,
                        evidence_id=primary_evidence_id,
                        confidence=relationship.confidence,
                    )
                )

        for source_id, target_id in zip(page_entity_ids, page_entity_ids[1:], strict=False):
            STORE.relationships.append(
                RelationshipRecord(
                    source_entity_id=source_id,
                    relationship_type="RELATED_TO",
                    target_entity_id=target_id,
                    evidence_id=primary_evidence_id,
                    confidence=0.5,
                )
            )
        if previous_entity_id and page_entity_ids:
            STORE.relationships.append(
                RelationshipRecord(
                    source_entity_id=previous_entity_id,
                    relationship_type="NEXT_PAGE_CONTEXT",
                    target_entity_id=page_entity_ids[0],
                    evidence_id=primary_evidence_id,
                    confidence=0.5,
                )
            )
        if page_entity_ids:
            previous_entity_id = page_entity_ids[-1]

        evidence_ids = list(text_evidence_ids)
        evidence_ids.extend(create_table_evidence(document_id, tables, page_entity_names))
        evidence_ids.extend(create_image_evidence(document_id, images, page_entity_names))

        document.pages[page_number] = PageRecord(
            page_number=page_number,
            text=page_text,
            entity_ids=page_entity_ids,
            evidence_ids=evidence_ids,
            tables=tables,
            images=images,
            layout_blocks=parsed_page.layout_blocks or [],
            artifact_uris={
                "page_markdown": page_artifact.uri if page_artifact.stored else "",
            },
        )

    hydrate_evidence_embeddings(document_id)
    document.status = "completed"
    document.artifact_gcs_uris = manifest.all_uris()
    if manifest.errors:
        document.parser_metadata["artifact_errors"] = manifest.errors
    persist_document_state(document_id)
    return get_ingestion_status(document_id)


def get_ingestion_status(document_id: str) -> IngestionStatus | None:
    hydrate_store()
    document = STORE.documents.get(document_id)
    if document is None:
        return None
    pages = [
        PageStatus(
            page_number=page.page_number,
            status=page.status,
            entity_count=len(page.entity_ids),
            evidence_count=len(page.evidence_ids),
        )
        for page in sorted(document.pages.values(), key=lambda item: item.page_number)
    ]
    return IngestionStatus(
        document_id=document_id,
        status=document.status,
        page_count=len(document.pages),
        pages=pages,
    )


def get_ontology(document_id: str) -> OntologyResponse | None:
    hydrate_store()
    document = STORE.documents.get(document_id)
    if document is None:
        return None

    document_entities = [
        entity for entity in STORE.entities.values() if entity.document_id == document_id
    ]
    entity_names = [entity.name for entity in document_entities]
    typed_counts: Counter[str] = Counter(entity.label or "Entity" for entity in document_entities)
    typed_examples: defaultdict[str, list[str]] = defaultdict(list)
    typed_properties: defaultdict[str, set[str]] = defaultdict(set)
    for entity in document_entities:
        if len(typed_examples[entity.label]) < 5:
            typed_examples[entity.label].append(entity.name)
        typed_properties[entity.label].update(entity.properties.keys())
    object_types = [
        OntologyObjectType(
            label="Document",
            count=1,
            properties=["document_id", "filename", "title", "status", "page_count"],
            examples=[document.title or document.filename],
        ),
        OntologyObjectType(
            label="Page",
            count=len(document.pages),
            properties=["page_number", "text", "status"],
            examples=[f"Page {page_number}" for page_number in sorted(document.pages)[:3]],
        ),
        OntologyObjectType(
            label="EvidenceSpan",
            count=sum(len(page.evidence_ids) for page in document.pages.values()),
            properties=["evidence_id", "page_number", "text", "entities"],
            examples=[
                evidence.text[:120]
                for evidence in STORE.evidence.values()
                if evidence.document_id == document_id
            ][:3],
        ),
        OntologyObjectType(
            label="Entity",
            count=len(entity_names),
            properties=["entity_id", "name", "label", "page_numbers", "evidence_ids", "confidence"],
            examples=entity_names[:5],
        ),
    ]
    for label, count in sorted(typed_counts.items()):
        if label == "Entity":
            continue
        object_types.append(
            OntologyObjectType(
                label=label,
                count=count,
                properties=sorted(typed_properties[label])
                or ["entity_id", "name", "page_numbers", "evidence_ids", "confidence"],
                examples=typed_examples[label],
            )
        )

    relationship_counts: Counter[str] = Counter()
    relationship_examples: defaultdict[str, list[str]] = defaultdict(list)
    for relationship in STORE.relationships:
        source = STORE.entities.get(relationship.source_entity_id)
        target = STORE.entities.get(relationship.target_entity_id)
        if source is None or target is None or source.document_id != document_id:
            continue
        relationship_counts[relationship.relationship_type] += 1
        if len(relationship_examples[relationship.relationship_type]) < 3:
            relationship_examples[relationship.relationship_type].append(
                f"{source.name} -> {target.name}"
            )

    relationships = [
        OntologyRelationship(
            type=relationship_type,
            source_label="Entity",
            target_label="Entity",
            count=count,
            examples=relationship_examples[relationship_type],
        )
        for relationship_type, count in sorted(relationship_counts.items())
    ]
    relationships.insert(
        0,
        OntologyRelationship(
            type="HAS_PAGE",
            source_label="Document",
            target_label="Page",
            count=len(document.pages),
            examples=[f"{document.title or document.filename} -> Page 1"] if document.pages else [],
        ),
    )
    object_edges = [
        {
            "entity_id": entity.entity_id,
            "name": entity.name,
            "label": entity.label,
            "page_numbers": sorted(entity.page_numbers),
            "evidence_ids": sorted(entity.evidence_ids),
            "confidence": entity.confidence,
            "properties": entity.properties,
        }
        for entity in document_entities
    ]
    relationship_edges = []
    for relationship in STORE.relationships:
        source = STORE.entities.get(relationship.source_entity_id)
        target = STORE.entities.get(relationship.target_entity_id)
        if source is None or target is None or source.document_id != document_id:
            continue
        relationship_edges.append(
            {
                "source_entity_id": relationship.source_entity_id,
                "source": source.name,
                "relationship_type": relationship.relationship_type,
                "target_entity_id": relationship.target_entity_id,
                "target": target.name,
                "evidence_id": relationship.evidence_id,
                "confidence": relationship.confidence,
            }
        )

    return OntologyResponse(
        document_id=document_id,
        object_types=object_types,
        relationships=relationships,
        objects=object_edges,
        relationship_edges=relationship_edges,
    )


def split_text_into_pages(text: str, max_chars: int = 1800) -> list[str]:
    clean = text.strip()
    if not clean:
        return []
    return [clean[index : index + max_chars].strip() for index in range(0, len(clean), max_chars)]


def normalize_tables(
    document_id: str,
    page_number: int,
    table_payloads: list[dict],
    manifest: ArtifactManifest,
) -> list[TableRecord]:
    records: list[TableRecord] = []
    settings = get_settings()
    for index, payload in enumerate(table_payloads, start=1):
        table_id = stable_asset_id(
            document_id,
            "table",
            payload.get("table_id") or f"page_{page_number}_table_{index}",
        )
        markdown = str(payload.get("markdown") or payload.get("html") or payload.get("text") or "")
        summary = str(
            payload.get("summary") or summarize_artifact_text(markdown, "Extracted table.")
        )
        artifact = upload_table_json(
            document_id,
            page_number,
            table_id,
            {
                "table_id": table_id,
                "markdown": markdown,
                "summary": summary,
                "metadata": payload.get("metadata", {}),
            },
            settings,
        )
        if artifact.error:
            manifest.errors.append(f"table {table_id}: {artifact.error}")
        if artifact.stored:
            manifest.table_uris[table_id] = artifact.uri
        records.append(
            TableRecord(
                table_id=table_id,
                page_number=page_number,
                markdown=markdown,
                summary=summary,
                artifact_uri=artifact.uri if artifact.stored else None,
                metadata=dict(payload.get("metadata", {})),
            )
        )
    return records


def normalize_images(
    document_id: str,
    page_number: int,
    image_payloads: list[dict],
    manifest: ArtifactManifest,
) -> list[ImageRecord]:
    records: list[ImageRecord] = []
    settings = get_settings()
    for index, payload in enumerate(image_payloads, start=1):
        image_id = stable_asset_id(
            document_id,
            "image",
            payload.get("image_id") or f"page_{page_number}_image_{index}",
        )
        caption = str(payload.get("caption") or payload.get("alt") or "Extracted image.")
        source_ref = payload.get("source_ref") or payload.get("path") or payload.get("url")
        metadata = dict(payload.get("metadata", {}))
        metadata["source_ref"] = source_ref
        asset_artifact = upload_image_bytes_if_present(
            document_id=document_id,
            page_number=page_number,
            image_id=image_id,
            payload=payload,
            manifest=manifest,
            settings=settings,
        )
        if asset_artifact.stored:
            metadata["asset_uri"] = asset_artifact.uri
        artifact = upload_image_metadata(
            document_id,
            page_number,
            image_id,
            {
                "image_id": image_id,
                "caption": caption,
                "source_ref": source_ref,
                "asset_uri": asset_artifact.uri if asset_artifact.stored else None,
                "metadata": metadata,
            },
            settings,
        )
        if artifact.error:
            manifest.errors.append(f"image {image_id}: {artifact.error}")
        if artifact.stored:
            manifest.image_uris[image_id] = artifact.uri
        records.append(
            ImageRecord(
                image_id=image_id,
                page_number=page_number,
                caption=caption,
                source_ref=source_ref,
                artifact_uri=(
                    asset_artifact.uri
                    if asset_artifact.stored
                    else artifact.uri
                    if artifact.stored
                    else None
                ),
                metadata=metadata,
            )
        )
    return records


def upload_image_bytes_if_present(
    document_id: str,
    page_number: int,
    image_id: str,
    payload: dict,
    manifest: ArtifactManifest,
    settings,
) -> StoredArtifact:
    raw_data = payload.get("image_data") or payload.get("data") or payload.get("base64")
    if not raw_data:
        return StoredArtifact(uri="", stored=False)
    try:
        if isinstance(raw_data, bytes):
            content = raw_data
        else:
            text_data = str(raw_data)
            if "," in text_data and text_data.strip().startswith("data:"):
                text_data = text_data.split(",", 1)[1]
            content = b64decode(text_data, validate=False)
    except Exception as exc:
        manifest.errors.append(f"image {image_id}: invalid image data {type(exc).__name__}")
        return StoredArtifact(uri="", stored=False, error=str(exc))
    content_type = str(payload.get("mime_type") or payload.get("content_type") or "image/png")
    extension = str(
        payload.get("extension") or payload.get("ext") or content_type.rsplit("/", 1)[-1]
    )
    artifact = upload_image_asset(
        document_id=document_id,
        page_number=page_number,
        image_id=image_id,
        content=content,
        extension=extension,
        content_type=content_type,
        settings=settings,
    )
    if artifact.error:
        manifest.errors.append(f"image asset {image_id}: {artifact.error}")
    if artifact.stored:
        manifest.image_uris[image_id] = artifact.uri
    return artifact


def create_text_evidence(
    document_id: str,
    page_number: int,
    page_text: str,
    entities: list[str],
    page_artifact_uri: str | None,
    ontology: ExtractedOntology,
) -> list[str]:
    spans = split_page_text_into_evidence_spans(page_text)
    evidence_ids: list[str] = []
    span_count = len(spans)
    for index, span in enumerate(spans, start=1):
        evidence_id = new_id("ev")
        STORE.evidence[evidence_id] = EvidenceRecord(
            evidence_id=evidence_id,
            document_id=document_id,
            page_number=page_number,
            text=span,
            entities=entities,
            evidence_type="text",
            artifact_uri=page_artifact_uri,
            content_summary=summarize_artifact_text(span, "Text evidence span."),
            metadata={
                "ontology_status": ontology.status,
                "extractor_model_call": ontology.model_call,
                "span_index": index,
                "span_count": span_count,
                "page_artifact_uri": page_artifact_uri,
            },
        )
        evidence_ids.append(evidence_id)
    return evidence_ids


def split_page_text_into_evidence_spans(
    text: str,
    max_chars: int = 650,
    min_chars: int = 120,
) -> list[str]:
    clean = text.strip()
    if not clean:
        return ["No extractable text was provided for this document."]
    blocks = [block.strip() for block in re.split(r"\n{2,}", clean) if block.strip()]
    spans: list[str] = []
    current = ""
    for block in blocks or [clean]:
        for piece in split_long_block(block, max_chars):
            candidate = f"{current}\n\n{piece}".strip() if current else piece
            if current and len(candidate) > max_chars:
                spans.append(current)
                current = piece
            else:
                current = candidate
    if current:
        spans.append(current)

    merged: list[str] = []
    for span in spans:
        if merged and len(span) < min_chars and len(merged[-1]) + len(span) + 2 <= max_chars:
            merged[-1] = f"{merged[-1]}\n\n{span}"
        else:
            merged.append(span)
    return merged or [clean[:max_chars]]


def split_long_block(block: str, max_chars: int) -> list[str]:
    if len(block) <= max_chars:
        return [block]
    pieces: list[str] = []
    remaining = block
    while len(remaining) > max_chars:
        split_at = max(
            remaining.rfind("\n", 0, max_chars),
            remaining.rfind(". ", 0, max_chars),
            remaining.rfind("; ", 0, max_chars),
            remaining.rfind(" ", 0, max_chars),
        )
        if split_at < max_chars // 2:
            split_at = max_chars
        piece = remaining[:split_at].strip()
        if piece:
            pieces.append(piece)
        remaining = remaining[split_at:].strip()
    if remaining:
        pieces.append(remaining)
    return pieces


def create_table_evidence(
    document_id: str,
    tables: list[TableRecord],
    page_entities: list[str],
) -> list[str]:
    evidence_ids: list[str] = []
    for table in tables:
        evidence_id = new_id("ev")
        table.evidence_id = evidence_id
        STORE.evidence[evidence_id] = EvidenceRecord(
            evidence_id=evidence_id,
            document_id=document_id,
            page_number=table.page_number,
            text=f"Table summary: {table.summary}\n\n{table.markdown}",
            entities=page_entities,
            evidence_type="table",
            artifact_uri=table.artifact_uri,
            content_summary=table.summary,
            metadata={"table_id": table.table_id},
        )
        evidence_ids.append(evidence_id)
    return evidence_ids


def create_image_evidence(
    document_id: str,
    images: list[ImageRecord],
    page_entities: list[str],
) -> list[str]:
    evidence_ids: list[str] = []
    for image in images:
        evidence_id = new_id("ev")
        image.evidence_id = evidence_id
        STORE.evidence[evidence_id] = EvidenceRecord(
            evidence_id=evidence_id,
            document_id=document_id,
            page_number=image.page_number,
            text=f"Image caption: {image.caption}",
            entities=page_entities,
            evidence_type="image",
            artifact_uri=image.artifact_uri,
            content_summary=image.caption,
            metadata={"image_id": image.image_id, "source_ref": image.source_ref},
        )
        evidence_ids.append(evidence_id)
    return evidence_ids


def unique_ontology_objects(ontology: ExtractedOntology, fallback_entities: list[str]):
    seen: set[str] = set()
    objects = []
    for item in ontology.objects:
        key = item.name.lower()
        if not item.name or key in seen:
            continue
        seen.add(key)
        objects.append(item)
    if objects:
        return objects
    return [
        ExtractedObject(name=name, label="Entity", confidence=0.45)
        for name in fallback_entities
    ]


def table_to_simple_dict(table: TableRecord) -> dict:
    return {
        "table_id": table.table_id,
        "summary": table.summary,
        "markdown": table.markdown[:1200],
        "artifact_uri": table.artifact_uri,
    }


def image_to_simple_dict(image: ImageRecord) -> dict:
    return {
        "image_id": image.image_id,
        "caption": image.caption,
        "source_ref": image.source_ref,
        "artifact_uri": image.artifact_uri,
    }


def stable_asset_id(document_id: str, asset_type: str, value: object) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")[:80]
    return f"{document_id}:{asset_type}:{slug or asset_type}"


def summarize_artifact_text(text: str, fallback: str, max_chars: int = 360) -> str:
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return fallback
    return clean[: max_chars - 1].rstrip() + ("..." if len(clean) >= max_chars else "")


def hydrate_evidence_embeddings(document_id: str) -> None:
    evidence_items = [
        evidence
        for evidence in sorted(STORE.evidence.values(), key=lambda item: item.page_number)
        if evidence.document_id == document_id
    ]
    if not evidence_items:
        return
    embeddings = embed_texts([evidence.text for evidence in evidence_items])
    for evidence, embedding in zip(evidence_items, embeddings, strict=True):
        evidence.embedding = embedding
        if evidence.evidence_type == "image":
            update_image_embedding(document_id, evidence, embedding)


def update_image_embedding(
    document_id: str,
    evidence: EvidenceRecord,
    embedding: list[float],
) -> None:
    image_id = evidence.metadata.get("image_id")
    if not image_id:
        return
    document = STORE.documents.get(document_id)
    if document is None:
        return
    for page in document.pages.values():
        for image in page.images:
            if image.image_id == image_id:
                image.image_embedding = embedding
                return


def extract_entities(text: str) -> list[str]:
    seen: set[str] = set()
    entities: list[str] = []
    for match in ENTITY_PATTERN.finditer(text):
        entity = " ".join(match.group(0).split())
        if entity in STOP_ENTITIES or entity in seen:
            continue
        seen.add(entity)
        entities.append(entity)
    if not entities:
        words = [word.strip(".,:;()[]{}").lower() for word in text.split()]
        common = [word for word, _ in Counter(words).most_common(3) if len(word) > 4]
        entities = [word.title() for word in common] or ["Document Topic"]
    return entities[:20]


def stable_entity_id(document_id: str, entity_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", entity_name.lower()).strip("_")
    return f"{document_id}:entity:{slug}"


def remove_existing_document_graph(document_id: str) -> None:
    entity_ids = {
        entity_id
        for entity_id, entity in STORE.entities.items()
        if entity.document_id == document_id
    }
    evidence_ids = {
        evidence_id
        for evidence_id, evidence in STORE.evidence.items()
        if evidence.document_id == document_id
    }
    for entity_id in entity_ids:
        STORE.entities.pop(entity_id, None)
    for evidence_id in evidence_ids:
        STORE.evidence.pop(evidence_id, None)
    STORE.relationships[:] = [
        relationship
        for relationship in STORE.relationships
        if relationship.source_entity_id not in entity_ids
        and relationship.target_entity_id not in entity_ids
    ]
