from __future__ import annotations

from collections.abc import Iterable

from neo4j import GraphDatabase

from app.core.config import Settings, get_settings


def graph_persistence_enabled(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return settings.graph_store_backend.lower() == "neo4j"


def persist_document_graph_to_neo4j(
    document_payload: dict,
    graph_payload: dict,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    if not graph_persistence_enabled(settings):
        return

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )
    try:
        with driver.session() as session:
            session.execute_write(
                _replace_document_graph,
                document_payload,
                graph_payload,
            )
    finally:
        driver.close()


def _replace_document_graph(tx, document_payload: dict, graph_payload: dict) -> None:
    document_id = document_payload["document_id"]
    tx.run(
        """
        MATCH (n {document_id: $document_id})
        DETACH DELETE n
        """,
        document_id=document_id,
    )
    tx.run(
        """
        MERGE (d:Document {document_id: $document_id})
        SET d.filename = $filename,
            d.title = $title,
            d.status = $status,
            d.gcs_uri = $gcs_uri,
            d.page_count = $page_count
        """,
        document_id=document_id,
        filename=document_payload["filename"],
        title=document_payload.get("title"),
        status=document_payload.get("status"),
        gcs_uri=document_payload.get("gcs_uri"),
        page_count=len(document_payload.get("pages", [])),
    )

    _persist_pages(tx, document_id, document_payload.get("pages", []))
    _persist_entities(tx, document_id, graph_payload.get("entities", []))
    _persist_evidence(tx, document_id, graph_payload.get("evidence", []))
    _persist_relationships(tx, graph_payload.get("relationships", []))


def _persist_pages(tx, document_id: str, pages: Iterable[dict]) -> None:
    for page in pages:
        tx.run(
            """
            MATCH (d:Document {document_id: $document_id})
            MERGE (p:Page {document_id: $document_id, page_number: $page_number})
            SET p.status = $status,
                p.text = $text
            MERGE (d)-[:HAS_PAGE]->(p)
            """,
            document_id=document_id,
            page_number=page["page_number"],
            status=page.get("status", "completed"),
            text=page.get("text", ""),
        )


def _persist_entities(tx, document_id: str, entities: Iterable[dict]) -> None:
    for entity in entities:
        tx.run(
            """
            MATCH (d:Document {document_id: $document_id})
            MERGE (e:Entity {entity_id: $entity_id})
            SET e.document_id = $document_id,
                e.name = $name,
                e.label = $label,
                e.page_numbers = $page_numbers,
                e.evidence_ids = $evidence_ids
            MERGE (d)-[:MENTIONS]->(e)
            """,
            document_id=document_id,
            entity_id=entity["entity_id"],
            name=entity["name"],
            label=entity.get("label", "Entity"),
            page_numbers=entity.get("page_numbers", []),
            evidence_ids=entity.get("evidence_ids", []),
        )


def _persist_evidence(tx, document_id: str, evidence_items: Iterable[dict]) -> None:
    for evidence in evidence_items:
        tx.run(
            """
            MATCH (p:Page {document_id: $document_id, page_number: $page_number})
            MERGE (ev:EvidenceSpan {evidence_id: $evidence_id})
            SET ev.document_id = $document_id,
                ev.page_number = $page_number,
                ev.text = $text,
                ev.entities = $entities
            MERGE (p)-[:HAS_EVIDENCE]->(ev)
            """,
            document_id=document_id,
            page_number=evidence["page_number"],
            evidence_id=evidence["evidence_id"],
            text=evidence["text"],
            entities=evidence.get("entities", []),
        )
        for entity_name in evidence.get("entities", []):
            tx.run(
                """
                MATCH (ev:EvidenceSpan {evidence_id: $evidence_id})
                MATCH (e:Entity {document_id: $document_id, name: $entity_name})
                MERGE (ev)-[:SUPPORTS_ENTITY]->(e)
                """,
                document_id=document_id,
                evidence_id=evidence["evidence_id"],
                entity_name=entity_name,
            )


def _persist_relationships(tx, relationships: Iterable[dict]) -> None:
    for relationship in relationships:
        tx.run(
            """
            MATCH (source:Entity {entity_id: $source_entity_id})
            MATCH (target:Entity {entity_id: $target_entity_id})
            MERGE (source)-[r:GRAPH_LINK {
                relationship_type: $relationship_type,
                evidence_id: $evidence_id
            }]->(target)
            """,
            source_entity_id=relationship["source_entity_id"],
            target_entity_id=relationship["target_entity_id"],
            relationship_type=relationship["relationship_type"],
            evidence_id=relationship["evidence_id"],
        )
