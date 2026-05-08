from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from sqlalchemy import JSON, Column, Float, MetaData, String, Table, create_engine, delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings

metadata = MetaData()

documents_table = Table(
    "app_documents",
    metadata,
    Column("document_id", String(128), primary_key=True),
    Column("payload", JSON, nullable=False),
    Column("updated_at", Float, nullable=False),
)

graph_table = Table(
    "app_document_graphs",
    metadata,
    Column("document_id", String(128), primary_key=True),
    Column("payload", JSON, nullable=False),
    Column("updated_at", Float, nullable=False),
)

skills_table = Table(
    "app_skills",
    metadata,
    Column("skill_id", String(220), primary_key=True),
    Column("payload", JSON, nullable=False),
    Column("updated_at", Float, nullable=False),
)

traces_table = Table(
    "app_traces",
    metadata,
    Column("trace_id", String(128), primary_key=True),
    Column("payload", JSON, nullable=False),
    Column("updated_at", Float, nullable=False),
)


class PersistentRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(to_sync_database_url(database_url), pool_pre_ping=True)

    def init_schema(self) -> None:
        metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Any:
        with Session(self.engine) as session:
            yield session
            session.commit()

    def upsert_document(self, document_id: str, payload: dict, updated_at: float) -> None:
        upsert_payload(
            self.engine,
            documents_table,
            "document_id",
            document_id,
            payload,
            updated_at,
        )

    def upsert_graph(self, document_id: str, payload: dict, updated_at: float) -> None:
        upsert_payload(self.engine, graph_table, "document_id", document_id, payload, updated_at)

    def upsert_skill(self, skill_id: str, payload: dict, updated_at: float) -> None:
        upsert_payload(self.engine, skills_table, "skill_id", skill_id, payload, updated_at)

    def upsert_trace(self, trace_id: str, payload: dict, updated_at: float) -> None:
        upsert_payload(self.engine, traces_table, "trace_id", trace_id, payload, updated_at)

    def load_snapshot(self) -> dict[str, dict[str, dict]]:
        self.init_schema()
        with Session(self.engine) as session:
            return {
                "documents": load_payloads(session, documents_table, "document_id"),
                "graphs": load_payloads(session, graph_table, "document_id"),
                "skills": load_payloads(session, skills_table, "skill_id"),
                "traces": load_payloads(session, traces_table, "trace_id"),
            }

    def clear_all(self) -> None:
        self.init_schema()
        with Session(self.engine) as session:
            for table in (traces_table, skills_table, graph_table, documents_table):
                session.execute(delete(table))
            session.commit()


def upsert_payload(
    engine: Engine,
    table: Table,
    id_column: str,
    record_id: str,
    payload: dict,
    updated_at: float,
) -> None:
    with Session(engine) as session:
        session.execute(delete(table).where(table.c[id_column] == record_id))
        session.execute(
            table.insert().values(
                {id_column: record_id, "payload": payload, "updated_at": updated_at}
            )
        )
        session.commit()


def load_payloads(session: Session, table: Table, id_column: str) -> dict[str, dict]:
    rows = session.execute(select(table.c[id_column], table.c.payload)).all()
    return {record_id: payload for record_id, payload in rows}


def to_sync_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    return database_url


def persistence_enabled(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return settings.store_backend.lower() == "sql"


_repository: PersistentRepository | None = None


def get_repository(settings: Settings | None = None) -> PersistentRepository:
    global _repository
    settings = settings or get_settings()
    if _repository is None:
        _repository = PersistentRepository(settings.database_url)
    return _repository


def set_repository_for_tests(repository: PersistentRepository | None) -> None:
    global _repository
    _repository = repository
