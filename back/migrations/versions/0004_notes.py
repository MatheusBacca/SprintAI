"""Lembretes / post-its do dev, com busca própria (FTS português sem acento + trigram).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # unaccent() não é IMMUTABLE e por isso não entra em coluna gerada nem em índice;
    # o wrapper com dicionário explícito é o padrão recomendado.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION f_tags_text(text[]) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE
        AS $$ SELECT coalesce(array_to_string($1, ' '), '') $$
        """
    )
    op.execute(
        """
        CREATE TABLE note (
            id           bigserial PRIMARY KEY,
            title        text NOT NULL DEFAULT '',
            body         text NOT NULL DEFAULT '',
            color        text NOT NULL DEFAULT 'yellow'
                         CHECK (color IN ('yellow', 'pink', 'green', 'blue', 'purple', 'gray')),
            tags         text[] NOT NULL DEFAULT '{}',
            pinned       boolean NOT NULL DEFAULT false,
            archived     boolean NOT NULL DEFAULT false,
            remind_at    timestamptz,
            reminded_at  timestamptz,
            created_at   timestamptz NOT NULL DEFAULT now(),
            updated_at   timestamptz NOT NULL DEFAULT now(),
            search       tsvector GENERATED ALWAYS AS (
                setweight(to_tsvector('portuguese', f_unaccent(title)), 'A')
                || setweight(to_tsvector('simple', f_unaccent(f_tags_text(tags))), 'A')
                || setweight(to_tsvector('portuguese', f_unaccent(body)), 'B')
            ) STORED,
            CHECK (title <> '' OR body <> '')
        )
        """
    )
    op.execute("CREATE INDEX ix_note_search ON note USING gin (search)")
    op.execute(
        "CREATE INDEX ix_note_trgm ON note USING gin "
        "(f_unaccent(lower(title || ' ' || body)) gin_trgm_ops)"
    )
    op.execute("CREATE INDEX ix_note_tags ON note USING gin (tags)")
    op.execute("CREATE INDEX ix_note_remind ON note (remind_at) WHERE NOT archived")
    op.execute(
        """
        CREATE TABLE note_issue_link (
            note_id     bigint NOT NULL REFERENCES note (id) ON DELETE CASCADE,
            issue_key   text NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (note_id, issue_key)
        )
        """
    )
    op.execute("CREATE INDEX ix_note_issue_link_key ON note_issue_link (issue_key)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS note_issue_link")
    op.execute("DROP TABLE IF EXISTS note")
    op.execute("DROP FUNCTION IF EXISTS f_tags_text(text[])")
    op.execute("DROP FUNCTION IF EXISTS f_unaccent(text)")
