"""Escopo da sincronização: o que entra no espelho local.

Padrão combinado com o Matheus (2026-09-14): board Engenharia (144) do WAI, sprints
da squad Growth + "baldes" sem squad, e **só o que é meu** (tarefas em que sou o
Responsável; PRs em que sou autor/revisor ou vinculados a tarefas minhas).
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# "mine": só o que é do dev conectado · "all": tudo que casar com o resto do escopo.
OwnershipScope = Literal["mine", "all"]


class JiraScope(BaseModel):
    board_ids: list[int] = Field(default_factory=lambda: [144])
    # Vazio = todas as squads. Comparação sem diferenciar maiúsculas.
    squads: list[str] = Field(default_factory=lambda: ["Growth"])
    include_unsquadded: bool = True
    # Quantas sprints fechadas (as mais recentes) têm as tarefas espelhadas.
    closed_sprints_limit: int = Field(default=6, ge=0, le=100)
    # Tarefas atribuídas a mim fora das sprints (visão Semana).
    my_issues_lookback_days: int = Field(default=30, ge=1, le=365)
    project_keys: list[str] = Field(default_factory=lambda: ["WAI"])
    # "mine": só tarefas com o dev como Responsável (+ pais delas, para a árvore).
    assignee_scope: OwnershipScope = "mine"

    @field_validator("project_keys")
    @classmethod
    def _upper(cls, value: list[str]) -> list[str]:
        return sorted({v.strip().upper() for v in value if v.strip()})


class BitbucketScope(BaseModel):
    # Escolhidos pelo dev na configuração (agrupados por projeto do Bitbucket).
    # Vazio = Bitbucket não sincroniza.
    repo_slugs: list[str] = Field(default_factory=list)
    # Na primeira carga de um repositório, PRs/branches até esta idade.
    initial_lookback_days: int = Field(default=60, ge=1, le=365)
    # Repositório sem push desde o último ciclo só é reconsultado neste intervalo
    # (aprovações e pedidos de ajuste não mudam o `updated_on` do repositório).
    full_sweep_minutes: int = Field(default=30, ge=5, le=1440)
    # "mine": PRs em que o dev é autor ou participante, ou ligados a tarefas dele.
    pr_scope: OwnershipScope = "mine"

    @field_validator("repo_slugs")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        return sorted({v.strip().lower() for v in value if v.strip()})


class SyncScope(BaseModel):
    enabled: bool = True
    interval_minutes: int = Field(default=5, ge=1, le=240)
    jira: JiraScope = Field(default_factory=JiraScope)
    bitbucket: BitbucketScope = Field(default_factory=BitbucketScope)


def sprint_in_scope(*, board_id: int | None, squad: str | None, scope: JiraScope) -> bool:
    if board_id not in scope.board_ids:
        return False
    if squad is None:
        return scope.include_unsquadded
    if not scope.squads:
        return True
    return squad.casefold() in {s.casefold() for s in scope.squads}
