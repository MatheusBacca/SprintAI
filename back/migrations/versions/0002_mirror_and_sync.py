"""Espelho local do Jira e do Bitbucket + controle de sincronização.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute_script(sql: str) -> None:
    # asyncpg não aceita vários comandos num único execute.
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    _execute_script(
        """
        CREATE TABLE app_setting (
            key         text PRIMARY KEY,
            value       jsonb NOT NULL,
            updated_at  timestamptz NOT NULL DEFAULT now()
        );

        -- Jira ---------------------------------------------------------------
        CREATE TABLE jira_board (
            id            integer PRIMARY KEY,
            name          text NOT NULL,
            type          text NOT NULL,
            project_key   text,
            project_name  text,
            synced_at     timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE jira_sprint (
            id                integer PRIMARY KEY,
            board_id          integer,
            name              text NOT NULL,
            state             text NOT NULL CHECK (state IN ('active', 'future', 'closed')),
            squad             text,
            goal              text,
            start_date        timestamptz,
            end_date          timestamptz,
            complete_date     timestamptz,
            in_scope          boolean NOT NULL DEFAULT false,
            issues_synced_at  timestamptz,
            synced_at         timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_jira_sprint_board_state ON jira_sprint (board_id, state);

        CREATE TABLE jira_issue (
            key                  text PRIMARY KEY,
            id                   text NOT NULL UNIQUE,
            project_key          text NOT NULL,
            issue_type           text NOT NULL,
            is_subtask           boolean NOT NULL DEFAULT false,
            summary              text NOT NULL,
            description_adf      jsonb,
            description_text     text,
            status               text NOT NULL,
            status_category      text NOT NULL,
            priority             text,
            assignee_account_id  text,
            assignee_name        text,
            reporter_name        text,
            story_points         numeric,
            due_date             date,
            parent_key           text,
            labels               text[] NOT NULL DEFAULT '{}',
            components           text[] NOT NULL DEFAULT '{}',
            created_at           timestamptz NOT NULL,
            updated_at           timestamptz NOT NULL,
            resolved_at          timestamptz,
            raw                  jsonb NOT NULL,
            synced_at            timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_jira_issue_parent ON jira_issue (parent_key);
        CREATE INDEX ix_jira_issue_assignee ON jira_issue (assignee_account_id);
        CREATE INDEX ix_jira_issue_due_date ON jira_issue (due_date);

        CREATE TABLE jira_sprint_issue (
            sprint_id  integer NOT NULL,
            issue_key  text NOT NULL REFERENCES jira_issue (key) ON DELETE CASCADE ON UPDATE CASCADE,
            PRIMARY KEY (sprint_id, issue_key)
        );
        CREATE INDEX ix_jira_sprint_issue_issue ON jira_sprint_issue (issue_key);

        CREATE TABLE jira_issue_link (
            id              text NOT NULL,
            source_key      text NOT NULL REFERENCES jira_issue (key) ON DELETE CASCADE ON UPDATE CASCADE,
            target_key      text NOT NULL,
            link_type       text NOT NULL,
            direction       text NOT NULL CHECK (direction IN ('inward', 'outward')),
            label           text NOT NULL,
            target_summary  text,
            target_status   text,
            target_type     text,
            PRIMARY KEY (id, source_key)
        );
        CREATE INDEX ix_jira_issue_link_target ON jira_issue_link (target_key);

        CREATE TABLE jira_comment (
            id           text PRIMARY KEY,
            issue_key    text NOT NULL REFERENCES jira_issue (key) ON DELETE CASCADE ON UPDATE CASCADE,
            author_name  text,
            body_adf     jsonb,
            body_text    text,
            created_at   timestamptz NOT NULL,
            updated_at   timestamptz
        );
        CREATE INDEX ix_jira_comment_issue ON jira_comment (issue_key);

        -- Bitbucket ------------------------------------------------------------
        CREATE TABLE bb_repository (
            slug         text PRIMARY KEY,
            name         text NOT NULL,
            is_private   boolean,
            main_branch  text,
            updated_on   timestamptz,
            synced_at    timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE bb_pull_request (
            repo_slug           text NOT NULL,
            id                  integer NOT NULL,
            title               text NOT NULL,
            description         text,
            state               text NOT NULL,
            draft               boolean NOT NULL DEFAULT false,
            author_name         text,
            source_branch       text,
            source_commit       text,
            destination_branch  text,
            participants        jsonb NOT NULL DEFAULT '[]',
            comment_count       integer,
            task_count          integer,
            build_status        text,
            issue_keys          text[] NOT NULL DEFAULT '{}',
            url                 text,
            created_on          timestamptz,
            updated_on          timestamptz,
            synced_at           timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (repo_slug, id)
        );
        CREATE INDEX ix_bb_pull_request_issue_keys ON bb_pull_request USING gin (issue_keys);
        CREATE INDEX ix_bb_pull_request_state ON bb_pull_request (state);

        CREATE TABLE bb_branch (
            repo_slug    text NOT NULL,
            name         text NOT NULL,
            target_hash  text,
            target_date  timestamptz,
            issue_keys   text[] NOT NULL DEFAULT '{}',
            synced_at    timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (repo_slug, name)
        );
        CREATE INDEX ix_bb_branch_issue_keys ON bb_branch USING gin (issue_keys);

        -- Sincronização ----------------------------------------------------------
        CREATE TABLE sync_state (
            resource         text PRIMARY KEY,
            last_success_at  timestamptz,
            cursor           jsonb NOT NULL DEFAULT '{}'
        );

        CREATE TABLE sync_run (
            id           bigserial PRIMARY KEY,
            trigger      text NOT NULL CHECK (trigger IN ('manual', 'scheduled')),
            status       text NOT NULL CHECK (status IN ('running', 'success', 'partial', 'failed')),
            started_at   timestamptz NOT NULL DEFAULT now(),
            finished_at  timestamptz,
            stats        jsonb NOT NULL DEFAULT '{}',
            errors       jsonb NOT NULL DEFAULT '[]'
        );
        CREATE INDEX ix_sync_run_started ON sync_run (started_at DESC);
        """
    )


def downgrade() -> None:
    _execute_script(
        """
        DROP TABLE IF EXISTS sync_run, sync_state, bb_branch, bb_pull_request, bb_repository,
            jira_comment, jira_issue_link, jira_sprint_issue, jira_issue, jira_sprint,
            jira_board, app_setting;
        """
    )
