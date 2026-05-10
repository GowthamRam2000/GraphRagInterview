from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from uuid import uuid4

from app.models.schemas import SkillDefinition


@dataclass
class EvidenceRecord:
    evidence_id: str
    document_id: str
    page_number: int
    text: str
    entities: list[str]
    embedding: list[float] = field(default_factory=list)
    evidence_type: str = "text"
    artifact_uri: str | None = None
    content_summary: str | None = None
    metadata: dict = field(default_factory=dict)
    confidence: float = 1.0


@dataclass
class EntityRecord:
    entity_id: str
    document_id: str
    name: str
    label: str = "Entity"
    page_numbers: set[int] = field(default_factory=set)
    evidence_ids: set[str] = field(default_factory=set)
    confidence: float = 1.0
    properties: dict = field(default_factory=dict)


@dataclass
class RelationshipRecord:
    source_entity_id: str
    relationship_type: str
    target_entity_id: str
    evidence_id: str
    confidence: float = 1.0


@dataclass
class TableRecord:
    table_id: str
    page_number: int
    markdown: str
    summary: str
    artifact_uri: str | None = None
    evidence_id: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ImageRecord:
    image_id: str
    page_number: int
    caption: str
    source_ref: str | None = None
    artifact_uri: str | None = None
    evidence_id: str | None = None
    image_embedding: list[float] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class PageRecord:
    page_number: int
    text: str
    status: str = "completed"
    entity_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    tables: list[TableRecord] = field(default_factory=list)
    images: list[ImageRecord] = field(default_factory=list)
    layout_blocks: list[dict] = field(default_factory=list)
    artifact_uris: dict[str, str] = field(default_factory=dict)


@dataclass
class DocumentRecord:
    document_id: str
    filename: str
    title: str | None = None
    status: str = "created"
    upload_url: str = ""
    gcs_uri: str = ""
    raw_pdf_gcs_uri: str = ""
    artifact_gcs_uris: list[str] = field(default_factory=list)
    parser_metadata: dict = field(default_factory=dict)
    legacy_text_only: bool = False
    migration_status: str | None = None
    pages: dict[int, PageRecord] = field(default_factory=dict)
    created_at: float = field(default_factory=time)


@dataclass
class SkillRecord:
    skill_id: str
    definition: SkillDefinition


@dataclass
class TraceRecord:
    trace_id: str
    route: str
    user_message: str
    document_id: str | None
    retrieval: list[dict]
    evidence: list[dict]
    graph_paths: list[list[str]]
    answer: str
    prompts: list[dict] = field(default_factory=list)
    model_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)
    cache: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time)


@dataclass
class AppStore:
    documents: dict[str, DocumentRecord] = field(default_factory=dict)
    entities: dict[str, EntityRecord] = field(default_factory=dict)
    relationships: list[RelationshipRecord] = field(default_factory=list)
    evidence: dict[str, EvidenceRecord] = field(default_factory=dict)
    skills: dict[str, SkillRecord] = field(default_factory=dict)
    traces: dict[str, TraceRecord] = field(default_factory=dict)


STORE = AppStore()
_HYDRATED = False


def reset_store() -> None:
    STORE.documents.clear()
    STORE.entities.clear()
    STORE.relationships.clear()
    STORE.evidence.clear()
    STORE.skills.clear()
    STORE.traces.clear()
    global _HYDRATED
    _HYDRATED = False


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def hydrate_store() -> None:
    from app.services.repository import get_repository, persistence_enabled

    global _HYDRATED
    if _HYDRATED or not persistence_enabled():
        return
    snapshot = get_repository().load_snapshot()
    reset_store()
    for payload in snapshot["documents"].values():
        document = document_from_payload(payload)
        STORE.documents[document.document_id] = document
    for payload in snapshot["graphs"].values():
        load_graph_payload(payload)
    for payload in snapshot["skills"].values():
        skill = SkillRecord(
            skill_id=payload["skill_id"],
            definition=SkillDefinition.model_validate(payload["definition"]),
        )
        STORE.skills[skill.skill_id] = skill
    for payload in snapshot["traces"].values():
        trace = TraceRecord(**payload)
        STORE.traces[trace.trace_id] = trace
    _HYDRATED = True


def persist_document_state(document_id: str) -> None:
    from app.services.neo4j_repository import persist_document_graph_to_neo4j
    from app.services.repository import get_repository, persistence_enabled

    document = STORE.documents.get(document_id)
    if document is None:
        return
    document_payload = document_to_payload(document)
    graph_payload = graph_payload_for_document(document_id)
    persist_document_graph_to_neo4j(document_payload, graph_payload)
    if not persistence_enabled():
        return
    repository = get_repository()
    repository.init_schema()
    repository.upsert_document(document_id, document_payload, time())
    repository.upsert_graph(document_id, graph_payload, time())


