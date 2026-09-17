"""F11 e B10 — a Home e a timeline.

O cenário é o real de 14/09/2026: a Sprint 73 - Growth terminou em 11/09 e continuou
`active`, e a Sprint 74 começa hoje.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from services import home_service

SITE = "https://weon.atlassian.net"
ME = "acc-me"
TZ = "America/Sao_Paulo"
NOW = datetime(2026, 9, 14, 15, 0, tzinfo=UTC)


async def _issue(pool, key, summary, *, status, category, **kw):
    await pool.execute(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, summary, status, status_category,
                                priority, assignee_account_id, assignee_name, story_points,
                                due_date, parent_key, created_at, updated_at, resolved_at, raw)
        VALUES ($1, $1, 'WAI', $2, $3, $4, $5, 'Medium', $6, 'Dev', $7, $8, $9,
                '2026-09-01T10:00:00+00'::timestamptz, $10, $11, '{}')
        """,
        key,
        kw.get("type", "Tarefa"),
        summary,
        status,
        category,
        kw.get("assignee", ME),
        kw.get("points"),
        kw.get("due"),
        kw.get("parent"),
        kw.get("updated", NOW),
        kw.get("resolved"),
    )


async def _sprint(pool, sprint_id, name, state, keys, *, start, end):
    await pool.execute(
        """
        INSERT INTO jira_sprint (id, board_id, name, state, squad, start_date, end_date, in_scope)
        VALUES ($1, 144, $2, $3, 'Growth', $4, $5, true)
        """,
        sprint_id,
        name,
        state,
        start,
        end,
    )
    await pool.executemany(
        "INSERT INTO jira_sprint_issue (sprint_id, issue_key) VALUES ($1, $2)",
        [(sprint_id, k) for k in keys],
    )


async def _transition(pool, changelog_id, key, before, after, when):
    await pool.execute(
        """
        INSERT INTO jira_status_transition (changelog_id, issue_key, from_status, to_status,
                                            changed_at)
        VALUES ($1, $2, $3, $4, $5)
        """,
        changelog_id,
        key,
        before,
        after,
        when,
    )


@pytest.fixture
async def mirror(db_pool, credential_store):
    credential_store.set(
        "jira", {"site_url": SITE, "email": "d@w.com", "api_token": "t" * 24, "account_id": ME}
    )
    await _issue(
        db_pool,
        "WAI-100",
        "Coleta consolidada",
        status="Em Desenvolvimento",
        category="indeterminate",
        type="Épico",
    )
    await _issue(
        db_pool,
        "WAI-1",
        "Endpoint da coleta",
        status="DISPONIVEL PARA REVIEW",
        category="new",
        points=5,
        parent="WAI-100",
    )
    await _issue(
        db_pool,
        "WAI-2",
        "Migration da coleta",
        status="Concluído",
        category="done",
        points=3,
        parent="WAI-100",
        resolved=datetime(2026, 9, 10, 20, 0, tzinfo=UTC),
    )
    await _issue(
        db_pool,
        "WAI-3",
        "Tela da coleta",
        status="Disponivel para análise",
        category="new",
    )
    await _issue(
        db_pool,
        "WAI-9",
        "De outro dev",
        status="Em Desenvolvimento",
        category="indeterminate",
        assignee="acc-outro",
    )
    await _sprint(
        db_pool,
        3995,
        "Sprint 73 - Growth",
        "active",
        ["WAI-100", "WAI-1", "WAI-2", "WAI-3", "WAI-9"],
        start=datetime(2026, 9, 9, 13, 0, tzinfo=UTC),
        end=datetime(2026, 9, 11, 3, 0, tzinfo=UTC),
    )
    await _sprint(
        db_pool,
        3997,
        "Sprint 74 - Growth",
        "future",
        [],
        start=datetime(2026, 9, 14, 3, 0, tzinfo=UTC),
        end=datetime(2026, 9, 19, 2, 59, tzinfo=UTC),
    )
    await _transition(
        db_pool,
        "1",
        "WAI-1",
        "Disponivel para análise",
        "Em Desenvolvimento",
        datetime(2026, 9, 9, 14, 0, tzinfo=UTC),
    )
    await _transition(
        db_pool,
        "2",
        "WAI-1",
        "Em Desenvolvimento",
        "DISPONIVEL PARA REVIEW",
        datetime(2026, 9, 10, 18, 0, tzinfo=UTC),
    )
    return db_pool


