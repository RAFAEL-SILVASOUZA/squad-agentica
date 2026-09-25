"""Embedder interface + factory with mock and OpenAI providers.

Dono: infra-docker. Contrato §4: provider `mock` = vetor determinístico da
dimensão EMBEDDING_DIM, sempre normalizado antes do insert.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

from app.core.config import settings


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
    """Provider real (OpenAI). Só instanciado com chave presente."""

    def __init__(self, api_key: str, dim: int) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(model="text-embedding-3-small", input=text)
        return _normalize(list(response.data[0].embedding))

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model="text-embedding-3-small", input=texts)
        return [_normalize(list(d.embedding)) for d in response.data]


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def get_embedder() -> Embedder:
    """Fábrica: escolhe o provider conforme EMBEDDING_PROVIDER e OPENAI_API_KEY."""
    if settings.embedding_provider == "openai" and settings.openai_api_key:
        return OpenAIEmbedder(settings.openai_api_key, settings.embedding_dim)
    return MockEmbedder(settings.embedding_dim)
