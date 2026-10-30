import pytest

from app.tools.exceptions import ToolInputValidationError, ToolNotFoundError
from app.tools.registry import get_tool, list_tools, run_tool


def test_list_tools_includes_all_five_expected_tools():
    names = {spec.name for spec in list_tools()}
    assert names == {"read_file", "search_code", "repository_structure", "modify_file", "git_diff"}


def test_get_tool_returns_spec_for_known_tool():
    spec = get_tool("read_file")
    assert spec.name == "read_file"
    assert spec.description


def test_get_tool_raises_for_unknown_tool():
    with pytest.raises(ToolNotFoundError):
        get_tool("delete_everything")


def test_run_tool_raises_not_found_for_unknown_tool_name(db_session):
    from app.api.deps import get_current_user

    user = get_current_user(db_session, None)
    with pytest.raises(ToolNotFoundError):
        run_tool(db_session, user=user, tool_name="shell_exec", raw_input={})


def test_run_tool_raises_validation_error_for_malformed_input(db_session):
    from app.api.deps import get_current_user

    user = get_current_user(db_session, None)
    with pytest.raises(ToolInputValidationError):
        # missing required repository_id/file_path
        run_tool(db_session, user=user, tool_name="read_file", raw_input={})


def test_run_tool_raises_validation_error_for_wrong_type(db_session):
    from app.api.deps import get_current_user

    user = get_current_user(db_session, None)
    with pytest.raises(ToolInputValidationError):
        run_tool(
            db_session, user=user, tool_name="read_file",
            raw_input={"repository_id": "not-a-uuid", "file_path": "a.py"},
        )
