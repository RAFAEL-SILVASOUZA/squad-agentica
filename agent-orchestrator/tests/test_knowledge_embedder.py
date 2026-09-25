"""Tests for the RAG embedder wrapper (D9 9.3, spec 7.2).

Cobre: contrato do wrapper (embed/embed_batch/dim), normalização,
determinismo do mock e injeção de embedder mockável.
"""

from __future__ import annotations

import math

from app.core.embeddings import MockEmbedder
from app.knowledge.embedder import get_embedder


class TestGetEmbedder:
    def test_returns_embedder_with_dim(self):
        embedder = get_embedder()
        # Contrato estrutural (Embedder é um Protocol): expõe dim/embed/embed_batch.
        assert hasattr(embedder, "dim")
        assert hasattr(embedder, "embed")
        assert hasattr(embedder, "embed_batch")
        assert embedder.dim == 1536  # V1: text-embedding-3-small

    def test_embed_returns_dim_length_vector(self):
        embedder = get_embedder()
        vec = embedder.embed("hello")
        assert len(vec) == embedder.dim

    def test_embed_is_normalized(self):
        embedder = get_embedder()
        vec = embedder.embed("hello world")
        norm = math.sqrt(sum(v * v for v in vec))
        assert abs(norm - 1.0) < 1e-6

    def test_embed_deterministic(self):
        embedder = get_embedder()
        assert embedder.embed("same text") == embedder.embed("same text")

    def test_embed_batch_matches_embed(self):
        embedder = get_embedder()
        texts = ["a", "b", "c"]
        batch = embedder.embed_batch(texts)
        assert len(batch) == 3
        for t, v in zip(texts, batch, strict=False):
            assert v == embedder.embed(t)


class TestInjectableEmbedder:
    """O RAG deve aceitar um embedder injetado (mockável nos testes)."""

    def test_custom_embedder_used(self):
        custom = MockEmbedder(dim=8)
        embedder = get_embedder(embedder=custom)
        # O wrapper delega ao embedder injetado (dim e vetor vêm dele).
        assert embedder.dim == 8
        wrapped = embedder.embed("x")
        base = custom.embed("x")
        assert len(wrapped) == 8
        for a, b in zip(wrapped, base, strict=False):
            assert abs(a - b) < 1e-9
