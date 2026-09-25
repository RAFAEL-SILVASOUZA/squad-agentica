"""Tests for the RAG chunker (D9 9.2, spec 7.2).

Cobre: chunking por tamanho com sobreposição, texto curto (1 chunk), texto
vazio, e o contrato de chunking usado pela ingestão.
"""

from __future__ import annotations

from app.knowledge.chunker import chunk_text


class TestChunkText:
    def test_short_text_single_chunk(self):
        """Texto menor que chunk_size vira um único chunk."""
        chunks = chunk_text("hello world", chunk_size=512, chunk_overlap=64)
        assert chunks == ["hello world"]

    def test_empty_text_no_chunks(self):
        """Texto vazio (ou só whitespace) não gera chunks."""
        assert chunk_text("", chunk_size=512, chunk_overlap=64) == []
        assert chunk_text("   \n  ", chunk_size=512, chunk_overlap=64) == []

    def test_long_text_multiple_chunks(self):
        """Texto longo é dividido em múltiplos chunks."""
        text = " ".join(f"word{i}" for i in range(2000))
        chunks = chunk_text(text, chunk_size=512, chunk_overlap=64)
        assert len(chunks) > 1

    def test_chunks_respect_max_size(self):
        """Nenhum chunk excede chunk_size tokens."""
        text = " ".join(f"word{i}" for i in range(2000))
        chunks = chunk_text(text, chunk_size=512, chunk_overlap=64)
        for chunk in chunks:
            assert len(chunk.split()) <= 512

    def test_overlap_between_consecutive_chunks(self):
        """Chunks consecutivos compartilham tokens de sobreposição."""
        # Texto com tokens únicos e numerados para detectar sobreposição.
        text = " ".join(f"t{i}" for i in range(1000))
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)
        assert len(chunks) >= 2
        # O fim do chunk N deve aparecer no início do chunk N+1 (sobreposição).
        tail = chunks[0].split()[-20:]
        head = chunks[1].split()[:20]
        assert tail == head

    def test_no_infinite_loop_with_small_overlap(self):
        """Overlap próximo de chunk_size não trava (progresso garantido)."""
        text = " ".join(f"w{i}" for i in range(500))
        chunks = chunk_text(text, chunk_size=50, chunk_overlap=40)
        assert len(chunks) >= 1
        # Deve terminar e cobrir o texto.
        assert " ".join(chunks[0].split())  # chunks não vazios

    def test_default_parameters(self):
        """Defaults da spec 7.2: chunk_size=512, chunk_overlap=64."""
        text = " ".join(f"x{i}" for i in range(1200))
        chunks = chunk_text(text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.split()) <= 512
