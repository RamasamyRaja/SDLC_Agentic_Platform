"""
Robust JSON extraction from an LLM response.

Even with `response_format={"type": "json_object"}` requested (see
mistral_provider.py's docstring — this guarantees valid JSON but not schema
conformance), defensive extraction is still worthwhile: some responses
include the JSON wrapped in markdown code fences despite instructions not
to, or with leading/trailing whitespace/prose. This performs the "robust
JSON extraction" half of the spec's "structured output OR robust JSON
extraction + Pydantic validation" fallback; Pydantic validation (schemas.py
/ service.py) is the other half, and runs regardless of how the JSON was
extracted.
"""
import json
import re


class JSONExtractionError(Exception):
    """The response text contained no parseable JSON object."""


_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> dict:
    text = text.strip()

    # Try straight parsing first — the common case with JSON mode enabled.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try unwrapping a markdown code fence.
    fence_match = _FENCE_PATTERN.search(text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Last resort: find the first '{' and matching last '}' and try that
    # substring — handles stray leading/trailing prose around the object.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise JSONExtractionError("No parseable JSON object found in the model's response")
