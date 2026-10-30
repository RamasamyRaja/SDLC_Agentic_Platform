"""
Maps domain-level exceptions (app.core.exceptions) to HTTP responses.

Kept separate from the exceptions themselves so app.core stays framework-
agnostic and app.services never needs to import FastAPI.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    BranchNotFoundError,
    InvalidStatusTransitionError,
    LLMOutputValidationError,
    LLMUnavailableError,
    NotFoundError,
    OwnershipError,
    PermissionDeniedError,
    RepositoryCloneError,
    ValidationError,
    WorkflowStateError,
)
from app.tools.exceptions import (
    AmbiguousModificationError,
    FileTooLargeError,
    ModificationNotFoundError,
    PathSecurityError,
    ToolCallLimitExceededError,
    ToolError,
    ToolFileNotFoundError,
    ToolInputValidationError,
    ToolNotFoundError,
)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(OwnershipError)
    async def ownership_handler(request: Request, exc: OwnershipError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(InvalidStatusTransitionError)
    async def invalid_transition_handler(
        request: Request, exc: InvalidStatusTransitionError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(WorkflowStateError)
    async def workflow_state_handler(request: Request, exc: WorkflowStateError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(PermissionDeniedError)
    async def permission_denied_handler(request: Request, exc: PermissionDeniedError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(ValidationError)
    async def validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(RepositoryCloneError)
    async def clone_error_handler(request: Request, exc: RepositoryCloneError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(BranchNotFoundError)
    async def branch_not_found_handler(request: Request, exc: BranchNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(LLMUnavailableError)
    async def llm_unavailable_handler(request: Request, exc: LLMUnavailableError) -> JSONResponse:
        # 502: the failure is upstream (the LLM provider), never presented
        # as if the application itself is broken, and never carries
        # provider internals (API keys, raw transport errors) — str(exc)
        # is already a clean, provider-specific message from mistral_provider.py.
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(LLMOutputValidationError)
    async def llm_output_validation_handler(
        request: Request, exc: LLMOutputValidationError
    ) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    # --- Tool-layer errors (Milestone 7) ---
    # Specific subclasses registered before the ToolError base handler so
    # FastAPI matches the most specific type first.

    @app.exception_handler(ToolNotFoundError)
    async def tool_not_found_handler(request: Request, exc: ToolNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ToolFileNotFoundError)
    async def tool_file_not_found_handler(request: Request, exc: ToolFileNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ModificationNotFoundError)
    async def modification_not_found_handler(
        request: Request, exc: ModificationNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(PathSecurityError)
    async def path_security_handler(request: Request, exc: PathSecurityError) -> JSONResponse:
        # Never echoes back the untrusted path in a way that could be
        # mistaken for a validated one — str(exc) already only contains
        # the rejected value inside a clear "not allowed" message.
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(ToolInputValidationError)
    async def tool_input_validation_handler(
        request: Request, exc: ToolInputValidationError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(FileTooLargeError)
    async def file_too_large_handler(request: Request, exc: FileTooLargeError) -> JSONResponse:
        return JSONResponse(status_code=413, content={"detail": str(exc)})

    @app.exception_handler(AmbiguousModificationError)
    async def ambiguous_modification_handler(
        request: Request, exc: AmbiguousModificationError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ToolCallLimitExceededError)
    async def tool_call_limit_handler(request: Request, exc: ToolCallLimitExceededError) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    @app.exception_handler(ToolError)
    async def tool_error_handler(request: Request, exc: ToolError) -> JSONResponse:
        # Fallback for any ToolError subclass not specifically handled above.
        return JSONResponse(status_code=400, content={"detail": str(exc)})
