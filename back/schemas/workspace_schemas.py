import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.pr_status_schemas import PrLinkOut
from schemas.sprint_schemas import TreeEdgeOut, TreeGroupOut, TreeNodeOut
from services.pr_status import PrStatus

# Slug de repositório do Bitbucket (`organia-configs`, `weaction-api`).
REPO_SLUG_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$"

_REF_CHARS = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


def safe_ref_name(value: str) -> str:
    """Subconjunto seguro de nome de ref do git. Nada começa com `-` (viraria opção na linha
    de comando) e nada de `..` (viraria intervalo de commits). O regex do pydantic não tem
    look-ahead, por isso a regra mora aqui."""
    if (
        not _REF_CHARS.match(value)
        or value.startswith(("-", "/", "."))
        or value.endswith(("/", ".", ".lock"))
        or ".." in value
        or "//" in value
    ):
        raise ValueError("Nome de branch inválido.")
    return value


RepoLink = Literal["auto", "manual", "none"]
BaseSource = Literal["manual", "bitbucket", "origin", "local"]


class WorkspaceRepoOut(BaseModel):
    slug: str
    path: str
    present: bool
    has_git: bool
    remote_url: str | None
    bb_slug: str | None = Field(description="Repo do Bitbucket ligado à pasta (efetivo)")
    link: RepoLink
    in_mirror: bool = Field(description="O repo ligado está no espelho (Sincronização)")
    base_branch: str | None
    base_source: BaseSource | None
    current_branch: str | None
    detached: bool
    detected_at: datetime


class WorkspaceReposOut(BaseModel):
    root: str
    repos: list[WorkspaceRepoOut]


class WorkspaceRepoUpdate(BaseModel):
    """Ajuste do dev. `link`: `auto` segue o remote, `none` desliga o vínculo e `manual` usa o
    `bb_slug` informado. `base_branch` nulo volta ao automático."""

    link: RepoLink = "auto"
    bb_slug: str | None = Field(default=None, pattern=REPO_SLUG_PATTERN)
    base_branch: str | None = None

    @field_validator("base_branch")
    @classmethod
    def _branch_segura(cls, value: str | None) -> str | None:
        return None if value is None else safe_ref_name(value)

    @model_validator(mode="after")
    def _manual_precisa_de_slug(self):
        if self.link == "manual" and not self.bb_slug:
            raise ValueError("Vínculo manual precisa do repositório do Bitbucket.")
        return self


# --- Linha do tempo das branches (B15) -------------------------------------------------------

GraphScope = Literal["feature", "all"]
RefKind = Literal["local", "remote", "tag"]


class GraphRefOut(BaseModel):
    name: str = Field(description="Nome curto: `WAI-8790-x`, `origin/WAI-8790-x`, `v1.42`")
    kind: RefKind
    target: str
    upstream: str | None
    ahead: int
    behind: int
    gone: bool = Field(description="O upstream foi apagado no remoto")
    worktree: str | None = Field(description="Worktree que está com a branch aberta")
    is_head: bool = Field(description="Branch aberta no clone principal")
    is_base: bool
    in_feature: bool
    issue_keys: list[str]
    pull_requests: list[PrLinkOut]
    committed_at: datetime | None = None
    subject: str | None = None


class WorktreeChangesOut(BaseModel):
    changed: int
    untracked: int
    conflicted: int


class GraphWorktreeOut(BaseModel):
    path: str
    head: str | None
    branch: str | None
    detached: bool
    is_main: bool
    locked: bool
    prunable: bool
    outside_roots: bool = Field(description="Fora das raízes do dev (ex.: pasta temp do Claude)")
    changes: WorktreeChangesOut | None = Field(
        description="Nulo quando não é lido: fora das raízes, sumida ou com erro"
    )


class GraphCommitOut(BaseModel):
    sha: str
    parents: list[str]
    author: str
    authored_at: datetime | None
    committed_at: datetime | None
    subject: str
    issue_keys: list[str]
    # "Só da feature": o commit é o ponto da base em que a feature se apoia, não dela — a
    # tela desenha sem as linhas para os pais.
    boundary: bool = False


class IssuePrStatusOut(BaseModel):
    """Status de PR da tarefa — a mesma conta do selo do card. A chave `WAI-XXXX` de um commit
    ou branch ganha a cor dele."""

    status: PrStatus
    status_label: str


class RepoGraphOut(BaseModel):
    repo: str
    path: str
    base_branch: str | None
    scope: GraphScope
    keys: list[str]
    fingerprint: str
    fetched_at: datetime | None = Field(description="Último `git fetch` (mtime do FETCH_HEAD)")
    # Com `since` igual à impressão atual, só as worktrees voltam — refs e commits não mudaram.
    unchanged: bool = False
    refs: list[GraphRefOut] = []
    worktrees: list[GraphWorktreeOut] = []
    commits: list[GraphCommitOut] = []
    skip: int = 0
    limit: int = 0
    has_more: bool = False
    issue_status: dict[str, IssuePrStatusOut] = {}


