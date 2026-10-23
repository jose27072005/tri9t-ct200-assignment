import json
from app import llm


def payload(node_id=12):
    return json.dumps({"cases": [
        {"title": f"Requirement check {i}", "preconditions": ["Requirement is loaded"],
         "steps": ["Read the requirement", "Perform the stated check"],
         "expected_result": "The observed result matches the documented requirement.",
         "source_node_ids": [node_id], "risk": "medium"}
        for i in range(3)
    ]})


def test_primary_validation_retry_then_fallback(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "primary")
    monkeypatch.setenv("LLM_FALLBACK_API_KEY", "secondary")
    monkeypatch.setenv("LLM_MODEL", "primary-model")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "fallback-model")
    responses = iter(["not json", "still not json", payload()])
    monkeypatch.setattr(llm, "_call", lambda *args: next(responses))

    cases, model, attempts, provider = llm.generate("[12] Exact requirement text", [12])

    assert len(cases.cases) == 3
    assert (model, attempts, provider) == ("fallback-model", 3, "fallback")


def test_generation_rejects_unselected_node_citations(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "primary")
    monkeypatch.delenv("LLM_FALLBACK_API_KEY", raising=False)
    monkeypatch.setattr(llm, "_call", lambda *args: payload(node_id=999))

    try:
        llm.generate("[12] Exact requirement text", [12])
    except ValueError as exc:
        assert "after bounded retry/fallback" in str(exc)
    else:
        raise AssertionError("out-of-selection citations must not be accepted")
