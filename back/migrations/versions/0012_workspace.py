"""Workspaces: a feature (ou o recorte livre) aberto na tela Workspace (B16).

Um workspace de tarefa é um por chave — abrir de novo a mesma feature reabre a aba que já
existia. O livre não tem tarefa: é só uma lista de repositórios para ter terminal à mão.

`workspace_repo_pin` guarda o que o dev mexeu na lista de repositórios envolvidos: `add`
para um repo que a descoberta não achou, `hide` para um que ela achou e não interessa.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute_script(sql: str) -> None:
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    _execute_script(
        """
        CREATE TABLE workspace (
            id              bigserial PRIMARY KEY,
            kind            text NOT NULL CHECK (kind IN ('issue', 'free')),
            root_issue_key  text,
            title           text NOT NULL,
            is_open         boolean NOT NULL DEFAULT true,
            tab_order       integer NOT NULL DEFAULT 0,
            created_at      timestamptz NOT NULL DEFAULT now(),
            last_opened_at  timestamptz NOT NULL DEFAULT now(),
            CHECK ((kind = 'issue') = (root_issue_key IS NOT NULL))
        );

        CREATE UNIQUE INDEX ux_workspace_root_issue ON workspace (root_issue_key)
            WHERE root_issue_key IS NOT NULL;

        -- Sem FK para workspace_repo: o pin de um repo cuja pasta sumiu continua valendo
        -- quando o clone voltar, como os ajustes de Configurações › Workspace.
        CREATE TABLE workspace_repo_pin (
            workspace_id  bigint NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
            repo_slug     text NOT NULL,
            mode          text NOT NULL CHECK (mode IN ('add', 'hide')),
            created_at    timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (workspace_id, repo_slug)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workspace_repo_pin")
    op.execute("DROP TABLE IF EXISTS workspace")
