from datetime import UTC, datetime, timedelta

import pytest

from services.search_service import query_terms, snippet

SITE = "https://weon.atlassian.net"
OLD = datetime.now(UTC) - timedelta(days=60)


async def _issue(pool, key, summary, description="", updated=None, labels=()):
    await pool.execute(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, summary, description_text,
                                status, status_category, labels, created_at, updated_at, raw)
        VALUES ($1, $1, 'WAI', 'Tarefa', $2, $3, 'Em Desenvolvimento', 'indeterminate', $4,
                now(), $5, '{}')
        """,
        key,
        summary,
        description,
        list(labels),
        updated or datetime.now(UTC),
    )


async def _comment(pool, comment_id, key, body, author="Maycon"):
    await pool.execute(
        """
        INSERT INTO jira_comment (id, issue_key, author_name, body_text, created_at)
        VALUES ($1, $2, $3, $4, now())
        """,
        comment_id,
        key,
        author,
        body,
    )


async def _pr(pool, pr_id, title, keys, description="", repo="monitoria"):
    await pool.execute(
        """
        INSERT INTO bb_pull_request (repo_slug, id, title, description, state, source_branch,
                                     issue_keys, url, updated_on)
        VALUES ($1, $2, $3, $4, 'OPEN', $5, $6, $7, now())
        """,
        repo,
        pr_id,
        title,
        description,
        f"feature/{keys[0]}" if keys else "feature/x",
        keys,
        f"https://bitbucket.org/weonrepo/{repo}/pull-requests/{pr_id}",
    )


@pytest.fixture
async def api(db_app, client, credential_store, db_pool):
    credential_store.set("jira", {"site_url": SITE, "email": "d@w.com", "api_token": "t" * 24})
    await _issue(db_pool, "WAI-1", "Retry exponencial no client", "Integração com a OpenAI")
    await _issue(db_pool, "WAI-2", "Fila de reprocessamento", "cita a WAI-1 no texto")
    await _issue(db_pool, "WAI-3", "Tarefa antiga de integração", updated=OLD, labels=["legado"])
    await _comment(db_pool, "c1", "WAI-2", "Precisamos de retry com jitter aqui", author="Ana")
    await _pr(db_pool, 10, "WAI-1 Retry exponencial", ["WAI-1"], "Adiciona backoff")
    return client


async def test_indice_acompanha_escritas_por_trigger(api, db_pool):
    docs = await db_pool.fetch("SELECT entity_type, entity_id FROM search_document ORDER BY 1, 2")
    assert [(d["entity_type"], d["entity_id"]) for d in docs] == [
        ("comment", "c1"),
        ("issue", "WAI-1"),
        ("issue", "WAI-2"),
        ("issue", "WAI-3"),
        ("pull_request", "monitoria#10"),
    ]

    # Contexto e lembrete entram pelo caminho normal da API, com relações e vínculos.
    ctx = await api.post(
        "/api/contexts",
        json={
            "issue_key": "WAI-2",
            "kind": "open_point",
            "title": "Definir jitter",
            "relations": [{"issue_key": "WAI-9"}],
        },
    )
    note = await api.post(
        "/api/notes", json={"title": "Lembrar do jitter", "issue_keys": ["WAI-7"]}
    )
    row = await db_pool.fetchrow(
        "SELECT issue_keys, meta FROM search_document WHERE entity_type = 'context'"
    )
    assert sorted(row["issue_keys"]) == ["WAI-2", "WAI-9"]
    assert row["meta"]["kind"] == "open_point"
    await api.post(f"/api/contexts/{ctx.json()['id']}/resolve", json={"issue_key": "WAI-5"})
    row = await db_pool.fetchrow(
        "SELECT issue_keys, meta FROM search_document WHERE entity_type = 'context'"
    )
    assert sorted(row["issue_keys"]) == ["WAI-2", "WAI-5", "WAI-9"]
    assert row["meta"]["status"] == "resolved"
    assert await db_pool.fetchval(
        "SELECT issue_keys FROM search_document WHERE entity_type = 'note'"
    ) == ["WAI-7"]

    # Atualização e exclusão refletem na hora (inclusive em cascata).
    await db_pool.execute("UPDATE jira_issue SET summary = 'Resumo novo' WHERE key = 'WAI-2'")
    assert (
        await db_pool.fetchval("SELECT title FROM search_document WHERE entity_id = 'WAI-2'")
        == "Resumo novo"
    )
    await db_pool.execute("DELETE FROM jira_issue WHERE key = 'WAI-2'")
    await api.delete(f"/api/notes/{note.json()['id']}")
    await api.delete(f"/api/contexts/{ctx.json()['id']}")
    remaining = await db_pool.fetch("SELECT entity_id FROM search_document")
    assert sorted(r["entity_id"] for r in remaining) == ["WAI-1", "WAI-3", "monitoria#10"]


async def test_busca_agrupa_por_tipo_na_ordem_da_tela(api):
    data = (await api.get("/api/search", params={"q": "retry"})).json()

    assert data["total"] == 3
    assert [(g["type"], g["total"]) for g in data["groups"]] == [
        ("issue", 1),
        ("comment", 1),
        ("pull_request", 1),
    ]
    issue, comment, pr = (g["items"][0] for g in data["groups"])
    assert issue["title"] == "Retry exponencial no client"
    assert issue["issue_url"] == f"{SITE}/browse/WAI-1"
    assert issue["meta"]["status"] == "Em Desenvolvimento"
    assert comment["title"] == "Comentário de Ana"
    assert (comment["issue_key"], comment["issue_summary"]) == ("WAI-2", "Fila de reprocessamento")
    assert "retry com jitter" in comment["snippet"]
    assert pr["meta"]["url"].endswith("/pull-requests/10")
    assert pr["issue_in_mirror"] is True


async def test_sem_acento_trecho_parcial_e_chave(api):
    no_accent = (await api.get("/api/search", params={"q": "integracao"})).json()
    assert {i["id"] for g in no_accent["groups"] for i in g["items"]} == {"WAI-1", "WAI-3"}

    partial = (await api.get("/api/search", params={"q": "reprocess"})).json()
    assert [i["id"] for g in partial["groups"] for i in g["items"]] == ["WAI-2"]

    by_key = (await api.get("/api/search", params={"q": "wai-1", "type": "issue"})).json()
    # A própria tarefa (chave exata) vem antes da que só cita a chave no texto.
    assert [i["id"] for i in by_key["groups"][0]["items"]] == ["WAI-1", "WAI-2"]

    labels = (await api.get("/api/search", params={"q": "legado"})).json()
    assert labels["groups"][0]["items"][0]["id"] == "WAI-3"


async def test_filtros_de_tipo_periodo_paginacao_e_minimo(api):
    recent = (await api.get("/api/search", params={"q": "integracao", "period": "30d"})).json()
    assert [i["id"] for g in recent["groups"] for i in g["items"]] == ["WAI-1"]

    types = await api.get(
        "/api/search", params=[("q", "retry"), ("type", "comment"), ("type", "pull_request")]
    )
    assert [g["type"] for g in types.json()["groups"]] == ["comment", "pull_request"]

    page1 = (await api.get("/api/search", params={"q": "wai", "type": "issue", "limit": 2})).json()
    page2 = (
        await api.get("/api/search", params={"q": "wai", "type": "issue", "limit": 2, "offset": 2})
    ).json()
    assert page1["groups"][0]["total"] == page2["groups"][0]["total"] == 3
    ids = [i["id"] for i in page1["groups"][0]["items"] + page2["groups"][0]["items"]]
    assert sorted(ids) == ["WAI-1", "WAI-2", "WAI-3"]

    assert (await api.get("/api/search", params={"q": " a "})).json() == {
        "query": "a",
        "total": 0,
        "groups": [],
    }
    assert (await api.get("/api/search", params={"q": "x", "type": "bug"})).status_code == 422


def test_snippet_em_volta_do_termo_sem_acento():
    text = "a" * 300 + " Integração com OpenAI " + "b" * 300
    cut = snippet(text, ["integracao"], radius=40)
    assert cut.startswith("…") and cut.endswith("…")
    assert "Integração" in cut
    assert cut.index("Integração") <= 25
    assert snippet("curto e direto", ["nada"]) == "curto e direto"
    assert snippet("", ["x"]) == ""
    assert query_terms('retry or "exponencial" -client a') == ["retry", "exponencial", "client"]
