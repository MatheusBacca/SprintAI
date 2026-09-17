"""Contextos da tarefa: achados, correções, decisões, pontos em aberto e resumos.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE task_context (
            id                     bigserial PRIMARY KEY,
            issue_key              text NOT NULL,
            kind                   text NOT NULL
                                   CHECK (kind IN ('finding', 'fix', 'decision', 'open_point',
                                                   'summary')),
            title                  text NOT NULL DEFAULT '',
            body                   text NOT NULL DEFAULT '',
            tags                   text[] NOT NULL DEFAULT '{}',
            status                 text NOT NULL DEFAULT 'open'
                                   CHECK (status IN ('open', 'resolved')),
            resolved_in_issue_key  text,
            resolution             text NOT NULL DEFAULT '',
            resolved_at            timestamptz,
            source                 text NOT NULL DEFAULT 'manual'
                                   CHECK (source IN ('manual', 'ai_approved')),
            created_at             timestamptz NOT NULL DEFAULT now(),
            updated_at             timestamptz NOT NULL DEFAULT now(),
            search                 tsvector GENERATED ALWAYS AS (
                setweight(to_tsvector('portuguese', f_unaccent(title)), 'A')
                || setweight(to_tsvector('simple', f_unaccent(f_tags_text(tags))), 'A')
                || setweight(to_tsvector('portuguese', f_unaccent(body)), 'B')
                || setweight(to_tsvector('portuguese', f_unaccent(resolution)), 'C')
            ) STORED,
            CHECK (title <> '' OR body <> ''),
            -- Só ponto em aberto é resolvido; resolvido sempre diz quando.
            CHECK (status = 'open' OR kind = 'open_point'),
            CHECK ((status = 'resolved') = (resolved_at IS NOT NULL))
        )
        """
    )
    op.execute("CREATE INDEX ix_task_context_issue ON task_context (issue_key)")
    op.execute("CREATE INDEX ix_task_context_open ON task_context (kind, status)")
    op.execute("CREATE INDEX ix_task_context_search ON task_context USING gin (search)")
    op.execute(
        "CREATE INDEX ix_task_context_trgm ON task_context USING gin "
        "(f_unaccent(lower(title || ' ' || body)) gin_trgm_ops)"
    )
    op.execute(
        """
        CREATE TABLE context_relation (
            context_id  bigint NOT NULL REFERENCES task_context (id) ON DELETE CASCADE,
            issue_key   text NOT NULL,
            relation    text NOT NULL DEFAULT 'relates'
                        CHECK (relation IN ('relates', 'continues', 'resolves')),
            created_at  timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (context_id, issue_key)
        )
        """
    )
    op.execute("CREATE INDEX ix_context_relation_key ON context_relation (issue_key)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS context_relation")
    op.execute("DROP TABLE IF EXISTS task_context")
