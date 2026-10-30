import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _build_local_git_repo(tmp_path: Path, name: str = "tools_origin") -> Path:
    origin = tmp_path / name
    origin.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=origin, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=origin, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=origin, check=True)

    (origin / "src").mkdir()
    shutil.copy(FIXTURES / "python_sample" / "investigation_service.py", origin / "src")
    (origin / "node_modules").mkdir()
    (origin / "node_modules" / "ignored.js").write_text("should never be scanned")

    subprocess.run(["git", "add", "."], cwd=origin, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=origin, check=True, capture_output=True)
    return origin


@pytest.fixture()
def onboarded_repo(client, db_session, tmp_path):
    origin = _build_local_git_repo(tmp_path)
    repo = client.post("/api/repositories", json={"url": f"file://{origin}", "branch": "main"}).json()
    assert client.post(f"/api/repositories/{repo['id']}/onboard", json={}).status_code == 201

    yield repo

    from app.models.repository import Repository
    from app.services import workspace_service

    db_session.query(Repository).filter(Repository.id == repo["id"]).delete()
    db_session.commit()
    workspace_service.remove_workspace(uuid.UUID(repo["id"]))


def _user(db_session):
    from app.api.deps import get_current_user

    return get_current_user(db_session, None)


# ============================================================
# read_file
# ============================================================


def test_read_file_returns_full_content(db_session, onboarded_repo):
    from app.tools.filesystem import read_file
    from app.tools.models import ReadFileInput

    output = read_file(
        db_session, user=_user(db_session),
        input_data=ReadFileInput(repository_id=uuid.UUID(onboarded_repo["id"]), file_path="src/investigation_service.py"),
    )
    assert "class InvestigationService" in output.content
    assert output.total_lines == 6


def test_read_file_respects_line_range(db_session, onboarded_repo):
    from app.tools.filesystem import read_file
    from app.tools.models import ReadFileInput

    output = read_file(
        db_session, user=_user(db_session),
        input_data=ReadFileInput(
            repository_id=uuid.UUID(onboarded_repo["id"]), file_path="src/investigation_service.py",
            start_line=4, end_line=4,
        ),
    )
    assert output.content == "class InvestigationService:"
    assert output.start_line == 4
    assert output.end_line == 4


def test_read_file_not_found_for_missing_file(db_session, onboarded_repo):
    from app.tools.exceptions import ToolFileNotFoundError
    from app.tools.filesystem import read_file
    from app.tools.models import ReadFileInput

    with pytest.raises(ToolFileNotFoundError):
        read_file(
            db_session, user=_user(db_session),
            input_data=ReadFileInput(repository_id=uuid.UUID(onboarded_repo["id"]), file_path="does/not/exist.py"),
        )


def test_read_file_rejects_path_traversal(db_session, onboarded_repo):
    from app.tools.exceptions import PathSecurityError
    from app.tools.filesystem import read_file
    from app.tools.models import ReadFileInput

    with pytest.raises(PathSecurityError):
        read_file(
            db_session, user=_user(db_session),
            input_data=ReadFileInput(repository_id=uuid.UUID(onboarded_repo["id"]), file_path="../../../etc/passwd"),
        )


def test_read_file_rejects_oversized_file(db_session, onboarded_repo, monkeypatch):
    from app.core import config as config_module
    from app.tools.exceptions import FileTooLargeError
    from app.tools.filesystem import read_file
    from app.tools.models import ReadFileInput

    settings = config_module.get_settings()
    monkeypatch.setattr(settings, "TOOL_MAX_FILE_SIZE_BYTES", 5)

    with pytest.raises(FileTooLargeError):
        read_file(
            db_session, user=_user(db_session),
            input_data=ReadFileInput(repository_id=uuid.UUID(onboarded_repo["id"]), file_path="src/investigation_service.py"),
        )


def test_read_file_rejects_directory_target(db_session, onboarded_repo):
    from app.tools.exceptions import PathSecurityError
    from app.tools.filesystem import read_file
    from app.tools.models import ReadFileInput

    with pytest.raises(PathSecurityError):
        read_file(
            db_session, user=_user(db_session),
            input_data=ReadFileInput(repository_id=uuid.UUID(onboarded_repo["id"]), file_path="src"),
        )


# ============================================================
# search_code
# ============================================================


def test_search_code_finds_matches(db_session, onboarded_repo):
    from app.tools.models import SearchCodeInput
    from app.tools.search import search_code

    output = search_code(
        db_session, user=_user(db_session),
        input_data=SearchCodeInput(repository_id=uuid.UUID(onboarded_repo["id"]), query="delete_investigation"),
    )
    assert len(output.matches) == 1
    assert output.matches[0].file == "src/investigation_service.py"


def test_search_code_respects_ignored_directories(db_session, onboarded_repo):
    from app.tools.models import SearchCodeInput
    from app.tools.search import search_code

    output = search_code(
        db_session, user=_user(db_session),
        input_data=SearchCodeInput(repository_id=uuid.UUID(onboarded_repo["id"]), query="ignored"),
    )
    assert output.matches == []  # node_modules/ignored.js must never be scanned


