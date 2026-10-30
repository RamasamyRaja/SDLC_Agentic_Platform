"""
Pydantic schemas for Repository create/read.

Validation only — no business logic here (that lives in
app/services/repository_service.py).
"""
import uuid
from datetime import datetime

from pydantic import AnyUrl, BaseModel, ConfigDict, Field

from app.models.repository import RepositoryStatus


class RepositoryCreate(BaseModel):
    url: AnyUrl = Field(..., description="Git repository URL, e.g. https://github.com/example/project")
    branch: str | None = Field(
        default=None,
        max_length=255,
        description="Target/default branch. Defaults to 'main' if not provided.",
    )
    name: str | None = Field(
        default=None,
        max_length=255,
        description="Optional display name. Derived from the URL if not provided.",
    )


class RepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    url: str
    default_branch: str
    workspace_path: str | None
    status: RepositoryStatus
    default_branch_source: str = "fallback"
    commit_sha: str | None = None
    indexing_status: str | None = None
    indexed_chunk_count: int | None = None
    last_indexed_at: datetime | None = None
    onboarding_error: str | None = None
    indexing_error: str | None = None
    created_at: datetime
    updated_at: datetime
