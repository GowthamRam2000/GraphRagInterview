from __future__ import annotations

import re
from collections import Counter, defaultdict

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
from app.services.embeddings import embed_texts
from app.services.store import (
    STORE,
    DocumentRecord,
    EntityRecord,
    EvidenceRecord,
    PageRecord,
    RelationshipRecord,
    hydrate_store,
    new_id,
    persist_document_state,
)

ENTITY_PATTERN = re.compile(r"\b(?:[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+){0,4})\b")
STOP_ENTITIES = {"The", "A", "An", "This", "That", "It"}


def create_upload(request: UploadUrlRequest) -> UploadUrlResponse:
    hydrate_store()
    document_id = new_id("doc")
    gcs_uri = f"gs://raw-pdfs/{document_id}/{request.filename}"
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
    hydrate_store()
    document = STORE.documents.get(document_id)
    if document is None:
        return None

    pages = request.pages
    if not pages and request.text:
        pages = split_text_into_pages(request.text)
    if not pages:
        pages = ["No extractable text was provided for this document."]

    document.title = request.title or document.filename
    document.pages.clear()
    document.status = "processing"
    remove_existing_document_graph(document_id)

    previous_entity_id: str | None = None
    for index, page_text in enumerate(pages, start=1):
        entities = extract_entities(page_text)
        evidence_id = new_id("ev")
        evidence = EvidenceRecord(
            evidence_id=evidence_id,
            document_id=document_id,
            page_number=index,
            text=page_text,
            entities=entities,
        )
        STORE.evidence[evidence_id] = evidence

        page_entity_ids: list[str] = []
        for entity_name in entities:
            entity_id = stable_entity_id(document_id, entity_name)
            entity = STORE.entities.setdefault(
                entity_id,
                EntityRecord(entity_id=entity_id, document_id=document_id, name=entity_name),
            )
            entity.page_numbers.add(index)
            entity.evidence_ids.add(evidence_id)
            page_entity_ids.append(entity_id)

        for source_id, target_id in zip(page_entity_ids, page_entity_ids[1:], strict=False):
            STORE.relationships.append(
                RelationshipRecord(
                    source_entity_id=source_id,
                    relationship_type="RELATED_TO",
                    target_entity_id=target_id,
                    evidence_id=evidence_id,
                )
            )
        if previous_entity_id and page_entity_ids:
            STORE.relationships.append(
                RelationshipRecord(
                    source_entity_id=previous_entity_id,
                    relationship_type="NEXT_PAGE_CONTEXT",
                    target_entity_id=page_entity_ids[0],
                    evidence_id=evidence_id,
                )
            )
        if page_entity_ids:
            previous_entity_id = page_entity_ids[-1]

        document.pages[index] = PageRecord(
            page_number=index,
            text=page_text,
            entity_ids=page_entity_ids,
            evidence_ids=[evidence_id],
        )

    hydrate_evidence_embeddings(document_id)
    document.status = "completed"
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

    entity_names = [
        entity.name for entity in STORE.entities.values() if entity.document_id == document_id
    ]
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
            properties=["entity_id", "name", "page_numbers", "evidence_ids"],
            examples=entity_names[:5],
        ),
    ]

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

    return OntologyResponse(
        document_id=document_id,
        object_types=object_types,
        relationships=relationships,
    )


def split_text_into_pages(text: str, max_chars: int = 1800) -> list[str]:
    clean = text.strip()
    if not clean:
        return []
    return [clean[index : index + max_chars].strip() for index in range(0, len(clean), max_chars)]


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
