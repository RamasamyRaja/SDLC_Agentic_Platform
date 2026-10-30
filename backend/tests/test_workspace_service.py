import uuid

from app.services.workspace_service import get_workspace_path


def test_get_workspace_path_is_under_workspace_root():
    repository_id = uuid.uuid4()
    path = get_workspace_path(repository_id)
    assert str(repository_id) in str(path)
    assert path.is_absolute()


def test_get_workspace_path_is_deterministic_for_same_id():
    repository_id = uuid.uuid4()
    assert get_workspace_path(repository_id) == get_workspace_path(repository_id)


def test_get_workspace_path_differs_for_different_ids():
    assert get_workspace_path(uuid.uuid4()) != get_workspace_path(uuid.uuid4())
