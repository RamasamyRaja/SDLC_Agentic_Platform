"""
Task analysis endpoint: runs the Milestone 5 reasoning layer against a
task and persists the result. Never exposes the raw Mistral response or
any credentials — only the validated, grounded structured result.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.rbac import Permission, require_permission
from app.core.exceptions import LLMOutputValidationError, LLMUnavailableError
from app.db.session import get_db
from app.llm import service as reasoning_service
from app.llm.schemas import PROMPT_VERSION
from app.models.task_analysis import TaskAnalysisStatus
from app.models.user import User
from app.schemas.task_analysis import TaskAnalyzeResponse

router = APIRouter(prefix="/api/tasks/{task_id}", tags=["task-analysis"])


@router.post("/analyze", response_model=TaskAnalyzeResponse, status_code=201)
def analyze_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.TASK_WRITE)),
) -> TaskAnalyzeResponse:
    try:
        result, _context, model_name = reasoning_service.analyze_task(
            db, user=current_user, task_id=task_id
        )
    except (LLMUnavailableError, LLMOutputValidationError) as exc:
        reasoning_service.persist_task_analysis(
            db,
            task_id=task_id,
            model_name="unknown",
            status=TaskAnalysisStatus.FAILED,
            error=str(exc),
        )
        raise

    reasoning_service.persist_task_analysis(
        db,
        task_id=task_id,
        model_name=model_name,
        status=TaskAnalysisStatus.COMPLETED,
        result=result,
    )

    return TaskAnalyzeResponse(
        task_id=task_id, model=model_name, prompt_version=PROMPT_VERSION, result=result
    )
