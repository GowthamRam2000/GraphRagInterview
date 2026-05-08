import json

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.core.auth import require_api_key
from app.models.schemas import ChatRequest
from app.rag.answerer import stream_answer_with_llm
from app.rag.model_policy import router_profile
from app.rag.prompts import build_answer_prompt
from app.services.chat import (
    answer_chat,
    apply_skill_if_needed,
    format_ontology_answer,
    persist_graph_rag_trace,
    persist_trace,
    prepare_graph_rag_answer,
    route_message,
    skill_contract_text,
)
from app.services.ingestion import get_ontology
from app.services.store import STORE, hydrate_store

router = APIRouter(prefix="/v1/chat", tags=["chat"], dependencies=[Depends(require_api_key)])


@router.get("/ready")
async def chat_ready() -> dict[str, str]:
    return {"status": "chat-api-ready"}


@router.post("")
async def chat(request: ChatRequest) -> dict:
    response = answer_chat(request)
    if response is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return response.model_dump()


@router.post("/stream")
async def chat_stream(request: ChatRequest) -> EventSourceResponse:
    async def events():
        try:
            yield {"event": "progress", "data": "hydrating"}
            hydrate_store()
            message = request.message.strip()
            route = route_message(message)
            yield {"event": "route", "data": route}

            if route == "greeting":
                answer = (
                    "Hello. Upload or select a PDF document, then ask "
                    "document-grounded questions."
                )
                router = router_profile()
                for delta in chunk_text(answer, 18):
                    yield {"event": "answer_delta", "data": delta}
                trace = persist_trace(
                    route=route,
                    request=request,
                    retrieval=[],
                    evidence=[],
                    graph_paths=[],
                    answer=answer,
                    prompts=[
                        {
                            "purpose": "router",
                            "version": router.prompt_version,
                            "route": route,
                            "deterministic": True,
                        }
                    ],
                    model_calls=[
                        {
                            "purpose": router.purpose,
                            "model": router.model,
                            "reasoning_effort": router.reasoning_effort,
                            "thinking": router.thinking,
                            "status": "deterministic",
                        }
                    ],
                    usage={"prompt_tokens_estimated": 0},
                )
                yield {"event": "trace", "data": trace.trace_id}
                yield {"event": "done", "data": "ok"}
                return

            if not request.document_id or request.document_id not in STORE.documents:
                yield {"event": "error", "data": "Document not found"}
                return

            if route == "ontology":
                ontology = get_ontology(request.document_id)
                if ontology is None:
                    yield {"event": "error", "data": "Document not found"}
                    return
                answer = format_ontology_answer(ontology.object_types, ontology.relationships)
                for delta in chunk_text(answer, 24):
                    yield {"event": "answer_delta", "data": delta}
                trace = persist_trace(
                    route=route,
                    request=request,
                    retrieval=[],
                    evidence=[],
                    graph_paths=[],
                    answer=answer,
                    prompts=[
                        {
                            "purpose": "ontology",
                            "version": "ontology-answer-v1.0",
                            "deterministic": True,
                        }
                    ],
                    model_calls=[
                        {
                            "purpose": "ontology",
                            "model": "deterministic",
                            "reasoning_effort": "none",
                            "thinking": False,
                            "status": "deterministic",
                        }
                    ],
                    usage={"prompt_tokens_estimated": 0},
                )
                yield {"event": "trace", "data": trace.trace_id}
                yield {"event": "done", "data": "ok"}
                return

            yield {"event": "progress", "data": "retrieving"}
            candidates, hits, graph_paths, citations, fallback_answer, skill = (
                prepare_graph_rag_answer(
                    request,
                    message,
                )
            )
            yield {"event": "progress", "data": "reranking"}
            for citation in citations:
                yield {"event": "citation", "data": citation.model_dump_json()}
            yield {"event": "progress", "data": "building_prompt"}
            answer_prompt = build_answer_prompt(
                message=message,
                evidence=hits,
                graph_paths=graph_paths,
                skill_name=skill.definition.name if skill is not None else None,
                skill_contract=skill_contract_text(skill.definition) if skill is not None else None,
            )
            yield {"event": "progress", "data": "generating"}
            answer_result = None
            answer = ""
            for stream_event in stream_answer_with_llm(answer_prompt, fallback_answer):
                if stream_event.kind == "delta":
                    answer += stream_event.delta
                    yield {"event": "answer_delta", "data": stream_event.delta}
                elif stream_event.kind == "final":
                    answer_result = stream_event.result
            if answer_result is None:
                yield {"event": "error", "data": "Answer generation failed"}
                return
            if answer_result.model_call.get("fallback"):
                yield {"event": "progress", "data": "fallback"}
            final_answer = apply_skill_if_needed(request, answer_result.answer, skill, citations)
            if final_answer != answer:
                answer = final_answer
                yield {"event": "answer_replace", "data": final_answer}
            yield {"event": "progress", "data": "saving_trace"}
            trace = persist_graph_rag_trace(
                request,
                candidates,
                hits,
                graph_paths,
                final_answer,
                answer_result,
            )
            yield {
                "event": "metrics",
                "data": json.dumps(
                    {
                        "usage": answer_result.usage,
                        "timings": answer_result.timings,
                        "model_call": answer_result.model_call,
                    }
                ),
            }
            yield {"event": "trace", "data": trace.trace_id}
            yield {"event": "done", "data": "ok"}
        except Exception as exc:
            yield {"event": "error", "data": f"{type(exc).__name__}: {str(exc)[:180]}"}

    return EventSourceResponse(events())


def chunk_text(text: str, size: int) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)]
