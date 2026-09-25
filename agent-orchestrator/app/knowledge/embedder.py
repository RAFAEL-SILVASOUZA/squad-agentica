"""Embedder wrapper para RAG (D9 9.3, spec 7.2).

Dono: be-knowledge (FASE 4). Não recria o client de embeddings: consome a
interface ``app.core.embeddings.Embedder`` (dono: infra-docker) e a fábrica
``get_embedder()``. O wrapper existe para:

- Dar um ponto único de injeção para o RAG (mockável nos testes).
- Garantir que o vetor é normalizado antes do insert (spec 7.2: cosine
  distance ``<=>`` exige vetores normalizados).

V1: ``text-embedding-3-small`` (OpenAI, 1536 dims). Fallback local
(``all-MiniLM-L6-v2``, 384 dims) é V2.
"""

from __future__ import annotations

import math

from app.core.embeddings import Embedder
from app.core.embeddings import get_embedder as _core_get_embedder


def _normalize(vec: list[float]) -> list[float]:
    """Normaliza o vetor para norma 2 (cosine distance)."""
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


class RagEmbedder:
    """Wrapper do embedder do core: garante normalização e injetabilidade."""

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder

    @property
    def dim(self) -> int:
        return self._embedder.dim

    def embed(self, text: str) -> list[float]:
        return _normalize(self._embedder.embed(text))

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [_normalize(v) for v in self._embedder.embed_batch(texts)]


def get_embedder(embedder: Embedder | None = None) -> RagEmbedder:
    """Fábrica do embedder do RAG.

    Args:
        embedder: Embedder injetado (mock nos testes). Se ``None``, usa a
            fábrica do core (``app.core.embeddings.get_embedder``).

    Returns:
        ``RagEmbedder`` normalizado.
    """
    return RagEmbedder(embedder or _core_get_embedder())
