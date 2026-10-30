"""
Semantic repository retrieval: chunking, embeddings, Milvus vector storage,
and search.

Pipeline: RepositoryDocument (from Milestone 3) -> chunking.py (reuses the
Milestone 3 Tree-sitter analysis for structural chunk boundaries) ->
embeddings.py (EmbeddingProvider abstraction) -> milvus_client.py (vector
storage/search) -> retrieval_service.py (the single entry point:
index_repository() / search()).

This is a SEPARATE, complementary source of repository understanding from
Milestone 3's deterministic structural analysis — it does not replace it.
See README "Milestone 4" for the embedding model choice and its rationale,
and for what "real Milvus" means in this environment (embedded Milvus Lite,
not a mock — see milvus_client.py's docstring).
"""