# --- Home ----------------------------------------------------------------------------


async def test_home_mostra_a_sprint_vencida_com_progresso_ponderado(mirror, credential_store):
    home = await home_service.get_home(mirror, credential_store, timezone=TZ, now=NOW)

    assert home.today == date(2026, 9, 14)
    assert [s.name for s in home.sprints] == ["Sprint 73 - Growth"]
    sprint = home.sprints[0]
    assert sprint.overdue_active is True
    assert sprint.expected == 1.0
    # (0.7×5 + 1.0×3 + 0.0×1) / 9 — o épico e a tarefa do outro dev ficam de fora.
    assert round(sprint.real, 4) == round((0.7 * 5 + 3) / 9, 4)
    assert (sprint.issue_count, sprint.done_count) == (3, 1)


async def test_home_traz_o_topo_das_pendencias_da_semana(mirror, credential_store):
    await _issue(
        mirror,
        "WAI-4",
        "Atrasada",
        status="Em Desenvolvimento",
        category="indeterminate",
        due=date(2026, 9, 1),
    )
    await _issue(
        mirror,
        "WAI-5",
        "Analisar e fatiar a: Relatórios",
        status="Disponivel para análise",
        category="new",
    )
    home = await home_service.get_home(mirror, credential_store, timezone=TZ, now=NOW)

    assert [i.key for i in home.pending.overdue] == ["WAI-4"]
    assert [i.key for i in home.pending.slicing] == ["WAI-5"]
    # WAI-3 e WAI-1 estão em sprint ativa: não contam como "sem sprint".
    assert [i.key for i in home.pending.without_sprint] == ["WAI-4"]
    assert home.pending.total == 3


async def test_lembrete_relevante_vencido_fixado_ou_da_sprint(
    mirror, credential_store, client, db_app
):
    await client.post(
        "/api/notes", json={"title": "Venceu e não vi", "remind_at": "2026-09-13T09:00:00-03:00"}
    )
    await client.post("/api/notes", json={"title": "Fixado", "pinned": True})
    await client.post("/api/notes", json={"title": "Da tarefa da sprint", "issue_keys": ["WAI-1"]})
    await client.post("/api/notes", json={"title": "Solto e sem hora"})
    await client.post(
        "/api/notes", json={"title": "Semana que vem", "remind_at": "2026-09-25T09:00:00-03:00"}
    )

    home = await home_service.get_home(mirror, credential_store, timezone=TZ, now=NOW)
    titles = [n.title for n in home.reminders]

    assert "Venceu e não vi" == titles[0]
    assert set(titles) == {"Venceu e não vi", "Fixado", "Da tarefa da sprint"}


async def test_home_pela_api_responde_com_o_esqueleto(mirror, client, db_app):
    response = await client.get("/api/home", params={"tz": TZ})
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["filtered_by_assignee"] is True
    assert set(data) >= {"today", "sprints", "pending", "reminders", "week_start", "week_end"}


async def test_fuso_desconhecido_e_recusado(mirror, client, db_app):
    assert (await client.get("/api/home", params={"tz": "Marte/Olympus"})).status_code == 422


# --- Timeline ------------------------------------------------------------------------


async def test_timeline_traz_a_sprint_atual_e_a_proxima(mirror, credential_store):
    timeline = await home_service.get_timeline(mirror, credential_store, timezone=TZ, now=NOW)

    assert [(s.name, s.state) for s in timeline.sprints] == [
        ("Sprint 73 - Growth", "active"),
        ("Sprint 74 - Growth", "future"),
    ]
    assert timeline.sprints[0].overdue_active is True
    # A 73 venceu e a 74 começa hoje: a "atual" é a que contém hoje.
    assert [s.current for s in timeline.sprints] == [False, True]

    sem_proxima = await home_service.get_timeline(
        mirror, credential_store, include_next=False, timezone=TZ, now=NOW
    )
    assert [s.id for s in sem_proxima.sprints] == [3995]


