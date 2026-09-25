"""Chunking de texto para RAG (D9 9.2, spec 7.2).

Dono: be-knowledge (FASE 4). Divide o texto de um documento em chunks de
``chunk_size`` tokens com ``chunk_overlap`` tokens de sobreposição entre
chunks consecutivos.

Na V1 o "token" é aproximado por palavra (split por whitespace): simples,
determinístico e suficiente para o contrato. Os parâmetros vêm do
``KnowledgeBase`` (spec 7.2): defaults ``chunk_size=512``, ``chunk_overlap=64``.
"""

from __future__ import annotations


def chunk_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[str]:
    """Divide ``text`` em chunks de até ``chunk_size`` tokens com sobreposição.

    Args:
        text: Texto bruto do documento.
        chunk_size: Máximo de tokens por chunk (default 512).
        chunk_overlap: Tokens de sobreposição entre chunks consecutivos
            (default 64). Deve ser menor que ``chunk_size``.

    Returns:
        Lista de chunks (strings). Texto vazio -> lista vazia. Texto curto
        (<= chunk_size) -> um único chunk.

    Garantias:
        - Nenhum chunk excede ``chunk_size`` tokens.
        - Chunks consecutivos compartilham ``chunk_overlap`` tokens.
        - O avanço por iteração é ``chunk_size - chunk_overlap`` (>= 1),
          então nunca há loop infinito.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be in [0, chunk_size)")

    tokens = text.split()
    if not tokens:
        return []

    # Se cabe num chunk, devolve o texto original (preserva formatação).
    if len(tokens) <= chunk_size:
        return [text.strip()]

    step = chunk_size - chunk_overlap
    chunks: list[str] = []
    start = 0
    n = len(tokens)
    while start < n:
        end = min(start + chunk_size, n)
        chunk = " ".join(tokens[start:end])
        chunks.append(chunk)
        if end == n:
            break
        start += step
    return chunks
