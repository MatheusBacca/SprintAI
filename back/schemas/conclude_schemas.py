from typing import Literal

from pydantic import BaseModel, Field

# Mesmo formato que o Bitbucket aceita no slug.
REPO_SLUG_PATTERN = r"^[a-zA-Z0-9][\w.-]{0,98}$"

MergeStrategy = Literal["merge_commit", "squash", "fast_forward"]


# --- Configurações › Fluxo de trabalho › Concluir ----------------------------------------------


class RepoConclusionIn(BaseModel):
    """A receita de um repo. Sem status e sem merge, o repo fica sem "Concluir"."""

    jira_status: str | None = Field(default=None, max_length=80)
    merge: bool = False
    strategy: MergeStrategy = "merge_commit"
    close_source_branch: bool = True


class ConcludeSettingsIn(BaseModel):
    repos: dict[str, RepoConclusionIn] = Field(default_factory=dict, max_length=200)


class ConcludeSettingsOut(BaseModel):
    repos: dict[str, RepoConclusionIn]
    # Os da Sincronização mais os que têm receita — sem eles, o que foi gravado ficaria sem ter
    # por onde tirar.
    known_repos: list[str]
    # Status vistos no espelho, para sugerir no campo (o mais usado primeiro).
    statuses: list[str]


# --- O plano e a execução ---------------------------------------------------------------------


class ConcludeMergeOut(BaseModel):
    repo_slug: str
    pr_id: int
    title: str
    url: str | None
    source_branch: str | None
    destination_branch: str | None
    strategy: MergeStrategy
    close_source_branch: bool
    # O que o dev deveria saber antes de confirmar: rascunho, aprovações, build, ajustes.
    # Só avisa — quem barra é o Bitbucket, pelas merge checks do repo.
    warnings: list[str]
    # PR em rascunho hoje: o "Liberar e concluir" o libera antes do merge.
    draft: bool = False


class ConcludeTargetOut(BaseModel):
    status: str
    # A tarefa já está nele: o passo do Jira não faz nada.
    current: bool
    available: bool
    # Por que não dá (o workflow não oferece, a transição pede campos).
    reason: str | None = None


class ConcludeWaitingOut(BaseModel):
    """PR aberto que este Concluir não mergeia — enquanto houver um, o Jira não anda."""

    repo_slug: str
    pr_id: int
    title: str
    url: str | None
    # "sem a aprovação da regra", "com ajustes pedidos", "aprovado, mas o repo não tem receita"…
    reason: str


class ConcludeDraftOut(BaseModel):
    """PR aberto da tarefa em rascunho: o painel oferece liberar (ou liberar e concluir)."""

    repo_slug: str
    pr_id: int
    title: str
    url: str | None
    approvals: int
    # Liberado agora, ele entra no merge deste Concluir (aprovado pela regra, repo que mergeia).
    merges: bool
    # Por que não entra: "sem a aprovação da regra", "com ajustes pedidos"…
    reason: str | None = None


class ConcludePlanOut(BaseModel):
    issue_key: str
    # Status atual, lido agora no Jira.
    status: str
    repos: list[str]
    merges: list[ConcludeMergeOut]
    # Nenhum: o Jira fica como está. Um: é ele. Dois ou mais (repos com receitas diferentes):
    # o dev escolhe.
    targets: list[ConcludeTargetOut]
    # Repo que mergeia sem PR aberto da tarefa, e afins.
    notes: list[str]
    # Tarefa com mais de um PR: os abertos que ficam para depois. Com algum, `targets` vem
    # vazio e o status de destino vai em `held_statuses` — o Jira anda no Concluir do último.
    waiting: list[ConcludeWaitingOut] = []
    held_statuses: list[str] = []
    # PRs em rascunho. Com algum, `merges`, `waiting`, `targets` e `blocked` são os do "Liberar
    # e concluir" — a conta feita com eles já liberados.
    drafts: list[ConcludeDraftOut] = []
    # Por que o card não está apto (PR sem a aprovação da regra, tarefa já em testes...). Com
    # ele, a execução recusa.
    blocked: str | None = None


class ConcludeMergeRef(BaseModel):
    repo_slug: str = Field(pattern=REPO_SLUG_PATTERN)
    pr_id: int = Field(ge=1)


class ConcludeIn(BaseModel):
    """O que o dev confirmou no plano. O back confere contra o plano de agora antes de rodar."""

    jira_status: str | None = Field(default=None, max_length=80)
    merges: list[ConcludeMergeRef] = Field(default_factory=list, max_length=10)
    # Rascunhos liberados antes dos merges ("Liberar e concluir"). Com rascunho no plano, são
    # todos eles: PR em rascunho o Bitbucket não mergeia.
    release: list[ConcludeMergeRef] = Field(default_factory=list, max_length=10)


class ConcludeDraftIn(BaseModel):
    """Pôr em rascunho (`draft` verdadeiro) ou liberar PRs abertos da tarefa."""

    draft: bool
    prs: list[ConcludeMergeRef] = Field(min_length=1, max_length=10)


class ConcludeStepOut(BaseModel):
    # `hold`: o Jira ficou onde estava porque ainda há PR aberto da tarefa. `draft` e
    # `release`: o PR foi para o rascunho ou saiu dele.
    kind: Literal["merge", "transition", "hold", "draft", "release"]
    label: str
    ok: bool
    message: str | None = None
    url: str | None = None


class ConcludeResultOut(BaseModel):
    issue_key: str
    # Todos os passos deram certo. Falhou um merge: o resto não roda.
    done: bool
    steps: list[ConcludeStepOut]
    status: str | None = None
    # Para a tela desempatar a recarga com o `issue.changed` do stream.
    write_id: str | None = None


# --- Reviewers --------------------------------------------------------------------------------


class BitbucketMemberOut(BaseModel):
    account_id: str | None
    uuid: str | None
    name: str
    nickname: str | None = None
    is_me: bool = False


class BitbucketMembersOut(BaseModel):
    members: list[BitbucketMemberOut]


class ReviewersIn(BaseModel):
    """Ids de quem entra e de quem sai (`account_id` ou `uuid`, o que a tela tiver)."""

    add: list[str] = Field(default_factory=list, max_length=20)
    remove: list[str] = Field(default_factory=list, max_length=20)


class PrReviewerOut(BaseModel):
    account_id: str | None
    uuid: str | None
    name: str | None
    approved: bool
    state: str | None
    avatar_url: str | None = None


class PrReviewersOut(BaseModel):
    repo_slug: str
    pr_id: int
    reviewers: list[PrReviewerOut]
