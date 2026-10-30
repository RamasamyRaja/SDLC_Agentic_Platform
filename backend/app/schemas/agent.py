"""
Pydantic schemas for POST /api/tasks/{task_id}/run and
GET /api/tasks/{task_id}/run/{execution_id}.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.agent.models import AgentAction, AgentExecutionStatus
from app.llm.schemas import ReasoningResult


class AgentRunRequest(BaseModel):
    execute_changes: bool = False   # planning/analysis only; source changes go through the approved-plan lifecycle
    run_validation: bool = True
    max_repairs: int = 2

class AgentRunResponse(BaseModel):
    execution_id: uuid.UUID
    task_id: uuid.UUID
    status: AgentExecutionStatus
    action: AgentAction | None
    model_name: str | None
    reasoning_result: ReasoningResult | None
    errors: list[str]
    tool_call_count: int = 0
    tool_results: list[dict] = []
    validation: dict | None = None
    changed_files: list[str] = []
    repair_attempts: int = 0
    final_diff: str | None = None


class AgentExecutionDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    status: AgentExecutionStatus
    action: str | None
    model_name: str | None
    result: dict | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    validation: dict | None = None
    changed_files: list[str] = []
    repair_attempts: int | None = None
    final_diff: str | None = None

    @field_validator("changed_files", mode="before")
    @classmethod
    def _none_to_empty(cls, value):
        # rows written by the planning-only graph have no changed_files; that means "none", not "invalid"
        return [] if value is None else value
