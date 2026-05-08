from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict, dataclass

from openai import OpenAI

from app.core.config import get_settings
from app.rag.model_policy import answer_profile
from app.rag.prompts import PromptBundle
from app.rag.usage import Timer, usage_from_openai


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    prompt_trace: dict
    model_call: dict
    usage: dict
    timings: dict
    cache: dict


@dataclass(frozen=True)
class AnswerStreamEvent:
    kind: str
    delta: str = ""
    result: AnswerResult | None = None


def generate_answer_with_llm(prompt: PromptBundle, fallback_answer: str) -> AnswerResult:
    settings = get_settings()
    profile = answer_profile()
    prompt_trace = {
        "purpose": "answer",
        "version": prompt.version,
        "system_hash": short_hash(prompt.system),
        "developer_hash": short_hash(prompt.developer),
        "user_chars": len(prompt.user),
        "token_estimate": prompt.token_estimate,
        "cache_key": prompt.cache_key,
    }
    model_call = {
        **asdict(profile),
        "provider": "openai",
        "status": "skipped",
        "fallback": False,
    }
    cache = {
        "prompt_cache_key": prompt.cache_key,
        "namespace": settings.prompt_cache_namespace,
        "cached_input_tokens": 0,
    }
    if not settings.llm_answer_enabled or not settings.openai_api_key:
        model_call["status"] = "fallback_disabled"
        return AnswerResult(
            answer=fallback_answer,
            prompt_trace=prompt_trace,
            model_call=model_call,
            usage={"prompt_tokens_estimated": prompt.token_estimate},
            timings={},
            cache=cache,
        )

    timer = Timer()
    try:
        client = OpenAI(api_key=settings.openai_api_key, timeout=45)
        reasoning = None
        if profile.reasoning_effort != "none":
            reasoning = {"effort": profile.reasoning_effort}
        response = client.responses.create(
            model=profile.model,
            instructions=prompt.system + "\n\n" + prompt.developer,
            input=prompt.user,
            max_output_tokens=settings.answer_max_output_tokens,
            reasoning=reasoning,
            prompt_cache_key=prompt.cache_key,
            store=False,
            metadata={
                "prompt_version": prompt.version,
                "purpose": "graph_rag_answer",
            },
        )
        answer = extract_output_text(response) or fallback_answer
        usage = usage_from_openai(response, prompt.token_estimate)
        cache["cached_input_tokens"] = usage.cached_input_tokens
        model_call["status"] = "ok"
        model_call["response_id"] = getattr(response, "id", None)
        return AnswerResult(
            answer=answer,
            prompt_trace=prompt_trace,
            model_call=model_call,
            usage=usage.as_dict(),
            timings={"answer_model_ms": timer.elapsed_ms()},
            cache=cache,
        )
    except Exception as exc:
        model_call["status"] = "fallback_error"
        model_call["fallback"] = True
        model_call["error"] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:180]}"
        return AnswerResult(
            answer=fallback_answer,
            prompt_trace=prompt_trace,
            model_call=model_call,
            usage={"prompt_tokens_estimated": prompt.token_estimate},
            timings={"answer_model_ms": timer.elapsed_ms()},
            cache=cache,
        )


def stream_answer_with_llm(
    prompt: PromptBundle,
    fallback_answer: str,
) -> Iterator[AnswerStreamEvent]:
    settings = get_settings()
    profile = answer_profile()
    prompt_trace = {
        "purpose": "answer",
        "version": prompt.version,
        "system_hash": short_hash(prompt.system),
        "developer_hash": short_hash(prompt.developer),
        "user_chars": len(prompt.user),
        "token_estimate": prompt.token_estimate,
        "cache_key": prompt.cache_key,
    }
    model_call = {
        **asdict(profile),
        "provider": "openai",
        "status": "skipped",
        "fallback": False,
    }
    cache = {
        "prompt_cache_key": prompt.cache_key,
        "namespace": settings.prompt_cache_namespace,
        "cached_input_tokens": 0,
    }
    if not settings.llm_answer_enabled or not settings.openai_api_key:
        model_call["status"] = "fallback_disabled"
        yield from fallback_stream(
            fallback_answer=fallback_answer,
            prompt_trace=prompt_trace,
            model_call=model_call,
            usage={"prompt_tokens_estimated": prompt.token_estimate},
            timings={},
            cache=cache,
        )
        return

    timer = Timer()
    answer_parts: list[str] = []
    final_response: object | None = None
    try:
        client = OpenAI(api_key=settings.openai_api_key, timeout=45)
        reasoning = None
        if profile.reasoning_effort != "none":
            reasoning = {"effort": profile.reasoning_effort}
        stream = client.responses.create(
            model=profile.model,
            instructions=prompt.system + "\n\n" + prompt.developer,
            input=prompt.user,
            max_output_tokens=settings.answer_max_output_tokens,
            reasoning=reasoning,
            prompt_cache_key=prompt.cache_key,
            store=False,
            stream=True,
            metadata={
                "prompt_version": prompt.version,
                "purpose": "graph_rag_answer",
            },
        )
        for event in stream:
            event_type = getattr(event, "type", "")
            if event_type == "response.output_text.delta":
                delta = getattr(event, "delta", "") or ""
                if delta:
                    answer_parts.append(delta)
                    yield AnswerStreamEvent(kind="delta", delta=delta)
            elif event_type == "response.completed":
                final_response = getattr(event, "response", None)
        answer = "".join(answer_parts).strip()
        if final_response is not None:
            answer = extract_output_text(final_response) or answer
        answer = answer or fallback_answer
        usage_record = usage_from_openai(final_response, prompt.token_estimate)
        cache["cached_input_tokens"] = usage_record.cached_input_tokens
        model_call["status"] = "ok"
        if final_response is not None:
            model_call["response_id"] = getattr(final_response, "id", None)
        yield AnswerStreamEvent(
            kind="final",
            result=AnswerResult(
                answer=answer,
                prompt_trace=prompt_trace,
                model_call=model_call,
                usage=usage_record.as_dict(),
                timings={"answer_model_ms": timer.elapsed_ms()},
                cache=cache,
            ),
        )
    except Exception as exc:
        model_call["status"] = "fallback_error"
        model_call["fallback"] = True
        model_call["error"] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:180]}"
        yield from fallback_stream(
            fallback_answer=fallback_answer,
            prompt_trace=prompt_trace,
            model_call=model_call,
            usage={"prompt_tokens_estimated": prompt.token_estimate},
            timings={"answer_model_ms": timer.elapsed_ms()},
            cache=cache,
        )


def fallback_stream(
    fallback_answer: str,
    prompt_trace: dict,
    model_call: dict,
    usage: dict,
    timings: dict,
    cache: dict,
) -> Iterator[AnswerStreamEvent]:
    for index in range(0, len(fallback_answer), 24):
        yield AnswerStreamEvent(kind="delta", delta=fallback_answer[index : index + 24])
    yield AnswerStreamEvent(
        kind="final",
        result=AnswerResult(
            answer=fallback_answer,
            prompt_trace=prompt_trace,
            model_call=model_call,
            usage=usage,
            timings=timings,
            cache=cache,
        ),
    )


def extract_output_text(response: object) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        return output_text.strip()
    output = getattr(response, "output", None) or []
    chunks: list[str] = []
    for item in output:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks).strip()


def short_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
