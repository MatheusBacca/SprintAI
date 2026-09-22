"""As notificações de tarefa do sino — `GET /api/notifications/updates`.

A janela é relativa a agora, então o cenário é montado com deslocamentos do relógio
de verdade: é o que o endpoint vê sem injetar tempo.
"""

from datetime import UTC, datetime, timedelta

import pytest

SITE = "https://weon.atlassian.net"
ME = "acc-me"
AGORA = datetime.now(UTC)


async def _issue(pool, key, summary, *, kind="Tarefa", assignee=ME):
    await pool.execute(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, summary, status, status_category,
                                assignee_account_id, assignee_name, story_points,
                                created_at, updated_at, raw)
        VALUES ($1, $1, 'WAI', $2, $3, 'Em Desenvolvimento', 'indeterminate', $4, 'Dev', 5,
                $5, $5, '{}')
        """,
        key,
        kind,
        summary,
        assignee,
        AGORA,
    )


async def _sprint(pool, sprint_id, name, state, keys):
    await pool.execute(
        """
        INSERT INTO jira_sprint (id, board_id, name, state, squad, start_date, end_date, in_scope)
        VALUES ($1, 144, $2, $3, 'Growth', $4, $5, true)
        """,
        sprint_id,
        name,
        state,
        AGORA - timedelta(days=4),
        AGORA - timedelta(days=1),
    )
    await pool.executemany(
        "INSERT INTO jira_sprint_issue (sprint_id, issue_key) VALUES ($1, $2)",
        [(sprint_id, k) for k in keys],
    )


async def _event(pool, dedupe, key, kind, title, when, *, mine=False, source="jira"):
    await pool.execute(
        """
        INSERT INTO activity_event (dedupe_key, source, kind, issue_key, actor_name,
                                    actor_is_me, occurred_at, title)
        VALUES ($1, $2, $3, $4, 'Outro Dev', $5, $6, $7)
        """,
        dedupe,
        source,
        kind,
        key,
        mine,
        when,
        title,
    )


@pytest.fixture
async def mirror(db_pool, credential_store):
    credential_store.set(
        "jira", {"site_url": SITE, "email": "d@w.com", "api_token": "t" * 24, "account_id": ME}
    )
    await _issue(db_pool, "WAI-100", "Coleta consolidada", kind="Épico")
    await _issue(db_pool, "WAI-1", "Endpoint da coleta")
    await _issue(db_pool, "WAI-2", "Tela da coleta")
    await _issue(db_pool, "WAI-9", "De outro dev", assignee="acc-outro")
    await _issue(db_pool, "WAI-50", "Da sprint fechada")
    await _sprint(db_pool, 3995, "Sprint 73 - Growth", "active", ["WAI-100", "WAI-1", "WAI-2", "WAI-9"])
    await _sprint(db_pool, 3990, "Sprint 72 - Growth", "closed", ["WAI-50"])
    return db_pool


async def _updates(client):
    response = await client.get("/api/notifications/updates")
    assert response.status_code == 200
    return response.json()["updates"]


async def test_sino_traz_as_tarefas_da_sprint_ativa_que_outro_mexeu(mirror, db_app, client):
    await _event(mirror, "a", "WAI-1", "status", "Em Review", AGORA - timedelta(hours=5))
    await _event(mirror, "b", "WAI-1", "comment", "Achei um caso", AGORA - timedelta(hours=2))
    await _event(
        mirror, "c", "WAI-2", "pr_approved", "PR 7", AGORA - timedelta(hours=30), source="bitbucket"
    )

    updates = await _updates(client)

    # Uma linha por tarefa, a mexida mais recente primeiro, com o último evento e a contagem.
    assert [(u["key"], u["kind"], u["event_count"]) for u in updates] == [
        ("WAI-1", "comment", 2),
        ("WAI-2", "pr_approved", 1),
    ]
    assert updates[0]["actor_name"] == "Outro Dev"
    assert updates[0]["summary"] == "Endpoint da coleta"
    assert updates[0]["url"] == f"{SITE}/browse/WAI-1"
    # A sprint vai junto: é nela que o clique abre a tela da Sprint.
    assert (updates[0]["sprint_id"], updates[0]["sprint_name"]) == (3995, "Sprint 73 - Growth")


async def test_o_que_eu_mesmo_fiz_e_o_que_passou_da_janela_nao_notifica(mirror, db_app, client):
    await _event(mirror, "a", "WAI-1", "status", "Em Review", AGORA - timedelta(hours=1), mine=True)
    await _event(mirror, "b", "WAI-2", "comment", "Antigo", AGORA - timedelta(hours=60))

    assert await _updates(client) == []


async def test_epico_tarefa_de_outro_dev_e_sprint_fechada_ficam_de_fora(mirror, db_app, client):
    await _event(mirror, "a", "WAI-100", "comment", "no épico", AGORA - timedelta(hours=1))
    await _event(mirror, "b", "WAI-9", "status", "Em Review", AGORA - timedelta(hours=1))
    await _event(mirror, "c", "WAI-50", "status", "Concluído", AGORA - timedelta(hours=1))

    assert await _updates(client) == []
