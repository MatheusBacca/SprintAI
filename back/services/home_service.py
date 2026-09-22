"""A Home: onde eu estou hoje (F11 + B10).

Duas respostas:

- `get_home` — barra de progresso por sprint **com trabalho meu em aberto**, o topo das
  pendências da semana (reusando o `week_service`, sem duplicar regra) e os lembretes que
  importam agora;
- `get_timeline` — as faixas das sprints e as linhas agrupadas por pai, com a barra
  segmentada por status de cada tarefa minha.
"""

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg

from repositories import activity_repo, notes_repo, progress_repo
from schemas.home_schemas import (
    HomeOut,
    HomePendingOut,
    TimelineGroupOut,
    TimelineIssueOut,
    TimelineLinkOut,
    TimelineOut,
    TimelineSegmentOut,
    TimelineSprintOut,
)
from schemas.progress_schemas import ProgressOut, SprintProgressOut
from security.credential_store import CredentialStore
from services import notes_service, pr_status_service, progress, sprint_updates, week_service
from services.progress import timeline as timeline_math
from services.sprint_service import jira_identity

TOP_PENDING = 5
REMINDER_WINDOW = timedelta(hours=48)
# Janela desenhada quando a sprint não tem data (não dá para desenhar o nada).
FALLBACK_WINDOW = timedelta(days=7)
NO_PARENT = "Sem pai"


def _today(tz: ZoneInfo, now: datetime | None = None) -> date:
    return (now or datetime.now(tz)).astimezone(tz).date()


async def get_home(
    pool: asyncpg.Pool,
    store: CredentialStore,
    *,
    timezone: str | None = None,
    now: datetime | None = None,
) -> HomeOut:
    tz = week_service.resolve_timezone(timezone)
    instant = (now or datetime.now(tz)).astimezone(tz)
    today = instant.date()
    account_id, site_url = jira_identity(store)
    browse = f"{site_url.rstrip('/')}/browse/" if site_url else None

    week = await week_service.get_week(pool, store, day=None, timezone=tz.key, now=now)
    open_slicing = [i for i in week.slicing if i.status_category != "done"]
    open_due = [i for i in week.due if i.status_category != "done"]
    pending = HomePendingOut(
        overdue=week.overdue[:TOP_PENDING],
        due=open_due[:TOP_PENDING],
        slicing=open_slicing[:TOP_PENDING],
        without_sprint=week.without_sprint[:TOP_PENDING],
        total=len(week.overdue) + len(open_due) + len(open_slicing) + len(week.without_sprint),
    )

    stages = await progress.load_stages(pool)
    sources = progress.sources_for(stages)
    sprints = await progress_repo.timeline_sprints(pool, include_next=False)
    issues = await progress_repo.sprint_issues(pool, [s["id"] for s in sprints], account_id)
    by_sprint: dict[int, list[dict[str, Any]]] = {s["id"]: [] for s in sprints}
    for issue in issues:
        by_sprint.setdefault(issue["sprint_id"], []).append(issue)

    # Uma sprint só ocupa espaço na Home enquanto tiver trabalho meu por fazer. Sprint que
    # passou da data e continua aberta fica; sprint em dia sem pendência minha sai.
    working = [s for s in sprints if _has_open_mine(by_sprint.get(s["id"], []))]
    updates = await sprint_updates.by_sprint(
        pool,
        [s["id"] for s in working],
        account_id=account_id,
        since=instant - sprint_updates.WINDOW,
        browse=browse,
    )

    sprint_progress = [
        SprintProgressOut(
            **vars(
                progress.sprint_progress(
                    sprint, by_sprint.get(sprint["id"], []), sources, today=today, tz=tz
                )
            )
            | {"squad": sprint.get("squad"), "updates": updates.get(sprint["id"], [])}
        )
        for sprint in working
    ]

    reminder_rows = await notes_repo.relevant(
        pool,
        until=instant + REMINDER_WINDOW,
        issue_keys=[i["key"] for i in issues],
    )
    for row in reminder_rows:
        row.pop("overdue", None)

    return HomeOut(
        today=today,
        timezone=tz.key,
        filtered_by_assignee=account_id is not None,
        week_start=week.start,
        week_end=week.end,
        sprints=sprint_progress,
        pending=pending,
        reminders=await notes_service.hydrate(pool, store, reminder_rows),
    )


def _has_open_mine(rows: list[dict[str, Any]]) -> bool:
    """A sprint tem tarefa minha por fazer? Épico é contêiner, não conta."""
    return any(not progress.is_epic(row) and row.get("status_category") != "done" for row in rows)


