"""Índice de busca global (F6): um documento por tarefa, comentário, PR, contexto e lembrete.

Mantido por triggers — qualquer escrita no espelho (sync) ou nos dados do dev atualiza o
índice na mesma transação, sem código extra na aplicação. A parte semântica (coluna de
embedding + worker local) chega na B6 sobre esta mesma tabela.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Texto muito longo (descrição gigante) estoura o limite do tsvector e não ajuda a achar.
MAX_CONTENT = 100_000

REFRESH_FUNCTIONS = [
    f"""
    CREATE FUNCTION search_upsert(
        p_type text, p_id text, p_issue_key text, p_issue_keys text[], p_title text,
        p_keywords text, p_content text, p_meta jsonb, p_occurred_at timestamptz
    ) RETURNS void LANGUAGE sql AS $$
        INSERT INTO search_document (entity_type, entity_id, issue_key, issue_keys, title,
                                     keywords, content, meta, occurred_at, indexed_at)
        VALUES (p_type, p_id, p_issue_key, coalesce(p_issue_keys, '{{}}'), coalesce(p_title, ''),
                coalesce(p_keywords, ''), left(coalesce(p_content, ''), {MAX_CONTENT}),
                coalesce(p_meta, '{{}}'), p_occurred_at, now())
        ON CONFLICT (entity_type, entity_id) DO UPDATE SET
            issue_key = EXCLUDED.issue_key, issue_keys = EXCLUDED.issue_keys,
            title = EXCLUDED.title, keywords = EXCLUDED.keywords, content = EXCLUDED.content,
            meta = EXCLUDED.meta, occurred_at = EXCLUDED.occurred_at, indexed_at = now()
    $$
    """,
    """
    CREATE FUNCTION search_refresh_issue(p_key text) RETURNS void LANGUAGE plpgsql AS $$
    DECLARE r jira_issue%ROWTYPE;
    BEGIN
        SELECT * INTO r FROM jira_issue WHERE key = p_key;
        IF NOT FOUND THEN
            DELETE FROM search_document WHERE entity_type = 'issue' AND entity_id = p_key;
            RETURN;
        END IF;
        PERFORM search_upsert(
            'issue', r.key, r.key, ARRAY[r.key], r.summary,
            array_to_string(r.labels || r.components, ' '), r.description_text,
            jsonb_build_object('issue_type', r.issue_type, 'status', r.status,
                               'status_category', r.status_category,
                               'assignee_name', r.assignee_name),
            r.updated_at);
    END $$
    """,
    """
    CREATE FUNCTION search_refresh_comment(p_id text) RETURNS void LANGUAGE plpgsql AS $$
    DECLARE r jira_comment%ROWTYPE;
    BEGIN
        SELECT * INTO r FROM jira_comment WHERE id = p_id;
        IF NOT FOUND THEN
            DELETE FROM search_document WHERE entity_type = 'comment' AND entity_id = p_id;
            RETURN;
        END IF;
        PERFORM search_upsert(
            'comment', r.id, r.issue_key, ARRAY[r.issue_key], '', '', r.body_text,
            jsonb_build_object('author_name', r.author_name),
            coalesce(r.updated_at, r.created_at));
    END $$
    """,
    """
    CREATE FUNCTION search_refresh_pull_request(p_repo text, p_id integer)
    RETURNS void LANGUAGE plpgsql AS $$
    DECLARE r bb_pull_request%ROWTYPE;
    BEGIN
        SELECT * INTO r FROM bb_pull_request WHERE repo_slug = p_repo AND id = p_id;
        IF NOT FOUND THEN
            DELETE FROM search_document
            WHERE entity_type = 'pull_request' AND entity_id = p_repo || '#' || p_id;
            RETURN;
        END IF;
        PERFORM search_upsert(
            'pull_request', r.repo_slug || '#' || r.id, r.issue_keys[1], r.issue_keys, r.title,
            concat_ws(' ', r.source_branch, r.repo_slug), r.description,
            jsonb_build_object('repo_slug', r.repo_slug, 'pr_id', r.id, 'state', r.state,
                               'draft', r.draft, 'author_name', r.author_name, 'url', r.url,
                               'source_branch', r.source_branch,
                               'destination_branch', r.destination_branch),
            coalesce(r.updated_on, r.created_on, r.synced_at));
    END $$
    """,
    """
    CREATE FUNCTION search_refresh_context(p_id bigint) RETURNS void LANGUAGE plpgsql AS $$
    DECLARE r task_context%ROWTYPE; keys text[];
    BEGIN
        SELECT * INTO r FROM task_context WHERE id = p_id;
        IF NOT FOUND THEN
            DELETE FROM search_document WHERE entity_type = 'context' AND entity_id = p_id::text;
            RETURN;
        END IF;
        SELECT array_agg(DISTINCT k) INTO keys FROM (
            SELECT r.issue_key AS k
            UNION ALL SELECT r.resolved_in_issue_key WHERE r.resolved_in_issue_key IS NOT NULL
            UNION ALL SELECT issue_key FROM context_relation WHERE context_id = p_id
        ) s;
        PERFORM search_upsert(
            'context', r.id::text, r.issue_key, keys, r.title, f_tags_text(r.tags),
            concat_ws(E'\\n', nullif(r.body, ''), nullif(r.resolution, '')),
            jsonb_build_object('kind', r.kind, 'status', r.status,
                               'resolved_in_issue_key', r.resolved_in_issue_key),
            r.updated_at);
    END $$
    """,
    """
    CREATE FUNCTION search_refresh_note(p_id bigint) RETURNS void LANGUAGE plpgsql AS $$
    DECLARE r note%ROWTYPE; keys text[];
    BEGIN
        SELECT * INTO r FROM note WHERE id = p_id;
        IF NOT FOUND THEN
            DELETE FROM search_document WHERE entity_type = 'note' AND entity_id = p_id::text;
            RETURN;
        END IF;
        SELECT array_agg(issue_key ORDER BY created_at) INTO keys
        FROM note_issue_link WHERE note_id = p_id;
        PERFORM search_upsert(
            'note', r.id::text, keys[1], keys, r.title, f_tags_text(r.tags), r.body,
            jsonb_build_object('color', r.color, 'pinned', r.pinned, 'archived', r.archived,
                               'remind_at', r.remind_at),
            r.updated_at);
    END $$
    """,
]

# (tabela, função do trigger, corpo que chama o refresh com OLD/NEW)
TRIGGERS = [
    (
        "jira_issue",
        "trg_search_jira_issue",
        """
        IF TG_OP = 'DELETE' OR (TG_OP = 'UPDATE' AND OLD.key <> NEW.key) THEN
            PERFORM search_refresh_issue(OLD.key);
        END IF;
        IF TG_OP <> 'DELETE' THEN PERFORM search_refresh_issue(NEW.key); END IF;
        """,
    ),
    (
        "jira_comment",
        "trg_search_jira_comment",
        """
        IF TG_OP = 'DELETE' THEN PERFORM search_refresh_comment(OLD.id);
        ELSE PERFORM search_refresh_comment(NEW.id); END IF;
        """,
    ),
    (
        "bb_pull_request",
        "trg_search_bb_pull_request",
        """
        IF TG_OP = 'DELETE' THEN PERFORM search_refresh_pull_request(OLD.repo_slug, OLD.id);
        ELSE PERFORM search_refresh_pull_request(NEW.repo_slug, NEW.id); END IF;
        """,
    ),
    (
        "task_context",
        "trg_search_task_context",
        """
        IF TG_OP = 'DELETE' THEN PERFORM search_refresh_context(OLD.id);
        ELSE PERFORM search_refresh_context(NEW.id); END IF;
        """,
    ),
    (
        "context_relation",
        "trg_search_context_relation",
        """
        IF TG_OP = 'DELETE' OR (TG_OP = 'UPDATE' AND OLD.context_id <> NEW.context_id) THEN
            PERFORM search_refresh_context(OLD.context_id);
        END IF;
        IF TG_OP <> 'DELETE' THEN PERFORM search_refresh_context(NEW.context_id); END IF;
        """,
    ),
    (
        "note",
        "trg_search_note",
        """
        IF TG_OP = 'DELETE' THEN PERFORM search_refresh_note(OLD.id);
        ELSE PERFORM search_refresh_note(NEW.id); END IF;
        """,
    ),
    (
        "note_issue_link",
        "trg_search_note_issue_link",
        """
        IF TG_OP = 'DELETE' OR (TG_OP = 'UPDATE' AND OLD.note_id <> NEW.note_id) THEN
            PERFORM search_refresh_note(OLD.note_id);
        END IF;
        IF TG_OP <> 'DELETE' THEN PERFORM search_refresh_note(NEW.note_id); END IF;
        """,
    ),
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE search_document (
            entity_type  text NOT NULL
                         CHECK (entity_type IN ('issue', 'comment', 'pull_request', 'context',
                                                'note')),
            entity_id    text NOT NULL,
            issue_key    text,
            issue_keys   text[] NOT NULL DEFAULT '{}',
            title        text NOT NULL DEFAULT '',
            keywords     text NOT NULL DEFAULT '',
            content      text NOT NULL DEFAULT '',
            meta         jsonb NOT NULL DEFAULT '{}',
            occurred_at  timestamptz,
            indexed_at   timestamptz NOT NULL DEFAULT now(),
            search       tsvector GENERATED ALWAYS AS (
                setweight(to_tsvector('simple', f_unaccent(f_tags_text(issue_keys))), 'A')
                || setweight(to_tsvector('portuguese', f_unaccent(title)), 'A')
                || setweight(to_tsvector('simple', f_unaccent(keywords)), 'A')
                || setweight(to_tsvector('portuguese', f_unaccent(content)), 'B')
            ) STORED,
            PRIMARY KEY (entity_type, entity_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_search_document_search ON search_document USING gin (search)")
    op.execute(
        "CREATE INDEX ix_search_document_trgm ON search_document USING gin "
        "(f_unaccent(lower(title || ' ' || keywords || ' ' || content)) gin_trgm_ops)"
    )
    op.execute("CREATE INDEX ix_search_document_keys ON search_document USING gin (issue_keys)")
    op.execute("CREATE INDEX ix_search_document_occurred ON search_document (occurred_at)")

    for statement in REFRESH_FUNCTIONS:
        op.execute(statement)
    for table, function, body in TRIGGERS:
        op.execute(
            f"CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$ "
            f"BEGIN {body} RETURN NULL; END $$"
        )
        op.execute(
            f"CREATE TRIGGER {function} AFTER INSERT OR UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {function}()"
        )

    # Carga inicial com o que já está no espelho e nos dados do dev.
    op.execute("SELECT search_refresh_issue(key) FROM jira_issue")
    op.execute("SELECT search_refresh_comment(id) FROM jira_comment")
    op.execute("SELECT search_refresh_pull_request(repo_slug, id) FROM bb_pull_request")
    op.execute("SELECT search_refresh_context(id) FROM task_context")
    op.execute("SELECT search_refresh_note(id) FROM note")


def downgrade() -> None:
    for table, function, _ in TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {function} ON {table}")
        op.execute(f"DROP FUNCTION IF EXISTS {function}()")
    for name in (
        "search_refresh_note(bigint)",
        "search_refresh_context(bigint)",
        "search_refresh_pull_request(text, integer)",
        "search_refresh_comment(text)",
        "search_refresh_issue(text)",
        "search_upsert(text, text, text, text[], text, text, text, jsonb, timestamptz)",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {name}")
    op.execute("DROP TABLE IF EXISTS search_document")
