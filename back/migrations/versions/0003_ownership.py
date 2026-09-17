"""Identidade de autor nos PRs (filtro "só os meus").

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE bb_pull_request ADD COLUMN author_account_id text")
    op.execute("CREATE INDEX ix_bb_pull_request_author ON bb_pull_request (author_account_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_bb_pull_request_author")
    op.execute("ALTER TABLE bb_pull_request DROP COLUMN IF EXISTS author_account_id")
