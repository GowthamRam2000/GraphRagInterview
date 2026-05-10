from app.rag.model_policy import answer_profile, router_profile
from app.rag.prompts import build_answer_prompt
from app.services.store import EvidenceRecord


def test_answer_prompt_has_cache_key_and_evidence_boundaries() -> None:
    prompt = build_answer_prompt(
        message="What is secure AI?",
        evidence=[
            EvidenceRecord(
                evidence_id="ev_1",
                document_id="doc_1",
                page_number=4,
                text="Secure AI preserves confidentiality and integrity.",
                entities=["Secure AI"],
            )
        ],
        graph_paths=[["Secure AI", "RELATED_TO", "Integrity"]],
    )

    assert prompt.version == "rag-answer-v1.2"
    assert prompt.cache_key.startswith("cognizinterview-")
    assert "rag-answer-v1-2" in prompt.cache_key
    assert len(prompt.cache_key) <= 64
    assert "[Evidence 1 | type text | page 4 | id ev_1 | artifact none]" in prompt.user
    assert "Attach page citations like [p. 8] to every factual claim" in prompt.system
    assert "Response contract for GPT-5.4 mini" in prompt.developer
    assert prompt.token_estimate > 0


def test_model_profiles_capture_thinking_policy() -> None:
    router = router_profile()
    answer = answer_profile()

    assert router.model == "gpt-5.4-mini"
    assert router.reasoning_effort == "none"
    assert router.thinking is False
    assert answer.model == "gpt-5.4-mini"
    assert answer.reasoning_effort == "low"
    assert answer.thinking is True
