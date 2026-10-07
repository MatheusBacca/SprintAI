from collections.abc import Iterable

import asyncpg

from repositories import pr_status_repo, seen_repo, settings_repo
from schemas.pr_status_schemas import (
    BranchOut,
    IssuePrSummaryOut,
    PrLinkOut,
    PrStatusBadgeOut,
    PullRequestOut,
    RepoPrStatusOut,
    ReviewerOut,
    ReviewPersonOut,
    ReviewProgressOut,
)
from services.pr_status import (
    CLOSED_WITHOUT_MERGE,
    LABELS,
    ApprovalRule,
    IssuePrSummary,
    PullRequestLink,
    ReviewProgress,
    summarize_issue,
)

APPROVAL_SETTING = "pr_approval"


async def load_rule(pool: asyncpg.Pool) -> ApprovalRule:
    return ApprovalRule.from_setting(await settings_repo.get_setting(pool, APPROVAL_SETTING))


async def save_rule(pool: asyncpg.Pool, rule: ApprovalRule) -> ApprovalRule:
    """Troca a regra e leva junto a foto de quem já tinha visto o card.

    A regra muda o status de PR de vários cards de uma vez; sem acompanhar a foto
    (`issue_seen`), cada um acenderia a bolinha de "teve atualização" por uma mudança que
    o próprio dev fez. Só anda a foto que estava no status da regra antiga — card com
    mudança de verdade ainda não vista continua aceso.
    """
    previous = await load_rule(pool)
    moves: dict[str, tuple[str, str]] = {}
    if rule != previous:
        keys = await seen_repo.keys_with_pr(pool)
        before = await summaries(pool, keys, previous) if keys else {}
        after = await summaries(pool, keys, rule) if keys else {}
        moves = {
            key: (before[key].status, after[key].status)
            for key in keys
            if before[key].status != after[key].status
        }
    async with pool.acquire() as conn, conn.transaction():
        await settings_repo.set_setting(conn, APPROVAL_SETTING, rule.to_setting())
        await seen_repo.move_pr_status(conn, moves)
    return rule


async def summaries(
    pool: asyncpg.Pool, issue_keys: Iterable[str], rule: ApprovalRule | None = None
) -> dict[str, IssuePrSummary]:
    keys = list(issue_keys)
    if rule is None:
        rule = await load_rule(pool)
    pr_rows = await pr_status_repo.pull_requests_for(pool, keys)
    branch_rows = await pr_status_repo.branches_for(pool, keys)
    return {key: summarize_issue(key, pr_rows, branch_rows, rule) for key in keys}


def review_out(review: ReviewProgress | None) -> ReviewProgressOut | None:
    if review is None:
        return None
    people = [ReviewPersonOut(**vars(person)) for person in review.people]
    return ReviewProgressOut(**{**vars(review), "people": people})


def badge_links(summary: IssuePrSummary) -> list[PrLinkOut]:
    """PRs que o badge abre, na ordem de atenção: repositório que decide o status primeiro
    e, dentro dele, aberto antes de mergeado — o primeiro é o PR que o badge está contando.

    Recusado e substituído ficam de fora enquanto houver outro PR: não pesam no status do
    card, e abrir um deles pelo badge seria engano. Sendo tudo o que há, são eles.
    """
    prs = [pr for repo in summary.repos for pr in repo.pull_requests if pr.url]
    live = [pr for pr in prs if pr.status not in CLOSED_WITHOUT_MERGE]
    return [link_out(pr) for pr in live or prs]


def link_out(pr: PullRequestLink) -> PrLinkOut:
    return PrLinkOut(
        repo_slug=pr.repo_slug,
        id=pr.id,
        title=pr.title,
        status=pr.status,
        status_label=LABELS[pr.status],
        url=pr.url,
        review=review_out(pr.review),
    )


def to_badge(summary: IssuePrSummary) -> PrStatusBadgeOut:
    return PrStatusBadgeOut(
        status=summary.status,
        status_label=summary.label,
        pr_count=summary.pr_count,
        open_pr_count=summary.open_pr_count,
        build_failed=summary.build_failed,
        links=badge_links(summary),
        review=review_out(summary.review),
    )


def to_detail(summary: IssuePrSummary) -> IssuePrSummaryOut:
    return IssuePrSummaryOut(
        issue_key=summary.issue_key,
        status=summary.status,
        status_label=summary.label,
        pr_count=summary.pr_count,
        open_pr_count=summary.open_pr_count,
        build_failed=summary.build_failed,
        last_activity=summary.last_activity,
        repos=[
            RepoPrStatusOut(
                repo_slug=repo.repo_slug,
                status=repo.status,
                status_label=LABELS[repo.status],
                pull_requests=[
                    PullRequestOut(
                        repo_slug=pr.repo_slug,
                        id=pr.id,
                        title=pr.title,
                        state=pr.state,
                        status=pr.status,
                        status_label=LABELS[pr.status],
                        draft=pr.draft,
                        source_branch=pr.source_branch,
                        destination_branch=pr.destination_branch,
                        url=pr.url,
                        updated_on=pr.updated_on,
                        approvals=pr.approvals,
                        changes_requested=pr.changes_requested,
                        reviewers=[ReviewerOut(**vars(r)) for r in pr.reviewers],
                        build_status=pr.build_status,
                        build_failed=pr.build_failed,
                        comment_count=pr.comment_count,
                        match=pr.match,
                        fix_pushed=pr.fix_pushed,
                        review=review_out(pr.review),
                    )
                    for pr in repo.pull_requests
                ],
                branches=[
                    BranchOut(name=b.name, target_date=b.target_date, stale=b.stale)
                    for b in repo.branches
                ],
                review=review_out(repo.review),
            )
            for repo in summary.repos
        ],
        links=badge_links(summary),
        review=review_out(summary.review),
    )
