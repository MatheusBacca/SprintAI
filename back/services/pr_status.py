"""Status de PR de uma tarefa — funções puras, sem banco nem HTTP.

Por PR:
    MERGED → mergeada · DECLINED → recusada · SUPERSEDED → substituida
    OPEN + draft → rascunho
    OPEN + algum "changes requested" e ainda sem correção → ajustes_requisitados
    OPEN + algum "changes requested" com correção já enviada → pr_aberta
    OPEN + aprovações que a regra pede (`ApprovalRule`) → aprovada
    OPEN → pr_aberta

Por repositório (uma tarefa pode ter vários PRs no mesmo repo):
    PR aberto prevalece sobre mergeado; recusado/substituído só conta se for o
    único estado do repo. Branch com a chave e sem PR no repo → branch_sem_pr.

Agregado no card — o que pede atenção vence:
    sem_pr < branch_sem_pr < ajustes_requisitados < rascunho < pr_aberta < aprovada < mergeada
    Repositório só com PR recusado/substituído não puxa o agregado para baixo se
    outro repositório tem trabalho; branch antiga (último commit antes da última
    atividade de PR da tarefa) é sobra de merge e também não conta.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from utils.issue_keys import extract_issue_keys


class PrStatus(StrEnum):
    SEM_PR = "sem_pr"
    BRANCH_SEM_PR = "branch_sem_pr"
    AJUSTES_REQUISITADOS = "ajustes_requisitados"
    RASCUNHO = "rascunho"
    PR_ABERTA = "pr_aberta"
    APROVADA = "aprovada"
    MERGEADA = "mergeada"
    RECUSADA = "recusada"
    SUBSTITUIDA = "substituida"


LABELS: dict[PrStatus, str] = {
    PrStatus.SEM_PR: "Sem PR",
    PrStatus.BRANCH_SEM_PR: "Branch sem PR",
    PrStatus.AJUSTES_REQUISITADOS: "Ajustes requisitados",
    PrStatus.RASCUNHO: "Rascunho",
    PrStatus.PR_ABERTA: "PR aberta",
    PrStatus.APROVADA: "Aprovada",
    PrStatus.MERGEADA: "Mergeada",
    PrStatus.RECUSADA: "Recusada",
    PrStatus.SUBSTITUIDA: "Substituída",
}

# Menor = pede mais atenção.
ATTENTION_RANK: dict[PrStatus, int] = {
    PrStatus.SEM_PR: 0,
    PrStatus.BRANCH_SEM_PR: 1,
    PrStatus.AJUSTES_REQUISITADOS: 2,
    PrStatus.RASCUNHO: 3,
    PrStatus.PR_ABERTA: 4,
    PrStatus.APROVADA: 5,
    PrStatus.MERGEADA: 6,
}

CLOSED_WITHOUT_MERGE = {PrStatus.RECUSADA, PrStatus.SUBSTITUIDA}
FAILED_BUILDS = {"FAILED", "STOPPED"}


@dataclass(frozen=True)
class ApprovalRule:
    """Quanto dos revisores precisa aprovar para o PR contar como aprovado.

    `min_percent` 0 é a regra de antes da configuração — basta uma aprovação —; 50 é
    "pelo menos metade" e 100, "todos". Uma aprovação é o piso de qualquer regra: PR sem
    ninguém aprovando não está aprovado nem com 0%.
    """

    min_percent: int = 0

    @classmethod
    def from_setting(cls, value: Any) -> "ApprovalRule":
        """Sem configuração salva vale a regra de antes: nada muda sozinho no card."""
        percent = value.get("min_percent") if isinstance(value, dict) else None
        if isinstance(percent, int) and not isinstance(percent, bool) and 0 <= percent <= 100:
            return cls(min_percent=percent)
        return cls()

    def to_setting(self) -> dict[str, int]:
        return {"min_percent": self.min_percent}

    def required(self, reviewers: int) -> int:
        # Teto em inteiro: 50% de 3 revisores são 2 aprovações, não 1,5.
        return max(1, -(-reviewers * self.min_percent // 100))

    def approved(self, approvals: int, reviewers: int) -> bool:
        return approvals >= self.required(reviewers)


DEFAULT_RULE = ApprovalRule()


@dataclass(frozen=True)
class ReviewPerson:
    """Um revisor na review andando: a foto que o badge mostra no lugar da barra."""

    name: str | None
    # `approved`, `changes_requested` ou `pending`. Ajuste pedido com a correção já no ar é
    # `pending`: a vez é do revisor, como no status do PR.
    state: str
    account_id: str | None = None
    avatar_url: str | None = None


# A ordem das fotos é a da barra que elas substituem: quem aprovou, quem pediu ajuste, quem falta.
PERSON_ORDER = {"approved": 0, "changes_requested": 1, "pending": 2}


@dataclass(frozen=True)
class ReviewProgress:
    """Andamento da review de um PR aberto — o badge mostra as fotos e o "N/X"."""

    approvals: int
    reviewers: int
    # Pedidos de ajuste ainda sem correção: o amarelo da barra. Com a correção no ar a vez
    # é do revisor, e o pedaço dele volta a ser espera — o mesmo que o status já diz.
    changes_requested: int
    # Aprovações que a regra pede para o PR contar como aprovado.
    required: int
    people: tuple[ReviewPerson, ...] = ()


@dataclass(frozen=True)
class Reviewer:
    name: str | None
    role: str | None
    approved: bool
    state: str | None
    # `account_id` do Bitbucket (ou o `uuid`, sem ele): é por ele que a tela tira o reviewer.
    account_id: str | None = None
    # A foto do Bitbucket, para o painel da tarefa (só https; PR espelhado antes dela vem sem,
    # até a próxima varredura dos abertos).
    avatar_url: str | None = None


@dataclass
class PullRequestLink:
    repo_slug: str
    id: int
    title: str
    state: str
    status: PrStatus
    draft: bool
    source_branch: str | None
    destination_branch: str | None
    url: str | None
    updated_on: datetime | None
    approvals: int
    changes_requested: int
    reviewers: list[Reviewer]
    build_status: str | None
    comment_count: int | None
    # "branch": a chave está no nome da branch; "title": só citada no título.
    match: str
    # Ajuste pedido e correção já subida — o PR voltou para a fila do revisor.
    fix_pushed: bool = False
    review: ReviewProgress | None = None

    @property
    def build_failed(self) -> bool:
        return self.state == "OPEN" and self.build_status in FAILED_BUILDS


@dataclass
class BranchLink:
    repo_slug: str
    name: str
    target_date: datetime | None
    stale: bool = False


@dataclass
class RepoPrStatus:
    repo_slug: str
    status: PrStatus
    pull_requests: list[PullRequestLink] = field(default_factory=list)
    branches: list[BranchLink] = field(default_factory=list)
    review: ReviewProgress | None = None


@dataclass
class IssuePrSummary:
    issue_key: str
    status: PrStatus
    pr_count: int
    open_pr_count: int
    build_failed: bool
    repos: list[RepoPrStatus]
    last_activity: datetime | None
    # Do PR que decide o status — o mesmo que o badge abre primeiro.
    review: ReviewProgress | None = None

    @property
    def label(self) -> str:
        return LABELS[self.status]


# --- Por PR ---------------------------------------------------------------------------------


def fix_after_request(last_request: datetime | None, last_commit: datetime | None) -> bool:
    """Correção enviada: entrou commit depois do último pedido de ajuste.

    O Bitbucket não limpa o `changes_requested` do revisor quando a correção sobe — só
    ele limpa, aprovando ou pedindo outro ajuste. Quem diz que a correção veio é o
    histórico do espelho (`activity_event`), a mesma fonte da linha do tempo do PR.

    Sem o evento do pedido não dá para dizer que o commit responde a ele: é o PR que já
    estava em ajustes quando o espelho nasceu (o sync grava a transição, não o estado) e
    o status continua em "ajustes requisitados". Empate conta como correção, mesma regra
    de `pr_timeline.pending_review` — dentro de um ciclo de sync os dois eventos herdam o
    `updated_on` do PR e não há como ordená-los.
    """
    if last_request is None or last_commit is None:
        return False
    return last_commit >= last_request


def _is_reviewer(participant: dict[str, Any]) -> bool:
    """Revisor designado ou quem se manifestou — quem só comentou não entra na conta."""
    return (
        participant.get("role") == "REVIEWER"
        or bool(participant.get("approved"))
        or bool(participant.get("state"))
    )


def derive_pr_status(
    *,
    state: str,
    draft: bool,
    participants: list[dict[str, Any]],
    fix_pushed: bool = False,
    rule: ApprovalRule = DEFAULT_RULE,
) -> PrStatus:
    if state == "MERGED":
        return PrStatus.MERGEADA
    if state == "DECLINED":
        return PrStatus.RECUSADA
    if state == "SUPERSEDED":
        return PrStatus.SUBSTITUIDA
    if draft:
        return PrStatus.RASCUNHO
    if any(p.get("state") == "changes_requested" for p in participants):
        # Com a correção no ar a bola está com o revisor, não comigo — o card volta a
        # "PR aberta" e não a "aprovada", nem com a regra já batida pelos outros: quem
        # pediu o ajuste ainda não olhou a correção.
        return PrStatus.PR_ABERTA if fix_pushed else PrStatus.AJUSTES_REQUISITADOS
    approvals = sum(1 for p in participants if p.get("approved"))
    if rule.approved(approvals, sum(1 for p in participants if _is_reviewer(p))):
        return PrStatus.APROVADA
    return PrStatus.PR_ABERTA


def review_progress(
    *,
    state: str,
    draft: bool,
    participants: list[dict[str, Any]],
    fix_pushed: bool = False,
    rule: ApprovalRule = DEFAULT_RULE,
) -> ReviewProgress | None:
    """Só PR aberto, fora do rascunho e com alguém revisando tem review andando."""
    reviewers = [p for p in participants if _is_reviewer(p)]
    if state != "OPEN" or draft or not reviewers:
        return None
    changes = sum(1 for p in reviewers if p.get("state") == "changes_requested")
    people = sorted(
        (
            ReviewPerson(
                name=p.get("name"),
                state=_person_state(p, fix_pushed),
                account_id=p.get("account_id"),
                avatar_url=p.get("avatar_url"),
            )
            for p in reviewers
        ),
        key=lambda person: PERSON_ORDER[person.state],
    )
    return ReviewProgress(
        approvals=sum(1 for p in reviewers if p.get("approved")),
        reviewers=len(reviewers),
        changes_requested=0 if fix_pushed else changes,
        required=rule.required(len(reviewers)),
        people=tuple(people),
    )


def _person_state(participant: dict[str, Any], fix_pushed: bool) -> str:
    if participant.get("approved"):
        return "approved"
    if participant.get("state") == "changes_requested" and not fix_pushed:
        return "changes_requested"
    return "pending"


def pull_request_link(
    issue_key: str | None, row: dict[str, Any], rule: ApprovalRule = DEFAULT_RULE
) -> PullRequestLink:
    """`issue_key` só decide o `match` (chave na branch ou citada no título). Sem tarefa —
    o PR achado pela branch, na linha do tempo do Workspace —, o vínculo é a branch."""
    participants = row.get("participants") or []
    fix_pushed = fix_after_request(
        row.get("last_changes_requested_at"), row.get("last_commit_at")
    )
    branch_keys = (
        extract_issue_keys(row.get("source_branch"), project_keys=[issue_key.split("-", 1)[0]])
        if issue_key
        else []
    )
    pr_state = {
        "state": row["state"],
        "draft": bool(row.get("draft")),
        "participants": participants,
        "fix_pushed": fix_pushed,
        "rule": rule,
    }
    return PullRequestLink(
        repo_slug=row["repo_slug"],
        id=row["id"],
        title=row.get("title") or "",
        state=row["state"],
        status=derive_pr_status(**pr_state),
        draft=bool(row.get("draft")),
        source_branch=row.get("source_branch"),
        destination_branch=row.get("destination_branch"),
        url=row.get("url"),
        updated_on=row.get("updated_on"),
        approvals=sum(1 for p in participants if p.get("approved")),
        changes_requested=sum(1 for p in participants if p.get("state") == "changes_requested"),
        reviewers=[
            Reviewer(
                name=p.get("name"),
                role=p.get("role"),
                approved=bool(p.get("approved")),
                state=p.get("state"),
                account_id=p.get("account_id"),
                avatar_url=p.get("avatar_url"),
            )
            for p in participants
            if _is_reviewer(p)
        ],
        build_status=row.get("build_status"),
        comment_count=row.get("comment_count"),
        match="title" if issue_key and issue_key not in branch_keys else "branch",
        fix_pushed=fix_pushed,
        review=review_progress(**pr_state),
    )


# --- Por repositório ----------------------------------------------------------------------


def _most_attention(statuses: list[PrStatus]) -> PrStatus:
    return min(statuses, key=ATTENTION_RANK.__getitem__)


def _relevance(pr: PullRequestLink) -> tuple[int, float]:
    """Ordem de exibição: abertos primeiro (o que pede atenção antes), depois mergeados,
    depois fechados sem merge; dentro do grupo, o mais recente primeiro."""
    if pr.status in CLOSED_WITHOUT_MERGE:
        group = 9
    else:
        group = ATTENTION_RANK[pr.status] if pr.state == "OPEN" else 7
    recency = -(pr.updated_on.timestamp() if pr.updated_on else 0)
    return group, recency


def _deciding_review(
    items: list[PullRequestLink] | list[RepoPrStatus], status: PrStatus
) -> ReviewProgress | None:
    """A review de quem decide o status: o primeiro, na ordem de atenção, que está nele."""
    return next((item.review for item in items if item.status == status), None)


def repo_status(prs: list[PullRequestLink], branches: list[BranchLink]) -> PrStatus:
    if not prs:
        return PrStatus.BRANCH_SEM_PR if branches else PrStatus.SEM_PR
    open_statuses = [pr.status for pr in prs if pr.state == "OPEN"]
    if open_statuses:
        return _most_attention(open_statuses)
    if any(pr.status == PrStatus.MERGEADA for pr in prs):
        return PrStatus.MERGEADA
    if any(pr.status == PrStatus.RECUSADA for pr in prs):
        return PrStatus.RECUSADA
    return PrStatus.SUBSTITUIDA


# --- Agregado da tarefa --------------------------------------------------------------------


def summarize_issue(
    issue_key: str,
    pr_rows: list[dict[str, Any]],
    branch_rows: list[dict[str, Any]],
    rule: ApprovalRule = DEFAULT_RULE,
) -> IssuePrSummary:
    prs = [
        pull_request_link(issue_key, row, rule)
        for row in pr_rows
        if issue_key in row["issue_keys"]
    ]
    last_pr_activity = max((pr.updated_on for pr in prs if pr.updated_on), default=None)

    prs_by_repo: dict[str, list[PullRequestLink]] = defaultdict(list)
    for pr in prs:
        prs_by_repo[pr.repo_slug].append(pr)

    branches_by_repo: dict[str, list[BranchLink]] = defaultdict(list)
    for row in branch_rows:
        if issue_key not in row["issue_keys"] or prs_by_repo.get(row["repo_slug"]):
            continue  # branch de repo que já tem PR da tarefa é a própria branch do PR
        target = row.get("target_date")
        stale = bool(last_pr_activity and target and target <= last_pr_activity)
        branches_by_repo[row["repo_slug"]].append(
            BranchLink(
                repo_slug=row["repo_slug"], name=row["name"], target_date=target, stale=stale
            )
        )

    repos = []
    for slug in sorted(set(prs_by_repo) | set(branches_by_repo)):
        repo_prs = sorted(prs_by_repo.get(slug, []), key=_relevance)
        repo_branches = sorted(
            branches_by_repo.get(slug, []),
            key=lambda b: -(b.target_date.timestamp() if b.target_date else 0),
        )
        of_repo = repo_status(repo_prs, repo_branches)
        repos.append(
            RepoPrStatus(
                repo_slug=slug,
                status=of_repo,
                pull_requests=repo_prs,
                branches=repo_branches,
                review=_deciding_review(repo_prs, of_repo),
            )
        )

    status = aggregate_status(repos)
    repos = sorted(repos, key=lambda r: _repo_order(r.status))
    return IssuePrSummary(
        issue_key=issue_key,
        status=status,
        pr_count=len(prs),
        open_pr_count=sum(1 for pr in prs if pr.state == "OPEN"),
        build_failed=any(pr.build_failed for pr in prs),
        repos=repos,
        last_activity=max(
            [pr.updated_on for pr in prs if pr.updated_on]
            + [b.target_date for r in repos for b in r.branches if b.target_date],
            default=None,
        ),
        review=_deciding_review(repos, status),
    )


def _repo_order(status: PrStatus) -> int:
    return ATTENTION_RANK.get(status, 8)


def aggregate_status(repos: list[RepoPrStatus]) -> PrStatus:
    considered: list[PrStatus] = []
    for repo in repos:
        stale_only = bool(repo.branches) and all(b.stale for b in repo.branches)
        if repo.status == PrStatus.BRANCH_SEM_PR and stale_only:
            continue
        if repo.status in CLOSED_WITHOUT_MERGE:
            continue
        considered.append(repo.status)

    if considered:
        return _most_attention(considered)
    closed = [r.status for r in repos if r.status in CLOSED_WITHOUT_MERGE]
    if closed:
        return PrStatus.RECUSADA if PrStatus.RECUSADA in closed else PrStatus.SUBSTITUIDA
    return PrStatus.SEM_PR
