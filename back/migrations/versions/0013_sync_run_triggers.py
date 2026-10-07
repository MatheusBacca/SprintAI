"""Gatilhos do sync disparados pelas escritas no Bitbucket: `concluir` e `reviewers`.

O "Concluir" e a troca de reviewers chamam o sync logo depois da escrita (o espelho do PR é
dele), cada um com o seu gatilho — e o CHECK de `sync_run.trigger` só aceitava `manual` e
`scheduled`. O INSERT estourava depois do PUT no Bitbucket já ter entrado: o reviewer ia para o
PR e a tela recebia um 500.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute_script(sql: str) -> None:
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    _execute_script(
        """
        ALTER TABLE sync_run DROP CONSTRAINT sync_run_trigger_check;
        ALTER TABLE sync_run ADD CONSTRAINT sync_run_trigger_check
            CHECK (trigger IN ('manual', 'scheduled', 'concluir', 'reviewers'))
        """
    )


def downgrade() -> None:
    _execute_script(
        """
        UPDATE sync_run SET trigger = 'manual' WHERE trigger IN ('concluir', 'reviewers');
        ALTER TABLE sync_run DROP CONSTRAINT sync_run_trigger_check;
        ALTER TABLE sync_run ADD CONSTRAINT sync_run_trigger_check
            CHECK (trigger IN ('manual', 'scheduled'))
        """
    )