def persist_skill_state(skill_id: str) -> None:
    from app.services.repository import get_repository, persistence_enabled

    if not persistence_enabled():
        return
    skill = STORE.skills.get(skill_id)
    if skill is None:
        return
    repository = get_repository()
    repository.init_schema()
    repository.upsert_skill(
        skill_id,
        {"skill_id": skill.skill_id, "definition": skill.definition.model_dump()},
        time(),
    )


def persist_trace_state(trace_id: str) -> None:
    from app.services.repository import get_repository, persistence_enabled

    if not persistence_enabled():
        return
    trace = STORE.traces.get(trace_id)
    if trace is None:
        return
    repository = get_repository()
    repository.init_schema()
    repository.upsert_trace(trace_id, trace_to_payload(trace), time())


def document_to_payload(document: DocumentRecord) -> dict:
    return {
        "document_id": document.document_id,
        "filename": document.filename,
        "title": document.title,
        "status": document.status,
        "upload_url": document.upload_url,
        "gcs_uri": document.gcs_uri,
        "raw_pdf_gcs_uri": document.raw_pdf_gcs_uri,
        "artifact_gcs_uris": document.artifact_gcs_uris,
        "parser_metadata": document.parser_metadata,
        "legacy_text_only": document.legacy_text_only,
        "migration_status": document.migration_status,
        "created_at": document.created_at,
        "pages": [
            {
                "page_number": page.page_number,
                "text": page.text,
                "status": page.status,
                "entity_ids": page.entity_ids,
                "evidence_ids": page.evidence_ids,
                "tables": [table_to_payload(table) for table in page.tables],
                "images": [image_to_payload(image) for image in page.images],
                "layout_blocks": page.layout_blocks,
                "artifact_uris": page.artifact_uris,
            }
            for page in sorted(document.pages.values(), key=lambda item: item.page_number)
        ],
    }


def document_from_payload(payload: dict) -> DocumentRecord:
    document = DocumentRecord(
        document_id=payload["document_id"],
        filename=payload["filename"],
        title=payload.get("title"),
        status=payload.get("status", "created"),
        upload_url=payload.get("upload_url", ""),
        gcs_uri=payload.get("gcs_uri", ""),
        raw_pdf_gcs_uri=payload.get("raw_pdf_gcs_uri") or payload.get("gcs_uri", ""),
        artifact_gcs_uris=list(payload.get("artifact_gcs_uris", [])),
        parser_metadata=dict(payload.get("parser_metadata", {})),
        legacy_text_only=bool(payload.get("legacy_text_only", False)),
        migration_status=payload.get("migration_status"),
        created_at=payload.get("created_at", time()),
    )
    for page_payload in payload.get("pages", []):
        page = PageRecord(
            page_number=page_payload["page_number"],
            text=page_payload["text"],
            status=page_payload.get("status", "completed"),
            entity_ids=list(page_payload.get("entity_ids", [])),
            evidence_ids=list(page_payload.get("evidence_ids", [])),
            tables=[table_from_payload(item) for item in page_payload.get("tables", [])],
            images=[image_from_payload(item) for item in page_payload.get("images", [])],
            layout_blocks=list(page_payload.get("layout_blocks", [])),
            artifact_uris=dict(page_payload.get("artifact_uris", {})),
        )
        document.pages[page.page_number] = page
    return document


def graph_payload_for_document(document_id: str) -> dict:
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
    return {
        "document_id": document_id,
        "entities": [
            {
                "entity_id": entity.entity_id,
                "document_id": entity.document_id,
                "name": entity.name,
                "label": entity.label,
                "page_numbers": sorted(entity.page_numbers),
                "evidence_ids": sorted(entity.evidence_ids),
                "confidence": entity.confidence,
                "properties": entity.properties,
            }
            for entity in STORE.entities.values()
            if entity.entity_id in entity_ids
        ],
        "evidence": [
            {
                "evidence_id": evidence.evidence_id,
                "document_id": evidence.document_id,
                "page_number": evidence.page_number,
                "text": evidence.text,
                "entities": evidence.entities,
                "embedding": evidence.embedding,
                "evidence_type": evidence.evidence_type,
                "artifact_uri": evidence.artifact_uri,
                "content_summary": evidence.content_summary,
                "metadata": evidence.metadata,
                "confidence": evidence.confidence,
            }
            for evidence in STORE.evidence.values()
            if evidence.evidence_id in evidence_ids
        ],
        "relationships": [
            {
                "source_entity_id": relationship.source_entity_id,
                "relationship_type": relationship.relationship_type,
                "target_entity_id": relationship.target_entity_id,
                "evidence_id": relationship.evidence_id,
                "confidence": relationship.confidence,
            }
            for relationship in STORE.relationships
            if relationship.source_entity_id in entity_ids
            or relationship.target_entity_id in entity_ids
        ],
        "tables": [
            table_to_payload(table)
            for document in STORE.documents.values()
            if document.document_id == document_id
            for page in document.pages.values()
            for table in page.tables
        ],
        "images": [
            image_to_payload(image)
            for document in STORE.documents.values()
            if document.document_id == document_id
            for page in document.pages.values()
            for image in page.images
        ],
        "layout_blocks": [
            {"page_number": page.page_number, "blocks": page.layout_blocks}
            for document in STORE.documents.values()
            if document.document_id == document_id
            for page in document.pages.values()
            if page.layout_blocks
        ],
    }


