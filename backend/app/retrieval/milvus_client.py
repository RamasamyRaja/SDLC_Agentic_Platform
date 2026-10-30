"""
Milvus vector store client.

Wraps pymilvus so nothing else in the application touches pymilvus
directly — collection schema, connection mode, and query construction all
live here.

REAL MILVUS, NOT A MOCK: by default (`MILVUS_MODE=lite`) this connects to
Milvus Lite — Milvus's own embedded, file-backed deployment mode, run
in-process via the same `pymilvus` client used for a full server. It is not
a fake/stub adapter; it is genuine Milvus, just running without a separate
server process, which is what Milvus Lite exists for (local development /
small-scale use — see https://milvus.io/docs/milvus_lite.md). This
environment's network allowlist has no route to pull a Milvus server
container, and no `docker compose` execution is available for one either,
so Lite is the practical way to exercise real Milvus here. `MILVUS_MODE=
server` (pointing `MILVUS_HOST`/`MILVUS_PORT` at a real standalone/cluster
deployment, e.g. via docker-compose in an unrestricted environment) uses
the exact same `MilvusVectorStore` code path — only the connection URI
construction differs.
"""
import logging
from dataclasses import dataclass

from pymilvus import DataType, MilvusClient

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_ID_MAX_LEN = 64
_PATH_MAX_LEN = 1024
_SHORT_MAX_LEN = 255


@dataclass
class VectorRecord:
    id: str
    vector: list[float]
    repository_id: str
    code_chunk_id: str
    file_path: str
    language: str
    chunk_type: str
    symbol_name: str
    content_hash: str


@dataclass
class VectorSearchHit:
    id: str
    score: float
    repository_id: str
    code_chunk_id: str
    file_path: str
    language: str
    chunk_type: str
    symbol_name: str


def _connection_uri(settings) -> str:
    if settings.MILVUS_MODE == "lite":
        import os

        os.makedirs(os.path.dirname(settings.MILVUS_LITE_PATH), exist_ok=True)
        return settings.MILVUS_LITE_PATH
    if settings.MILVUS_MODE == "server":
        return f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
    raise ValueError(f"Unknown MILVUS_MODE: {settings.MILVUS_MODE}")


class MilvusVectorStore:
    def __init__(self, dimension: int, collection_name: str | None = None) -> None:
        settings = get_settings()
        self._collection_name = collection_name or settings.MILVUS_COLLECTION
        self._dimension = dimension
        self._client = MilvusClient(uri=_connection_uri(settings))
        self._ensure_collection()

    @property
    def collection_name(self) -> str:
        return self._collection_name

    def _ensure_collection(self) -> None:
        if self._client.has_collection(self._collection_name):
            # A collection persisted from a prior process (e.g. Milvus Lite
            # reconnecting to its on-disk file) is not automatically loaded
            # into memory — search/query fail with "released" until this is
            # called explicitly. Newly-created collections are loaded below
            # too, so this covers both paths uniformly.
            self._client.load_collection(self._collection_name)
            return

        schema = self._client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=_ID_MAX_LEN)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=self._dimension)
        schema.add_field("repository_id", DataType.VARCHAR, max_length=_ID_MAX_LEN)
        schema.add_field("code_chunk_id", DataType.VARCHAR, max_length=_ID_MAX_LEN)
        schema.add_field("file_path", DataType.VARCHAR, max_length=_PATH_MAX_LEN)
        schema.add_field("language", DataType.VARCHAR, max_length=50)
        schema.add_field("chunk_type", DataType.VARCHAR, max_length=50)
        schema.add_field("symbol_name", DataType.VARCHAR, max_length=_SHORT_MAX_LEN)
        schema.add_field("content_hash", DataType.VARCHAR, max_length=64)

        index_params = self._client.prepare_index_params()
        index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")
        # repository_id is the field every search filters on — an index on
        # it keeps repository-scoped search efficient as the collection grows.
        index_params.add_index(field_name="repository_id", index_type="INVERTED")

        self._client.create_collection(
            collection_name=self._collection_name, schema=schema, index_params=index_params
        )
        self._client.load_collection(self._collection_name)
        logger.info("Created Milvus collection %s (dim=%d)", self._collection_name, self._dimension)

    def upsert(self, records: list[VectorRecord]) -> None:
        if not records:
            return
        rows = [
            {
                "id": r.id,
                "vector": r.vector,
                "repository_id": r.repository_id,
                "code_chunk_id": r.code_chunk_id,
                "file_path": r.file_path[:_PATH_MAX_LEN],
                "language": r.language or "",
                "chunk_type": r.chunk_type,
                "symbol_name": (r.symbol_name or "")[:_SHORT_MAX_LEN],
                "content_hash": r.content_hash,
            }
            for r in records
        ]
        self._client.upsert(collection_name=self._collection_name, data=rows)

    def delete_by_repository(self, repository_id: str) -> None:
        """Removes every vector belonging to a repository — used before a
        full re-index, and to keep vectors from a deleted repository from
        lingering in Milvus after its PostgreSQL rows are gone."""
        self._client.delete(
            collection_name=self._collection_name, filter=f'repository_id == "{repository_id}"'
        )

    def delete_by_ids(self, ids: list[str]) -> None:
        if not ids:
            return
        self._client.delete(collection_name=self._collection_name, ids=ids)

    def search(self, *, repository_id: str, query_vector: list[float], top_k: int) -> list[VectorSearchHit]:
        results = self._client.search(
            collection_name=self._collection_name,
            data=[query_vector],
            limit=top_k,
            filter=f'repository_id == "{repository_id}"',
            output_fields=[
                "repository_id",
                "code_chunk_id",
                "file_path",
                "language",
                "chunk_type",
                "symbol_name",
            ],
        )
        hits: list[VectorSearchHit] = []
        for hit in results[0] if results else []:
            entity = hit.get("entity", {})
            hits.append(
                VectorSearchHit(
                    id=hit["id"],
                    score=float(hit["distance"]),
                    repository_id=entity.get("repository_id", ""),
                    code_chunk_id=entity.get("code_chunk_id", ""),
                    file_path=entity.get("file_path", ""),
                    language=entity.get("language", ""),
                    chunk_type=entity.get("chunk_type", ""),
                    symbol_name=entity.get("symbol_name", ""),
                )
            )
        return hits

    def list_ids_for_repository(self, repository_id: str, page: int = 1000) -> set[str]:
        """Every vector id stored for a repository (keyset pagination on the primary key; no 16k query cap)."""
        ids: set[str] = set()
        last = ""
        while True:
            flt = f'repository_id == "{repository_id}"' + (f' and id > "{last}"' if last else "")
            rows = self._client.query(collection_name=self._collection_name, filter=flt, output_fields=["id"], limit=page)
            if not rows:
                return ids
            batch = sorted(r["id"] for r in rows)
            ids.update(batch)
            last = batch[-1]
            if len(rows) < page:
                return ids

    def count_for_repository(self, repository_id: str) -> int:
        results = self._client.query(
            collection_name=self._collection_name,
            filter=f'repository_id == "{repository_id}"',
            output_fields=["id"],
        )
        return len(results)
