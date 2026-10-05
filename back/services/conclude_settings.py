"""O que o "Concluir" do card faz em cada repositório (Configurações › Concluir).

Cada repo do Bitbucket tem a sua receita: para que status do Jira a tarefa vai (ou não mexe no
Jira) e se o PR aberto é mergeado — com que estratégia e se a branch de origem fecha. Um repo
pode levar direto a "Concluído"; outro, a "DISPONIVEL PARA TESTES" mergeando o PR. Repo sem
receita não tem "Concluir": o card nem mostra o botão.

Guardado em `app_setting` (`conclude`), como as cores dos cards: é preferência do dev, não
dado do espelho. O que vem de lá é validado na leitura — um valor estranho vira "sem receita",
nunca um merge com estratégia inventada.

Ter receita não basta para o botão aparecer: o card precisa estar **apto** (`blocked_reason`)
— PR aprovado pela regra de Configurações › Pull requests e a tarefa ainda antes de testes.
"""

from dataclasses import dataclass
from typing import Any

import asyncpg

from repositories import settings_repo
from services import card_colors
from services.pr_status import IssuePrSummary, PrStatus
from services.progress.service import load_stages
from services.progress.stages import TESTS, ProgressStages

SETTING_KEY = "conclude"
MERGE_STRATEGIES = ("merge_commit", "squash", "fast_forward")
DEFAULT_STRATEGY = "merge_commit"
MAX_STATUS_LENGTH = 80


@dataclass(frozen=True)
class RepoConclusion:
    jira_status: str | None = None
    merge: bool = False
    strategy: str = DEFAULT_STRATEGY
    close_source_branch: bool = True

    @property
    def does_something(self) -> bool:
        return bool(self.jira_status) or self.merge

    def to_setting(self) -> dict[str, Any]:
        return {
            "jira_status": self.jira_status,
            "merge": self.merge,
            "strategy": self.strategy,
            "close_source_branch": self.close_source_branch,
        }


def valid_rule(raw: Any) -> RepoConclusion | None:
    """A receita aproveitável de um repo, ou `None` se ela não faz nada."""
    if not isinstance(raw, dict):
        return None
    status = raw.get("jira_status")
    status = status.strip() if isinstance(status, str) else ""
    strategy = raw.get("strategy")
    rule = RepoConclusion(
        jira_status=status[:MAX_STATUS_LENGTH] or None,
        merge=raw.get("merge") is True,
        strategy=strategy if strategy in MERGE_STRATEGIES else DEFAULT_STRATEGY,
        close_source_branch=raw.get("close_source_branch") is not False,
    )
    return rule if rule.does_something else None


def from_setting(value: Any) -> dict[str, RepoConclusion]:
    repos = (value or {}).get("repos") if isinstance(value, dict) else None
    if not isinstance(repos, dict):
        return {}
    rules = {}
    for slug, raw in repos.items():
        rule = valid_rule(raw)
        if rule is not None and isinstance(slug, str) and slug:
            rules[slug] = rule
    return rules


def to_setting(rules: dict[str, RepoConclusion]) -> dict[str, Any]:
    return {"repos": {slug: rule.to_setting() for slug, rule in sorted(rules.items())}}


async def load_rules(pool: asyncpg.Pool) -> dict[str, RepoConclusion]:
    return from_setting(await settings_repo.get_setting(pool, SETTING_KEY))


async def save_rules(
    pool: asyncpg.Pool, rules: dict[str, RepoConclusion]
) -> dict[str, RepoConclusion]:
    kept = {slug: rule for slug, rule in rules.items() if rule.does_something}
    await settings_repo.set_setting(pool, SETTING_KEY, to_setting(kept))
    return kept


def concludable(rules: dict[str, RepoConclusion], repos: list[str]) -> list[str]:
    """Os repos da tarefa que têm receita, na ordem em que apareceram."""
    return [slug for slug in repos if slug in rules]


def task_repos(summary: IssuePrSummary | None, title_repos: list[str]) -> list[str]:
    """Repos da tarefa: os dos PRs e branches dela no espelho, depois o `[repo]` do título."""
    found: list[str] = []
    for slug in [*(r.repo_slug for r in (summary.repos if summary else [])), *title_repos]:
        if slug not in found:
            found.append(slug)
    return found


@dataclass(frozen=True)
class ConcludeTask:
    key: str
    # O título: o `[repo]` dele conta como repo da tarefa.
    title: str | None
    status: str | None
    status_category: str | None


def blocked_reason(
    rules: dict[str, RepoConclusion],
    task: ConcludeTask,
    summary: IssuePrSummary | None,
    title_repos: list[str],
    stages: ProgressStages,
) -> str | None:
    """Por que o card **não** está apto ao Concluir — `None` quando está. Pedido do dev: o
    botão só aparece em quem pode mesmo concluir.

    - algum repo da tarefa tem receita;
    - a tarefa ainda não chegou a testes nem foi concluída (etapas de Configurações ›
      Progresso; sem a etapa de testes no mapa, vale só a categoria "done" do Jira);
    - ela tem PR nesses repos, e todo PR aberto está **aprovado pela regra** de Configurações ›
      Pull requests — o que já deixa de fora rascunho e ajuste pedido. PR já mergeado conta:
      falta só o Jira andar.
    """
    repos = concludable(rules, task_repos(summary, title_repos))
    if not repos:
        return "Nenhum repo da tarefa tem receita em Configurações › Concluir."
    if task.status_category == "done":
        return "A tarefa já está concluída."
    tests = stages.by_id.get(TESTS)
    stage = stages.stage_of(task.status)
    if tests is not None and stage is not None and stage.order >= tests.order:
        return f"A tarefa já está em “{task.status}” — o Concluir é para antes dos testes."
    prs = [
        pr
        for repo in (summary.repos if summary else [])
        if repo.repo_slug in repos
        for pr in repo.pull_requests
        if pr.state in ("OPEN", "MERGED")
    ]
    if not prs:
        return "A tarefa não tem PR nos repos do Concluir."
    pending = [pr for pr in prs if pr.state == "OPEN" and pr.status != PrStatus.APROVADA]
    if pending:
        ids = ", ".join(f"#{pr.id}" for pr in pending)
        return (
            f"PR {ids} ainda não está aprovado pela regra de Configurações › Pull requests."
        )
    return None


async def with_conclusion(
    pool: asyncpg.Pool, tasks: list[ConcludeTask], prs: dict[str, IssuePrSummary]
) -> set[str]:
    """Chaves das tarefas aptas ao Concluir (ver `blocked_reason`)."""
    rules = await load_rules(pool)
    if not rules:
        return set()
    colors = await card_colors.load_colors(pool)
    stages = await load_stages(pool)
    return {
        task.key
        for task in tasks
        if blocked_reason(
            rules, task, prs.get(task.key), colors.title_repos(task.title), stages
        )
        is None
    }
