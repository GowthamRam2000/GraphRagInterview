from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UploadUrlRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = "application/pdf"

    @field_validator("filename")
    @classmethod
    def require_pdf_extension(cls, value: str) -> str:
        if not value.lower().endswith(".pdf"):
            raise ValueError("filename must end with .pdf")
        return value

    @field_validator("content_type")
    @classmethod
    def require_pdf_content_type(cls, value: str) -> str:
        if value != "application/pdf":
            raise ValueError("content_type must be application/pdf")
        return value


class UploadUrlResponse(BaseModel):
    document_id: str
    upload_url: str
    gcs_uri: str
    status: str


class FinalizeDocumentRequest(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    pages: list[str] = Field(default_factory=list, max_length=500)
    text: str | None = Field(default=None, max_length=2_000_000)

    @field_validator("pages")
    @classmethod
    def reject_empty_pages(cls, value: list[str]) -> list[str]:
        return [page.strip() for page in value if page.strip()]


class PageStatus(BaseModel):
    page_number: int
    status: Literal["queued", "processing", "completed", "failed"]
    entity_count: int = 0
    evidence_count: int = 0
    error: str | None = None


class DocumentSummary(BaseModel):
    document_id: str
    filename: str
    title: str | None = None
    status: str
    page_count: int


class IngestionStatus(BaseModel):
    document_id: str
    status: str
    page_count: int
    pages: list[PageStatus]


class OntologyObjectType(BaseModel):
    label: str
    count: int
    properties: list[str]
    examples: list[str] = Field(default_factory=list)


class OntologyRelationship(BaseModel):
    type: str
    source_label: str
    target_label: str
    count: int
    examples: list[str] = Field(default_factory=list)


class OntologyResponse(BaseModel):
    document_id: str
    object_types: list[OntologyObjectType]
    relationships: list[OntologyRelationship]


class Citation(BaseModel):
    page_number: int
    evidence_id: str
    text: str


class ChatRequest(BaseModel):
    document_id: str | None = None
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=8000)
    skill_id: str | None = None
    demo_trace: bool = True


class ChatResponse(BaseModel):
    answer: str
    route: Literal["greeting", "graph_rag", "ontology", "skill_management", "out_of_scope"]
    citations: list[Citation]
    graph_paths: list[list[str]]
    trace_id: str


class SkillSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str = Field(min_length=1, max_length=80)
    max_words: int | None = Field(default=None, ge=1, le=500)
    citation_required: bool = False


class SkillDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-zA-Z0-9_-]+$", max_length=80)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str = Field(max_length=500)
    output_mode: Literal["markdown", "json"] = "markdown"
    required_sections: list[SkillSection] = Field(min_length=1, max_length=8)
    tone: Literal["concise", "executive", "technical", "audit", "cyber"] = "concise"
    citation_style: Literal["page", "footnote", "inline"] = "page"
    require_citations: bool = True

    @field_validator("description")
    @classmethod
    def reject_prompt_control(cls, value: str) -> str:
        lowered = value.lower()
        blocked = (
            "ignore previous instructions",
            "system prompt",
            "developer message",
            "tool call",
            "exfiltrate",
            "secret",
        )
        if any(phrase in lowered for phrase in blocked):
            raise ValueError("skill description contains blocked prompt-control text")
        return value


class SkillResponse(BaseModel):
    skill_id: str
    definition: SkillDefinition


class SkillPreviewResponse(BaseModel):
    skill_id: str
    formatted_answer: str
