"""
Pydantic schemas for the POST /api/tasks/{task_id}/analyze response.

Deliberately does NOT expose the raw Mistral response or the full prompt —
only the validated, grounded `ReasoningResult`.
"""
import uuid

from pydantic import BaseModel

from app.llm.schemas import ReasoningResult


class TaskAnalyzeResponse(BaseModel):
    task_id: uuid.UUID
    model: str
    prompt_version: str
    result: ReasoningResult
