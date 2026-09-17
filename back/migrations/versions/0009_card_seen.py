"""O que o dev já viu de cada card do canvas (bolinha de "teve atualização").

Guarda uma foto do que o card mostra — status, etapa de PR, Story Points e
responsável —, não um horário: o `activity_event` só registra as tarefas do dev, e a
bolinha vale para qualquer card da sprint. A foto nasce na primeira vez que o card
aparece (sem bolinha) e é refeita quando o dev clica nele.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute_script(sql: str) -> None:
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    _execute_script(
        """
        -- Sem FK para jira_issue: o card de um pai fora do espelho também tem foto, e
        -- um prune do espelho não deve fazer a tarefa voltar acesa quando reaparecer.
        CREATE TABLE issue_seen (
            issue_key  text PRIMARY KEY,
            snapshot   jsonb NOT NULL DEFAULT '{}',
            seen_at    timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS issue_seen")
