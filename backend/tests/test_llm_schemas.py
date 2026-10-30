import pydantic
import pytest

from app.llm.parsing import JSONExtractionError, extract_json
from app.llm.schemas import ReasoningResult

VALID_PAYLOAD = {
    "summary": "Add a delete button to the Investigations page.",
    "understanding": {"goal": "Allow deleting an investigation", "affected_area": "Investigations UI"},
    "relevant_files": [{"file_path": "src/InvestigationPage.tsx", "reason": "UI entry point", "confidence": 0.9}],
    "affected_symbols": [
        {"file_path": "src/InvestigationService.java", "symbol_name": "deleteInvestigation", "reason": "backend call"}
    ],
    "implementation_plan": [
        {"step": 1, "description": "Add delete button", "target_files": ["src/InvestigationPage.tsx"]}
    ],
    "dependencies": ["InvestigationService"],
    "risks": ["Could delete without confirmation"],
    "uncertainties": ["Unsure if soft-delete is required"],
    "confidence": 0.85,
}


def test_extract_json_parses_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_unwraps_markdown_fence():
    text = 'Here you go:\n```json\n{"a": 2}\n```\nDone.'
    assert extract_json(text) == {"a": 2}


def test_extract_json_finds_embedded_object():
    text = 'Sure, here is my answer: {"a": 3} - hope that helps!'
    assert extract_json(text) == {"a": 3}


def test_extract_json_raises_when_no_json_present():
    with pytest.raises(JSONExtractionError):
        extract_json("no json anywhere in this text")


def test_reasoning_result_accepts_valid_payload():
    result = ReasoningResult.model_validate(VALID_PAYLOAD)
    assert result.summary == VALID_PAYLOAD["summary"]
    assert result.confidence == 0.85
    assert result.relevant_files[0].file_path == "src/InvestigationPage.tsx"
    assert result.relevant_files[0].grounded is None  # not grounded yet


def test_reasoning_result_rejects_missing_required_field():
    payload = dict(VALID_PAYLOAD)
    del payload["summary"]
    with pytest.raises(pydantic.ValidationError):
        ReasoningResult.model_validate(payload)


def test_reasoning_result_rejects_blank_summary():
    payload = dict(VALID_PAYLOAD)
    payload["summary"] = "   "
    with pytest.raises(pydantic.ValidationError):
        ReasoningResult.model_validate(payload)


def test_reasoning_result_rejects_invalid_confidence_range():
    payload = dict(VALID_PAYLOAD)
    payload["confidence"] = 1.5
    with pytest.raises(pydantic.ValidationError):
        ReasoningResult.model_validate(payload)


def test_reasoning_result_rejects_wrong_type_for_relevant_files():
    payload = dict(VALID_PAYLOAD)
    payload["relevant_files"] = "not-a-list"
    with pytest.raises(pydantic.ValidationError):
        ReasoningResult.model_validate(payload)


def test_reasoning_result_rejects_invalid_step_number():
    payload = dict(VALID_PAYLOAD)
    payload["implementation_plan"] = [{"step": 0, "description": "bad step", "target_files": []}]
    with pytest.raises(pydantic.ValidationError):
        ReasoningResult.model_validate(payload)


def test_reasoning_result_allows_empty_optional_lists():
    payload = {
        "summary": "Minimal valid response.",
        "understanding": {"goal": "g", "affected_area": "a"},
        "confidence": 0.5,
    }
    result = ReasoningResult.model_validate(payload)
    assert result.relevant_files == []
    assert result.risks == []
