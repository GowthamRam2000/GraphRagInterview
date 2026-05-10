from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal

from openai import OpenAI

from app.core.config import get_settings
from app.rag.model_policy import router_profile
from app.rag.prompts import (
    ROUTER_PROMPT,
    ROUTER_PROMPT_VERSION,
    estimate_tokens,
    prompt_cache_key,
)
from app.rag.usage import Timer, usage_from_openai

RouteName = Literal["greeting", "graph_rag", "ontology", "skill_management", "out_of_scope"]

ALLOWED_ROUTES: set[str] = {
    "greeting",
    "graph_rag",
    "ontology",
    "skill_management",
    "out_of_scope",
}

GREETINGS = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}
OFF_TOPIC_KEYWORDS = {
    "weather",
    "stock price",
    "sports score",
    "movie recommendation",
    "restaurant",
    "flight",
    "hotel",
    "recipe",
    "cricket score",
    "football score",
    "news today",
}


@dataclass(frozen=True)
class RouteDecision:
    route: RouteName
    confidence: float
    reason: str
    prompt_trace: dict
    model_call: dict
    usage: dict
    timings: dict
    fallback_route: str | None = None


def classify_route(message: str) -> RouteDecision:
    settings = get_settings()
    profile = router_profile()
    prompt_trace = {
        "purpose": "router",
        "version": ROUTER_PROMPT_VERSION,
        "system_hash": short_hash(ROUTER_PROMPT),
        "user_chars": len(message),
        "token_estimate": estimate_tokens(ROUTER_PROMPT + message),
        "confidence_threshold": settings.router_confidence_threshold,
        "cache_key": prompt_cache_key(
            namespace=settings.prompt_cache_namespace,
            version=ROUTER_PROMPT_VERSION,
            stable_prefix=ROUTER_PROMPT,
        ),
    }
    model_call = {
        **asdict(profile),
        "provider": "openai",
        "status": "skipped",
        "fallback": False,
    }
    if not settings.llm_answer_enabled or not settings.openai_api_key:
        model_call["status"] = "fallback_disabled"
        model_call["fallback"] = True
        route = fallback_route_message(message)
        return RouteDecision(
            route=route,
            confidence=1.0,
            reason="OpenAI routing disabled; deterministic fallback used.",
            prompt_trace={**prompt_trace, "route": route, "fallback": True},
            model_call=model_call,
            usage={"prompt_tokens_estimated": prompt_trace["token_estimate"]},
            timings={},
            fallback_route=route,
        )

    timer = Timer()
    try:
        client = OpenAI(api_key=settings.openai_api_key, timeout=20)
        reasoning = None
        if profile.reasoning_effort != "none":
            reasoning = {"effort": profile.reasoning_effort}
        response = client.responses.create(
            model=profile.model,
            instructions=ROUTER_PROMPT,
            input=f"Message:\n{message}",
            max_output_tokens=120,
            reasoning=reasoning,
            prompt_cache_key=prompt_trace["cache_key"],
            store=False,
            metadata={
                "prompt_version": ROUTER_PROMPT_VERSION,
                "purpose": "message_router",
            },
        )
        payload = parse_router_payload(extract_output_text(response))
        route = sanitize_route(payload.get("route"))
        confidence = sanitize_confidence(payload.get("confidence"))
        reason = str(payload.get("reason") or "Mini-model route classification.")[:240]
        if route == "ontology" and not explicit_ontology_intent(message):
            route = "graph_rag"
            reason = "Ontology route overridden for document-grounded question."
            model_call["override"] = "ontology_to_graph_rag"
        model_call["status"] = "ok"
        model_call["response_id"] = getattr(response, "id", None)
        model_call["confidence"] = confidence
        model_call["selected_route"] = route
        usage_record = usage_from_openai(response, prompt_trace["token_estimate"])
        if confidence < settings.router_confidence_threshold:
            fallback_route = fallback_route_message(message)
            model_call["status"] = "fallback_low_confidence"
            model_call["fallback"] = True
            model_call["fallback_route"] = fallback_route
            return RouteDecision(
                route=fallback_route,
                confidence=confidence,
                reason=f"Router confidence below threshold; fallback route used. {reason}",
                prompt_trace={
                    **prompt_trace,
                    "route": fallback_route,
                    "model_route": route,
                    "fallback": True,
                },
                model_call=model_call,
                usage=usage_record.as_dict(),
                timings={"router_model_ms": timer.elapsed_ms()},
                fallback_route=fallback_route,
            )
        return RouteDecision(
            route=route,
            confidence=confidence,
            reason=reason,
            prompt_trace={**prompt_trace, "route": route, "fallback": False},
            model_call=model_call,
            usage=usage_record.as_dict(),
            timings={"router_model_ms": timer.elapsed_ms()},
        )
    except Exception as exc:
        fallback_route = fallback_route_message(message)
        model_call["status"] = "fallback_error"
        model_call["fallback"] = True
        model_call["fallback_route"] = fallback_route
        model_call["error"] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:180]}"
        return RouteDecision(
            route=fallback_route,
            confidence=0.0,
            reason="Router model failed; deterministic fallback used.",
            prompt_trace={**prompt_trace, "route": fallback_route, "fallback": True},
            model_call=model_call,
            usage={"prompt_tokens_estimated": prompt_trace["token_estimate"]},
            timings={"router_model_ms": timer.elapsed_ms()},
            fallback_route=fallback_route,
        )


def fallback_route_message(message: str) -> RouteName:
    normalized = " ".join(message.lower().strip(" !?.").split())
    if normalized in GREETINGS:
        return "greeting"
    if any(keyword in normalized for keyword in OFF_TOPIC_KEYWORDS):
        return "out_of_scope"
    if any(
        token in normalized
        for token in ("ontology", "domain object", "domain objects", "schema")
    ):
        return "ontology"
    if any(token in normalized for token in ("skill", "format", "json skill")):
        return "skill_management"
    return "graph_rag"


def explicit_ontology_intent(message: str) -> bool:
    normalized = " ".join(message.lower().strip(" !?.").split())
    ontology_terms = (
        "ontology",
        "domain object",
        "domain objects",
        "entities",
        "relationships",
        "graph structure",
        "schema",
        "object type",
        "object types",
    )
    return any(term in normalized for term in ontology_terms)


def parse_router_payload(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        parsed = json.loads(cleaned[start : end + 1])
    return parsed if isinstance(parsed, dict) else {}


def sanitize_route(value: object) -> RouteName:
    route = str(value or "").strip().lower()
    if route not in ALLOWED_ROUTES:
        return "graph_rag"
    return route  # type: ignore[return-value]


def sanitize_confidence(value: object) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


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
