"""Projeto do Bitbucket no espelho e o workspace de projeto.

O dev escolhe os repos do sync agrupados pelo projeto do Bitbucket (OrganIA, weon), mas o
projeto só existia na descoberta ao vivo. Guardado em `bb_repository`, ele segmenta o menu
"WAIs por repositório" e dá ao Workspace uma aba fixa por projeto — a mesma pré-seleção que
o dev montava à mão com um workspace livre por projeto.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute_script(sql: str) -> None:
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    _execute_script(
        """
        ALTER TABLE bb_repository ADD COLUMN project_key text, ADD COLUMN project_name text;

        ALTER TABLE workspace ADD COLUMN project_key text;
        ALTER TABLE workspace DROP CONSTRAINT workspace_kind_check;
        ALTER TABLE workspace ADD CONSTRAINT workspace_kind_check
            CHECK (kind IN ('issue', 'free', 'project'));
        ALTER TABLE workspace ADD CONSTRAINT workspace_project_check
            CHECK ((kind = 'project') = (project_key IS NOT NULL));
        CREATE UNIQUE INDEX ux_workspace_project ON workspace (project_key)
            WHERE project_key IS NOT NULL
        """
    )


def downgrade() -> None:
    _execute_script(
        """
        DROP INDEX IF EXISTS ux_workspace_project;
        ALTER TABLE workspace DROP CONSTRAINT workspace_project_check;
        UPDATE workspace SET kind = 'free' WHERE kind = 'project';
        ALTER TABLE workspace DROP CONSTRAINT workspace_kind_check;
        ALTER TABLE workspace ADD CONSTRAINT workspace_kind_check
            CHECK (kind IN ('issue', 'free'));
        ALTER TABLE workspace DROP COLUMN project_key;

        ALTER TABLE bb_repository DROP COLUMN project_name, DROP COLUMN project_key
        """
    )
