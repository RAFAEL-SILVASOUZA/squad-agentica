"""Verificação manual: conexão Excel cadastrada, sem imprimir credenciais.

Não é teste automatizado (precisa do servidor "Excel" cadastrado e de um LLM
real). Rodar dentro do container do orchestrator, em /app:

    python -m scripts.verify_excel_mcp
"""

import asyncio
import json
import shutil
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import httpx
from sqlalchemy import select

from app.agents.service import AgentService
from app.auth.jwt import create_access_token
from app.core.config import settings
from app.db.models import MCPServer
from app.db.session import async_session_factory
from app.runtime.worker_client import HttpWorkerClient


async def main():
    async with async_session_factory() as db:
        server = (
            (await db.execute(select(MCPServer).where(MCPServer.name == "Excel"))).scalars().first()
        )
        assert server is not None, "Servidor Excel não cadastrado"
        async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=90) as client:
            response = await client.post(
                f"/api/mcp-servers/{server.id}/test",
                headers={"Authorization": f"Bearer {create_access_token(str(server.owner_id))}"},
            )
        result = response.json()
        print(
            json.dumps(
                {
                    "httpStatus": response.status_code,
                    "status": result.get("status"),
                    "tools": [t["name"] for t in result.get("discoveredTools", [])],
                },
                ensure_ascii=False,
            )
        )
        assert response.status_code == 200 and result["status"] == "connected"
        assert settings.llm_provider == "openai"
        print(json.dumps({"provider": settings.llm_provider, "model": settings.llm_model}))
        await db.refresh(server)
        workspace = Path(settings.workspaces_dir) / f"task14-validation-{uuid.uuid4().hex[:8]}"
        workspace.mkdir(parents=True)
        book = workspace / "validacao.xlsx"
        with zipfile.ZipFile(book, "w", zipfile.ZIP_DEFLATED) as workbook:
            content_types_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
            package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
            office_rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            workbook_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
            content_types = ET.Element(f"{{{content_types_ns}}}Types")
            ET.SubElement(
                content_types,
                f"{{{content_types_ns}}}Default",
                {
                    "Extension": "rels",
                    "ContentType": "application/vnd.openxmlformats-package.relationships+xml",
                },
            )
            ET.SubElement(
                content_types,
                f"{{{content_types_ns}}}Default",
                {"Extension": "xml", "ContentType": "application/xml"},
            )
            ET.SubElement(
                content_types,
                f"{{{content_types_ns}}}Override",
                {
                    "PartName": "/xl/workbook.xml",
                    "ContentType": (
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
                    ),
                },
            )
            ET.SubElement(
                content_types,
                f"{{{content_types_ns}}}Override",
                {
                    "PartName": "/xl/worksheets/sheet1.xml",
                    "ContentType": (
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
                    ),
                },
            )
            workbook.writestr("[Content_Types].xml", ET.tostring(content_types))

            package_rels = ET.Element(f"{{{package_rel_ns}}}Relationships")
            ET.SubElement(
                package_rels,
                f"{{{package_rel_ns}}}Relationship",
                {
                    "Id": "rId1",
                    "Type": f"{office_rel_ns}/officeDocument",
                    "Target": "xl/workbook.xml",
                },
            )
            workbook.writestr("_rels/.rels", ET.tostring(package_rels))

            book_root = ET.Element(f"{{{workbook_ns}}}workbook")
            sheets = ET.SubElement(book_root, f"{{{workbook_ns}}}sheets")
            ET.SubElement(
                sheets,
                f"{{{workbook_ns}}}sheet",
                {"name": "Sheet1", "sheetId": "1", f"{{{office_rel_ns}}}id": "rId1"},
            )
            workbook.writestr("xl/workbook.xml", ET.tostring(book_root))

            book_rels = ET.Element(f"{{{package_rel_ns}}}Relationships")
            ET.SubElement(
                book_rels,
                f"{{{package_rel_ns}}}Relationship",
                {
                    "Id": "rId1",
                    "Type": f"{office_rel_ns}/worksheet",
                    "Target": "worksheets/sheet1.xml",
                },
            )
            workbook.writestr("xl/_rels/workbook.xml.rels", ET.tostring(book_rels))

            sheet = ET.Element(f"{{{workbook_ns}}}worksheet")
            ET.SubElement(sheet, f"{{{workbook_ns}}}sheetData")
            workbook.writestr(
                "xl/worksheets/sheet1.xml",
                ET.tostring(sheet),
            )
        async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=90) as client:
            response = await client.post(
                f"/internal/mcp/{server.id}/call",
                headers={"X-Worker-Token": settings.worker_token},
                json={
                    "ownerId": str(server.owner_id),
                    "tool": "excel_write_to_sheet",
                    "arguments": {
                        "fileAbsolutePath": str(book),
                        "sheetName": "Dados",
                        "newSheet": True,
                        "range": "A1:B2",
                        "values": [["item", "valor"], ["TASK14_REAL", 42]],
                    },
                    "workspaceDir": str(workspace),
                },
            )
        assert response.status_code == 200 and not response.json()["isError"], response.text
        service = AgentService()
        try:
            agent = await service.create_agent(
                db,
                server.owner_id,
                {
                    "name": f"Task14 validação {uuid.uuid4().hex[:8]}",
                    "type": "custom",
                    "prompt": (
                        "Use obrigatoriamente excel_read_sheet para ler o arquivo informado. "
                        "Não use shell nem outras ferramentas. Responda result com os valores "
                        "reais lidos. Depois finalize."
                    ),
                    "mcpServers": [{"serverId": str(server.id)}],
                    "outputs": [{"name": "result", "type": "document", "required": False}],
                    "actions": ["finalize"],
                },
            )
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            raise
        try:
            worker = HttpWorkerClient()
            execution = await worker.execute(
                str(agent.id),
                "excel-validation",
                {
                    "task": (
                        f"Leia com excel_read_sheet o arquivo {book}, sheetName Dados, range A1:B2."
                    )
                },
                timeout=180,
                workspace_dir=str(workspace),
                owner_id=str(server.owner_id),
            )
            print(
                json.dumps(
                    {
                        "status": execution.status,
                        "error": execution.error,
                        "outputs": execution.outputs,
                        "logs": execution.logs[-8:],
                        "mcpCalled": any(
                            "Tool call: excel_read_sheet" in line for line in execution.logs
                        ),
                    },
                    ensure_ascii=False,
                )
            )
            assert execution.status == "completed"
            assert any("Tool call: excel_read_sheet" in line for line in execution.logs)
            assert "TASK14_REAL" in json.dumps(execution.outputs)
        finally:
            await service.delete_agent(db, server.owner_id, agent.id)
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
