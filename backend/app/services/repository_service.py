"""
Repository service.

Handles create/retrieve/list for Repository records. Does NOT clone
repositories — that begins in Milestone 3, which will move
`RepositoryStatus` from PENDING to READY (or ERROR) once onboarding runs.
"""
import re
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import BranchNotFoundError, NotFoundError, OwnershipError
from app.services import git_service
from app.models.repository import Repository
from app.models.user import User
from app.schemas.repository import RepositoryCreate

_DEFAULT_BRANCH = "main"


def _derive_name_from_url(url: str) -> str:
    """Best-effort repository name derived from a Git URL, e.g. .../org/project(.git) -> project."""
    cleaned = url.rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[: -len(".git")]
    match = re.search(r"[^/]+$", cleaned)
    return match.group(0) if match else cleaned


def create_repository(db: Session, *, user: User, payload: RepositoryCreate) -> Repository:
    """
    Register a repository and record its REAL default branch.

    * no branch supplied -> ask the remote for its HEAD symref (`git ls-remote --symref`); never assume "main"
    * branch supplied    -> use it; if the remote is reachable and lacks that branch, refuse
    * remote unreachable -> fall back to "main" but record `default_branch_source="fallback"`; onboarding re-resolves it
    """
    url = str(payload.url)
    if payload.branch:
        branch, source = payload.branch, "user_specified"
        if not git_service.remote_branch_exists(url, payload.branch, default=True):
            raise BranchNotFoundError(f"Branch '{payload.branch}' does not exist in {url}")
    else:
        detected = git_service.resolve_remote_default_branch(url)
        branch, source = (detected, "remote_head") if detected else (_DEFAULT_BRANCH, "fallback")
    repository = Repository(
        user_id=user.id,
        name=payload.name or _derive_name_from_url(url),
        url=url,
        default_branch=branch,
        default_branch_source=source,
    )
    db.add(repository)
    db.commit()
    db.refresh(repository)
    return repository


def get_repository(db: Session, *, user: User, repository_id: uuid.UUID) -> Repository:
    # Repositories are a shared team resource: the lifecycle needs an Architect or Viewer to read what a Developer
    # onboarded. What each role may DO is decided by RBAC permissions on the endpoints, not by row ownership.
    repository = db.get(Repository, repository_id)
    if repository is None:
        raise NotFoundError(f"Repository {repository_id} not found")
    return repository


def list_repositories(db: Session, *, user: User) -> list[Repository]:
    return db.query(Repository).order_by(Repository.created_at.desc()).all()
