"""Linha do tempo de um Pull Request: comentários do espelho + eventos já gravados.

Duas fontes porque cada uma sabe de metade da história. `bb_pr_comment` guarda o
texto da review; `activity_event` guarda o que não é texto (abriu, subiu commit,
aprovou, pediu ajustes, build, mergeou) — o mesmo diff que alimenta o feed da Home.

Funções puras: quem lê o banco é `pr_timeline_service`.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

# O evento `pr_comment` existe para o feed da Home. Aqui ele seria a segunda cópia
# do mesmo comentário, e a pior das duas: o feed guarda só um trecho do corpo.
EVENT_KINDS_FROM_COMMENTS = {"pr_comment"}

CHANGES_REQUESTED = "pr_changes_requested"
COMMIT = "pr_commit"


@dataclass
class TimelineEntry:
    kind: str
    at: datetime
    actor_name: str | None = None
    actor_is_me: bool = False
    body: str | None = None
    comment_id: int | None = None
    parent_id: int | None = None
    inline_path: str | None = None
    inline_from: int | None = None
    inline_to: int | None = None
    is_deleted: bool = False
    commit: str | None = None
    build: str | None = None
    # Commit que entrou depois do último pedido de ajuste — é a "correção enviada".
    after_changes_requested: bool = False


def _comment_entry(row: dict[str, Any], mine: set[str]) -> TimelineEntry:
    account_id = row.get("author_account_id")
    return TimelineEntry(
        kind="comment",
        at=row["created_on"],
        actor_name=row.get("author_name"),
        actor_is_me=bool(account_id) and account_id in mine,
        body=row.get("body_text") or "",
        comment_id=row["id"],
        parent_id=row.get("parent_id"),
        inline_path=row.get("inline_path"),
        inline_from=row.get("inline_from"),
        inline_to=row.get("inline_to"),
        is_deleted=bool(row.get("is_deleted")),
    )


def _event_entry(row: dict[str, Any]) -> TimelineEntry:
    detail = row.get("detail") or {}
    return TimelineEntry(
        kind=row["kind"],
        at=row["occurred_at"],
        actor_name=row.get("actor_name"),
        actor_is_me=bool(row.get("actor_is_me")),
        commit=detail.get("commit"),
        build=detail.get("build"),
    )


def merge_timeline(
    comments: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    my_identities: set[str] | None = None,
) -> list[TimelineEntry]:
    """Do mais novo para o mais antigo — a última atualização primeiro.

    Mesma ordem do feed da Home e da aba Histórico: ao abrir a tarefa, a pergunta é
    "o que mudou agora no PR", e a resposta tem de estar na primeira linha, não depois
    de rolar a review inteira.

    A marcação de correção não depende dessa ordem: ela sai da data do último pedido
    de ajuste, calculada sobre o conjunto.
    """
    mine = my_identities or set()
    entries = [
        _comment_entry(row, mine)
        for row in comments
        # Sem data não há onde encaixar na linha; o Bitbucket sempre manda.
        if row.get("created_on") is not None
    ]
    entries += [_event_entry(row) for row in events if row["kind"] not in EVENT_KINDS_FROM_COMMENTS]
    entries.sort(key=lambda e: (e.at, e.kind), reverse=True)

    last_request = max(
        (e.at for e in entries if e.kind == CHANGES_REQUESTED),
        default=None,
    )
    if last_request is not None:
        for entry in entries:
            if entry.kind == COMMIT and entry.at >= last_request:
                entry.after_changes_requested = True
    return entries


def pending_review(entries: list[TimelineEntry]) -> bool:
    """Ajuste pedido e ainda sem commit depois dele — o PR está parado comigo."""
    last_request = max((e.at for e in entries if e.kind == CHANGES_REQUESTED), default=None)
    if last_request is None:
        return False
    return not any(e.kind == COMMIT and e.at >= last_request for e in entries)


def request_before_history(
    entries: list[TimelineEntry], participants: list[dict[str, Any]]
) -> bool:
    """Revisor ainda pedindo ajuste, mas sem o evento que diz **quando** ele pediu.

    Acontece com PR que já estava em "ajustes requisitados" quando o espelho começou a
    registrar eventos: o sync grava a transição, não o estado. Sem esse aviso a aba
    pareceria quebrada — o pedido está no topo do card e a linha do tempo não o mostra.
    """
    if any(e.kind == CHANGES_REQUESTED for e in entries):
        return False
    return any((p or {}).get("state") == "changes_requested" for p in participants or [])
