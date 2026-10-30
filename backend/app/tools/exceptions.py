"""
Tool-layer exceptions.

Deliberately distinct from the M1-M6 domain exceptions (NotFoundError,
ValidationError, ...) so a tool failure is always identifiable as a tool
failure at the API/graph layer — but every ToolError still maps to a
sensible HTTP status via app/api/errors.py, same as every other exception
family in this project.
"""


class ToolError(Exception):
    """Base class for all tool-layer failures."""


class ToolNotFoundError(ToolError):
    """The requested tool name is not in the registry."""


class ToolInputValidationError(ToolError):
    """The tool's input failed Pydantic/domain validation."""


class PathSecurityError(ToolError):
    """
    A supplied path failed workspace-boundary validation: absolute path,
    `..` traversal, or a resolved/symlinked target outside the repository
    workspace. Always treated as untrusted input — see
    app/tools/path_safety.py.
    """


class ToolFileNotFoundError(ToolError):
    """The target file does not exist inside the repository workspace."""


class FileTooLargeError(ToolError):
    """The target file exceeds TOOL_MAX_FILE_SIZE_BYTES."""


class ModificationNotFoundError(ToolError):
    """modify_file's `old_content` was not found in the target file."""


class AmbiguousModificationError(ToolError):
    """modify_file's `old_content` occurs more than once — refusing to guess."""


class ToolCallLimitExceededError(ToolError):
    """The automated TOOL_EXECUTION node hit AGENT_MAX_TOOL_CALLS."""
