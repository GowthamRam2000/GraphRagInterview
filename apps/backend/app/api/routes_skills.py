import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import ValidationError

from app.core.auth import require_api_key
from app.models.schemas import SkillDefinition
from app.services.skills import create_skill, list_skills, preview_skill

router = APIRouter(prefix="/v1/skills", tags=["skills"], dependencies=[Depends(require_api_key)])


@router.get("/ready")
async def skills_ready() -> dict[str, str]:
    return {"status": "skills-api-ready"}


@router.get("")
async def skills_list() -> list[dict]:
    return [skill.model_dump() for skill in list_skills()]


@router.post("")
async def skills_create(definition: SkillDefinition) -> dict:
    return create_skill(definition).model_dump()


@router.post("/upload")
async def skills_upload(file: Annotated[UploadFile, File()]) -> dict:
    if file.content_type not in {"application/json", "text/json", "application/octet-stream"}:
        raise HTTPException(status_code=422, detail="Only JSON skill uploads are supported")
    if not (file.filename or "").lower().endswith(".json"):
        raise HTTPException(status_code=422, detail="Skill filename must end with .json")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded skill file is empty")
    if len(content) > 64 * 1024:
        raise HTTPException(status_code=413, detail="Skill file exceeds 64 KB limit")

    try:
        payload = json.loads(content.decode("utf-8"))
        definition = SkillDefinition.model_validate(payload)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="Skill file must be UTF-8 JSON") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Skill file contains invalid JSON") from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_context=False)) from exc

    return create_skill(definition).model_dump()


@router.post("/{skill_id}/preview")
async def skills_preview(skill_id: str) -> dict:
    preview = preview_skill(skill_id)
    if preview is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return preview.model_dump()
