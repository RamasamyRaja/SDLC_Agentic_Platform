"""
ToolRegistry: name -> ToolSpec lookup, the single place tool name
validation happens. Both the API (app/api/tools.py) and the LangGraph
TOOL_EXECUTION node (app/agent/nodes.py) go through this registry rather
than importing a tool function directly by name — an unknown tool name is
always rejected here, in one place.

Adding a future tool (a formatter, a linter, eventually a bounded test
runner under a real sandbox) means adding one entry here — nothing else
needs to change.
"""
from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.user import User
from app.tools.exceptions import ToolNotFoundError
from app.tools.filesystem import modify_file, read_file
from app.tools.git import git_diff
from app.tools.models import (
    GitDiffInput,
    GitDiffOutput,
    ModifyFileInput,
    ModifyFileOutput,
    ReadFileInput,
    ReadFileOutput,
    RepositoryStructureInput,
    RepositoryStructureOutput,
    SearchCodeInput,
    SearchCodeOutput,
)
from app.tools.search import search_code
from app.tools.tree import repository_structure


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    func: Callable[[Session, User, BaseModel], BaseModel]


def _run_read_file(db: Session, user: User, input_data: ReadFileInput) -> ReadFileOutput:
    return read_file(db, user=user, input_data=input_data)


def _run_search_code(db: Session, user: User, input_data: SearchCodeInput) -> SearchCodeOutput:
    return search_code(db, user=user, input_data=input_data)


def _run_repository_structure(
    db: Session, user: User, input_data: RepositoryStructureInput
) -> RepositoryStructureOutput:
    return repository_structure(db, user=user, input_data=input_data)


def _run_modify_file(db: Session, user: User, input_data: ModifyFileInput) -> ModifyFileOutput:
    return modify_file(db, user=user, input_data=input_data)


def _run_git_diff(db: Session, user: User, input_data: GitDiffInput) -> GitDiffOutput:
    return git_diff(db, user=user, input_data=input_data)


_TOOL_REGISTRY: dict[str, ToolSpec] = {
    "read_file": ToolSpec(
        name="read_file",
        description="Read a file (optionally a line range) from a repository's workspace.",
        input_model=ReadFileInput,
        output_model=ReadFileOutput,
        func=_run_read_file,
    ),
    "search_code": ToolSpec(
        name="search_code",
        description="Search source files in a repository's workspace for a text query.",
        input_model=SearchCodeInput,
        output_model=SearchCodeOutput,
        func=_run_search_code,
    ),
    "repository_structure": ToolSpec(
        name="repository_structure",
        description="Return a bounded directory/file tree for a repository's workspace.",
        input_model=RepositoryStructureInput,
        output_model=RepositoryStructureOutput,
        func=_run_repository_structure,
    ),
    "modify_file": ToolSpec(
        name="modify_file",
        description=(
            "Replace an unambiguous, single occurrence of old_content with new_content "
            "in one file. Refuses to act if old_content is missing or ambiguous."
        ),
        input_model=ModifyFileInput,
        output_model=ModifyFileOutput,
        func=_run_modify_file,
    ),
    "git_diff": ToolSpec(
        name="git_diff",
        description="Inspect local, uncommitted changes in a repository's workspace.",
        input_model=GitDiffInput,
        output_model=GitDiffOutput,
        func=_run_git_diff,
    ),
}


def get_tool(name: str) -> ToolSpec:
    spec = _TOOL_REGISTRY.get(name)
    if spec is None:
        raise ToolNotFoundError(f"Unknown tool: {name!r}")
    return spec


def list_tools() -> list[ToolSpec]:
    return list(_TOOL_REGISTRY.values())


def run_tool(db: Session, *, user: User, tool_name: str, raw_input: dict) -> BaseModel:
    """
    Validates `raw_input` against the tool's input model, then executes it.
    This is the ONE function that should be called to run a tool by name
    with untrusted (e.g. model-generated or HTTP-request) input — it never
    trusts `raw_input`'s shape.
    """
    from pydantic import ValidationError as PydanticValidationError

    from app.tools.exceptions import ToolInputValidationError

    spec = get_tool(tool_name)
    try:
        validated_input = spec.input_model.model_validate(raw_input)
    except PydanticValidationError as exc:
        raise ToolInputValidationError(f"Invalid input for tool {tool_name!r}: {exc}") from exc

    return spec.func(db, user, validated_input)