def test_search_code_respects_max_results(db_session, onboarded_repo):
    from app.tools.models import SearchCodeInput
    from app.tools.search import search_code

    output = search_code(
        db_session, user=_user(db_session),
        input_data=SearchCodeInput(repository_id=uuid.UUID(onboarded_repo["id"]), query="e", max_results=1),
    )
    assert len(output.matches) <= 1


def test_search_code_respects_file_pattern(db_session, onboarded_repo):
    from app.tools.models import SearchCodeInput
    from app.tools.search import search_code

    output = search_code(
        db_session, user=_user(db_session),
        input_data=SearchCodeInput(
            repository_id=uuid.UUID(onboarded_repo["id"]), query="class", file_pattern="*.java"
        ),
    )
    assert output.matches == []  # only .py files exist


def test_search_code_rejects_blank_query():
    from pydantic import ValidationError as PydanticValidationError

    from app.tools.models import SearchCodeInput

    with pytest.raises(PydanticValidationError):
        SearchCodeInput(repository_id=uuid.uuid4(), query="   ")


# ============================================================
# repository_structure
# ============================================================


def test_repository_structure_returns_files_and_dirs(db_session, onboarded_repo):
    from app.tools.models import RepositoryStructureInput
    from app.tools.tree import repository_structure

    output = repository_structure(
        db_session, user=_user(db_session),
        input_data=RepositoryStructureInput(repository_id=uuid.UUID(onboarded_repo["id"])),
    )
    paths = {e.path: e.type for e in output.entries}
    assert paths.get("src") == "dir"
    assert paths.get("src/investigation_service.py") == "file"


def test_repository_structure_excludes_ignored_directories(db_session, onboarded_repo):
    from app.tools.models import RepositoryStructureInput
    from app.tools.tree import repository_structure

    output = repository_structure(
        db_session, user=_user(db_session),
        input_data=RepositoryStructureInput(repository_id=uuid.UUID(onboarded_repo["id"])),
    )
    paths = {e.path for e in output.entries}
    assert not any("node_modules" in p for p in paths)


def test_repository_structure_respects_max_entries(db_session, onboarded_repo):
    from app.tools.models import RepositoryStructureInput
    from app.tools.tree import repository_structure

    output = repository_structure(
        db_session, user=_user(db_session),
        input_data=RepositoryStructureInput(repository_id=uuid.UUID(onboarded_repo["id"]), max_entries=1),
    )
    assert len(output.entries) <= 1
    assert output.truncated is True


def test_repository_structure_is_deterministically_ordered(db_session, onboarded_repo):
    from app.tools.models import RepositoryStructureInput
    from app.tools.tree import repository_structure

    output1 = repository_structure(
        db_session, user=_user(db_session),
        input_data=RepositoryStructureInput(repository_id=uuid.UUID(onboarded_repo["id"])),
    )
    output2 = repository_structure(
        db_session, user=_user(db_session),
        input_data=RepositoryStructureInput(repository_id=uuid.UUID(onboarded_repo["id"])),
    )
    assert [e.path for e in output1.entries] == [e.path for e in output2.entries]
    assert [e.path for e in output1.entries] == sorted(e.path for e in output1.entries)


# ============================================================
# modify_file
# ============================================================


def test_modify_file_applies_unambiguous_replacement(db_session, onboarded_repo):
    from app.tools.filesystem import modify_file, read_file
    from app.tools.models import ModifyFileInput, ReadFileInput

    output = modify_file(
        db_session, user=_user(db_session),
        input_data=ModifyFileInput(
            repository_id=uuid.UUID(onboarded_repo["id"]), file_path="src/investigation_service.py",
            old_content="class InvestigationService:", new_content="class InvestigationServiceV2:",
        ),
    )
    assert output.success is True

    read_output = read_file(
        db_session, user=_user(db_session),
        input_data=ReadFileInput(repository_id=uuid.UUID(onboarded_repo["id"]), file_path="src/investigation_service.py"),
    )
    assert "InvestigationServiceV2" in read_output.content


def test_modify_file_rejects_missing_old_content(db_session, onboarded_repo):
    from app.tools.exceptions import ModificationNotFoundError
    from app.tools.filesystem import modify_file
    from app.tools.models import ModifyFileInput

    with pytest.raises(ModificationNotFoundError):
        modify_file(
            db_session, user=_user(db_session),
            input_data=ModifyFileInput(
                repository_id=uuid.UUID(onboarded_repo["id"]), file_path="src/investigation_service.py",
                old_content="this text does not exist anywhere", new_content="x",
            ),
        )


def test_modify_file_rejects_ambiguous_old_content(db_session, onboarded_repo):
    from app.tools.exceptions import AmbiguousModificationError
    from app.tools.filesystem import modify_file
    from app.tools.models import ModifyFileInput

    with pytest.raises(AmbiguousModificationError):
        modify_file(
            db_session, user=_user(db_session),
            input_data=ModifyFileInput(
                repository_id=uuid.UUID(onboarded_repo["id"]), file_path="src/investigation_service.py",
                old_content="id", new_content="x",  # occurs multiple times
            ),
        )


