from datetime import UTC, datetime

import pytest

from repositories import bitbucket_repo
from security.paths import Roots, get_roots
from services.sync.mappers import repository_row
from tests.workspace_fakes import make_repo

T0 = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)


def _bb(slug, project_key, project_name):
    return {
        "slug": slug,
        "name": slug,
        "is_private": True,
        "main_branch": "main",
        "updated_on": T0,
        "project_key": project_key,
        "project_name": project_name,
    }


@pytest.fixture
async def mirror(db_app, db_pool, tmp_path):
    """Repos escolhidos no sync em dois projetos do Bitbucket, com clone de dois deles."""
    root = tmp_path / "projects"
    root.mkdir()
    make_repo(root, "monitoria", url="git@bitbucket.org:weonrepo/monitoria.git")
    make_repo(root, "qualificai", url="git@bitbucket.org:weonrepo/qualificai.git")
    db_app.dependency_overrides[get_roots] = lambda: Roots(projects=root, claude=tmp_path / "c")
    await bitbucket_repo.upsert_repositories(
        db_pool,
        [
            _bb("monitoria", "ORGANIA", "OrganIA"),
            _bb("qualificai", "ORGANIA", "OrganIA"),
            _bb("supervisor-web", "WEON", "weon"),
        ],
    )


async def _workspaces(client):
    response = await client.get("/api/workspaces")
    assert response.status_code == 200, response.text
    return response.json()


def _projects(workspaces):
    return {w["project_key"]: w for w in workspaces if w["kind"] == "project"}


def test_sync_guarda_o_projeto_do_repositorio():
    row = repository_row({"slug": "monitoria", "project": {"key": "ORGANIA", "name": "OrganIA"}})
    assert (row["project_key"], row["project_name"]) == ("ORGANIA", "OrganIA")
    assert repository_row({"slug": "solto"})["project_key"] is None


async def test_cada_projeto_do_sync_vira_uma_aba_fixa_e_o_livre_de_mesmo_nome_e_adotado(
    client, mirror
):
    # O dev já tinha montado "WeON" à mão (e fechado a aba); o Bitbucket chama de "weon".
    livre = (
        await client.post("/api/workspaces", json={"title": "WeON", "repos": ["node-red4"]})
    ).json()
    await client.patch(f"/api/workspaces/{livre['id']}", json={"is_open": False})

    projects = _projects(await _workspaces(client))

    assert set(projects) == {"ORGANIA", "WEON"}
    assert projects["ORGANIA"]["title"] == "OrganIA"
    adotado = projects["WEON"]
    assert (adotado["id"], adotado["title"], adotado["is_open"]) == (livre["id"], "WeON", True)
    # Ler de novo não cria outra aba.
    assert len(_projects(await _workspaces(client))) == 2


async def test_menu_de_wais_usa_o_nome_que_o_dev_deu_a_aba_do_projeto(client, mirror, db_pool):
    await db_pool.execute(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, summary, status, status_category,
                                created_at, updated_at, raw)
        VALUES ('WAI-1', 'WAI-1', 'WAI', 'Tarefa', '[monitoria] Tela', 'Em Desenvolvimento',
                'indeterminate', now(), now(), '{}')
        """
    )
    await db_pool.execute(
        "INSERT INTO jira_sprint (id, board_id, name, state, squad, in_scope)"
        " VALUES (1, 144, 'Sprint 77 - Growth', 'active', 'Growth', true)"
    )
    await db_pool.execute(
        "INSERT INTO jira_sprint_issue (sprint_id, issue_key) VALUES (1, 'WAI-1')"
    )
    organia = _projects(await _workspaces(client))["ORGANIA"]
    await client.patch(f"/api/workspaces/{organia['id']}", json={"title": "Org IA"})

    repos = (await client.get("/api/workspace/repo-issues")).json()["repos"]

    assert [(r["slug"], r["project_key"], r["project_name"]) for r in repos] == [
        ("monitoria", "ORGANIA", "Org IA")
    ]


async def test_aba_do_projeto_nao_fecha_nem_se_apaga(client, mirror):
    organia = _projects(await _workspaces(client))["ORGANIA"]
    url = f"/api/workspaces/{organia['id']}"

    fechar = await client.patch(url, json={"is_open": False})
    assert fechar.status_code == 409
    assert "Sincronização" in fechar.json()["detail"]
    assert (await client.delete(url)).status_code == 409
    assert (await client.patch(url, json={"title": "Org"})).json()["title"] == "Org"


async def test_repos_do_projeto_entram_sozinhos_e_ainda_se_escondem(client, mirror):
    organia = _projects(await _workspaces(client))["ORGANIA"]
    url = f"/api/workspaces/{organia['id']}"

    repos = {r["slug"]: r for r in (await client.get(url)).json()["repos"]}
    assert set(repos) == {"monitoria", "qualificai"}
    assert repos["monitoria"]["sources"] == ["project"]
    assert repos["monitoria"]["local"] is True

    await client.put(f"{url}/repos/qualificai", json={"mode": "hide"})
    repos = {r["slug"]: r for r in (await client.get(url)).json()["repos"]}
    assert repos["qualificai"]["hidden"] is True


async def test_projeto_que_sai_do_sync_devolve_a_aba_como_livre(client, mirror, db_pool):
    weon = _projects(await _workspaces(client))["WEON"]
    await bitbucket_repo.prune(
        db_pool, repo_slugs=["monitoria", "qualificai"], my_identities=None, my_issue_keys=[]
    )

    workspaces = {w["id"]: w for w in await _workspaces(client)}

    liberado = workspaces[weon["id"]]
    # Os repos vinham do projeto: aberta, a aba ficaria vazia. Vai para "Abertos antes".
    assert (liberado["kind"], liberado["project_key"], liberado["is_open"]) == ("free", None, False)
    assert (await client.delete(f"/api/workspaces/{weon['id']}")).status_code == 204
