import uuid

import pytest

from app.retrieval.milvus_client import MilvusVectorStore, VectorRecord

DIM = 8


def _vec(seed: int) -> list[float]:
    import random

    rnd = random.Random(seed)
    return [rnd.random() for _ in range(DIM)]


@pytest.fixture()
def vector_store(tmp_path):
    """An isolated Milvus Lite instance per test — a real Milvus, not a
    mock (see app/retrieval/milvus_client.py's module docstring), just
    pointed at a throwaway file so tests never share state."""
    from app.core import config as config_module

    settings = config_module.get_settings()
    original_mode = settings.MILVUS_MODE
    original_path = settings.MILVUS_LITE_PATH
    settings.MILVUS_MODE = "lite"
    settings.MILVUS_LITE_PATH = str(tmp_path / "milvus_test.db")

    collection_name = f"test_chunks_{uuid.uuid4().hex[:8]}"
    store = MilvusVectorStore(dimension=DIM, collection_name=collection_name)

    yield store

    settings.MILVUS_MODE = original_mode
    settings.MILVUS_LITE_PATH = original_path


def test_collection_is_created(vector_store):
    assert vector_store.collection_name.startswith("test_chunks_")


def test_upsert_and_search(vector_store):
    records = [
        VectorRecord(
            id="v1", vector=_vec(1), repository_id="repoA", code_chunk_id="c1",
            file_path="a.py", language="python", chunk_type="FUNCTION",
            symbol_name="delete_investigation", content_hash="h1",
        ),
    ]
    vector_store.upsert(records)

    hits = vector_store.search(repository_id="repoA", query_vector=_vec(1), top_k=5)
    assert len(hits) == 1
    assert hits[0].code_chunk_id == "c1"
    assert hits[0].symbol_name == "delete_investigation"


def test_search_respects_top_k(vector_store):
    records = [
        VectorRecord(
            id=f"v{i}", vector=_vec(i), repository_id="repoA", code_chunk_id=f"c{i}",
            file_path=f"{i}.py", language="python", chunk_type="FUNCTION",
            symbol_name=f"fn{i}", content_hash=f"h{i}",
        )
        for i in range(10)
    ]
    vector_store.upsert(records)

    hits = vector_store.search(repository_id="repoA", query_vector=_vec(0), top_k=3)
    assert len(hits) == 3


def test_repository_isolation_in_search(vector_store):
    """Repository A vectors must not be returned when searching Repository B."""
    records = [
        VectorRecord(
            id="a1", vector=_vec(1), repository_id="repoA", code_chunk_id="a1",
            file_path="a.py", language="python", chunk_type="FUNCTION",
            symbol_name="delete_investigation", content_hash="ha",
        ),
        VectorRecord(
            id="b1", vector=_vec(1), repository_id="repoB", code_chunk_id="b1",
            file_path="b.py", language="python", chunk_type="FUNCTION",
            symbol_name="delete_investigation", content_hash="hb",
        ),
    ]
    vector_store.upsert(records)

    hits_a = vector_store.search(repository_id="repoA", query_vector=_vec(1), top_k=10)
    assert {h.repository_id for h in hits_a} == {"repoA"}

    hits_b = vector_store.search(repository_id="repoB", query_vector=_vec(1), top_k=10)
    assert {h.repository_id for h in hits_b} == {"repoB"}


def test_delete_by_repository_only_removes_that_repository(vector_store):
    records = [
        VectorRecord(
            id="a1", vector=_vec(1), repository_id="repoA", code_chunk_id="a1",
            file_path="a.py", language="python", chunk_type="FUNCTION",
            symbol_name="fn", content_hash="ha",
        ),
        VectorRecord(
            id="b1", vector=_vec(1), repository_id="repoB", code_chunk_id="b1",
            file_path="b.py", language="python", chunk_type="FUNCTION",
            symbol_name="fn", content_hash="hb",
        ),
    ]
    vector_store.upsert(records)

    vector_store.delete_by_repository("repoA")

    assert vector_store.count_for_repository("repoA") == 0
    assert vector_store.count_for_repository("repoB") == 1


def test_count_for_repository(vector_store):
    records = [
        VectorRecord(
            id=f"v{i}", vector=_vec(i), repository_id="repoA", code_chunk_id=f"c{i}",
            file_path=f"{i}.py", language="python", chunk_type="FUNCTION",
            symbol_name=f"fn{i}", content_hash=f"h{i}",
        )
        for i in range(3)
    ]
    vector_store.upsert(records)
    assert vector_store.count_for_repository("repoA") == 3
    assert vector_store.count_for_repository("repoB") == 0
