from datetime import UTC, datetime

import pytest

from repositories import bitbucket_repo
from security.paths import Roots, get_roots
from tests.workspace_fakes import make_repo

T0 = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)


async def _issue(pool, key, summary, status="Em Desenvolvimento", category="indeterminate"):
    await pool.execute(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, summary, status, status_category,
                                assignee_account_id, created_at, updated_at, raw)
        VALUES ($1, $1, 'WAI', 'Tarefa', $2, $3, $4, 'acc-me', now(), now(), '{}')
        """,
        key,
        summary,
        status,
        category,
    )


async def _sprint(pool, sprint_id, name, state, *keys, squad="Growth"):
    await pool.execute(
        """
        INSERT INTO jira_sprint (id, board_id, name, state, squad, in_scope)
        VALUES ($1, 144, $2, $3, $4::text, $4::text IS NOT NULL) ON CONFLICT (id) DO NOTHING
        """,
        sprint_id,
        name,
        state,
        squad,
    )
    for key in keys:
        await pool.execute(
            "INSERT INTO jira_sprint_issue (sprint_id, issue_key) VALUES ($1, $2)", sprint_id, key
        )


def _pr(repo_slug, pr_id, key):
    return {
        "repo_slug": repo_slug,
        "id": pr_id,
        "title": "PR",
        "description": None,
        "state": "OPEN",
        "draft": False,
        "author_name": "Dev",
        "source_branch": f"{key}-pr",
        "source_commit": "a",
        "destination_branch": "main",
        "participants": [],
        "comment_count": 0,
        "task_count": 0,
        "build_status": None,
        "issue_keys": [key],
        "url": f"https://bitbucket.org/weonrepo/{repo_slug}/pull-requests/{pr_id}",
        "created_on": T0,
        "updated_on": T0,
    }


@pytest.fixture
async def seeded(db_app, db_pool, tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    make_repo(
        root,
        "monitoria",
        url="git@bitbucket.org:weonrepo/monitoria.git",
        files={"refs/heads/WAI-103-sem-colchete": "abc\n"},
    )
    make_repo(root, "qualificai", url="git@bitbucket.org:weonrepo/qualificai.git")
    db_app.dependency_overrides[get_roots] = lambda: Roots(projects=root, claude=tmp_path / "c")

    await _issue(db_pool, "WAI-100", "[monitoria] Rolou de sprint")
    await _issue(db_pool, "WAI-101", "[monitoria] Já entregue", "Concluído", "done")
    await _issue(
        db_pool, "WAI-102", "[monitoria] Da semana que vem", "Disponivel para análise", "new"
    )
    await _issue(db_pool, "WAI-103", "Sem colchete, só a branch", "Disponivel para análise", "new")
    await _issue(db_pool, "WAI-104", "[qualificai] Saiu da anterior para a fila")
    await _issue(db_pool, "WAI-106", "Só o PR diz o repo", "DISPONIVEL PARA REVIEW", "new")
    await _issue(db_pool, "WAI-108", "[monitoria] De duas sprints atrás", "Concluído", "done")
    await _issue(db_pool, "WAI-109", "[monitoria] De daqui a duas sprints")
    await _issue(db_pool, "WAI-110", "[monitoria] Sem sprint nenhuma")
    await _issue(db_pool, "WAI-111", "[qualificai] Só na fila do board")

    # Ids como os do Jira: a fila do board é antiga, as semanais crescem.
    await _sprint(db_pool, 5, "🛠️BUG-SUPORT", "future", "WAI-104", "WAI-111", squad=None)
    await _sprint(db_pool, 8, "Sprint 75 - Growth", "closed", "WAI-108")
    await _sprint(db_pool, 10, "Sprint 76 - Growth", "closed", "WAI-100", "WAI-103", "WAI-104")
    await _sprint(db_pool, 20, "Sprint 77 - Growth", "active", "WAI-100", "WAI-101", "WAI-106")
    await _sprint(db_pool, 30, "Sprint 78 - Growth", "future", "WAI-102")
    await _sprint(db_pool, 40, "Sprint 79 - Growth", "future", "WAI-109")
    await bitbucket_repo.upsert_pull_requests(db_pool, [_pr("qualificai", 7, "WAI-106")])
    await bitbucket_repo.upsert_repositories(
        db_pool,
        [
            {
                "slug": "monitoria",
                "name": "monitoria",
                "is_private": True,
                "main_branch": "main",
                "updated_on": T0,
                "project_key": "ORGANIA",
                "project_name": "OrganIA",
            }
        ],
    )


async def _repos(client):
    response = await client.get("/api/workspace/repo-issues")
    assert response.status_code == 200, response.text
    return {r["slug"]: r for r in response.json()["repos"]}


def _keys(sprint):
    return [i["key"] for i in sprint["issues"]]


async def test_so_a_sprint_atual_a_anterior_e_a_proxima(client, seeded):
    repos = await _repos(client)

    assert list(repos) == ["monitoria", "qualificai"]
    monitoria = repos["monitoria"]
    assert monitoria["local"] is True
    assert [(s["id"], s["name"], s["state"], s["position"]) for s in monitoria["sprints"]] == [
        (30, "Sprint 78 - Growth", "future", "proxima"),
        (20, "Sprint 77 - Growth", "active", "atual"),
        (10, "Sprint 76 - Growth", "closed", "anterior"),
    ]
    # Sprint 75, Sprint 79 e a tarefa sem sprint ficam de fora.
    assert monitoria["issue_count"] == 4
    assert [_keys(s) for s in monitoria["sprints"]] == [
        ["WAI-102"],
        ["WAI-100", "WAI-101"],
        ["WAI-103"],
    ]


async def test_rolou_de_sprint_aparece_so_na_mais_nova_e_na_cor_da_etapa(client, seeded):
    atual = (await _repos(client))["monitoria"]["sprints"][1]["issues"]

    # A que rolou da 76 para a 77 aparece uma vez só, na 77 — e o que falta fazer vem antes.
    assert [i["key"] for i in atual] == ["WAI-100", "WAI-101"]
    assert atual[0]["stage"] == {
        "id": "desenvolvimento",
        "label": "Desenvolvimento",
        "color": "#2f7cf6",
    }
    assert atual[1]["stage"]["id"] == "concluido"


async def test_repo_leva_o_projeto_do_bitbucket_em_que_foi_escolhido(client, seeded):
    repos = await _repos(client)

    assert (repos["monitoria"]["project_key"], repos["monitoria"]["project_name"]) == (
        "ORGANIA",
        "OrganIA",
    )
    # Fora do sync (só o PR no espelho), sem projeto.
    assert repos["qualificai"]["project_key"] is None


async def test_fila_do_board_nao_conta_e_o_pr_liga_ao_repo(client, seeded):
    qualificai = (await _repos(client))["qualificai"]

    assert [(s["position"], _keys(s)) for s in qualificai["sprints"]] == [
        ("atual", ["WAI-106"]),
        ("anterior", ["WAI-104"]),
    ]
    assert qualificai["sprints"][0]["issues"][0]["stage"]["id"] == "review"


async def test_sem_sprint_ativa_a_atual_e_a_ultima_fechada(client, seeded, db_pool):
    await db_pool.execute("UPDATE jira_sprint SET state = 'closed' WHERE id = 20")

    monitoria = (await _repos(client))["monitoria"]

    assert [(s["id"], s["position"]) for s in monitoria["sprints"]] == [
        (30, "proxima"),
        (20, "atual"),
        (10, "anterior"),
    ]


async def test_cada_squad_do_escopo_traz_a_sua_janela(client, seeded, db_pool):
    await _issue(db_pool, "WAI-120", "[monitoria] Da outra squad")
    await _sprint(db_pool, 50, "Sprint 12 - Core", "active", "WAI-120", squad="Core")

    monitoria = (await _repos(client))["monitoria"]

    assert [(s["name"], s["position"]) for s in monitoria["sprints"]] == [
        ("Sprint 78 - Growth", "proxima"),
        ("Sprint 12 - Core", "atual"),
        ("Sprint 77 - Growth", "atual"),
        ("Sprint 76 - Growth", "anterior"),
    ]


async def test_vizinha_fora_do_escopo_nao_entra(client, seeded, db_pool):
    # A 76 saiu do escopo do sync (só as N últimas fechadas são espelhadas): a anterior
    # passa a ser a sprint do escopo antes dela, e não uma de tarefas congeladas.
    await db_pool.execute("UPDATE jira_sprint SET in_scope = false WHERE id = 10")

    monitoria = (await _repos(client))["monitoria"]

    assert [(s["name"], s["position"]) for s in monitoria["sprints"]][-1] == (
        "Sprint 75 - Growth",
        "anterior",
    )


async def test_status_sem_etapa_vem_sem_cor(client, seeded, db_pool):
    await _issue(db_pool, "WAI-107", "[monitoria] Status inventado", "Cruzeiro", "indeterminate")
    await db_pool.execute(
        "INSERT INTO jira_sprint_issue (sprint_id, issue_key) VALUES (20, 'WAI-107')"
    )

    atual = (await _repos(client))["monitoria"]["sprints"][1]["issues"]

    assert {i["key"]: i["stage"] for i in atual}["WAI-107"] is None


async def test_sem_sprint_no_espelho_a_lista_vem_vazia(client, db_app, credential_store):
    assert (await client.get("/api/workspace/repo-issues")).json() == {"repos": []}
