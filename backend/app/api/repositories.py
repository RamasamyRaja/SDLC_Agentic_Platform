"""
Repository endpoints.

Route handlers stay thin: validate via Pydantic, delegate to
app.services.repository_service, and shape the response. No cloning or
onboarding happens here (Milestone 3).
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.rbac import Permission, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.repository import RepositoryCreate, RepositoryResponse
from app.services import repository_service

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


@router.post("", response_model=RepositoryResponse, status_code=201)
def create_repository(
    payload: RepositoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPOSITORY_WRITE)),
) -> RepositoryResponse:
    repository = repository_service.create_repository(db, user=current_user, payload=payload)
    return RepositoryResponse.model_validate(repository)


@router.get("", response_model=list[RepositoryResponse])
def list_repositories(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPOSITORY_READ)),
) -> list[RepositoryResponse]:
    repositories = repository_service.list_repositories(db, user=current_user)
    return [RepositoryResponse.model_validate(r) for r in repositories]


@router.get("/{repository_id}", response_model=RepositoryResponse)
def get_repository(
    repository_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPOSITORY_READ)),
) -> RepositoryResponse:
    repository = repository_service.get_repository(db, user=current_user, repository_id=repository_id)
    return RepositoryResponse.model_validate(repository)
