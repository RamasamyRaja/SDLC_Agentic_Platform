"""
Pydantic schemas for Task create/read/status-update.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.task import TaskStatus

MIN_TASK_DESCRIPTION_LENGTH = 3
MAX_TASK_DESCRIPTION_LENGTH = 10_000


class TaskCreate(BaseModel):
    repository_id: uuid.UUID
    request: str = Field(
        ...,
        min_length=MIN_TASK_DESCRIPTION_LENGTH,
        max_length=MAX_TASK_DESCRIPTION_LENGTH,
        description="Natural-language description of the requested change.",
    )
    title: str | None = Field(default=None, max_length=255)
    branch: str | None = Field(default=None, max_length=255)
    expected_outcome: str | None = Field(default=None, max_length=5_000)
    context: str | None = Field(default=None, max_length=50_000, description="Extra context, e.g. pasted requirement document text")

    @field_validator("request")
    @classmethod
    def request_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("request must not be empty or whitespace-only")
        return stripped


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    repository_id: uuid.UUID
    title: str | None
    description: str
    branch: str | None
    status: TaskStatus
    created_at: datetime
    updated_at: datetime


class TaskCreateResponse(BaseModel):
    """Lean response returned right after creation (task_id/repository_id/status)."""

    task_id: uuid.UUID
    repository_id: uuid.UUID
    status: TaskStatus
    workflow_stage: str = "CREATED"
    planning_started: bool = False
    planning_blocker: str | None = None


class TaskStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: TaskStatus
    updated_at: datetime


class TaskStatusUpdate(BaseModel):
    status: TaskStatus