async def test_linhas_agrupadas_por_pai_com_sem_pai_no_fim(mirror, credential_store):
    timeline = await home_service.get_timeline(mirror, credential_store, timezone=TZ, now=NOW)

    assert [g.key for g in timeline.groups] == ["WAI-100", None]
    # Dentro do grupo, quem começou antes vem em cima: a WAI-2 nunca saiu da análise,
    # então sua barra nasce no início da sprint.
    assert [i.key for i in timeline.groups[0].issues] == ["WAI-2", "WAI-1"]
    assert timeline.groups[0].summary == "Coleta consolidada"
    assert timeline.groups[1].summary == "Sem pai"
    # Épico e tarefa de outro dev não viram linha.
    assert all(i.key not in {"WAI-100", "WAI-9"} for g in timeline.groups for i in g.issues)


async def test_barra_comeca_na_saida_da_analise_e_segmenta_por_status(mirror, credential_store):
    timeline = await home_service.get_timeline(mirror, credential_store, timezone=TZ, now=NOW)
    issue = next(i for g in timeline.groups for i in g.issues if i.key == "WAI-1")

    assert issue.started is True
    assert issue.start == datetime(2026, 9, 9, 14, 0, tzinfo=UTC)
    # Não terminou: a barra é projetada até o fim da sprint.
    assert issue.projected is True
    assert [(s.status, s.stage_id) for s in issue.segments] == [
        ("Em Desenvolvimento", "desenvolvimento"),
        ("DISPONIVEL PARA REVIEW", "review"),
    ]
    assert (
        issue.segments[0].end == issue.segments[1].start == datetime(2026, 9, 10, 18, 0, tzinfo=UTC)
    )
    assert issue.progress.value == 0.7
    assert issue.progress.source == "status"


async def test_tarefa_concluida_fecha_a_barra_no_resolved_at(mirror, credential_store):
    timeline = await home_service.get_timeline(mirror, credential_store, timezone=TZ, now=NOW)
    issue = next(i for g in timeline.groups for i in g.issues if i.key == "WAI-2")

    assert issue.projected is False
    assert issue.end == datetime(2026, 9, 10, 20, 0, tzinfo=UTC)


async def test_tarefa_sem_transicao_comeca_no_inicio_da_sprint_com_um_segmento(
    mirror, credential_store
):
    timeline = await home_service.get_timeline(mirror, credential_store, timezone=TZ, now=NOW)
    issue = next(i for g in timeline.groups for i in g.issues if i.key == "WAI-3")

    assert issue.started is False
    assert issue.start.astimezone(UTC).date() == date(2026, 9, 9)
    assert [s.status for s in issue.segments] == ["Disponivel para análise"]


async def test_setas_de_bloqueio_so_entre_tarefas_desenhadas(mirror, credential_store):
    await mirror.executemany(
        """
        INSERT INTO jira_issue_link (id, source_key, target_key, link_type, direction, label)
        VALUES ($1, $2, $3, 'Blocks', 'outward', 'bloqueia')
        """,
        [("l1", "WAI-1", "WAI-3"), ("l2", "WAI-1", "WAI-9")],
    )
    timeline = await home_service.get_timeline(mirror, credential_store, timezone=TZ, now=NOW)

    assert [(link.source, link.target) for link in timeline.links] == [("WAI-1", "WAI-3")]


async def test_janela_da_timeline_cobre_sprints_e_barras(mirror, credential_store):
    timeline = await home_service.get_timeline(mirror, credential_store, timezone=TZ, now=NOW)

    assert timeline.start == date(2026, 9, 9)
    assert timeline.end >= date(2026, 9, 18)


async def test_barra_nao_concluida_em_sprint_vencida_chega_ate_hoje(mirror, credential_store):
    # A Sprint 73 acabou em 11/09 e hoje é 14/09: parar a barra no fim da sprint daria
    # a impressão de que a tarefa parou junto com ela.
    timeline = await home_service.get_timeline(mirror, credential_store, timezone=TZ, now=NOW)
    issue = next(i for g in timeline.groups for i in g.issues if i.key == "WAI-1")

    assert issue.end == NOW.astimezone(issue.end.tzinfo)
    assert issue.segments[-1].end == issue.end


async def test_concluida_sem_resolved_at_fecha_na_transicao_para_a_etapa_final(
    mirror, credential_store
):
    # Neste workflow o Jira nunca preenche `resolutiondate`: sem esta regra, toda tarefa
    # concluída teria a barra correndo até hoje.
    await mirror.execute("UPDATE jira_issue SET resolved_at = NULL WHERE key = 'WAI-2'")
    await _transition(
        mirror,
        "3",
        "WAI-2",
        "DISPONIVEL PARA TESTES",
        "Concluído",
        datetime(2026, 9, 10, 21, 0, tzinfo=UTC),
    )
    timeline = await home_service.get_timeline(mirror, credential_store, timezone=TZ, now=NOW)
    issue = next(i for g in timeline.groups for i in g.issues if i.key == "WAI-2")

    assert issue.projected is False
    assert issue.end == datetime(2026, 9, 10, 21, 0, tzinfo=UTC)


