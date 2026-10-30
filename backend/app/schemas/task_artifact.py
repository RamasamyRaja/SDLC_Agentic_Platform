"""
Pydantic schemas for TaskArtifact create/read.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.task_artifact import ArtifactType


class TaskArtifactCreate(BaseModel):
    file_path: str = Field(..., min_length=1, max_length=1024)
    artifact_type: ArtifactType = ArtifactType.OTHER
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("file_path")
    @classmethod
    def file_path_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("file_path must not be empty or whitespace-only")
        if stripped.startswith("/") or ".." in stripped.split("/"):
            raise ValueError("file_path must be a relative, repository-scoped path")
        return stripped


class TaskArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    file_path: str
    artifact_type: ArtifactType
    notes: str | None
    created_at: datetime
