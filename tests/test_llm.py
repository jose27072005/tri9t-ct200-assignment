import json
from app import llm


def payload(node_id=12):
    return json.dumps({"cases": [
        {"title": "Requirement check", "preconditions": ["Requirement is loaded"],
         "steps": ["Read the requirement", "Perform the stated check"],
         "expected_result": "Exact requirement text",
         "source_evidence": "Exact requirement text",
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


def test_generation_retries_when_expected_result_is_not_source_evidence(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "primary")
    monkeypatch.delenv("LLM_FALLBACK_API_KEY", raising=False)
    unsupported = json.loads(payload())
    unsupported["cases"][0]["expected_result"] = "Replacing batteries clears the low battery icon."
    unsupported["cases"][0]["source_evidence"] = "Exact requirement text"
    responses = iter([json.dumps(unsupported), payload()])
    monkeypatch.setattr(llm, "_call", lambda *args: next(responses))

    cases, model, attempts, provider = llm.generate("[12] Exact requirement text", [12])

    assert len(cases.cases) == 3
    assert attempts == 2
    assert provider == "primary"


def test_generation_rejects_invented_numeric_claims(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "primary")
    monkeypatch.delenv("LLM_FALLBACK_API_KEY", raising=False)
    invented = json.loads(payload())
    invented["cases"][0]["steps"][0] = "Perform 255 measurement cycles"
    monkeypatch.setattr(llm, "_call", lambda *args: json.dumps(invented))

    try:
        llm.generate("[12] Exact requirement text", [12])
    except ValueError as exc:
        assert "numeric values absent" in str(exc)
    else:
        raise AssertionError("invented numeric claims must not be accepted")


def test_generation_rejects_predicted_outcomes_inside_steps(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "primary")
    monkeypatch.delenv("LLM_FALLBACK_API_KEY", raising=False)
    unsupported = json.loads(payload())
    unsupported["cases"][0]["steps"][1] = "Confirm the device indicates replacement is required"
    monkeypatch.setattr(llm, "_call", lambda *args: json.dumps(unsupported))

    try:
        llm.generate("[12] Exact requirement text", [12])
    except ValueError as exc:
        assert "device-output concept absent" in str(exc)
    else:
        raise AssertionError("steps must not invent an expected device outcome")


def test_generation_allows_neutral_observation_question(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "primary")
    monkeypatch.delenv("LLM_FALLBACK_API_KEY", raising=False)
    observed = json.loads(payload())
    evidence = "The low-battery icon appears."
    for case in observed["cases"]:
        case["expected_result"] = evidence
        case["source_evidence"] = evidence
    observed["cases"][0]["steps"][1] = "Observe whether the low-battery icon appears"
    monkeypatch.setattr(llm, "_call", lambda *args: json.dumps(observed))

    cases, _, attempts, _ = llm.generate("[12] " + evidence, [12])

    assert len(cases.cases) == 3
    assert attempts == 1


def test_generation_allows_outcome_verb_supported_by_exact_evidence(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "primary")
    monkeypatch.delenv("LLM_FALLBACK_API_KEY", raising=False)
    supported_text = "Device displays a low battery icon."
    supported = json.loads(payload())
    for case in supported["cases"]:
        case["expected_result"] = supported_text
        case["source_evidence"] = supported_text
    supported["cases"][0]["steps"][1] = "Observe that the device displays a low battery icon"
    monkeypatch.setattr(llm, "_call", lambda *args: json.dumps(supported))

    cases, _, attempts, _ = llm.generate("[12] " + supported_text, [12])

    assert len(cases.cases) == 3
    assert attempts == 1


def test_generation_rejects_unstated_device_indication(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "primary")
    monkeypatch.delenv("LLM_FALLBACK_API_KEY", raising=False)
    unsupported = json.loads(payload())
    unsupported["cases"][0]["steps"][1] = "Observe device indication for battery replacement"
    monkeypatch.setattr(llm, "_call", lambda *args: json.dumps(unsupported))

    try:
        llm.generate("[12] Exact requirement text", [12])
    except ValueError as exc:
        assert "device-output concept absent" in str(exc)
    else:
        raise AssertionError("steps must not assume an undocumented device indication")


def test_generation_evidence_must_match_a_cited_node(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "primary")
    monkeypatch.delenv("LLM_FALLBACK_API_KEY", raising=False)
    monkeypatch.setattr(llm, "_call", lambda *args: payload(node_id=12))

    try:
        llm.generate("[12] Other source text", [12, 13], {12: "Different source text", 13: "Exact requirement text"})
    except ValueError as exc:
        assert "cited source nodes" in str(exc)
    else:
        raise AssertionError("evidence from an uncited node must not be accepted")