async def test_concluida_sem_transicao_registrada_cai_no_updated_at(mirror, credential_store):
    await mirror.execute(
        """
        UPDATE jira_issue SET resolved_at = NULL, updated_at = '2026-09-10T12:00:00+00'
        WHERE key = 'WAI-2'
        """
    )
    timeline = await home_service.get_timeline(mirror, credential_store, timezone=TZ, now=NOW)
    issue = next(i for g in timeline.groups for i in g.issues if i.key == "WAI-2")

    assert issue.projected is False
    assert issue.end.astimezone(UTC) == datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


# --- Sprints com trabalho meu em aberto ----------------------------------------------


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


async def test_sprint_sem_tarefa_minha_em_aberto_sai_da_home(mirror, credential_store):
    await mirror.execute(
        "UPDATE jira_issue SET status = 'Concluído', status_category = 'done' "
        "WHERE key IN ('WAI-1', 'WAI-3')"
    )
    home = await home_service.get_home(mirror, credential_store, timezone=TZ, now=NOW)

    assert home.sprints == []


async def test_sprint_vencida_fica_enquanto_tiver_tarefa_minha_por_fazer(mirror, credential_store):
    # A 73 passou da data e continua `active`: enquanto sobrar trabalho meu, ela fica.
    home = await home_service.get_home(mirror, credential_store, timezone=TZ, now=NOW)
    assert [s.sprint_id for s in home.sprints] == [3995]
    assert home.sprints[0].overdue_active is True


async def test_epico_aberto_sozinho_nao_segura_a_sprint_na_home(mirror, credential_store):
    await mirror.execute(
        "UPDATE jira_issue SET status = 'Concluído', status_category = 'done' "
        "WHERE key IN ('WAI-1', 'WAI-3')"
    )
    # WAI-100 é Épico e segue em aberto: contêiner não é trabalho.
    home = await home_service.get_home(mirror, credential_store, timezone=TZ, now=NOW)
    assert home.sprints == []


# --- Linha de tarefas atualizadas ----------------------------------------------------


async def test_atualizacoes_da_sprint_trazem_so_o_que_outro_mexeu_nas_ultimas_48h(
    mirror, credential_store
):
    await _event(mirror, "a", "WAI-1", "status", "Em Review", NOW - timedelta(hours=2))
    await _event(mirror, "b", "WAI-1", "comment", "Achei um caso", NOW - timedelta(hours=5))
    await _event(
        mirror, "c", "WAI-3", "pr_approved", "PR 7", NOW - timedelta(hours=30), source="bitbucket"
    )
    # Fora da janela e coisa minha não entram.
    await _event(mirror, "d", "WAI-2", "status", "Concluído", NOW - timedelta(days=4))
    await _event(
        mirror, "e", "WAI-3", "status", "Em Desenvolvimento", NOW - timedelta(hours=1), mine=True
    )
    # Épico não vira card.
    await _event(mirror, "f", "WAI-100", "comment", "no épico", NOW - timedelta(hours=1))

    home = await home_service.get_home(mirror, credential_store, timezone=TZ, now=NOW)
    updates = home.sprints[0].updates

    # Uma linha por tarefa, a mais recente primeiro, com o último evento e a contagem.
    assert [(u.key, u.kind, u.event_count) for u in updates] == [
        ("WAI-1", "status", 2),
        ("WAI-3", "pr_approved", 1),
    ]
    assert updates[0].title == "Em Review"
    assert updates[0].actor_name == "Outro Dev"
    assert updates[0].url == f"{SITE}/browse/WAI-1"
    assert updates[1].source == "bitbucket"


async def test_sem_mexida_de_ninguem_a_linha_fica_vazia(mirror, credential_store):
    await _event(mirror, "e", "WAI-3", "status", "x", NOW - timedelta(hours=1), mine=True)
    home = await home_service.get_home(mirror, credential_store, timezone=TZ, now=NOW)

    assert home.sprints[0].updates == []
