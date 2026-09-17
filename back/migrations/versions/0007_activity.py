"""Histórico de atividade: transições de status do Jira e feed de eventos (B8).

O sync não guardava história — o changelog do Jira era buscado ao vivo e o PR era
sobrescrito a cada ciclo. Sem isso não há feed nem timeline. Estas duas tabelas são
preenchidas **durante o sync**, com `dedupe_key`/`changelog_id` únicos para que rodar
o sync de novo não duplique nada.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute_script(sql: str) -> None:
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    _execute_script(
        """
        -- Transições de status: matéria-prima dos segmentos da timeline (B10).
        CREATE TABLE jira_status_transition (
            id             bigserial PRIMARY KEY,
            changelog_id   text NOT NULL UNIQUE,
            issue_key      text NOT NULL REFERENCES jira_issue (key)
                           ON DELETE CASCADE ON UPDATE CASCADE,
            from_status    text,
            to_status      text NOT NULL,
            from_category  text,
            to_category    text,
            author_name    text,
            changed_at     timestamptz NOT NULL,
            recorded_at    timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_jira_status_transition_issue
            ON jira_status_transition (issue_key, changed_at);

        -- Feed da Home. `detail` guarda só o que a linha precisa mostrar, nunca o
        -- corpo inteiro de um comentário (o trecho vai no título, cortado na aplicação).
        CREATE TABLE activity_event (
            id           bigserial PRIMARY KEY,
            dedupe_key   text NOT NULL UNIQUE,
            source       text NOT NULL CHECK (source IN ('jira', 'bitbucket', 'local')),
            kind         text NOT NULL,
            issue_key    text,
            repo_slug    text,
            pr_id        integer,
            actor_name   text,
            actor_is_me  boolean NOT NULL DEFAULT false,
            occurred_at  timestamptz NOT NULL,
            title        text NOT NULL DEFAULT '',
            detail       jsonb NOT NULL DEFAULT '{}',
            created_at   timestamptz NOT NULL DEFAULT now()
        );
        -- Paginação do feed por cursor (occurred_at, id), do mais novo para o mais antigo.
        CREATE INDEX ix_activity_event_feed ON activity_event (occurred_at DESC, id DESC);
        CREATE INDEX ix_activity_event_issue ON activity_event (issue_key);
        CREATE INDEX ix_activity_event_source ON activity_event (source, occurred_at DESC);

        -- Sem o accountId do autor não dá para saber se um comentário é meu ou de outro,
        -- e o filtro "só de outros" do feed depende disso.
        ALTER TABLE jira_comment ADD COLUMN author_account_id text;
        """
    )


def downgrade() -> None:
    _execute_script(
        """
        ALTER TABLE jira_comment DROP COLUMN IF EXISTS author_account_id;
        DROP TABLE IF EXISTS activity_event, jira_status_transition;
        """
    )
