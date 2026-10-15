"""WAIs por repositório — o menu do topo: as tarefas da sprint atual, da anterior e da
próxima no repo em que cada uma mexe, separadas por sprint (a próxima em cima).

Três sprints e não o espelho inteiro: o menu é para a semana que corre e as vizinhas dela.
As sprints antigas, as filas do board (🛠️BUG-SUPORT) e as tarefas sem sprint ficam de fora.

O vínculo tarefa ↔ repo é o mesmo dos "Repositórios envolvidos" do Workspace
(`workspace_service.link_issue_repos`): branch local com a chave, PR/branch do espelho do
Bitbucket e o `[repo]` do começo do título. Tarefa em dois repos aparece nos dois.

Cada repo leva o projeto do Bitbucket em que o dev o escolheu no sync (OrganIA, weon): é o
que segmenta o menu. Repo que só aparece pela branch ou pelo título, fora do sync, vem sem.
O nome do projeto é o da aba dele no Workspace, que o dev pode ter acertado (`WeON`).
"""

from typing import Any

import asyncpg

from repositories import workspace_repo
from schemas.workspace_schemas import (
    RepoIssueOut,
    RepoIssuesOut,
    RepoIssueSprintOut,
    RepoIssuesRepoOut,
)
from security.paths import Roots
from services import card_colors
from services.progress import ProgressStages, load_stages
from services.progress.service import stage_ref
from services.workspace import repos_service
from services.workspace.workspace_service import link_issue_repos


async def list_repo_issues(pool: asyncpg.Pool, roots: Roots) -> RepoIssuesOut:
    window = await workspace_repo.sprint_window(pool)
    if not window:
        return RepoIssuesOut(repos=[])
    rows = {
        r["key"]: r for r in await workspace_repo.issues_in_sprints(pool, [s["id"] for s in window])
    }
    local = (await repos_service.list_repos(pool, roots)).repos
    colors = await card_colors.load_colors(pool)
    summaries = {key: row["summary"] for key, row in rows.items()}
    links = await link_issue_repos(pool, local, list(rows), summaries, colors)
    stages = await load_stages(pool)
    by_slug = {r.slug: r for r in local}
    titles = await workspace_repo.project_titles(pool)
    project_of = {
        slug: (key, titles.get(key) or project["name"])
        for key, project in (await workspace_repo.mirror_projects(pool)).items()
        for slug in project["slugs"]
    }

    repos = []
    for slug in sorted(links.issue_keys, key=str.lower):
        keys = links.issue_keys[slug]
        if not keys:
            continue
        repo = by_slug.get(slug)
        bb_slug = repo.bb_slug if repo else links.remote_only.get(slug)
        project_key, project_name = project_of.get(bb_slug or slug, (None, None))
        repos.append(
            RepoIssuesRepoOut(
                slug=slug,
                bb_slug=bb_slug,
                local=bool(repo and repo.present and repo.has_git),
                color=colors.repos.get(slug) or colors.repos.get(bb_slug or ""),
                project_key=project_key,
                project_name=project_name,
                issue_count=len(keys),
                sprints=_by_sprint(window, [rows[key] for key in keys], stages),
            )
        )
    return RepoIssuesOut(repos=repos)


def _by_sprint(
    window: list[dict[str, Any]], rows: list[dict[str, Any]], stages: ProgressStages
) -> list[RepoIssueSprintOut]:
    """Na ordem da janela (próxima → atual → anterior); sprint sem WAI do repo não aparece."""
    result = []
    for sprint in window:
        members = [row for row in rows if row["sprint_id"] == sprint["id"]]
        if not members:
            continue
        result.append(
            RepoIssueSprintOut(
                id=sprint["id"],
                name=sprint["name"],
                state=sprint["state"],
                position=sprint["position"],
                issues=[_issue(row, stages) for row in sorted(members, key=_order(stages))],
            )
        )
    return result


def _order(stages: ProgressStages):
    """O que falta fazer primeiro (pela etapa: análise → concluído), e a tarefa mais nova
    antes da mais antiga na mesma etapa."""

    def key(row: dict[str, Any]) -> tuple[float, int, int]:
        weight, stage = stages.weight_of(row["status"], row["status_category"])
        return (weight, stage.order if stage else len(stages.stages), -_key_number(row["key"]))

    return key


def _key_number(key: str) -> int:
    number = key.rpartition("-")[2]
    return int(number) if number.isdigit() else 0


def _issue(row: dict[str, Any], stages: ProgressStages) -> RepoIssueOut:
    return RepoIssueOut(
        key=row["key"],
        summary=row["summary"],
        issue_type=row["issue_type"],
        status=row["status"],
        stage=stage_ref(stages.stage_of(row["status"])),
    )