def test_modify_file_rejects_nonexistent_target(db_session, onboarded_repo):
    from app.tools.exceptions import ModificationNotFoundError
    from app.tools.filesystem import modify_file
    from app.tools.models import ModifyFileInput

    with pytest.raises(ModificationNotFoundError):
        modify_file(
            db_session, user=_user(db_session),
            input_data=ModifyFileInput(
                repository_id=uuid.UUID(onboarded_repo["id"]), file_path="does/not/exist.py",
                old_content="x", new_content="y",
            ),
        )


def test_modify_file_rejects_directory_target(db_session, onboarded_repo):
    from app.tools.exceptions import PathSecurityError
    from app.tools.filesystem import modify_file
    from app.tools.models import ModifyFileInput

    with pytest.raises(PathSecurityError):
        modify_file(
            db_session, user=_user(db_session),
            input_data=ModifyFileInput(
                repository_id=uuid.UUID(onboarded_repo["id"]), file_path="src",
                old_content="x", new_content="y",
            ),
        )


def test_modify_file_rejects_path_traversal(db_session, onboarded_repo):
    from app.tools.exceptions import PathSecurityError
    from app.tools.filesystem import modify_file
    from app.tools.models import ModifyFileInput

    with pytest.raises(PathSecurityError):
        modify_file(
            db_session, user=_user(db_session),
            input_data=ModifyFileInput(
                repository_id=uuid.UUID(onboarded_repo["id"]), file_path="../../../etc/passwd",
                old_content="x", new_content="y",
            ),
        )


def test_modify_file_leaves_file_intact_after_rejected_ambiguous_modification(db_session, onboarded_repo):
    """A refused (ambiguous) modification must never partially write."""
    from app.tools.exceptions import AmbiguousModificationError
    from app.tools.filesystem import modify_file, read_file
    from app.tools.models import ModifyFileInput, ReadFileInput

    before = read_file(
        db_session, user=_user(db_session),
        input_data=ReadFileInput(repository_id=uuid.UUID(onboarded_repo["id"]), file_path="src/investigation_service.py"),
    )

    with pytest.raises(AmbiguousModificationError):
        modify_file(
            db_session, user=_user(db_session),
            input_data=ModifyFileInput(
                repository_id=uuid.UUID(onboarded_repo["id"]), file_path="src/investigation_service.py",
                old_content="id", new_content="x",
            ),
        )

    after = read_file(
        db_session, user=_user(db_session),
        input_data=ReadFileInput(repository_id=uuid.UUID(onboarded_repo["id"]), file_path="src/investigation_service.py"),
    )
    assert before.content == after.content


# ============================================================
# git_diff
# ============================================================


def test_git_diff_reports_no_changes_initially(db_session, onboarded_repo):
    from app.tools.git import git_diff
    from app.tools.models import GitDiffInput

    output = git_diff(
        db_session, user=_user(db_session), input_data=GitDiffInput(repository_id=uuid.UUID(onboarded_repo["id"]))
    )
    assert output.files_changed == []
    assert output.summary == "No local changes"


def test_git_diff_reflects_a_modification(db_session, onboarded_repo):
    from app.tools.filesystem import modify_file
    from app.tools.git import git_diff
    from app.tools.models import GitDiffInput, ModifyFileInput

    modify_file(
        db_session, user=_user(db_session),
        input_data=ModifyFileInput(
            repository_id=uuid.UUID(onboarded_repo["id"]), file_path="src/investigation_service.py",
            old_content="class InvestigationService:", new_content="class Renamed:",
        ),
    )

    output = git_diff(
        db_session, user=_user(db_session), input_data=GitDiffInput(repository_id=uuid.UUID(onboarded_repo["id"]))
    )
    assert "src/investigation_service.py" in output.files_changed
    assert output.additions >= 1
    assert output.deletions >= 1
    assert "Renamed" in output.diff_text


# ============================================================
# additional limit coverage
# ============================================================


def test_repository_structure_respects_max_depth(db_session, onboarded_repo):
    from app.tools.models import RepositoryStructureInput
    from app.tools.tree import repository_structure

    output = repository_structure(
        db_session, user=_user(db_session),
        input_data=RepositoryStructureInput(repository_id=uuid.UUID(onboarded_repo["id"]), max_depth=1),
    )
    # depth 1 means only top-level entries — "src" itself, not
    # "src/investigation_service.py" (depth 2).
    paths = {e.path for e in output.entries}
    assert "src" in paths
    assert "src/investigation_service.py" not in paths


def test_search_code_skips_oversized_files_without_failing(db_session, onboarded_repo, monkeypatch):
    """An oversized file must be skipped (not scanned), not cause the
    whole search to fail."""
    from app.core import config as config_module
    from app.tools.models import SearchCodeInput
    from app.tools.search import search_code

    settings = config_module.get_settings()
    monkeypatch.setattr(settings, "TOOL_MAX_FILE_SIZE_BYTES", 5)

    output = search_code(
        db_session, user=_user(db_session),
        input_data=SearchCodeInput(repository_id=uuid.UUID(onboarded_repo["id"]), query="class"),
    )
    assert output.matches == []  # file is now "too large" to scan, but no exception raised
