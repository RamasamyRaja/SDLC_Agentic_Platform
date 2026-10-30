"""
EmbeddingProvider abstraction.

Converts text/code into fixed-dimension vectors. Nothing outside this
module should know which specific embedding model or library is in use —
chunking.py and retrieval_service.py depend only on this interface, so the
concrete provider can be swapped via `EMBEDDING_PROVIDER` in config without
touching them.

Embedding model ≠ Mistral. This produces vectors for similarity search;
Mistral (not implemented until Milestone 5) will later do actual reasoning
over the text these vectors point back to.

See the module docstring on `SpacyEmbeddingProvider` below for which model
is used and why.
"""
import re
from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import get_settings

# snake_case / camelCase / kebab-case splitter, applied before embedding so
# an identifier like "deleteInvestigation" or "delete_investigation"
# contributes the words "delete" and "investigation" to the embedding
# rather than being treated as one opaque token.
_CAMEL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
_SEPARATOR = re.compile(r"[_\-]+")


def split_identifier_words(text: str) -> str:
    text = _SEPARATOR.sub(" ", text)
    text = _CAMEL_BOUNDARY.sub(r"\1 \2", text)
    return text.lower()


class EmbeddingProvider(ABC):
    """Abstract embedding provider. All providers must report a fixed,
    known dimension and embed both single strings and batches."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def dimension(self) -> int: ...

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns one vector per input text, same
        order. Empty/whitespace-only strings still return a valid
        (zero) vector rather than raising, so a batch never partially fails."""
        ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class SpacyEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider backed by spaCy's `en_core_web_md` pipeline, which
    ships real pretrained (GloVe-derived) 300-dimensional static word
    vectors — a document's vector is the average of its token vectors.

    WHY THIS MODEL:
      - No OpenAI, runs fully locally/offline once installed.
      - Documented, fixed dimension (300).
      - Small and practical for local development (~40 MB model).
      - Crucially: installable in this sandboxed build environment, whose
        network allowlist does not include huggingface.co — which rules out
        every HuggingFace-hosted transformer/ONNX embedding model (the
        usual first choice, e.g. sentence-transformers or fastembed with a
        BAAI/bge-* model). spaCy's models are published as plain pip wheels
        on GitHub Releases, which the allowlist does permit
        (github.com / release-assets.githubusercontent.com), so this is the
        strongest *real, pretrained* semantic embedding option that
        actually installs here — not a fallback hash or random vector.

    HONEST LIMITATION: static word-vector averaging is meaningfully weaker
    than a modern transformer sentence/code embedding — it has no notion of
    word order or context, and code identifiers/punctuation are only
    partially meaningful to a model trained on general English text (which
    is why `split_identifier_words` is applied before embedding: it turns
    `deleteInvestigation` into words the model actually has vectors for).
    The `EmbeddingProvider` abstraction exists specifically so a stronger
    model (e.g. a HuggingFace-hub code-embedding model, once network access
    to it is available) can replace this one via `EMBEDDING_PROVIDER` /
    `EMBEDDING_MODEL_NAME` config, without changing chunking or retrieval
    code.
    """

    def __init__(self, model_name: str = "en_core_web_md") -> None:
        import spacy

        self._model_name = model_name
        self._nlp = spacy.load(model_name, disable=["parser", "ner", "tagger", "lemmatizer"])
        self._dimension = self._nlp.vocab.vectors_length

    @property
    def name(self) -> str:
        return "spacy"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        processed = [split_identifier_words(t) if t.strip() else "" for t in texts]
        vectors: list[list[float]] = []
        for doc in self._nlp.pipe(processed):
            if doc.has_vector:
                vectors.append([float(x) for x in doc.vector])
            else:
                vectors.append([0.0] * self._dimension)
        return vectors


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    """Returns the configured embedding provider (cached — loading the
    spaCy model is relatively expensive, so this should happen once)."""
    settings = get_settings()
    if settings.EMBEDDING_PROVIDER == "spacy":
        return SpacyEmbeddingProvider(model_name=settings.EMBEDDING_MODEL_NAME)
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {settings.EMBEDDING_PROVIDER}")
