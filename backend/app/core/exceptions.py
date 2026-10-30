"""
Domain-level exceptions for the service layer.

Services raise these instead of leaking raw SQLAlchemy/database exceptions.
API routers translate them into appropriate HTTP responses (see
app/api/errors.py) so route handlers stay free of try/except boilerplate.
"""


class NotFoundError(Exception):
    """A requested resource does not exist."""


class OwnershipError(Exception):
    """The current user does not own/have access to the requested resource."""


class InvalidStatusTransitionError(Exception):
    """The requested status transition is not allowed from the current status."""


class ValidationError(Exception):
    """A domain-level validation rule failed (distinct from Pydantic input validation)."""


class RepositoryCloneError(Exception):
    """Cloning or checking out the repository failed (unreachable host, bad URL, auth, etc.)."""


class BranchNotFoundError(Exception):
    """The requested/default branch does not exist in the remote repository."""


class LLMUnavailableError(Exception):
    """The LLM provider could not be reached/authenticated — a controlled
    failure, never papered over with a fabricated answer."""


class LLMOutputValidationError(Exception):
    """The model's response could not be validated as a ReasoningResult
    even after the bounded retry budget was exhausted."""


class WorkflowStateError(Exception):
    """The requested lifecycle action is not allowed from the task's current stage (HTTP 409)."""


class PermissionDeniedError(Exception):
    """The caller's role does not allow this lifecycle action (HTTP 403)."""
