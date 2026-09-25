"""Skill Loader: monta a mochila do agente em runtime (D8, spec 6.6).

Dono: pe-loader (FASE 4). Contrato (spec 6.6 "Contrato de injeção" + ADR-008):
    loader.load(agent_snapshot) -> AgentCapabilities

O loader roda no **worker** (ADR-008), não no orchestrator: é pesado
(download de skills do Garage, descoberta de tools MCP, query RAG) e não pode
consumir o event loop do grafo. O worker baixa o .yml do agente, chama
``load()`` e passa o resultado como segundo argumento de ``Agent.run()``.

Capacidades são **derivadas em runtime** e nunca persistidas no snapshot
(contrato §11, divergência X-01). O snapshot carrega só os campos da spec.

Resolução da mochila (spec 6.6):
- (a) skills: baixa o .md do Garage (cache local por versão + TTL) e injeta
  os prompts no ``systemPrompt``.
- (b) tools: carrega CustomTools deployadas + ferramentas básicas habilitadas
  (``shell`` só quando ``shellAccess=true``).
- (c) mcpServers: conecta aos servidores associados e descobre tools via
  ``tools/list``, aplicando ``toolFilter``.
- (d) knowledge: prepara o acesso a knowledge (retriever por escopo) e busca
  contexto via RAG, delimitado por marcadores de dado externo (spec 14.1).

Falhas parciais (uma skill ausente, um MCP fora do ar, uma KB sem chunks)
**não derrubam** o carregamento: registram um aviso em ``warnings`` e seguem
(D8 riscos). Só uma falha de dependência estrutural (ex.: DB indisponível)
propaga, porque sem ela não há como derivar nada.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentCapabilities, AgentSnapshot
from app.db.models import CustomTool, MCPServer
from app.integrations.github import wrap_external_data
from app.knowledge.rag import RagService
from app.mcp.client import MCPClient
from app.skills.builtins import get_builtin_skill
from app.skills.storage import SkillStorage
from app.tools.builtins import list_builtin_tools

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache local de skills (D8 riscos: N downloads por load -> cache + TTL)
# ---------------------------------------------------------------------------

# TTL em segundos para o cache local de conteúdo de skills.
SKILL_CACHE_TTL_SECONDS = 300.0


@dataclass
class _SkillCacheEntry:
    content: str
    fetched_at: float


class SkillContentCache:
    """Cache local (em memória) de conteúdo de skills, com TTL.

    Chave: ``skill_id``. O conteúdo .md de uma skill raramente muda; o cache
    evita N downloads do Garage a cada load. A invalidação é por TTL (simples
    e suficiente para a V1, onde skills são editadas raramente).
    """

    def __init__(self, ttl_seconds: float = SKILL_CACHE_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, _SkillCacheEntry] = {}

    def get(self, skill_id: str) -> str | None:
        entry = self._entries.get(skill_id)
        if entry is None:
            return None
        if (time.monotonic() - entry.fetched_at) > self._ttl:
            # Expirado: remove e trata como miss.
            del self._entries[skill_id]
            return None
        return entry.content

    def put(self, skill_id: str, content: str) -> None:
        self._entries[skill_id] = _SkillCacheEntry(content=content, fetched_at=time.monotonic())

    def clear(self) -> None:
        self._entries.clear()


# ---------------------------------------------------------------------------
# Protocols de dependência (injetáveis para testes)
# ---------------------------------------------------------------------------


class MCPClientFactory(Protocol):
    """Fábrica de client MCP (injetável para mockar a conexão)."""

    def __call__(
        self,
        transport: str,
        command: str | None = None,
        url: str | None = None,
        env: dict[str, str] | None = None,
    ) -> MCPClient:
        ...


def _default_mcp_client_factory(
    transport: str,
    command: str | None = None,
    url: str | None = None,
    env: dict[str, str] | None = None,
) -> MCPClient:
    return MCPClient(transport=transport, command=command, url=url, env=env)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


@dataclass
class LoadResult:
    """Resultado de ``load()``: capacidades + avisos de falha parcial.

    ``warnings`` carrega mensagens de falha parcial (skill ausente, MCP fora
    do ar, KB sem chunks). O worker pode logá-las e/ou expô-las nos logs do
    run, mas **não** falha a execução por causa delas.
    """

    capabilities: AgentCapabilities
    warnings: list[str] = field(default_factory=list)


class SkillLoader:
    """Monta a mochila do agente a partir do snapshot (spec 6.6).

    Dependências são injetadas no construtor para permitir testes isolados
    (Garage, MCP e embedder mockados). O ``db`` é a sessão do worker.
    """

    def __init__(
        self,
        db: AsyncSession,
        storage: SkillStorage,
        rag: RagService | None = None,
        mcp_client_factory: MCPClientFactory | None = None,
        cache: SkillContentCache | None = None,
    ) -> None:
        self._db = db
        self._storage = storage
        self._rag = rag
        self._mcp_factory = mcp_client_factory or _default_mcp_client_factory
        self._cache = cache or SkillContentCache()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    async def load(self, snapshot: AgentSnapshot) -> LoadResult:
        """Resolve a mochila completa do agente.

        Args:
            snapshot: definição do agente (campos da spec 4.1/4.2).

        Returns:
            LoadResult com AgentCapabilities + warnings de falha parcial.
        """
        warnings: list[str] = []

        # (a) skills -> systemPrompt.
        system_prompt = await self._resolve_skills(snapshot, warnings)

        # (b) tools -> custom deployadas + básicas habilitadas.
        tools = await self._resolve_tools(snapshot, warnings)

        # (c) mcpServers -> tools descobertas via tools/list.
        mcp_tools = await self._resolve_mcp(snapshot, warnings)

        # (d) knowledge -> contexto via RAG (delimitado por EXTERNAL_DATA).
        knowledge_context = await self._resolve_knowledge(snapshot, warnings)

        capabilities = AgentCapabilities(
            system_prompt=system_prompt,
            tools=tools,
            mcp_tools=mcp_tools,
            knowledge_context=knowledge_context,
        )
        return LoadResult(capabilities=capabilities, warnings=warnings)

    # ------------------------------------------------------------------
    # (a) Skills
    # ------------------------------------------------------------------

    async def _resolve_skills(
        self, snapshot: AgentSnapshot, warnings: list[str]
    ) -> str:
        """Baixa o .md das skills associadas e injeta no systemPrompt.

        O systemPrompt base é o ``snapshot.prompt``. Cada skill associada
        contribui com um bloco ``## Skill: <name>`` contendo o conteúdo .md.
        Skills built-in (por nome) são resolvidas em memória; skills custom
        são baixadas do Garage (com cache).
        """
        parts: list[str] = []
        if snapshot.prompt:
            parts.append(snapshot.prompt)

        for ref in snapshot.skills:
            skill_id = self._ref_id(ref, "skillId")
            if not skill_id:
                warnings.append(f"skill ref sem skillId ignorada: {ref!r}")
                continue

            content = await self._load_skill_content(skill_id, warnings)
            if content is None:
                continue

            name = self._ref_name(ref, skill_id)
            parts.append(f"## Skill: {name}\n{content}")

        return "\n\n".join(parts)

    async def _load_skill_content(self, skill_id: str, warnings: list[str]) -> str | None:
        """Resolve o conteúdo .md de uma skill (built-in ou do Garage).

        Ordem: (1) built-in por nome, (2) cache local, (3) Garage. Falha
        parcial: se o Garage não tem a skill, registra aviso e retorna None.
        """
        # Built-in: o "id" pode ser o nome da skill built-in.
        builtin = get_builtin_skill(skill_id)
        if builtin is not None:
            return builtin.template

        # Cache local (evita N downloads do Garage por load).
        cached = self._cache.get(skill_id)
        if cached is not None:
            return cached

        # Garage (source of truth do conteúdo .md).
        try:
            content = await self._storage.get_skill(skill_id)
        except Exception as e:  # noqa: BLE001 - falha parcial, não derruba o load.
            warnings.append(f"skill {skill_id} indisponível no storage: {e}")
            return None

        self._cache.put(skill_id, content)
        return content

    # ------------------------------------------------------------------
    # (b) Tools
    # ------------------------------------------------------------------

    async def _resolve_tools(
        self, snapshot: AgentSnapshot, warnings: list[str]
    ) -> list[dict[str, Any]]:
        """Carrega CustomTools deployadas + ferramentas básicas habilitadas.

        Ambas são expostas ao LLM no mesmo formato de function calling
        (nome, descrição, schema de entrada) — spec 6.6 nota.
        """
        tools: list[dict[str, Any]] = []

        # Ferramentas básicas (shell só se shellAccess=true).
        for builtin in list_builtin_tools(shell_access=snapshot.shell_access):
            tools.append(
                {
                    "name": builtin.name,
                    "description": builtin.description,
                    "inputSchema": builtin.input_schema,
                    "source": "builtin",
                }
            )

        # CustomTools deployadas.
        for ref in snapshot.tools:
            tool_id = self._ref_id(ref, "toolId")
            if not tool_id:
                warnings.append(f"tool ref sem toolId ignorada: {ref!r}")
                continue

            tool = await self._load_custom_tool(tool_id, warnings)
            if tool is None:
                continue

            schema = self._tool_input_schema(tool)
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": schema,
                    "source": "custom",
                    "version": tool.version,
                }
            )

        return tools

    async def _load_custom_tool(self, tool_id: str, warnings: list[str]) -> CustomTool | None:
        """Carrega uma CustomTool do Postgres (só as deployadas entram)."""
        try:
            parsed_id = uuid.UUID(tool_id)
        except (ValueError, TypeError):
            warnings.append(f"toolId inválido ignorado: {tool_id!r}")
            return None

        result = await self._db.execute(select(CustomTool).where(CustomTool.id == parsed_id))
        tool = result.scalar_one_or_none()
        if tool is None:
            warnings.append(f"tool {tool_id} não encontrada")
            return None
        if tool.status != "deployed":
            warnings.append(f"tool {tool_id} não está deployada (status={tool.status})")
            return None
        return tool

    @staticmethod
    def _tool_input_schema(tool: CustomTool) -> dict[str, Any]:
        """Converte o contrato de I/O da tool num JSON Schema de entrada.

        O campo ``io`` da CustomTool tem a forma ``{inputs: ToolParam[],
        outputs: ToolParam[]}`` (spec 6.4). Cada ToolParam tem ``name``,
        ``type`` e ``required``.
        """
        io = tool.io or {}
        params = io.get("inputs", []) or []
        properties: dict[str, Any] = {}
        required: list[str] = []
        for p in params:
            if not isinstance(p, dict):
                continue
            name = p.get("name")
            if not name:
                continue
            properties[name] = {"type": p.get("type", "string")}
            if p.get("required"):
                required.append(name)
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    # ------------------------------------------------------------------
    # (c) MCP servers
    # ------------------------------------------------------------------

    async def _resolve_mcp(
        self, snapshot: AgentSnapshot, warnings: list[str]
    ) -> list[dict[str, Any]]:
        """Conecta aos servidores MCP associados e descobre tools.

        Cada servidor contribui com suas tools descobertas (ou um subconjunto
        via ``toolFilter``). Falha parcial: um servidor fora do ar registra
        aviso e segue (D8).
        """
        mcp_tools: list[dict[str, Any]] = []

        for ref in snapshot.mcp_servers:
            server_id = self._ref_id(ref, "serverId")
            if not server_id:
                warnings.append(f"mcp ref sem serverId ignorada: {ref!r}")
                continue

            tool_filter = ref.get("toolFilter") if isinstance(ref, dict) else None
            tools = await self._discover_mcp_tools(server_id, tool_filter, warnings)
            mcp_tools.extend(tools)

        return mcp_tools

    async def _discover_mcp_tools(
        self,
        server_id: str,
        tool_filter: list[str] | None,
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        """Descobre as tools de um servidor MCP (tools/list) e aplica o filtro."""
        server = await self._load_mcp_server(server_id, warnings)
        if server is None:
            return []

        client = self._mcp_factory(
            transport=server.transport,
            command=server.command,
            url=server.url,
            env=server.env or {},
        )
        try:
            await client.connect()
            discovered = await client.list_tools()
        except Exception as e:  # noqa: BLE001 - falha parcial, não derruba o load.
            warnings.append(f"MCP server {server_id} indisponível: {e}")
            return []
        finally:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001 - disconnect é best-effort.
                pass

        # Aplica toolFilter (subconjunto de tools a expor; default: todas).
        if tool_filter:
            allowed = set(tool_filter)
            discovered = [t for t in discovered if t.get("name") in allowed]

        # Prefixa o nome com o id do servidor para evitar colisão entre
        # servidores que expõem tools com o mesmo nome.
        result: list[dict[str, Any]] = []
        for t in discovered:
            result.append(
                {
                    "name": f"{server.name}__{t.get('name', '')}",
                    "description": t.get("description", ""),
                    "inputSchema": t.get("inputSchema", {}),
                    "source": "mcp",
                    "serverId": server_id,
                    "originalName": t.get("name", ""),
                }
            )
        return result

    async def _load_mcp_server(self, server_id: str, warnings: list[str]) -> MCPServer | None:
        """Carrega um servidor MCP do Postgres."""
        try:
            parsed_id = uuid.UUID(server_id)
        except (ValueError, TypeError):
            warnings.append(f"serverId inválido ignorado: {server_id!r}")
            return None

        result = await self._db.execute(select(MCPServer).where(MCPServer.id == parsed_id))
        server = result.scalar_one_or_none()
        if server is None:
            warnings.append(f"MCP server {server_id} não encontrado")
            return None
        return server

    # ------------------------------------------------------------------
    # (d) Knowledge
    # ------------------------------------------------------------------

    async def _resolve_knowledge(
        self, snapshot: AgentSnapshot, warnings: list[str]
    ) -> list[str]:
        """Busca contexto via RAG para as KBs associadas ao agente.

        Cada KnowledgeRef referencia uma KnowledgeBase por id (spec 4.6 nota).
        O query usado é o prompt do agente (proxy do contexto da tarefa). Os
        chunks retornados são delimitados por marcadores de dado externo
        (spec 14.1) para mitigar prompt injection.
        """
        if self._rag is None:
            return []

        kb_ids: list[uuid.UUID] = []
        for ref in snapshot.knowledge:
            kb_id = self._ref_id(ref, "reference")
            if not kb_id:
                continue
            try:
                kb_ids.append(uuid.UUID(kb_id))
            except (ValueError, TypeError):
                warnings.append(f"knowledge ref inválida ignorada: {ref!r}")

        if not kb_ids:
            return []

        query_text = snapshot.prompt or snapshot.name or "contexto"
        try:
            chunks = await self._rag.query(
                self._db,
                owner_id=self._owner_id_from_snapshot(snapshot),
                text=query_text,
                knowledge_base_ids=kb_ids,
                agent_id=snapshot.id,
            )
        except Exception as e:  # noqa: BLE001 - falha parcial, não derruba o load.
            warnings.append(f"knowledge query falhou: {e}")
            return []

        return [wrap_external_data(c["content"]) for c in chunks]

    @staticmethod
    def _owner_id_from_snapshot(snapshot: AgentSnapshot) -> uuid.UUID:
        """Deriva o owner_id do snapshot.

        O snapshot da spec 4.1 não carrega ``ownerId`` explicitamente (V1 é
        single-user). Para o isolamento por owner na query RAG, usamos um UUID
        determinístico derivado do id do agente. Em produção, o worker injeta
        o owner real via o snapshot (ver pendências).
        """
        return uuid.uuid5(uuid.NAMESPACE_URL, f"agent-portal:owner:{snapshot.id}")

    # ------------------------------------------------------------------
    # Helpers de ref
    # ------------------------------------------------------------------

    @staticmethod
    def _ref_id(ref: Any, key: str) -> str | None:
        """Extrai o id de um ref (dict com a chave ``key``)."""
        if isinstance(ref, dict):
            value = ref.get(key)
            return str(value) if value else None
        return None

    @staticmethod
    def _ref_name(ref: Any, fallback: str) -> str:
        """Extrai um nome legível de um ref (para o título do bloco de skill)."""
        if isinstance(ref, dict):
            name = ref.get("name")
            if name:
                return str(name)
        return fallback


# ---------------------------------------------------------------------------
# API de conveniência (contrato D8: loader.load(agent_snapshot))
# ---------------------------------------------------------------------------


def get_loader(
    db: AsyncSession,
    storage: SkillStorage,
    rag: RagService | None = None,
    mcp_client_factory: MCPClientFactory | None = None,
    cache: SkillContentCache | None = None,
) -> SkillLoader:
    """Fábrica do loader (injetável para testes)."""
    return SkillLoader(
        db=db,
        storage=storage,
        rag=rag,
        mcp_client_factory=mcp_client_factory,
        cache=cache,
    )


async def load(
    snapshot: AgentSnapshot,
    db: AsyncSession,
    storage: SkillStorage,
    rag: RagService | None = None,
    mcp_client_factory: MCPClientFactory | None = None,
    cache: SkillContentCache | None = None,
) -> LoadResult:
    """API de conveniência: ``loader.load(agent_snapshot)`` (spec 6.6).

    Cria um loader efêmero e resolve a mochila. O worker pode usar esta
    função diretamente ou instanciar ``SkillLoader`` para reutilizar o cache
    entre execuções.
    """
    loader = get_loader(db, storage, rag, mcp_client_factory, cache)
    return await loader.load(snapshot)