async def get_timeline(
    pool: asyncpg.Pool,
    store: CredentialStore,
    *,
    include_next: bool = True,
    timezone: str | None = None,
    now: datetime | None = None,
) -> TimelineOut:
    tz = week_service.resolve_timezone(timezone)
    instant = (now or datetime.now(tz)).astimezone(tz)
    today = instant.date()
    account_id, site_url = jira_identity(store)
    browse = f"{site_url.rstrip('/')}/browse/" if site_url else None

    stages = await progress.load_stages(pool)
    sources = progress.sources_for(stages)
    sprints = await progress_repo.timeline_sprints(pool, include_next=include_next)
    issues = await progress_repo.sprint_issues(pool, [s["id"] for s in sprints], account_id)
    issues = [i for i in issues if not progress.is_epic(i)]

    keys = [i["key"] for i in issues]
    transitions: dict[str, list[dict[str, Any]]] = {}
    for row in await activity_repo.transitions_for(pool, keys):
        transitions.setdefault(row["issue_key"], []).append(row)
    badges = await pr_status_service.summaries(pool, keys) if keys else {}

    windows = {s["id"]: _sprint_window(s, tz, today) for s in sprints}
    out_sprints = [
        TimelineSprintOut(
            id=s["id"],
            name=s["name"],
            state=s["state"],
            squad=s.get("squad"),
            start=timeline_math.as_date(s.get("start_date"), tz),
            end=timeline_math.as_date(s.get("end_date"), tz),
            overdue_active=bool(
                s["state"] == "active"
                and (end := timeline_math.as_date(s.get("end_date"), tz))
                and end < today
            ),
            current=_contains(s, today, tz),
        )
        for s in sprints
    ]

    groups: dict[str | None, dict[str, Any]] = {}
    for issue in issues:
        window = windows.get(issue["sprint_id"]) or _default_window(today, tz)
        bar = timeline_math.build_bar(
            issue,
            transitions.get(issue["key"], []),
            stages,
            window_start=window[0],
            window_end=window[1],
            now=instant,
        )
        item = progress.issue_progress(issue, sources)
        points = issue.get("story_points")
        row = TimelineIssueOut(
            key=issue["key"],
            summary=issue["summary"],
            issue_type=issue["issue_type"],
            status=issue["status"],
            status_category=issue["status_category"],
            story_points=float(points) if points is not None else None,
            assignee_name=issue.get("assignee_name"),
            url=f"{browse}{issue['key']}" if browse else None,
            due_date=issue.get("due_date"),
            resolved_at=issue.get("resolved_at"),
            sprint_id=issue.get("sprint_id"),
            start=bar.start,
            end=bar.end,
            projected=bar.projected,
            started=bar.started,
            progress=ProgressOut(**vars(item)),
            segments=[TimelineSegmentOut(**vars(s)) for s in bar.segments],
            pr=pr_status_service.to_badge(badges[issue["key"]]) if issue["key"] in badges else None,
        )
        group_key = issue.get("parent_key")
        group = groups.setdefault(
            group_key,
            {
                "key": group_key,
                "summary": issue.get("parent_summary") or (group_key or NO_PARENT),
                "issue_type": issue.get("parent_type"),
                "url": f"{browse}{group_key}" if browse and group_key else None,
                "issues": [],
                "rows": [],
            },
        )
        group["issues"].append(row)
        group["rows"].append(issue)

    out_groups = [
        TimelineGroupOut(
            key=g["key"],
            summary=g["summary"],
            issue_type=g["issue_type"],
            url=g["url"],
            progress=progress.aggregate(g["rows"], sources)[0],
            issues=sorted(g["issues"], key=lambda i: (i.start, i.key)),
        )
        # Sem pai fica por último, como na árvore da sprint.
        for g in sorted(groups.values(), key=lambda g: (g["key"] is None, g["summary"]))
    ]

    start, end = _bounds(out_sprints, out_groups, today, tz)
    return TimelineOut(
        today=today,
        timezone=tz.key,
        start=start,
        end=end,
        sprints=out_sprints,
        groups=out_groups,
        links=[
            TimelineLinkOut(source=link["source_key"], target=link["target_key"])
            for link in await progress_repo.blocks_links(pool, keys)
        ],
    )


# --- Janelas -------------------------------------------------------------------------


def _at(day: date, tz: ZoneInfo, *, end: bool = False) -> datetime:
    return datetime.combine(day + timedelta(days=1) if end else day, time.min, tz)


def _default_window(today: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    return _at(today - FALLBACK_WINDOW, tz), _at(today + FALLBACK_WINDOW, tz, end=True)


def _sprint_window(sprint: dict[str, Any], tz: ZoneInfo, today: date) -> tuple[datetime, datetime]:
    start = timeline_math.as_date(sprint.get("start_date"), tz)
    end = timeline_math.as_date(sprint.get("end_date"), tz)
    if start is None or end is None:
        return _default_window(today, tz)
    return _at(start, tz), _at(end, tz, end=True)


def _contains(sprint: dict[str, Any], today: date, tz: ZoneInfo) -> bool:
    start = timeline_math.as_date(sprint.get("start_date"), tz)
    end = timeline_math.as_date(sprint.get("end_date"), tz)
    return bool(start and end and start <= today <= end)


def _bounds(
    sprints: list[TimelineSprintOut],
    groups: list[TimelineGroupOut],
    today: date,
    tz: ZoneInfo,
) -> tuple[date, date]:
    days = [d for s in sprints for d in (s.start, s.end) if d]
    for group in groups:
        for issue in group.issues:
            days += [issue.start.astimezone(tz).date(), issue.end.astimezone(tz).date()]
    days.append(today)
    return min(days), max(days)
