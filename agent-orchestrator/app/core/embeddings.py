"""Embedder interface + factory with mock and OpenAI providers.

Dono: infra-docker. Contrato §4: provider `mock` = vetor determinístico da
dimensão EMBEDDING_DIM, sempre normalizado antes do insert.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

from app.core.config import settings
from app.core.llm import LOCAL_API_KEY_PLACEHOLDER


class Embedder(Protocol):
    """Interface mínima de embeddings consumida pelo RAG (be-knowledge)."""

    @property
    def dim(self) -> int:
        """Dimensão fixa do vetor (V1: 1536)."""
        ...

    def embed(self, text: str) -> list[float]:
        """Embedding de um texto (normalizado)."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embeddings de vários textos."""
        ...


class MockEmbedder:
    """Provider determinístico: hash do texto expandido até a dimensão, normalizado."""

    def __init__(self, dim: int) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        vec: list[float] = []
        seed = 0
        while len(vec) < self._dim:
            digest = hashlib.sha256(f"{seed}:{text}".encode()).digest()
            for byte in digest:
                if len(vec) >= self._dim:
                    break
                vec.append((byte / 255.0) * 2.0 - 1.0)
            seed += 1
        return _normalize(vec)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class OpenAIEmbedder:
    """Provider real: OpenAI ou servidor compatível (``EMBEDDING_BASE_URL``).

    A coluna é ``vector(EMBEDDING_DIM)`` fixa: vetor menor é completado com zeros
    (preserva cosseno e produto interno); maior é erro de configuração.
    """

    def __init__(self, api_key: str, dim: int, base_url: str = "", model: str = "") -> None:
        from openai import OpenAI

        self._client = OpenAI(
            api_key=api_key or LOCAL_API_KEY_PLACEHOLDER, base_url=base_url or None
        )
        self._dim = dim
        self._model = model or "text-embedding-3-small"

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self._model, input=texts)
        return [_normalize(_fit_dim(list(d.embedding), self._dim)) for d in response.data]


def _fit_dim(vec: list[float], dim: int) -> list[float]:
    if len(vec) > dim:
        raise ValueError(
            f"Embedding model returned {len(vec)} dimensions, above EMBEDDING_DIM={dim}"
        )
    return vec + [0.0] * (dim - len(vec))


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def get_embedder() -> Embedder:
    """Fábrica: provider real com EMBEDDING_PROVIDER=openai e chave ou URL configurada."""
    base_url = settings.embedding_base_url or settings.openai_base_url
    if settings.embedding_provider == "openai" and (settings.openai_api_key or base_url):
        return OpenAIEmbedder(
            settings.openai_api_key, settings.embedding_dim, base_url, settings.embedding_model
        )
    return MockEmbedder(settings.embedding_dim)
