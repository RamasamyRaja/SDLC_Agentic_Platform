"""
Import every ORM model here so that:
  1. `Base.metadata` is fully populated for Alembic autogenerate.
  2. Application code can `from app.models import User` etc.

As later milestones add models, import them here as well.
"""
from app.models.agent_execution import AgentExecution, AgentExecutionStatus  # noqa: F401
from app.models.code_chunk import CodeChunk  # noqa: F401
from app.models.embedding_metadata import EmbeddingMetadata  # noqa: F401
from app.models.repository import IndexingStatus, Repository, RepositoryStatus  # noqa: F401
from app.models.repository_document import DocumentAnalysisStatus, RepositoryDocument  # noqa: F401
from app.models.sandbox_run import SandboxRun, SandboxRunStatus  # noqa: F401
from app.models.task import ALLOWED_TASK_STATUS_TRANSITIONS, Task, TaskStatus  # noqa: F401
from app.models.task_analysis import TaskAnalysis, TaskAnalysisStatus  # noqa: F401
from app.models.task_artifact import ArtifactType, TaskArtifact  # noqa: F401
from app.models.tool_invocation import ToolInvocation, ToolInvocationStatus  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.workflow import (  # noqa: F401
    Deployment,
    DevelopmentRun,
    MergeRequest,
    ReviewDecision,
    TaskPlan,
    ValidationCheck,
    WorkflowEvent,
)

__all__ = [
    "User",
    "Repository",
    "RepositoryStatus",
    "IndexingStatus",
    "RepositoryDocument",
    "SandboxRun",
    "SandboxRunStatus",
    "DocumentAnalysisStatus",
    "CodeChunk",
    "EmbeddingMetadata",
    "Task",
    "TaskStatus",
    "ALLOWED_TASK_STATUS_TRANSITIONS",
    "TaskArtifact",
    "ArtifactType",
    "TaskAnalysis",
    "TaskAnalysisStatus",
    "AgentExecution",
    "AgentExecutionStatus",
    "ToolInvocation",
    "ToolInvocationStatus",
    "TaskPlan",
    "DevelopmentRun",
    "ValidationCheck",
    "MergeRequest",
    "Deployment",
    "ReviewDecision",
    "WorkflowEvent",
]
