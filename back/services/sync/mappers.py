"""Payloads crus do Jira/Bitbucket → linhas do espelho."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from services.discovery_service import squad_from_sprint_name
from utils.adf import adf_to_text
from utils.issue_keys import extract_issue_keys


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    # Jira manda "2026-09-10T10:00:00.000-0300"; fromisoformat aceita a partir do 3.11.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@dataclass
class IssueRows:
    issue: dict[str, Any]
    sprints: list[dict[str, Any]] = field(default_factory=list)
    links: list[dict[str, Any]] = field(default_factory=list)
    comments: list[dict[str, Any]] = field(default_factory=list)
    comments_complete: bool = True


def sprint_row(raw: dict[str, Any], *, board_id: int | None = None) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "board_id": raw.get("originBoardId") or raw.get("boardId") or board_id,
        "name": raw["name"],
        "state": raw["state"],
        "squad": squad_from_sprint_name(raw["name"]),
        "goal": raw.get("goal") or None,
        "start_date": parse_dt(raw.get("startDate")),
        "end_date": parse_dt(raw.get("endDate")),
        "complete_date": parse_dt(raw.get("completeDate")),
    }


def comment_row(issue_key: str, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "issue_key": issue_key,
        "author_name": (raw.get("author") or {}).get("displayName"),
        "author_account_id": (raw.get("author") or {}).get("accountId"),
        "body_adf": raw.get("body") if isinstance(raw.get("body"), dict) else None,
        "body_text": adf_to_text(raw.get("body")),
        "created_at": parse_dt(raw["created"]),
        "updated_at": parse_dt(raw.get("updated")),
    }


def issue_rows(
    raw: dict[str, Any], *, sprint_field: str | None, story_points_field: str | None
) -> IssueRows:
    f = raw["fields"]
    key = raw["key"]
    issuetype = f.get("issuetype") or {}
    status = f.get("status") or {}
    assignee = f.get("assignee") or {}
    parent = f.get("parent") or {}

    issue = {
        "key": key,
        "id": raw["id"],
        "project_key": key.split("-", 1)[0],
        "issue_type": issuetype.get("name", "?"),
        "is_subtask": bool(issuetype.get("subtask")),
        "summary": f.get("summary") or "",
        "description_adf": f.get("description") if isinstance(f.get("description"), dict) else None,
        "description_text": adf_to_text(f.get("description")),
        "status": status.get("name", "?"),
        "status_category": (status.get("statusCategory") or {}).get("key", "undefined"),
        "priority": (f.get("priority") or {}).get("name"),
        "assignee_account_id": assignee.get("accountId"),
        "assignee_name": assignee.get("displayName"),
        "reporter_name": (f.get("reporter") or {}).get("displayName"),
        "story_points": f.get(story_points_field) if story_points_field else None,
        "due_date": parse_date(f.get("duedate")),
        "parent_key": parent.get("key"),
        "labels": list(f.get("labels") or []),
        "components": [c["name"] for c in f.get("components") or [] if c.get("name")],
        "created_at": parse_dt(f["created"]),
        "updated_at": parse_dt(f["updated"]),
        "resolved_at": parse_dt(f.get("resolutiondate")),
        "raw": raw,
    }

    sprints = [sprint_row(s) for s in (f.get(sprint_field) or [])] if sprint_field else []

    links = []
    for link in f.get("issuelinks") or []:
        link_type = link.get("type") or {}
        if "outwardIssue" in link:
            target, direction, label = link["outwardIssue"], "outward", link_type.get("outward")
        elif "inwardIssue" in link:
            target, direction, label = link["inwardIssue"], "inward", link_type.get("inward")
        else:
            continue
        tf = target.get("fields") or {}
        links.append(
            {
                "id": link["id"],
                "source_key": key,
                "target_key": target["key"],
                "link_type": link_type.get("name", "?"),
                "direction": direction,
                "label": label or link_type.get("name", "?"),
                "target_summary": tf.get("summary"),
                "target_status": (tf.get("status") or {}).get("name"),
                "target_type": (tf.get("issuetype") or {}).get("name"),
            }
        )

    comment_block = f.get("comment") or {}
    raw_comments = comment_block.get("comments") or []
    comments = [comment_row(key, c) for c in raw_comments]
    total = comment_block.get("total")
    complete = total is None or total <= len(raw_comments)

    return IssueRows(
        issue=issue, sprints=sprints, links=links, comments=comments, comments_complete=complete
    )


def repository_row(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": raw["slug"],
        "name": raw.get("name") or raw["slug"],
        "is_private": raw.get("is_private"),
        "main_branch": (raw.get("mainbranch") or {}).get("name"),
        "updated_on": parse_dt(raw.get("updated_on")),
    }


def _bitbucket_identity(user: dict[str, Any] | None) -> str | None:
    user = user or {}
    return user.get("account_id") or user.get("uuid")


def pull_request_row(
    repo_slug: str, raw: dict[str, Any], *, project_keys: list[str]
) -> dict[str, Any]:
    source = raw.get("source") or {}
    source_branch = (source.get("branch") or {}).get("name")
    participants = [
        {
            "role": p.get("role"),
            "approved": bool(p.get("approved")),
            "state": p.get("state"),
            "name": (p.get("user") or {}).get("display_name"),
            "account_id": _bitbucket_identity(p.get("user")),
        }
        for p in raw.get("participants") or []
    ]
    return {
        "repo_slug": repo_slug,
        "id": raw["id"],
        "title": raw.get("title") or "",
        "description": raw.get("description") or None,
        "state": raw["state"],
        "draft": bool(raw.get("draft")),
        "author_name": (raw.get("author") or {}).get("display_name"),
        "author_account_id": _bitbucket_identity(raw.get("author")),
        "source_branch": source_branch,
        "source_commit": (source.get("commit") or {}).get("hash"),
        "destination_branch": ((raw.get("destination") or {}).get("branch") or {}).get("name"),
        "participants": participants,
        "comment_count": raw.get("comment_count"),
        "task_count": raw.get("task_count"),
        "issue_keys": extract_issue_keys(
            source_branch, raw.get("title"), project_keys=project_keys
        ),
        "url": ((raw.get("links") or {}).get("html") or {}).get("href"),
        "created_on": parse_dt(raw.get("created_on")),
        "updated_on": parse_dt(raw.get("updated_on")),
    }


def pr_comment_row(repo_slug: str, pr_id: int, raw: dict[str, Any]) -> dict[str, Any]:
    """Comentário de PR.

    Guarda só o `raw` (markdown) de `content`. O `html` que o Bitbucket devolve junto
    é conteúdo de terceiro pronto para injeção — a tela renderiza texto, não HTML.
    """
    inline = raw.get("inline") or {}
    return {
        "repo_slug": repo_slug,
        "pr_id": pr_id,
        "id": raw["id"],
        "parent_id": (raw.get("parent") or {}).get("id"),
        "author_name": (raw.get("user") or {}).get("display_name"),
        "author_account_id": _bitbucket_identity(raw.get("user")),
        "body_text": (raw.get("content") or {}).get("raw") or "",
        "inline_path": inline.get("path"),
        "inline_from": inline.get("from"),
        "inline_to": inline.get("to"),
        "is_deleted": bool(raw.get("deleted")),
        "created_on": parse_dt(raw.get("created_on")),
        "updated_on": parse_dt(raw.get("updated_on")),
    }


def branch_row(repo_slug: str, raw: dict[str, Any], *, project_keys: list[str]) -> dict[str, Any]:
    target = raw.get("target") or {}
    return {
        "repo_slug": repo_slug,
        "name": raw["name"],
        "target_hash": target.get("hash"),
        "target_date": parse_dt(target.get("date")),
        "issue_keys": extract_issue_keys(raw["name"], project_keys=project_keys),
    }


def build_status(statuses: list[dict[str, Any]]) -> str | None:
    """Pior estado entre os builds do último commit: FAILED > INPROGRESS > SUCCESSFUL."""
    states = {s.get("state") for s in statuses}
    for state in ("FAILED", "STOPPED", "INPROGRESS", "SUCCESSFUL"):
        if state in states:
            return state
    return None
