"""Repositórios locais em `C:\\projects` e o vínculo de cada um com o Bitbucket (B12).

A descoberta lê o disco a cada listagem e grava aqui o que achou (`detected_*`). O que o dev
ajusta em Configurações › Workspace mora em colunas próprias (`*_override`), que a
redescoberta nunca toca — e a linha de uma pasta que sumiu fica, com `present = false`, para
o ajuste valer de novo quando o clone voltar.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute_script(sql: str) -> None:
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    _execute_script(
        """
        -- slug = nome da pasta. No weonrepo ele é igual ao slug do Bitbucket, mas não
        -- precisa ser: o vínculo vem do remote (detected_bb_slug) ou do ajuste do dev.
        CREATE TABLE workspace_repo (
            slug                  text PRIMARY KEY,
            local_path            text NOT NULL,
            present               boolean NOT NULL DEFAULT true,
            has_git               boolean NOT NULL DEFAULT false,
            remote_url            text,
            detected_bb_slug      text,
            current_branch        text,
            detached              boolean NOT NULL DEFAULT false,
            detected_base         text,
            detected_base_source  text,
            -- NULL = automático, '' = sem vínculo, texto = slug escolhido pelo dev
            link_override         text,
            -- NULL = automático (Bitbucket, origin/HEAD, palpite)
            base_branch_override  text,
            detected_at           timestamptz NOT NULL DEFAULT now(),
            updated_at            timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workspace_repo")
