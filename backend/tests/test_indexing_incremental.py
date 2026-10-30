"""Incremental indexing, readiness endpoint and stale-index detection (real Postgres + Milvus Lite, local git origin)."""
import subprocess
from pathlib import Path

from tests.test_retrieval_integration import indexed_repository  # noqa: F401  (fixture)


def _origin(indexed_repository):
    from app.core.config import get_settings  # noqa: F401
    url = indexed_repository["url"]
    return Path(url.replace("file://", ""))


def test_reindex_unchanged_is_a_noop(client, indexed_repository):
    rid = indexed_repository["id"]
    r = client.post(f"/api/repositories/{rid}/index")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["chunks_created"] == 0 and body["embeddings_generated"] == 0
    assert body["chunks_unchanged"] == 4 and body["total_chunks"] == 4


def test_readiness_reports_real_state(client, indexed_repository):
    rid = indexed_repository["id"]
    s = client.get(f"/api/repositories/{rid}/status")
    assert s.status_code == 200, s.text
    b = s.json()
    assert b["ready_for_retrieval"] is True and b["stale"] is False and b["reasons"] == []
    assert b["indexing"]["status"] == "INDEXED" and b["indexing"]["indexed_chunk_count"] == 4
    assert b["indexing"]["chunks_done"] == b["indexing"]["chunks_total"] == 4   # first run embedded all 4 chunks
    assert b["documents"]["total"] == sum(b["documents"]["by_status"].values())
    assert b["indexing"]["indexed_commit_sha"] == b["commit_sha"]


def test_changed_file_is_reindexed_and_stale_detected(client, indexed_repository):
    rid = indexed_repository["id"]
    origin = _origin(indexed_repository)
    f = origin / "src" / "investigation_service.py"
    f.write_text(f.read_text() + "\n\ndef brand_new_function():\n    return 42\n")
    subprocess.run(["git", "add", "."], cwd=origin, check=True)
    subprocess.run(["git", "commit", "-m", "change"], cwd=origin, check=True, capture_output=True)

    assert client.post(f"/api/repositories/{rid}/onboard", json={}).status_code == 201
    stale = client.get(f"/api/repositories/{rid}/status").json()
    assert stale["stale"] is True and stale["ready_for_retrieval"] is False and stale["documents"]["pending_index"] >= 1
    hit = client.post(f"/api/repositories/{rid}/search", json={"query": "brand new function", "top_k": 3}).json()
    assert hit["warnings"], "search on an out-of-date index must say so"

    r = client.post(f"/api/repositories/{rid}/index").json()
    assert r["chunks_created"] >= 1 and r["chunks_unchanged"] >= 1   # only the changed file was re-embedded
    ok = client.get(f"/api/repositories/{rid}/status").json()
    assert ok["ready_for_retrieval"] is True and ok["stale"] is False
    found = client.post(f"/api/repositories/{rid}/search", json={"query": "brand_new_function", "top_k": 3}).json()
    assert found["warnings"] == [] and any("brand_new_function" in x["content"] for x in found["results"])


def test_concurrent_indexing_is_refused(client, db_session, indexed_repository):
    from app.models.repository import IndexingStatus, Repository
    rid = indexed_repository["id"]
    repo = db_session.get(Repository, rid)
    repo.indexing_status = IndexingStatus.INDEXING
    db_session.commit()
    assert client.post(f"/api/repositories/{rid}/index").status_code == 409
    st = client.get(f"/api/repositories/{rid}/status").json()
    assert st["ready_for_retrieval"] is False and any("in progress" in x for x in st["reasons"])
    repo = db_session.get(Repository, rid)
    repo.indexing_status = IndexingStatus.INDEXED
    db_session.commit()
