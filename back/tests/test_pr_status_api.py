from datetime import UTC, datetime

import pytest

from repositories import bitbucket_repo

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
    assert pr["reviewers"] == [
        {"name": "Revisor", "role": "REVIEWER", "approved": False, "state": "changes_requested"}
    ]
    assert pr["match"] == "branch"
    assert pr["url"].endswith("/pull-requests/10")


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
    assert body["WAI-8278"] == {
        "status": "ajustes_requisitados",
        "status_label": "Ajustes requisitados",
        "pr_count": 2,
        "open_pr_count": 1,
        "build_failed": True,
    }
    assert body["WAI-8305"]["status"] == "mergeada"  # citada no título do PR
    assert body["WAI-8400"]["status"] == "branch_sem_pr"
    assert body["WAI-1"]["status"] == "sem_pr"


@pytest.mark.parametrize("keys", [[], ["nao-e-chave"]])
async def test_lote_invalido_da_422(db_app, client, keys):
    response = await client.post("/api/pr-status", json={"keys": keys})
    assert response.status_code == 422
