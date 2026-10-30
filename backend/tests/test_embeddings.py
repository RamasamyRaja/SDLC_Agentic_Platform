from app.retrieval.embeddings import get_embedding_provider, split_identifier_words


def test_split_identifier_words_handles_snake_case():
    assert split_identifier_words("delete_investigation") == "delete investigation"


def test_split_identifier_words_handles_camel_case():
    assert split_identifier_words("deleteInvestigation") == "delete investigation"


def test_split_identifier_words_handles_kebab_case():
    assert split_identifier_words("delete-investigation") == "delete investigation"


def test_embedding_provider_initializes():
    provider = get_embedding_provider()
    assert provider.name == "spacy"
    assert provider.dimension > 0


def test_embedding_provider_reports_documented_dimension():
    from app.core.config import get_settings

    provider = get_embedding_provider()
    settings = get_settings()
    assert provider.dimension == settings.EMBEDDING_DIMENSION


def test_embedding_produces_correct_shape_for_batch():
    provider = get_embedding_provider()
    vectors = provider.embed(["delete investigation", "create user", "authentication logic"])
    assert len(vectors) == 3
    assert all(len(v) == provider.dimension for v in vectors)


def test_embedding_is_deterministic_for_same_input():
    provider = get_embedding_provider()
    v1 = provider.embed_one("delete investigation")
    v2 = provider.embed_one("delete investigation")
    assert v1 == v2


def test_embedding_handles_empty_string_without_raising():
    provider = get_embedding_provider()
    vector = provider.embed_one("")
    assert len(vector) == provider.dimension


def test_embedding_similarity_reflects_semantic_relevance():
    """A reasonable, non-exact-ranking relevance check — spaCy static
    vectors won't be perfectly precise, but a query about deleting
    investigations should score closer to a delete-investigation chunk
    than to an unrelated create-user chunk."""
    import math

    provider = get_embedding_provider()

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        return dot / (norm_a * norm_b + 1e-9)

    query_vec = provider.embed_one("delete investigation")
    relevant_vec = provider.embed_one("deleteInvestigation removes the investigation record")
    irrelevant_vec = provider.embed_one("createUser saves a new user account")

    assert cosine(query_vec, relevant_vec) > cosine(query_vec, irrelevant_vec)
