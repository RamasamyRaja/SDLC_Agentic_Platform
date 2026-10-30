
from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict


class ExecutionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    status: str
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