def load_graph_payload(payload: dict) -> None:
    document_id = payload["document_id"]
    remove_document_graph_from_memory(document_id)
    for entity_payload in payload.get("entities", []):
        entity = EntityRecord(
            entity_id=entity_payload["entity_id"],
            document_id=entity_payload["document_id"],
            name=entity_payload["name"],
            label=entity_payload.get("label", "Entity"),
            page_numbers=set(entity_payload.get("page_numbers", [])),
            evidence_ids=set(entity_payload.get("evidence_ids", [])),
            confidence=float(entity_payload.get("confidence", 1.0)),
            properties=dict(entity_payload.get("properties", {})),
        )
        STORE.entities[entity.entity_id] = entity
    for evidence_payload in payload.get("evidence", []):
        evidence = EvidenceRecord(
            evidence_id=evidence_payload["evidence_id"],
            document_id=evidence_payload["document_id"],
            page_number=evidence_payload["page_number"],
            text=evidence_payload["text"],
            entities=list(evidence_payload.get("entities", [])),
            embedding=list(evidence_payload.get("embedding", [])),
            evidence_type=evidence_payload.get("evidence_type", "text"),
            artifact_uri=evidence_payload.get("artifact_uri"),
            content_summary=evidence_payload.get("content_summary"),
            metadata=dict(evidence_payload.get("metadata", {})),
            confidence=float(evidence_payload.get("confidence", 1.0)),
        )
        STORE.evidence[evidence.evidence_id] = evidence
    for relationship_payload in payload.get("relationships", []):
        STORE.relationships.append(RelationshipRecord(**relationship_payload))


def remove_document_graph_from_memory(document_id: str) -> None:
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


def trace_to_payload(trace: TraceRecord) -> dict:
    return {
        "trace_id": trace.trace_id,
        "route": trace.route,
        "user_message": trace.user_message,
        "document_id": trace.document_id,
        "retrieval": trace.retrieval,
        "evidence": trace.evidence,
        "graph_paths": trace.graph_paths,
        "answer": trace.answer,
        "prompts": trace.prompts,
        "model_calls": trace.model_calls,
        "usage": trace.usage,
        "timings": trace.timings,
        "cache": trace.cache,
        "created_at": trace.created_at,
    }


def table_to_payload(table: TableRecord) -> dict:
    return {
        "table_id": table.table_id,
        "page_number": table.page_number,
        "markdown": table.markdown,
        "summary": table.summary,
        "artifact_uri": table.artifact_uri,
        "evidence_id": table.evidence_id,
        "metadata": table.metadata,
    }


def table_from_payload(payload: dict) -> TableRecord:
    return TableRecord(
        table_id=payload["table_id"],
        page_number=payload["page_number"],
        markdown=payload.get("markdown", ""),
        summary=payload.get("summary", ""),
        artifact_uri=payload.get("artifact_uri"),
        evidence_id=payload.get("evidence_id"),
        metadata=dict(payload.get("metadata", {})),
    )


def image_to_payload(image: ImageRecord) -> dict:
    return {
        "image_id": image.image_id,
        "page_number": image.page_number,
        "caption": image.caption,
        "source_ref": image.source_ref,
        "artifact_uri": image.artifact_uri,
        "evidence_id": image.evidence_id,
        "image_embedding": image.image_embedding,
        "metadata": image.metadata,
    }


def image_from_payload(payload: dict) -> ImageRecord:
    return ImageRecord(
        image_id=payload["image_id"],
        page_number=payload["page_number"],
        caption=payload.get("caption", ""),
        source_ref=payload.get("source_ref"),
        artifact_uri=payload.get("artifact_uri"),
        evidence_id=payload.get("evidence_id"),
        image_embedding=list(payload.get("image_embedding", [])),
        metadata=dict(payload.get("metadata", {})),
    )
