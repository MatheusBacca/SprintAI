import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from repositories import search_repo
from schemas.search_schemas import SEARCH_TYPES, SearchGroupOut, SearchHitOut, SearchOut
from security.credential_store import CredentialStore
from services.sprint_service import jira_identity

PERIODS = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
SNIPPET_RADIUS = 90
MIN_QUERY = 2


def _fold(text: str) -> str:
    """Minúsculas sem acento, preservando o tamanho (posições batem com o original)."""
    return "".join((unicodedata.normalize("NFD", ch)[0].lower() or ch)[:1] for ch in text)


def query_terms(q: str) -> list[str]:
    """Palavras da busca que valem destacar (sem operadores do websearch)."""
    words = [w.strip("-") for w in re.findall(r"[\w-]+", q, flags=re.UNICODE)]
    return [w for w in dict.fromkeys(words) if len(w) >= 2 and w.lower() not in {"or", "and"}]


def snippet(content: str, terms: list[str], radius: int = SNIPPET_RADIUS) -> str:
    """Trecho de uma linha em volta da primeira ocorrência de algum termo."""
    flat = re.sub(r"\s+", " ", content or "").strip()
    if not flat:
        return ""
    folded = _fold(flat)
    hits = [folded.find(_fold(t)) for t in terms]
    hits = [h for h in hits if h >= 0]
    start = min(hits) if hits else 0
    # Pouco antes do termo e mais depois: o leitor vê o termo cedo e o que vem em seguida.
    before = radius // 2
    begin = 0 if start <= before else start - before
    end = min(len(flat), begin + radius * 2)
    prefix = "…" if begin else ""
    return f"{prefix}{flat[begin:end]}" + ("…" if end < len(flat) else "")


async def search(
    pool: asyncpg.Pool,
    store: CredentialStore,
    *,
    q: str,
    types: list[str] | None,
    period: str,
    limit: int,
    offset: int,
) -> SearchOut:
    term = q.strip()
    wanted = [t for t in SEARCH_TYPES if not types or t in types]
    if len(term) < MIN_QUERY:
        return SearchOut(query=term, total=0, groups=[])

    since = datetime.now(UTC) - timedelta(days=PERIODS[period]) if period in PERIODS else None
    rows, totals = await search_repo.search(
        pool, q=term, types=wanted, since=since, limit=limit, offset=offset
    )

    _, site_url = jira_identity(store)
    browse = f"{site_url.rstrip('/')}/browse/" if site_url else None
    terms = query_terms(term)

    by_type: dict[str, list[SearchHitOut]] = {}
    for row in rows:
        by_type.setdefault(row["entity_type"], []).append(_hit(row, terms, browse))

    groups = [
        SearchGroupOut(type=t, total=totals.get(t, 0), items=by_type.get(t, []))
        for t in wanted
        if totals.get(t)
    ]
    return SearchOut(query=term, total=sum(g.total for g in groups), groups=groups)


def _hit(row: dict[str, Any], terms: list[str], browse: str | None) -> SearchHitOut:
    meta = dict(row["meta"] or {})
    title = row["title"]
    if row["entity_type"] == "comment":
        title = f"Comentário de {meta.get('author_name') or 'alguém'}"
    issue_key = row["issue_key"]
    return SearchHitOut(
        type=row["entity_type"],
        id=row["entity_id"],
        title=title,
        snippet=snippet(row["content"], terms),
        issue_key=issue_key,
        issue_keys=row["issue_keys"],
        issue_summary=row["issue_summary"],
        issue_in_mirror=row["issue_in_mirror"],
        issue_url=f"{browse}{issue_key}" if browse and issue_key else None,
        meta=meta,
        occurred_at=row["occurred_at"],
        rank=round(float(row["rank"]), 4),
    )
