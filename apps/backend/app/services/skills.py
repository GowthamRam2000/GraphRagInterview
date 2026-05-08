from __future__ import annotations

import hashlib

from app.models.schemas import SkillDefinition, SkillPreviewResponse, SkillResponse
from app.services.store import STORE, SkillRecord, hydrate_store, persist_skill_state


def create_skill(definition: SkillDefinition) -> SkillResponse:
    hydrate_store()
    digest = hashlib.sha256(definition.model_dump_json().encode("utf-8")).hexdigest()[:12]
    skill_id = f"{definition.name}:{definition.version}:{digest}"
    record = SkillRecord(skill_id=skill_id, definition=definition)
    STORE.skills[skill_id] = record
    persist_skill_state(skill_id)
    return SkillResponse(skill_id=skill_id, definition=definition)


def list_skills() -> list[SkillResponse]:
    hydrate_store()
    return [
        SkillResponse(skill_id=record.skill_id, definition=record.definition)
        for record in STORE.skills.values()
    ]


def get_skill(skill_id: str) -> SkillRecord | None:
    hydrate_store()
    return STORE.skills.get(skill_id)


def preview_skill(skill_id: str) -> SkillPreviewResponse | None:
    skill = get_skill(skill_id)
    if skill is None:
        return None
    sample = "This is a grounded sample answer. [p. 1]"
    return SkillPreviewResponse(
        skill_id=skill_id,
        formatted_answer=apply_skill_format(sample, skill.definition, ["Sample evidence [p. 1]"]),
    )


def apply_skill_format(answer: str, definition: SkillDefinition, evidence_lines: list[str]) -> str:
    headings = [section.heading for section in definition.required_sections]
    if answer_satisfies_sections(answer, headings):
        return answer

    sections: list[str] = []
    for index, section in enumerate(definition.required_sections):
        heading = f"## {section.heading}"
        section_name = section.heading.lower()
        if index == 0 or section_name in {"executive summary", "summary", "answer"}:
            body = trim_words(answer, section.max_words)
        elif section.citation_required and any(
            token in section_name for token in ("evidence", "citation", "source", "control")
        ):
            body = (
                "\n".join(f"- {line}" for line in evidence_lines)
                or "- No cited evidence available."
            )
        else:
            body = trim_words(answer, section.max_words)
        sections.append(f"{heading}\n{body}")
    return "\n\n".join(sections)


def answer_satisfies_sections(answer: str, headings: list[str]) -> bool:
    if not headings:
        return True
    normalized = answer.lower()
    matched = sum(
        1
        for heading in headings
        if f"## {heading.lower()}" in normalized
        or f"{heading.lower()}:" in normalized
        or f"**{heading.lower()}**" in normalized
    )
    return matched >= max(1, min(len(headings), 2))


def trim_words(text: str, max_words: int | None) -> str:
    if max_words is None:
        return text
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(" .,") + "."
