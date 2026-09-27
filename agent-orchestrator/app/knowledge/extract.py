"""Extração do texto indexável de um documento enviado (spec: PDF, MD, TXT).

MD/TXT são texto; PDF é binário e precisa do texto das páginas: decodificar os
bytes indexava a estrutura crua do arquivo (``%PDF-1.4 ... obj``).
"""

from __future__ import annotations

import io


class UnreadableDocumentError(ValueError):
    """O arquivo não pôde ser lido no formato declarado pela extensão."""


def extract_text(data: bytes, ext: str) -> str:
    if ext != "pdf":
        return data.decode("utf-8", errors="replace")

    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, ValueError, KeyError) as e:
        raise UnreadableDocumentError("PDF ilegível") from e
    return "\n\n".join(p.strip() for p in pages if p.strip())
