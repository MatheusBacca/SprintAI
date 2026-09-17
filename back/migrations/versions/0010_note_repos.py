"""Repositórios citados no lembrete (menção `@organia-configs` no texto).

Lista solta de slugs, como as tags: o lembrete não depende do repositório estar no
espelho do Bitbucket — um repo que deixou de ser acompanhado continua citado.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE note ADD COLUMN repos text[] NOT NULL DEFAULT '{}'")
    op.execute("CREATE INDEX ix_note_repos ON note USING gin (repos)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_note_repos")
    op.execute("ALTER TABLE note DROP COLUMN IF EXISTS repos")
