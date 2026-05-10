from app.core.config import get_settings
from app.rag.router import classify_route, fallback_route_message


class FakeUsage:
    input_tokens = 12
    output_tokens = 6
    total_tokens = 18
    input_tokens_details = None
    output_tokens_details = None


class FakeResponse:
    id = "resp_router_test"
    output_text = '{"route":"ontology","confidence":0.94,"reason":"asks for schema"}'
    usage = FakeUsage()


class FakeResponses:
    def create(self, **kwargs):
        self.kwargs = kwargs
        return FakeResponse()


class FakeClient:
    last_responses = FakeResponses()

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.responses = self.last_responses


def test_router_uses_openai_mini_model_and_structured_prompt(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_ANSWER_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr("app.rag.router.OpenAI", FakeClient)

    decision = classify_route("List the ontology domain objects in this document")

    assert decision.route == "ontology"
    assert decision.confidence == 0.94
    assert decision.model_call["status"] == "ok"
    assert decision.model_call["model"] == "gpt-5.4-mini"
    assert decision.model_call["response_id"] == "resp_router_test"
    assert decision.prompt_trace["version"] == "router-v1.2"
    assert decision.prompt_trace["cache_key"]
    assert FakeClient.last_responses.kwargs["model"] == "gpt-5.4-mini"
    assert (
        FakeClient.last_responses.kwargs["prompt_cache_key"]
        == decision.prompt_trace["cache_key"]
    )
    assert "Return JSON only" in FakeClient.last_responses.kwargs["instructions"]

    get_settings.cache_clear()


def test_router_falls_back_when_confidence_is_low(monkeypatch) -> None:
    class LowConfidenceResponse(FakeResponse):
        output_text = '{"route":"out_of_scope","confidence":0.2,"reason":"ambiguous"}'

    class LowConfidenceResponses(FakeResponses):
        def create(self, **kwargs):
            self.kwargs = kwargs
            return LowConfidenceResponse()

    class LowConfidenceClient(FakeClient):
        last_responses = LowConfidenceResponses()

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.responses = self.last_responses

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_ANSWER_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr("app.rag.router.OpenAI", LowConfidenceClient)

    decision = classify_route("What are the four core functions?")

    assert decision.route == "graph_rag"
    assert decision.model_call["status"] == "fallback_low_confidence"
    assert decision.model_call["fallback"] is True
    assert decision.prompt_trace["model_route"] == "out_of_scope"

    get_settings.cache_clear()


def test_deterministic_fallback_routes_greeting_and_obvious_offtopic() -> None:
    assert fallback_route_message("hello") == "greeting"
    assert fallback_route_message("what is the weather today?") == "out_of_scope"
    assert fallback_route_message("show ontology domain objects") == "ontology"
    assert fallback_route_message("format this with a skill") == "skill_management"
    assert fallback_route_message("what are the four core functions?") == "graph_rag"


def test_router_overrides_ontology_for_document_category_questions(monkeypatch) -> None:
    class CategoryResponse(FakeResponse):
        output_text = '{"route":"ontology","confidence":0.93,"reason":"asks categories"}'

    class CategoryResponses(FakeResponses):
        def create(self, **kwargs):
            self.kwargs = kwargs
            return CategoryResponse()

    class CategoryClient(FakeClient):
        last_responses = CategoryResponses()

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.responses = self.last_responses

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_ANSWER_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr("app.rag.router.OpenAI", CategoryClient)

    decision = classify_route("What are important GOVERN categories or subcategories?")

    assert decision.route == "graph_rag"
    assert decision.model_call["override"] == "ontology_to_graph_rag"

    get_settings.cache_clear()
