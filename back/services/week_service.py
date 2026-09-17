from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import asyncpg

from repositories import week_repo
from schemas.week_schemas import WeekIssueOut, WeekOut
from security.credential_store import CredentialStore
from services import notes_service, pr_status_service
from services.sprint_service import jira_identity

DEFAULT_TIMEZONE = "America/Sao_Paulo"


class InvalidTimezone(ValueError):
    pass


def resolve_timezone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidTimezone(f"Fuso horário desconhecido: {name}") from exc


def week_bounds(day: date) -> tuple[date, date]:
    """Segunda a domingo da semana que contém `day`."""
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


async def get_week(
    pool: asyncpg.Pool,
    store: CredentialStore,
    *,
    day: date | None,
    timezone: str | None,
    now: datetime | None = None,
) -> WeekOut:
    tz = resolve_timezone(timezone)
    today = (now or datetime.now(tz)).astimezone(tz).date()
    start, end = week_bounds(day or today)
    since = datetime.combine(start, time.min, tz)
    until = datetime.combine(end + timedelta(days=1), time.min, tz)

    account_id, site_url = jira_identity(store)
    without_sprint = await week_repo.without_sprint(pool, account_id)
    due = await week_repo.due_between(pool, account_id, start, end)
    overdue = await week_repo.overdue_before(pool, account_id, start)
    slicing = await week_repo.slicing_cards(pool, account_id, since, until)

    issue_rows = without_sprint + due + overdue + slicing
    prs = await pr_status_service.summaries(pool, {r["key"] for r in issue_rows})
    browse = f"{site_url.rstrip('/')}/browse/" if site_url else None

    def issues(rows: list[dict[str, Any]]) -> list[WeekIssueOut]:
        return [
            WeekIssueOut(
                **row,
                url=f"{browse}{row['key']}" if browse else None,
                pr=pr_status_service.to_badge(prs[row["key"]]) if row["key"] in prs else None,
            )
            for row in rows
        ]

    reminders = await week_repo.reminders_between(pool, since, until)
    pending = await week_repo.pending_reminders_before(pool, since)

    return WeekOut(
        start=start,
        end=end,
        today=today,
        timezone=tz.key,
        filtered_by_assignee=account_id is not None,
        without_sprint=issues(without_sprint),
        due=issues(due),
        overdue=issues(overdue),
        slicing=issues(slicing),
        reminders=await notes_service.hydrate(pool, store, reminders),
        pending_reminders=await notes_service.hydrate(pool, store, pending),
    )
