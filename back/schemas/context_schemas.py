import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.note_schemas import LinkedIssueOut, normalize_tags
from schemas.pr_status_schemas import ISSUE_KEY_PATTERN

ContextKind = Literal["finding", "fix", "decision", "open_point", "summary"]
ContextStatus = Literal["open", "resolved"]
RelationKind = Literal["relates", "continues"]

_KEY = re.compile(ISSUE_KEY_PATTERN)
MAX_RELATIONS = 30


def normalize_key(value: str) -> str:
    key = value.strip().upper()
    if not _KEY.match(key):
        raise ValueError(f"Chave de tarefa inválida: {value!r}")
    return key


class RelationIn(BaseModel):
    issue_key: str
    relation: RelationKind = "relates"

    @field_validator("issue_key")
    @classmethod
    def _key(cls, value: str) -> str:
        return normalize_key(value)


def _normalize_relations(value: list[RelationIn]) -> list[RelationIn]:
    seen: dict[str, RelationIn] = {}
    for item in value:
        # A mesma tarefa duas vezes: "continua" é mais específico que "relaciona".
        if item.issue_key not in seen or item.relation == "continues":
            seen[item.issue_key] = item
    if len(seen) > MAX_RELATIONS:
        raise ValueError(f"No máximo {MAX_RELATIONS} tarefas relacionadas por contexto.")
    return list(seen.values())


class ContextCreate(BaseModel):
    issue_key: str
    kind: ContextKind
    title: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=20_000)
    tags: list[str] = Field(default_factory=list)
    relations: list[RelationIn] = Field(default_factory=list)

    @field_validator("issue_key")
    @classmethod
    def _key(cls, value: str) -> str:
        return normalize_key(value)

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: list[str]) -> list[str]:
        return normalize_tags(value, owner="contexto")

    @field_validator("relations")
    @classmethod
    def _relations(cls, value: list[RelationIn]) -> list[RelationIn]:
        return _normalize_relations(value)

    @model_validator(mode="after")
    def _consistent(self):
        self.title = self.title.strip()
        if not self.title and not self.body.strip():
            raise ValueError("Escreva um título ou um texto para o contexto.")
        # Relacionar a tarefa com ela mesma não acrescenta nada.
        self.relations = [r for r in self.relations if r.issue_key != self.issue_key]
        return self


class ContextUpdate(BaseModel):
    """Atualização parcial: só os campos enviados mudam."""

    issue_key: str | None = None
    kind: ContextKind | None = None
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=20_000)
    tags: list[str] | None = None
    relations: list[RelationIn] | None = None

    @field_validator("issue_key")
    @classmethod
    def _key(cls, value: str | None) -> str | None:
        return None if value is None else normalize_key(value)

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else normalize_tags(value, owner="contexto")

    @field_validator("relations")
    @classmethod
    def _relations(cls, value: list[RelationIn] | None) -> list[RelationIn] | None:
        return None if value is None else _normalize_relations(value)


class ResolveIn(BaseModel):
    issue_key: str
    resolution: str = Field(default="", max_length=5_000)

    @field_validator("issue_key")
    @classmethod
    def _key(cls, value: str) -> str:
        return normalize_key(value)


class RelationOut(LinkedIssueOut):
    relation: Literal["relates", "continues", "resolves"]


class ContextOut(BaseModel):
    id: int
    issue: LinkedIssueOut
    kind: ContextKind
    title: str
    body: str
    tags: list[str]
    status: ContextStatus
    resolved_in: LinkedIssueOut | None
    resolution: str
    resolved_at: datetime | None
    source: Literal["manual", "ai_approved"]
    created_at: datetime
    updated_at: datetime
    relations: list[RelationOut]
    rank: float | None = None


class ContextListOut(BaseModel):
    items: list[ContextOut]
    total: int


class IssueContextsOut(BaseModel):
    """Aba Contextos do painel da tarefa."""

    own: list[ContextOut]
    # Contextos de outras tarefas que citam esta (relação) ou foram resolvidos nela.
    linked: list[ContextOut]
    # Pontos em aberto de tarefas vizinhas (mesmo pai, pai/filhas, links do Jira).
    nearby_open: list[ContextOut]


class ContextCountsOut(BaseModel):
    open_points: int
    by_kind: dict[str, int]
