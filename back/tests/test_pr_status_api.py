from datetime import UTC, datetime, timedelta

import pytest

from repositories import activity_repo, bitbucket_repo

T0 = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)


def row(repo, pid, state, branch, keys, *, participants=(), build=None, title="PR", draft=False):
    return {
        "repo_slug": repo,
        "id": pid,
        "title": title,
        "description": None,
        "state": state,
        "draft": draft,
        "author_name": "Dev",
        "source_branch": branch,
        "source_commit": "abc",
        "destination_branch": "main",
        "participants": list(participants),
        "comment_count": 2,
        "task_count": 0,
        "build_status": build,
        "issue_keys": list(keys),
        "url": f"https://bitbucket.org/weonrepo/{repo}/pull-requests/{pid}",
        "created_on": T0,
        "updated_on": T0,
    }


@pytest.fixture
async def seeded(db_pool):
    await bitbucket_repo.upsert_pull_requests(
        db_pool,
        [
            row(
                "supervisor-web",
                10,
                "OPEN",
                "feature/WAI-8278",
                ["WAI-8278"],
                participants=[
                    {
                        "role": "REVIEWER",
                        "approved": False,
                        "state": "changes_requested",
                        "name": "Revisor",
                    }
                ],
                build="FAILED",
            ),
            row("weaction-api", 20, "MERGED", "feature/WAI-8278", ["WAI-8278"]),
            row(
                "weaction-api",
                30,
                "MERGED",
                "task/WAI-8279",
                ["WAI-8279", "WAI-8305"],
                title="WAI-8279 / WAI-8305",
            ),
        ],
    )
    await bitbucket_repo.upsert_branches(
        db_pool,
        [
            {
                "repo_slug": "monitoria",
                "name": "WAI-8400-nova",
                "target_hash": "x",
                "target_date": T0,
                "issue_keys": ["WAI-8400"],
            },
        ],
    )


async def test_detalhe_da_tarefa_multi_repo(db_app, client, seeded):
    response = await client.get("/api/issues/WAI-8278/pull-requests")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ajustes_requisitados"
    assert body["status_label"] == "Ajustes requisitados"
    assert body["pr_count"] == 2
    assert body["build_failed"] is True
    assert [(r["repo_slug"], r["status"]) for r in body["repos"]] == [
        ("supervisor-web", "ajustes_requisitados"),
        ("weaction-api", "mergeada"),
    ]
    pr = body["repos"][0]["pull_requests"][0]
    assert pr["changes_requested"] == 1
    # Sem `account_id` no participante (espelho antigo), o revisor só não ganha o "tirar"; sem
    # a foto, o painel mostra as iniciais.
    assert pr["reviewers"] == [
        {
            "name": "Revisor",
            "role": "REVIEWER",
            "approved": False,
            "state": "changes_requested",
            "account_id": None,
            "avatar_url": None,
        }
    ]
    assert pr["match"] == "branch"
    assert pr["url"].endswith("/pull-requests/10")


def event(kind, at, *, dedupe):
    return {
        "dedupe_key": f"bb:pr:supervisor-web:10:{dedupe}",
        "source": "bitbucket",
        "kind": kind,
        "issue_key": "WAI-8278",
        "repo_slug": "supervisor-web",
        "pr_id": 10,
        "actor_name": "Alguém",
        "actor_is_me": False,
        "occurred_at": at,
        "title": "PR 10",
        "detail": {},
    }


async def test_correcao_depois_do_pedido_devolve_o_card_para_pr_aberta(
    db_app, client, seeded, db_pool
):
    await activity_repo.insert_events(
        db_pool,
        [
            event("pr_changes_requested", T0 + timedelta(hours=1), dedupe="changes_requested:r"),
            event("pr_commit", T0 + timedelta(hours=2), dedupe="commit:def"),
        ],
    )

    body = (await client.get("/api/issues/WAI-8278/pull-requests")).json()

    # O revisor continua com "changes_requested" no espelho — é o histórico que muda o status.
    pr = body["repos"][0]["pull_requests"][0]
    assert pr["changes_requested"] == 1
    assert pr["fix_pushed"] is True
    assert pr["status"] == "pr_aberta"
    assert body["repos"][0]["status"] == "pr_aberta"
    assert body["status"] == "pr_aberta"


async def test_commit_anterior_ao_pedido_mantem_ajustes_requisitados(
    db_app, client, seeded, db_pool
):
    await activity_repo.insert_events(
        db_pool,
        [
            event("pr_commit", T0 + timedelta(hours=1), dedupe="commit:abc"),
            event("pr_changes_requested", T0 + timedelta(hours=2), dedupe="changes_requested:r"),
        ],
    )

    body = (await client.get("/api/issues/WAI-8278/pull-requests")).json()

    assert body["repos"][0]["pull_requests"][0]["fix_pushed"] is False
    assert body["status"] == "ajustes_requisitados"


