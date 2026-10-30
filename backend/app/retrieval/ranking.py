"""
Search post-processing. The vector index returns approximate neighbours only; embeddings of source code are weak at
exact identifiers. This module (pure, no I/O) improves the final list without a second model:

  1. drop hits whose PostgreSQL row is gone (dangling vectors) and exact duplicates (same file + same content hash);
  2. blend the vector score with a lexical score (query terms found in the symbol name, path and content);
  3. cap how many chunks one file may contribute, so one large file cannot crowd out every other file;
  4. return at most `top_k`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]+")
_STOP = {"the", "and", "for", "with", "that", "this", "from", "into", "add", "make", "should", "when", "have", "are", "not"}


def terms(text: str) -> set[str]:
    out: set[str] = set()
    for tok in _TOKEN.findall(text or ""):
        parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", tok).replace("_", " ").lower().split()   # camelCase / snake_case
        out.update(p for p in parts if len(p) > 2 and p not in _STOP)
        low = tok.lower()
        if len(low) > 2 and low not in _STOP:
            out.add(low)
    return out


@dataclass
class Candidate:
    chunk_id: str
    file_path: str
    symbol_name: str | None
    content: str
    content_hash: str
    vector_score: float


def lexical_score(query_terms: set[str], c: Candidate) -> float:
    if not query_terms:
        return 0.0
    sym, path, body = terms(c.symbol_name or ""), terms(c.file_path), terms(c.content[:4000])
    hit = 0.0
    for t in query_terms:
        if t in sym:
            hit += 1.0
        elif t in path:
            hit += 0.6
        elif t in body:
            hit += 0.3
    return min(1.0, hit / len(query_terms))


def rerank(query: str, cands: list[Candidate], *, top_k: int, lexical_weight: float = 0.3, max_per_file: int = 3) -> list[tuple[Candidate, float]]:
    qt = terms(query)
    seen: set[tuple[str, str]] = set()
    scored: list[tuple[Candidate, float]] = []
    for c in cands:
        key = (c.file_path, c.content_hash)
        if key in seen:
            continue
        seen.add(key)
        scored.append((c, (1 - lexical_weight) * c.vector_score + lexical_weight * lexical_score(qt, c)))
    scored.sort(key=lambda x: x[1], reverse=True)
    per_file: dict[str, int] = {}
    out: list[tuple[Candidate, float]] = []
    for c, score in scored:
        if per_file.get(c.file_path, 0) >= max_per_file:
            continue
        per_file[c.file_path] = per_file.get(c.file_path, 0) + 1
        out.append((c, score))
        if len(out) >= top_k:
            break
    return out
