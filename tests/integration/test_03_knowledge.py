"""Cenario 3 - Knowledge: criar base, upload de PDF, MD e TXT, ingestao ate
``ready``, query com topK e escopo.

Fontes: spec 7.x/9.x, GUIA-API-FRONTEND "Knowledge Base", contrato §4
(EMBEDDING_PROVIDER=mock: vetor deterministico por hash do texto; a mesma
string consultada devolve score ~1.0).
"""

from __future__ import annotations

import uuid

from conftest import assert_envelope, db_query, wait_until

TXT = "QA-TXT: a pipeline de integracao valida o fluxo de ponta a ponta."
MD = "# QA-MD\n\nO agente revisor aprova pull requests com testes."
PDF_PHRASE = "QA-PDF marcador de ingestao"


def make_pdf(text: str) -> bytes:
    """PDF 1.4 minimo, valido, com uma linha de texto (sem dependencias)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def create_kb(u, **over):
    body = {"name": f"qa-kb-{uuid.uuid4().hex[:6]}", "scope": "global", "source": "upload",
            "chunkSize": 2000, "chunkOverlap": 0, "topK": 5, "similarityThreshold": -1.0}
    body.update(over)
    r = u.post("/api/knowledge", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def upload(u, kb_id, name, data: bytes, ctype: str):
    return u.post(f"/api/knowledge/{kb_id}/upload", files={"file": (name, data, ctype)})


def doc_status(u, kb_id):
    return {d["name"]: d for d in u.get(f"/api/knowledge/{kb_id}/documents").json()["items"]}


def test_kb_crud_upload_three_formats_until_ready(user):
    kb = create_kb(user)
    assert kb["scope"] == "global" and kb["topK"] == 5

    for name, data, ctype in (
        ("qa.txt", TXT.encode(), "text/plain"),
        ("qa.md", MD.encode(), "text/markdown"),
        ("qa.pdf", make_pdf(PDF_PHRASE), "application/pdf"),
    ):
        r = upload(user, kb["id"], name, data, ctype)
        assert r.status_code in (200, 201, 202), f"{name}: {r.status_code} {r.text}"
        assert r.json()["documentId"]

    docs = wait_until(
        lambda: (d := doc_status(user, kb["id"])) and all(x["status"] == "ready" for x in d.values()) and len(d) == 3 and d,
        timeout=60, desc="3 documentos ready",
    )
    for d in docs.values():
        assert d["chunkCount"] >= 1, d
    assert user.get(f"/api/knowledge/{kb['id']}").json()["documentCount"] == 3

    r = user.put(f"/api/knowledge/{kb['id']}", json={"topK": 2})
    assert r.status_code == 200 and r.json()["topK"] == 2

    # Remocao de documento e da base.
    txt_id = docs["qa.txt"]["id"]
    assert user.delete(f"/api/knowledge/{kb['id']}/documents/{txt_id}").status_code == 204
    assert "qa.txt" not in doc_status(user, kb["id"])
    assert user.delete(f"/api/knowledge/{kb['id']}").status_code == 204
    assert_envelope(user.get(f"/api/knowledge/{kb['id']}"), 404)


def test_pdf_text_is_extracted_not_raw_bytes(user):
    """Upload de PDF deve indexar o TEXTO do PDF, nao a sintaxe do arquivo."""
    kb = create_kb(user)
    r = upload(user, kb["id"], "qa.pdf", make_pdf(PDF_PHRASE), "application/pdf")
    assert r.status_code in (200, 201, 202), r.text
    doc_id = r.json()["documentId"]
    wait_until(lambda: doc_status(user, kb["id"]).get("qa.pdf", {}).get("status") == "ready", timeout=60, desc="pdf ready")
    rows = db_query("SELECT content FROM knowledge_chunks WHERE document_id = %s ORDER BY chunk_index", (doc_id,))
    content = "\n".join(r[0] for r in rows)
    assert PDF_PHRASE in content
    assert "%PDF-" not in content and "endobj" not in content, f"PDF indexado cru: {content[:160]!r}"


def test_query_topk_and_exact_match(user):
    kb = create_kb(user)
    for name, text in (("a.txt", TXT), ("b.md", MD), ("c.txt", "QA-C: terceiro documento de controle.")):
        assert upload(user, kb["id"], name, text.encode(), "text/plain").status_code in (200, 201, 202)
    wait_until(lambda: len([d for d in doc_status(user, kb["id"]).values() if d["status"] == "ready"]) == 3,
               timeout=60, desc="3 ready")

    r = user.post("/api/knowledge/query", json={"query": TXT, "knowledgeBaseIds": [kb["id"]], "topK": 2})
    assert r.status_code == 200, r.text
    chunks = r.json()["chunks"]
    assert len(chunks) == 2, chunks
    assert chunks[0]["content"].strip() == TXT and chunks[0]["score"] > 0.99, chunks[0]
    assert chunks[0]["score"] >= chunks[1]["score"]

    r = user.post("/api/knowledge/query", json={"query": TXT, "knowledgeBaseIds": [kb["id"]], "topK": 1})
    assert len(r.json()["chunks"]) == 1

    # Sem topK: usa o topK da base (5), limitado ao que existe (3).
    r = user.post("/api/knowledge/query", json={"query": TXT, "knowledgeBaseIds": [kb["id"]]})
    assert len(r.json()["chunks"]) == 3


def test_query_respects_scope_and_threshold(user):
    ag_scoped = create_kb(user, scope="agent", scopeRef=str(uuid.uuid4()))
    strict = create_kb(user, similarityThreshold=0.9)
    for kb in (ag_scoped, strict):
        assert upload(user, kb["id"], "s.txt", TXT.encode(), "text/plain").status_code in (200, 201, 202)
        assert upload(user, kb["id"], "t.txt", b"QA-OUTRO: texto sem relacao.", "text/plain").status_code in (200, 201, 202)
    wait_until(lambda: all(d["status"] == "ready" for kb in (ag_scoped, strict) for d in doc_status(user, kb["id"]).values()),
               timeout=60, desc="ready")

    # Base de escopo "agent" nao aparece numa query sem contexto de agente.
    r = user.post("/api/knowledge/query", json={"query": TXT, "knowledgeBaseIds": [ag_scoped["id"]]})
    assert r.status_code == 200 and r.json()["chunks"] == [], r.json()

    # similarityThreshold 0.9: so o chunk identico passa.
    r = user.post("/api/knowledge/query", json={"query": TXT, "knowledgeBaseIds": [strict["id"]], "topK": 5})
    assert [c["content"].strip() for c in r.json()["chunks"]] == [TXT]

    # Filtro de listagem por escopo.
    lst = user.get("/api/knowledge", params={"scope": "agent"}).json()["items"]
    assert {k["id"] for k in lst} == {ag_scoped["id"]}


def test_scope_ref_required_and_invalid_file_type(user):
    r = user.post("/api/knowledge", json={"name": "qa-kb-x", "scope": "pipeline", "source": "upload"})
    assert_envelope(r, 400, "scope_ref_required")
    kb = create_kb(user)
    r = upload(user, kb["id"], "malware.exe", b"MZ....", "application/octet-stream")
    assert_envelope(r, 400, "invalid_file_type")