class RepoRefsOut(BaseModel):
    """Todas as branches (locais e `origin/`) e tags do repo — o painel de branches."""

    repo: str
    base_branch: str | None
    fetched_at: datetime | None
    refs: list[GraphRefOut]
    issue_status: dict[str, IssuePrStatusOut] = {}


class CommitSearchOut(BaseModel):
    query: str
    commits: list[GraphCommitOut]
    issue_status: dict[str, IssuePrStatusOut] = {}


class FetchResultOut(BaseModel):
    added: list[str]
    updated: list[str]
    pruned: list[str]
    tags: list[str]
    fetched_at: datetime | None


class BranchActionIn(BaseModel):
    name: str
    # Só no apagar: `-D` em vez de `-d`. A tela manda só depois da segunda confirmação.
    force: bool = False

    @field_validator("name")
    @classmethod
    def _branch_segura(cls, value: str) -> str:
        return safe_ref_name(value)


class BranchUpdateOut(BaseModel):
    name: str
    before: str
    after: str
    mode: Literal["worktree", "ref", "noop"]


class BranchDeleteOut(BaseModel):
    name: str
    # Para onde a branch apontava: `git branch <nome> <hash>` desfaz.
    target: str


class CommitFileOut(BaseModel):
    path: str
    added: int | None = Field(description="Nulo em arquivo binário")
    deleted: int | None


class CommitDetailOut(BaseModel):
    sha: str
    parents: list[str]
    author: str
    authored_at: datetime | None
    committer: str
    committed_at: datetime | None
    # Mensagem crua do commit — a tela mostra como texto, nunca como HTML.
    message: str
    issue_keys: list[str]
    files: list[CommitFileOut]
    files_truncated: bool


# --- Workspace (B16) ---------------------------------------------------------------------------

WorkspaceKind = Literal["issue", "free"]
RepoSource = Literal["branch", "pr", "title", "pin"]
PinMode = Literal["add", "hide", "auto"]


class WorkspaceOut(BaseModel):
    id: int
    kind: WorkspaceKind
    root_issue_key: str | None
    # Do espelho quando a tarefa está lá (o título do Jira muda); senão, o gravado ao abrir.
    title: str
    issue_type: str | None
    status: str | None
    is_open: bool
    tab_order: int
    created_at: datetime
    last_opened_at: datetime


class WorkspaceCreate(BaseModel):
    """De tarefa (`root_issue_key`) ou livre (`title`). Abrir de novo a mesma tarefa reabre o
    workspace dela."""

    root_issue_key: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9]{1,9}-\d{1,7}$")
    title: str | None = Field(default=None, min_length=1, max_length=120)
    repos: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def _tarefa_ou_titulo(self):
        if not self.root_issue_key and not self.title:
            raise ValueError("Informe a tarefa ou o nome do workspace livre.")
        if self.root_issue_key:
            self.root_issue_key = self.root_issue_key.upper()
        return self


class WorkspaceUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    is_open: bool | None = None
    tab_order: int | None = Field(default=None, ge=0, le=1000)


class InvolvedRepoOut(BaseModel):
    slug: str
    path: str | None = Field(description="Nulo quando o repo não tem clone local")
    local: bool
    bb_slug: str | None
    base_branch: str | None
    current_branch: str | None
    sources: list[RepoSource] = Field(
        description="De onde veio: branch local com a chave, PR/branch do espelho, colchete "
        "do título ou fixado pelo dev"
    )
    branches: list[str]
    issue_keys: list[str]
    hidden: bool


class WorkspaceDetailOut(BaseModel):
    workspace: WorkspaceOut
    keys: list[str]
    repos: list[InvolvedRepoOut]


class RepoPinIn(BaseModel):
    mode: PinMode


class TreeFrameOut(BaseModel):
    id: str
    label: str


class WorkspaceOpenIn(BaseModel):
    target: Literal["ide", "terminal"]
    path: str = Field(min_length=3, max_length=400)


class WorkspaceTreeOut(BaseModel):
    """Mesmo formato do `SprintTreeOut` para o canvas: `in_sprint` vale "dentro da moldura"
    (o conjunto da feature) e o pai que só dá contexto vem com `in_sprint = false`."""

    workspace_id: int
    frame: TreeFrameOut
    counters: dict[str, int]
    nodes: list[TreeNodeOut]
    edges: list[TreeEdgeOut]
    groups: list[TreeGroupOut]