async def test_tarefa_sem_nada_devolve_sem_pr(db_app, client, seeded):
    response = await client.get("/api/issues/WAI-1/pull-requests")

    assert response.json()["status"] == "sem_pr"
    assert response.json()["repos"] == []


async def test_chave_invalida_da_422(db_app, client):
    response = await client.get("/api/issues/wai-12;drop/pull-requests")
    assert response.status_code == 422


async def test_lote_para_os_cards(db_app, client, seeded):
    response = await client.post(
        "/api/pr-status", json={"keys": ["wai-8278", "WAI-8305", "WAI-8400", "WAI-1", "WAI-8278"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert sorted(body) == ["WAI-1", "WAI-8278", "WAI-8305", "WAI-8400"]
    links = body["WAI-8278"].pop("links")
    assert body["WAI-8278"] == {
        "status": "ajustes_requisitados",
        "status_label": "Ajustes requisitados",
        "pr_count": 2,
        "open_pr_count": 1,
        "build_failed": True,
        "review": {
            "approvals": 0,
            "reviewers": 1,
            "changes_requested": 1,
            "required": 1,
            "people": [
                {"name": "Revisor", "state": "changes_requested", "account_id": None,
                 "avatar_url": None},
            ],
        },
    }
    # O badge abre primeiro o PR que decide o status do card.
    assert [(link["repo_slug"], link["id"], link["status"]) for link in links] == [
        ("supervisor-web", 10, "ajustes_requisitados"),
        ("weaction-api", 20, "mergeada"),
    ]
    assert links[0]["url"] == "https://bitbucket.org/weonrepo/supervisor-web/pull-requests/10"
    assert body["WAI-8305"]["status"] == "mergeada"  # citada no título do PR
    assert body["WAI-8400"]["status"] == "branch_sem_pr"
    assert body["WAI-8400"]["links"] == []
    assert body["WAI-1"]["status"] == "sem_pr"


@pytest.mark.parametrize("keys", [[], ["nao-e-chave"]])
async def test_lote_invalido_da_422(db_app, client, keys):
    response = await client.post("/api/pr-status", json={"keys": keys})
    assert response.status_code == 422


# --- Regra de aprovação ------------------------------------------------------------------------

REVIEWER = {"role": "REVIEWER", "approved": False, "state": None, "name": "Rafael"}
APPROVED = {"role": "REVIEWER", "approved": True, "state": "approved", "name": "Felipe"}


async def test_regra_de_aprovacao_comeca_na_de_antes(db_app, client):
    response = await client.get("/api/preferences/pr-approval")

    assert response.status_code == 200
    assert response.json() == {"min_percent": 0}


async def test_regra_de_aprovacao_decide_quando_o_pr_esta_aprovado(db_app, client, db_pool):
    # Caso real WAI-8791: dois revisores, um aprovou.
    await bitbucket_repo.upsert_pull_requests(
        db_pool,
        [row("qualificai", 37, "OPEN", "WAI-8791-trial", ["WAI-8791"], participants=[REVIEWER, APPROVED])],
    )

    async def badge():
        return (await client.post("/api/pr-status", json={"keys": ["WAI-8791"]})).json()["WAI-8791"]

    assert (await badge())["status"] == "aprovada"  # uma aprovação basta, como antes

    saved = await client.put("/api/preferences/pr-approval", json={"min_percent": 100})
    assert saved.json() == {"min_percent": 100}
    assert (await client.get("/api/preferences/pr-approval")).json() == {"min_percent": 100}
    result = await badge()
    assert result["status"] == "pr_aberta"
    review = {k: v for k, v in result["review"].items() if k != "people"}
    assert review == {"approvals": 1, "reviewers": 2, "changes_requested": 0, "required": 2}
    assert [(p["name"], p["state"]) for p in result["review"]["people"]] == [
        ("Felipe", "approved"), ("Rafael", "pending"),
    ]
    assert result["links"][0]["review"]["required"] == 2

    await client.put("/api/preferences/pr-approval", json={"min_percent": 50})
    assert (await badge())["status"] == "aprovada"


@pytest.mark.parametrize("payload", [{"min_percent": 101}, {"min_percent": -1}, {"min_percent": "50"}, {}])
async def test_regra_de_aprovacao_invalida_da_422(db_app, client, payload):
    response = await client.put("/api/preferences/pr-approval", json=payload)

    assert response.status_code == 422
    assert (await client.get("/api/preferences/pr-approval")).json() == {"min_percent": 0}
