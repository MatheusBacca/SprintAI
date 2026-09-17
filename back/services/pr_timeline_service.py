import asyncpg

from repositories import activity_repo, bitbucket_repo
from schemas.pr_status_schemas import PrTimelineEntryOut, PrTimelineOut
from security.credential_store import CredentialStore
from services import pr_timeline


async def timeline(
    pool: asyncpg.Pool, store: CredentialStore, repo_slug: str, pr_id: int
) -> PrTimelineOut | None:
    """Linha do tempo de um PR do espelho. `None` quando o PR não está espelhado."""
    pull_request = await bitbucket_repo.pull_request(pool, repo_slug, pr_id)
    if pull_request is None:
        return None

    comments = await bitbucket_repo.pr_comments(pool, repo_slug, pr_id)
    events = await activity_repo.events_for_pr(pool, repo_slug, pr_id)
    entries = pr_timeline.merge_timeline(comments, events, my_identities=_my_identities(store))

    return PrTimelineOut(
        repo_slug=repo_slug,
        pr_id=pr_id,
        title=pull_request["title"],
        url=pull_request["url"],
        pending_review=pr_timeline.pending_review(entries),
        request_before_history=pr_timeline.request_before_history(
            entries, pull_request["participants"]
        ),
        entries=[PrTimelineEntryOut(**vars(entry)) for entry in entries],
    )


def _my_identities(store: CredentialStore) -> set[str]:
    """Quem sou eu no Bitbucket — só para marcar "meu" na linha, nunca para filtrar.

    Vem do Cofre (é onde a conexão mora); nenhum segredo sai daqui, só o accountId.
    """
    account_id = (store.get("bitbucket") or {}).get("account_id")
    return {account_id} if account_id else set()
