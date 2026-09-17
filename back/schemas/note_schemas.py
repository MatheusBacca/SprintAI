import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.pr_status_schemas import ISSUE_KEY_PATTERN

NoteColor = Literal["yellow", "pink", "green", "blue", "purple", "gray"]
DueFilter = Literal["any", "upcoming", "overdue", "none"]

_KEY = re.compile(ISSUE_KEY_PATTERN)
MAX_TAGS = 15
MAX_ISSUES = 30
MAX_REPOS = 15
# Slug do Bitbucket: minúsculas, dígitos, ponto, hífen e sublinhado.
_REPO = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")


def normalize_tags(value: list[str], owner: str = "lembrete") -> list[str]:
    tags: list[str] = []
    for raw in value:
        tag = re.sub(r"\s+", "-", raw.strip().lower().lstrip("#"))[:40]
        if tag and tag not in tags:
            tags.append(tag)
    if len(tags) > MAX_TAGS:
        raise ValueError(f"No máximo {MAX_TAGS} tags por {owner}.")
    return tags


def normalize_keys(value: list[str], owner: str = "lembrete") -> list[str]:
    keys: list[str] = []
    for raw in value:
        key = raw.strip().upper()
        if not _KEY.match(key):
            raise ValueError(f"Chave de tarefa inválida: {raw!r}")
        if key not in keys:
            keys.append(key)
    if len(keys) > MAX_ISSUES:
        raise ValueError(f"No máximo {MAX_ISSUES} tarefas por {owner}.")
    return keys


def normalize_repos(value: list[str], owner: str = "lembrete") -> list[str]:
    repos: list[str] = []
    for raw in value:
        repo = raw.strip().lower().lstrip("@")
        if not _REPO.match(repo):
            raise ValueError(f"Repositório inválido: {raw!r}")
        if repo not in repos:
            repos.append(repo)
    if len(repos) > MAX_REPOS:
        raise ValueError(f"No máximo {MAX_REPOS} repositórios por {owner}.")
    return repos


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError("Informe o horário do lembrete com fuso (ex.: 2026-09-15T09:00:00-03:00).")
    return value


class NoteCreate(BaseModel):
    title: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=20_000)
    color: NoteColor = "yellow"
    tags: list[str] = Field(default_factory=list)
    repos: list[str] = Field(default_factory=list)
    pinned: bool = False
    remind_at: datetime | None = None
    issue_keys: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: list[str]) -> list[str]:
        return normalize_tags(value)

    @field_validator("repos")
    @classmethod
    def _repos(cls, value: list[str]) -> list[str]:
        return normalize_repos(value)

    @field_validator("issue_keys")
    @classmethod
    def _keys(cls, value: list[str]) -> list[str]:
        return normalize_keys(value)

    @field_validator("remind_at")
    @classmethod
    def _remind(cls, value: datetime | None) -> datetime | None:
        return _aware(value)

    @model_validator(mode="after")
    def _not_empty(self):
        self.title = self.title.strip()
        if not self.title and not self.body.strip():
            raise ValueError("Escreva um título ou um texto para o lembrete.")
        return self


class NoteUpdate(BaseModel):
    """Atualização parcial: só os campos enviados mudam."""

    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=20_000)
    color: NoteColor | None = None
    tags: list[str] | None = None
    repos: list[str] | None = None
    pinned: bool | None = None
    archived: bool | None = None
    remind_at: datetime | None = None
    issue_keys: list[str] | None = None

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else normalize_tags(value)

    @field_validator("repos")
    @classmethod
    def _repos(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else normalize_repos(value)

    @field_validator("issue_keys")
    @classmethod
    def _keys(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else normalize_keys(value)

    @field_validator("remind_at")
    @classmethod
    def _remind(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class LinkedIssueOut(BaseModel):
    key: str
    summary: str | None = None
    status: str | None = None
    status_category: str | None = None
    in_mirror: bool = False
    url: str | None = None


class NoteOut(BaseModel):
    id: int
    title: str
    body: str
    color: NoteColor
    tags: list[str]
    repos: list[str] = []
    pinned: bool
    archived: bool
    remind_at: datetime | None
    reminded_at: datetime | None
    reminder_due: bool
    created_at: datetime
    updated_at: datetime
    issues: list[LinkedIssueOut]
    rank: float | None = None


class NoteListOut(BaseModel):
    items: list[NoteOut]
    total: int


class TagCountOut(BaseModel):
    tag: str
    count: int


class SnoozeIn(BaseModel):
    minutes: int = Field(default=10, ge=1, le=7 * 24 * 60)
