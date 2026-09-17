from datetime import UTC, date, datetime, timedelta

import pytest

from services.week_service import get_week, week_bounds

SITE = "https://weon.atlassian.net"
ME = "acc-me"
DAY = date(2026, 9, 16)  # quarta-feira
IN_WEEK = datetime(2026, 9, 17, 15, 0, tzinfo=UTC)
BEFORE = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


async def _issue(pool, key, summary, *, assignee=ME, category="indeterminate", **kw):
    await pool.execute(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, summary, status, status_category,
                                priority, assignee_account_id, due_date, parent_key, created_at,
                                updated_at, resolved_at, raw)
        VALUES ($1, $1, 'WAI', $2, $3, $4, $5, $6, $7, $8, $9, now(), $10, $11, '{}')
        """,
        key,
        kw.get("type", "Tarefa"),
        summary,
        kw.get("status", "Disponivel para análise"),
        category,
        kw.get("priority", "Medium"),
        assignee,
        kw.get("due"),
        kw.get("parent"),
        kw.get("updated", datetime.now(UTC)),
        kw.get("resolved"),
    )


async def _sprint(pool, sprint_id, name, state, keys, start=None):
    await pool.execute(
        "INSERT INTO jira_sprint (id, board_id, name, state, start_date) VALUES ($1, 144, $2, $3, $4)",
        sprint_id,
        name,
        state,
        start,
    )
    await pool.executemany(
        "INSERT INTO jira_sprint_issue (sprint_id, issue_key) VALUES ($1, $2)",
        [(sprint_id, k) for k in keys],
    )


@pytest.fixture
async def api(db_app, client, credential_store, db_pool):
    credential_store.set(
        "jira", {"site_url": SITE, "email": "d@w.com", "api_token": "t" * 24, "account_id": ME}
    )
    await _issue(db_pool, "WAI-100", "Épico de integrações", type="Épico")
    await _issue(db_pool, "WAI-1", "Solta de alta prioridade", priority="High", parent="WAI-100")
    await _issue(db_pool, "WAI-2", "Sobrou da sprint fechada", priority="Low")
    await _issue(db_pool, "WAI-3", "Na sprint ativa", due=date(2026, 9, 18))
    await _issue(db_pool, "WAI-4", "De outro dev sem sprint", assignee="acc-outro")
    await _issue(db_pool, "WAI-5", "Concluída sem sprint", category="done")
    await _issue(db_pool, "WAI-6", "Atrasada", due=date(2026, 9, 1))
    await _issue(db_pool, "WAI-7", "Prazo na semana já entregue", category="done", due=DAY)
    await _issue(db_pool, "WAI-8", "Analisar e fatiar a: Nova regra", status="Em Desenvolvimento")
    await _issue(
        db_pool,
        "WAI-9",
        "Analisar e Fatiar - Concluído nesta semana",
        category="done",
        resolved=IN_WEEK,
    )
    await _issue(db_pool, "WAI-10", "Analisar e fatiar a: Antigo", category="done", resolved=BEFORE)
    await _sprint(
        db_pool, 1, "Sprint 72", "closed", ["WAI-2"], start=datetime(2026, 8, 1, tzinfo=UTC)
    )
    await _sprint(db_pool, 2, "Sprint 73", "active", ["WAI-3", "WAI-8"])
    await db_pool.execute(
        "INSERT INTO task_context (issue_key, kind, title) VALUES ('WAI-1', 'open_point', 'x')"
    )
    return client


def test_semana_vai_de_segunda_a_domingo():
    assert week_bounds(DAY) == (date(2026, 9, 14), date(2026, 9, 20))
    assert week_bounds(date(2026, 9, 20)) == (date(2026, 9, 14), date(2026, 9, 20))
    assert week_bounds(date(2026, 9, 21)) == (date(2026, 9, 21), date(2026, 9, 27))


async def test_blocos_da_semana(api, db_pool):
    note = await api.post(
        "/api/notes", json={"title": "Na semana", "remind_at": "2026-09-19T12:00:00-03:00"}
    )
    await api.post(
        "/api/notes", json={"title": "Semana que vem", "remind_at": "2026-09-21T09:00:00-03:00"}
    )
    await api.post(
        "/api/notes", json={"title": "Venceu antes", "remind_at": "2026-09-08T09:00:00-03:00"}
    )
    # Domingo 23h em São Paulo ainda é a semana (em UTC já seria segunda).
    await api.post(
        "/api/notes", json={"title": "Domingo à noite", "remind_at": "2026-09-20T23:00:00-03:00"}
    )

    response = await api.get("/api/week", params={"day": "2026-09-16", "tz": "America/Sao_Paulo"})
    assert response.status_code == 200, response.text
    data = response.json()

    assert (data["start"], data["end"], data["timezone"]) == (
        "2026-09-14",
        "2026-09-20",
        "America/Sao_Paulo",
    )
    assert data["filtered_by_assignee"] is True

    # Sobra de sprint fechada primeiro; sem épico, sem card de fatiar, sem de outro dev.
    without = data["without_sprint"]
    assert [i["key"] for i in without] == ["WAI-2", "WAI-1", "WAI-6"]
    assert (without[0]["sprint_name"], without[0]["sprint_state"]) == ("Sprint 72", "closed")
    assert without[1]["parent_summary"] == "Épico de integrações"
    assert without[1]["open_points"] == 1
    assert without[1]["url"] == f"{SITE}/browse/WAI-1"
    assert without[1]["pr"]["status"] == "sem_pr"

    assert [i["key"] for i in data["due"]] == ["WAI-7", "WAI-3"]
    assert [i["key"] for i in data["overdue"]] == ["WAI-6"]
    assert [i["key"] for i in data["slicing"]] == ["WAI-8", "WAI-9"]
    assert data["slicing"][0]["sprint_name"] == "Sprint 73"

    assert [n["title"] for n in data["reminders"]] == ["Na semana", "Domingo à noite"]
    assert data["reminders"][0]["id"] == note.json()["id"]
    assert [n["title"] for n in data["pending_reminders"]] == ["Venceu antes"]


async def test_sem_account_id_nao_filtra_por_responsavel(api, db_pool, credential_store):
    credential_store.set("jira", {"site_url": SITE, "email": "d@w.com", "api_token": "t" * 24})
    data = (await api.get("/api/week", params={"day": "2026-09-16"})).json()
    assert data["filtered_by_assignee"] is False
    assert "WAI-4" in [i["key"] for i in data["without_sprint"]]


async def test_padrao_e_hoje_e_fuso_invalido(api, db_pool, credential_store):
    data = await get_week(
        db_pool,
        credential_store,
        day=None,
        timezone="America/Sao_Paulo",
        now=datetime(2026, 9, 21, 2, 0, tzinfo=UTC),  # domingo 23h em São Paulo
    )
    assert (data.today, data.start) == (date(2026, 9, 20), date(2026, 9, 14))

    response = await api.get("/api/week", params={"tz": "Marte/Olympus"})
    assert response.status_code == 422
    assert "Fuso horário desconhecido" in response.text
    assert (await api.get("/api/week", params={"day": "ontem"})).status_code == 422


def test_week_bounds_cobre_virada_de_ano():
    start, end = week_bounds(date(2027, 1, 1))
    assert (start, end) == (date(2026, 12, 28), date(2027, 1, 3))
    assert end - start == timedelta(days=6)
