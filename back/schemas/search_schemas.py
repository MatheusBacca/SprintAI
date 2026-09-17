from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

SearchType = Literal["issue", "comment", "pull_request", "context", "note"]
SearchPeriod = Literal["any", "7d", "30d", "90d", "365d"]

# Ordem dos grupos na tela: tarefas, comentários, PRs, contextos, lembretes.
SEARCH_TYPES: tuple[str, ...] = ("issue", "comment", "pull_request", "context", "note")


class SearchHitOut(BaseModel):
    type: SearchType
    id: str
    title: str
    snippet: str
    issue_key: str | None
    issue_keys: list[str]
    issue_summary: str | None
    issue_in_mirror: bool
    issue_url: str | None
    # Por tipo: status/tipo da tarefa, autor do comentário, repo/estado/url do PR,
    # tipo/status do contexto, cor do lembrete.
    meta: dict[str, Any]
    occurred_at: datetime | None
    rank: float


class SearchGroupOut(BaseModel):
    type: SearchType
    total: int
    items: list[SearchHitOut]


class SearchOut(BaseModel):
    query: str
    total: int
    groups: list[SearchGroupOut]
