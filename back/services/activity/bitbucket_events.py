"""Diff de um Pull Request entre dois ciclos de sync → eventos do feed.

O espelho sobrescreve o PR a cada ciclo, então a comparação tem de acontecer **antes**
do upsert: é a linha anterior (`previous`) contra a recém-baixada (`current`).

Função pura. A primeira carga de um repositório não chama isto (`baseline`), senão o
feed nasceria com todo o histórico de PRs de uma vez.
"""

from datetime import datetime
from typing import Any

from services.pr_status import FAILED_BUILDS

PASSED_BUILDS = {"SUCCESSFUL"}
FINAL_STATES = {"MERGED": "pr_merged", "DECLINED": "pr_declined", "SUPERSEDED": "pr_superseded"}
MAX_TITLE = 160


def _short(value: str | None) -> str:
    value = (value or "").strip()
    return value if len(value) <= MAX_TITLE else value[: MAX_TITLE - 1] + "…"


def _by_account(participants: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {p["account_id"]: p for p in participants or [] if p.get("account_id")}


def pull_request_events(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    *,
    my_identities: set[str] | None = None,
    now: datetime,
) -> list[dict[str, Any]]:
    repo, pr_id = current["repo_slug"], current["id"]
    mine = my_identities or set()
    occurred_at = current.get("updated_on") or now
    issue_keys = current.get("issue_keys") or []
    events: list[dict[str, Any]] = []

    def add(
        kind: str,
        dedupe_suffix: str,
        *,
        at: datetime,
        actor_name: str | None = None,
        actor_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        events.append(
            {
                "dedupe_key": f"bb:pr:{repo}:{pr_id}:{dedupe_suffix}",
                "source": "bitbucket",
                "kind": kind,
                "issue_key": issue_keys[0] if issue_keys else None,
                "repo_slug": repo,
                "pr_id": pr_id,
                "actor_name": actor_name,
                "actor_is_me": bool(actor_id) and actor_id in mine,
                "occurred_at": at,
                "title": current.get("title") or "",
                "detail": {
                    "url": current.get("url"),
                    "source_branch": current.get("source_branch"),
                    "issue_keys": issue_keys,
                    **(detail or {}),
                },
            }
        )

    author_name = current.get("author_name")
    author_id = current.get("author_account_id")

    if previous is None:
        add(
            "pr_created",
            "created:1",
            at=current.get("created_on") or occurred_at,
            actor_name=author_name,
            actor_id=author_id,
            detail={"draft": current.get("draft", False)},
        )
    else:
        if previous.get("draft") and not current.get("draft"):
            add("pr_ready", "ready:1", at=occurred_at, actor_name=author_name, actor_id=author_id)

        commit = current.get("source_commit")
        if commit and commit != previous.get("source_commit"):
            add(
                "pr_commit",
                f"commit:{commit}",
                at=occurred_at,
                actor_name=author_name,
                actor_id=author_id,
                detail={"commit": commit},
            )

    before = _by_account(previous.get("participants") if previous else [])
    for account_id, participant in _by_account(current.get("participants")).items():
        was = before.get(account_id) or {}
        name = participant.get("name")
        if participant.get("approved") and not was.get("approved"):
            add(
                "pr_approved",
                f"approved:{account_id}",
                at=occurred_at,
                actor_name=name,
                actor_id=account_id,
            )
        if (
            participant.get("state") == "changes_requested"
            and was.get("state") != "changes_requested"
        ):
            add(
                "pr_changes_requested",
                f"changes_requested:{account_id}",
                at=occurred_at,
                actor_name=name,
                actor_id=account_id,
            )

    # `build_status` nulo é "não conferido neste ciclo" (o upsert preserva o anterior).
    build = current.get("build_status")
    if build and build != (previous or {}).get("build_status"):
        commit = current.get("source_commit") or "?"
        kind = "pr_build_failed" if build in FAILED_BUILDS else "pr_build_passed"
        if build in FAILED_BUILDS or build in PASSED_BUILDS:
            add(kind, f"build:{build}@{commit}", at=occurred_at, detail={"build": build})

    state = current.get("state")
    if state in FINAL_STATES and state != (previous or {}).get("state"):
        add(FINAL_STATES[state], f"state:{state}", at=occurred_at, detail={"state": state})

    return events


def pull_request_comment_events(
    pull_request: dict[str, Any],
    comments: list[dict[str, Any]],
    known_ids: set[int],
    *,
    my_identities: set[str] | None = None,
    now: datetime,
) -> list[dict[str, Any]]:
    """Um evento por comentário **novo** de um PR.

    `known_ids` é o que já estava espelhado antes deste ciclo. Sem ele, reindexar um
    PR antigo despejaria a review inteira no feed de uma vez — o mesmo motivo pelo
    qual a primeira carga de um repositório não gera evento.
    """
    repo, pr_id = pull_request["repo_slug"], pull_request["id"]
    mine = my_identities or set()
    issue_keys = pull_request.get("issue_keys") or []
    events: list[dict[str, Any]] = []

    for comment in comments:
        if comment["id"] in known_ids or comment.get("is_deleted"):
            continue
        account_id = comment.get("author_account_id")
        events.append(
            {
                "dedupe_key": f"bb:pr:{repo}:{pr_id}:comment:{comment['id']}",
                "source": "bitbucket",
                "kind": "pr_comment",
                "issue_key": issue_keys[0] if issue_keys else None,
                "repo_slug": repo,
                "pr_id": pr_id,
                "actor_name": comment.get("author_name"),
                "actor_is_me": bool(account_id) and account_id in mine,
                "occurred_at": comment.get("created_on") or now,
                "title": _short(comment.get("body_text")),
                "detail": {
                    "url": pull_request.get("url"),
                    "source_branch": pull_request.get("source_branch"),
                    "issue_keys": issue_keys,
                    "comment_id": comment["id"],
                    "inline_path": comment.get("inline_path"),
                },
            }
        )
    return events
