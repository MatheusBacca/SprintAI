from collections.abc import Iterable

import asyncpg

from repositories import pr_status_repo
from schemas.pr_status_schemas import (
    BranchOut,
    IssuePrSummaryOut,
    PrStatusBadgeOut,
    PullRequestOut,
    RepoPrStatusOut,
    ReviewerOut,
)
from services.pr_status import LABELS, IssuePrSummary, summarize_issue


async def summaries(pool: asyncpg.Pool, issue_keys: Iterable[str]) -> dict[str, IssuePrSummary]:
    keys = list(issue_keys)
    pr_rows = await pr_status_repo.pull_requests_for(pool, keys)
    branch_rows = await pr_status_repo.branches_for(pool, keys)
    return {key: summarize_issue(key, pr_rows, branch_rows) for key in keys}


def to_badge(summary: IssuePrSummary) -> PrStatusBadgeOut:
    return PrStatusBadgeOut(
        status=summary.status,
        status_label=summary.label,
        pr_count=summary.pr_count,
        open_pr_count=summary.open_pr_count,
        build_failed=summary.build_failed,
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
                    )
                    for pr in repo.pull_requests
                ],
                branches=[
                    BranchOut(name=b.name, target_date=b.target_date, stale=b.stale)
                    for b in repo.branches
                ],
            )
            for repo in summary.repos
        ],
    )
