"""Changelog e comentários do Jira → transições de status e eventos do feed.

Funções puras: recebem o payload cru (ou a linha do espelho) e devolvem dicionários
prontos para o `activity_repo`. Quem busca no Jira é o `recorder`.

O changelog não traz a categoria do status — ela vem do mapa `category_of`, montado
a partir dos status que já existem no espelho.
"""

from datetime import datetime
from typing import Any

from services.sync.mappers import parse_dt

MAX_TITLE = 200

# Campo do changelog → kind do evento. A chave é o `field`/`fieldId` em minúsculas.
TRACKED_FIELDS = {
    "status": "status",
    "assignee": "assignee",
    "sprint": "sprint",
    "story points": "story_points",
    "priority": "priority",
}

NO_ASSIGNEE = "sem responsável"
NO_SPRINT = "fora de sprint"


def _short(value: str | None) -> str:
    value = (value or "").strip()
    return value if len(value) <= MAX_TITLE else value[: MAX_TITLE - 1] + "…"


def _field_kind(item: dict[str, Any]) -> str | None:
    for name in (item.get("field"), item.get("fieldId")):
        if name and (kind := TRACKED_FIELDS.get(str(name).lower())):
            return kind
    return None


def _title(kind: str, from_value: str | None, to_value: str | None) -> str:
    if kind == "status":
        return _short(to_value)
    if kind == "assignee":
        return _short(to_value) or NO_ASSIGNEE
    if kind == "sprint":
        return _short(to_value) or NO_SPRINT
    if kind == "story_points":
        return f"{from_value or '—'} → {to_value or '—'}"
    return _short(to_value) or "—"


def changelog_rows(
    issue_key: str,
    entries: list[dict[str, Any]],
    *,
    category_of: dict[str, str],
    my_account_id: str | None = None,
    since: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(transições, eventos) de um changelog. `since` corta o que é antigo demais."""
    transitions: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    for entry in entries:
        changed_at = parse_dt(entry.get("created"))
        if changed_at is None or (since is not None and changed_at < since):
            continue
        author = entry.get("author") or {}
        author_name = author.get("displayName")
        actor_is_me = bool(my_account_id) and author.get("accountId") == my_account_id
        entry_id = str(entry.get("id"))

        for item in entry.get("items") or []:
            kind = _field_kind(item)
            if kind is None:
                continue
            from_value = (item.get("fromString") or "").strip() or None
            to_value = (item.get("toString") or "").strip() or None
            if from_value == to_value:
                continue

            if kind == "status" and to_value:
                transitions.append(
                    {
                        "changelog_id": f"{entry_id}:status",
                        "issue_key": issue_key,
                        "from_status": from_value,
                        "to_status": to_value,
                        "from_category": category_of.get(from_value) if from_value else None,
                        "to_category": category_of.get(to_value),
                        "author_name": author_name,
                        "changed_at": changed_at,
                    }
                )

            events.append(
                {
                    "dedupe_key": f"jira:changelog:{entry_id}:{kind}",
                    "source": "jira",
                    "kind": kind,
                    "issue_key": issue_key,
                    "repo_slug": None,
                    "pr_id": None,
                    "actor_name": author_name,
                    "actor_is_me": actor_is_me,
                    "occurred_at": changed_at,
                    "title": _title(kind, from_value, to_value),
                    "detail": {"from": from_value, "to": to_value},
                }
            )

    return transitions, events


def comment_events(
    rows: list[dict[str, Any]],
    *,
    my_account_id: str | None = None,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Comentários do espelho → eventos. Só o trecho do corpo entra, nunca o texto inteiro."""
    events: list[dict[str, Any]] = []
    for row in rows:
        actor_is_me = bool(my_account_id) and row.get("author_account_id") == my_account_id
        body = _short(row.get("body_text"))
        created_at = row["created_at"]
        updated_at = row.get("updated_at")
        moments = [("created", created_at)]
        # O Jira preenche `updated` mesmo sem edição; só conta quando é depois da criação.
        if updated_at and created_at and updated_at > created_at:
            moments.append(("updated", updated_at))

        for kind, at in moments:
            if at is None or (since is not None and at < since):
                continue
            events.append(
                {
                    "dedupe_key": f"jira:comment:{row['id']}:{kind}",
                    "source": "jira",
                    "kind": "comment" if kind == "created" else "comment_edited",
                    "issue_key": row["issue_key"],
                    "repo_slug": None,
                    "pr_id": None,
                    "actor_name": row.get("author_name"),
                    "actor_is_me": actor_is_me,
                    "occurred_at": at,
                    "title": body,
                    "detail": {"comment_id": str(row["id"])},
                }
            )
    return events
