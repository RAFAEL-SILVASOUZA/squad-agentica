"""Built-in skills: prompt templates pre-definidos pela plataforma.

Dono: be-skills (FASE 4). Skills built-in sao templates de prompt que
representam capacidades prontas da plataforma. Nao sao persistidas no
Postgres/Garage; sao servidas em memoria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BuiltinSkill:
    """Definicao de uma skill built-in."""

    name: str
    description: str
    category: str
    template: str
    variables: list[str] = field(default_factory=list)
    inputs: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    required_integrations: list[str] = field(default_factory=list)


BUILTIN_SKILLS: list[BuiltinSkill] = [
    BuiltinSkill(
        name="code-gen",
        description="Gera codigo a partir de uma descricao funcional",
        category="code",
        template=(
            "Voce e um engenheiro de software sênior. Gere codigo limpo, "
            "testado e documentado para a seguinte tarefa:\n\n"
            "## Tarefa\n{task}\n\n"
            "## Linguagem/Framework\n{language}\n\n"
            "## Restricoes\n{constraints}\n\n"
            "Retorne o codigo completo com comentarios explicativos."
        ),
        variables=["task", "language", "constraints"],
    ),
    BuiltinSkill(
        name="test-runner",
        description="Analisa e executa testes, interpreta resultados",
        category="code",
        template=(
            "Voce e um QA engineer. Analise os resultados de teste abaixo "
            "e identifique falhas, causas provaveis e sugestoes de correcao:\n\n"
            "## Resultados\n{test_results}\n\n"
            "## Contexto\n{context}\n\n"
            "Retorne uma analise estruturada com: (1) resumo, (2) falhas "
            "criticas, (3) sugestoes de correcao."
        ),
        variables=["test_results", "context"],
    ),
    BuiltinSkill(
        name="security-scanner",
        description="Revisa codigo em busca de vulnerabilidades de seguranca",
        category="code",
        template=(
            "Voce e um security engineer especializado em OWASP Top 10. "
            "Revise o codigo abaixo em busca de vulnerabilidades:\n\n"
            "## Codigo\n{code}\n\n"
            "## Linguagem\n{language}\n\n"
            "Retorne: (1) vulnerabilidades encontradas com severidade, "
            "(2) localizacao exata, (3) correcao sugerida para cada uma."
        ),
        variables=["code", "language"],
    ),
    BuiltinSkill(
        name="doc-writer",
        description="Gera documentacao tecnica a partir de codigo ou descricao",
        category="docs",
        template=(
            "Voce e um technical writer. Gere documentacao clara e "
            "profissional para:\n\n"
            "## Codigo/Componente\n{code}\n\n"
            "## Publico-alvo\n{audience}\n\n"
            "## Formato\n{format}\n\n"
            "Inclua: descricao, uso, parametros, exemplos e notas de "
            "seguranca se aplicavel."
        ),
        variables=["code", "audience", "format"],
    ),
    BuiltinSkill(
        name="api-client",
        description="Gera codigo de cliente para consumir APIs REST",
        category="code",
        template=(
            "Voce e um engenheiro de integracoes. Gere um cliente de API "
            "para consumir a seguinte API:\n\n"
            "## Endpoints\n{endpoints}\n\n"
            "## Autenticacao\n{auth}\n\n"
            "## Linguagem\n{language}\n\n"
            "Inclua: tratamento de erros, retries, timeouts e logging."
        ),
        variables=["endpoints", "auth", "language"],
    ),
    BuiltinSkill(
        name="deploy-runner",
        description="Gera scripts e procedimentos de deploy",
        category="infra",
        template=(
            "Voce e um DevOps engineer. Gere o procedimento de deploy "
            "para a seguinte aplicacao:\n\n"
            "## Aplicacao\n{app_description}\n\n"
            "## Ambiente\n{environment}\n\n"
            "## Infraestrutura\n{infrastructure}\n\n"
            "Inclua: pre-requisitos, passos de deploy, rollback e "
            "verificacao pos-deploy."
        ),
        variables=["app_description", "environment", "infrastructure"],
    ),
]


def get_builtin_skill(name: str) -> BuiltinSkill | None:
    """Retorna uma skill built-in pelo nome."""
    for skill in BUILTIN_SKILLS:
        if skill.name == name:
            return skill
    return None


def list_builtin_skills() -> list[BuiltinSkill]:
    """Retorna todas as skills built-in."""
    return list(BUILTIN_SKILLS)
