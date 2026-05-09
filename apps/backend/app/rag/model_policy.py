from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True)
class ModelProfile:
    purpose: str
    model: str
    reasoning_effort: str
    prompt_version: str
    thinking: bool


def router_profile() -> ModelProfile:
    settings = get_settings()
    return ModelProfile(
        purpose="router",
        model=settings.router_model,
        reasoning_effort=settings.router_reasoning_effort,
        prompt_version="router-v1.1",
        thinking=settings.router_reasoning_effort != "none",
    )


def answer_profile() -> ModelProfile:
    settings = get_settings()
    return ModelProfile(
        purpose="answer",
        model=settings.answer_model,
        reasoning_effort=settings.answer_reasoning_effort,
        prompt_version="rag-answer-v1.2",
        thinking=settings.answer_reasoning_effort != "none",
    )


def extractor_profile() -> ModelProfile:
    settings = get_settings()
    return ModelProfile(
        purpose="extractor",
        model=settings.extractor_model,
        reasoning_effort=settings.extractor_reasoning_effort,
        prompt_version="ontology-extractor-v1.0",
        thinking=settings.extractor_reasoning_effort != "none",
    )
