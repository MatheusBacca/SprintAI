"""Comentários de Pull Request no espelho (histórico da PR dentro do painel).

O espelho guardava só o `comment_count` do PR, então a review recebida obrigava a
abrir o Bitbucket. Esta tabela guarda o texto **cru** (markdown) — nunca o HTML que
a API devolve: conteúdo de terceiro entra como dado, e a tela renderiza como texto.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute_script(sql: str) -> None:
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    _execute_script(
        """
        CREATE TABLE bb_pr_comment (
            repo_slug          text NOT NULL,
            pr_id              integer NOT NULL,
            id                 bigint NOT NULL,
            parent_id          bigint,
            author_name        text,
            author_account_id  text,
            body_text          text NOT NULL DEFAULT '',
            inline_path        text,
            inline_from        integer,
            inline_to          integer,
            is_deleted         boolean NOT NULL DEFAULT false,
            created_on         timestamptz,
            updated_on         timestamptz,
            synced_at          timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (repo_slug, pr_id, id),
            FOREIGN KEY (repo_slug, pr_id) REFERENCES bb_pull_request (repo_slug, id)
                ON DELETE CASCADE ON UPDATE CASCADE
        );

        -- A leitura é sempre "a linha do tempo de UM PR, do mais antigo para o mais novo".
        CREATE INDEX ix_bb_pr_comment_pr ON bb_pr_comment (repo_slug, pr_id, created_on)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bb_pr_comment")
