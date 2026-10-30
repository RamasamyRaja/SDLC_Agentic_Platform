"""
Pydantic schemas for RepositoryDocument (read-only — created internally by
the onboarding service, never via a create endpoint).
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.repository_document import DocumentAnalysisStatus


class RepositoryDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_id: uuid.UUID
    file_path: str
    language: str | None
    file_size: int
    content_hash: str
    analysis_status: DocumentAnalysisStatus
    created_at: datetime
