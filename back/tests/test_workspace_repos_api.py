import shutil
from datetime import UTC, datetime

import pytest

from repositories import bitbucket_repo
from security.paths import Roots, get_roots
from tests.workspace_fakes import make_repo

T0 = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)


@pytest.fixture
def projects(tmp_path, db_app):
    root = tmp_path / "projects"
    root.mkdir()
    make_repo(
        root,
        "monitoria",
        url="git@bitbucket.org:weonrepo/monitoria.git",
        head="ref: refs/heads/WAI-8790-rota",
        files={"refs/remotes/origin/HEAD": "ref: refs/remotes/origin/main\n"},
    )
    make_repo(
        root,
        "weaction-api",
        url="git@bitbucket.org:weonrepo/weaction-api.git",
        files={"refs/heads/develop": "abc\n"},
    )
    make_repo(root, "appingos", url="https://github.com/MatheusBacca/APPingos.git")
    db_app.dependency_overrides[get_roots] = lambda: Roots(projects=root, claude=tmp_path)
    return root


async def _repos(client):
    response = await client.get("/api/workspace/repos")
    assert response.status_code == 200
    return {r["slug"]: r for r in response.json()["repos"]}


async def test_lista_as_pastas_com_vinculo_e_base(client, projects, db_pool):
    await bitbucket_repo.upsert_repositories(
        db_pool,
        [
            {
                "slug": "weaction-api",
                "name": "weaction-api",
                "is_private": True,
                "main_branch": "develop",
                "updated_on": T0,
            }
        ],
    )
    repos = await _repos(client)
    assert set(repos) == {"appingos", "monitoria", "weaction-api"}

    monitoria = repos["monitoria"]
    assert monitoria["bb_slug"] == "monitoria"
    assert monitoria["link"] == "auto"
    assert monitoria["in_mirror"] is False
    assert (monitoria["base_branch"], monitoria["base_source"]) == ("main", "origin")
    assert monitoria["current_branch"] == "WAI-8790-rota"

    weaction = repos["weaction-api"]
    assert weaction["in_mirror"] is True
    assert (weaction["base_branch"], weaction["base_source"]) == ("develop", "bitbucket")

    assert repos["appingos"]["bb_slug"] is None


async def test_ajuste_do_dev_sobrevive_a_redescoberta_e_a_pasta_sumida(client, projects):
    await _repos(client)
    response = await client.put(
        "/api/workspace/repos/monitoria", json={"link": "none", "base_branch": "release/1.0"}
    )
    assert response.status_code == 200
    assert response.json()["link"] == "none"
    assert response.json()["bb_slug"] is None

    repos = await _repos(client)
    assert (repos["monitoria"]["base_branch"], repos["monitoria"]["base_source"]) == (
        "release/1.0",
        "manual",
    )

    shutil.rmtree(projects / "monitoria")
    repos = await _repos(client)
    assert repos["monitoria"]["present"] is False

    make_repo(projects, "monitoria", url="git@bitbucket.org:weonrepo/monitoria.git")
    repos = await _repos(client)
    assert repos["monitoria"]["present"] is True
    assert repos["monitoria"]["link"] == "none"


async def test_vinculo_manual_e_volta_ao_automatico(client, projects):
    await _repos(client)
    response = await client.put(
        "/api/workspace/repos/appingos", json={"link": "manual", "bb_slug": "appingos-web"}
    )
    assert response.json()["bb_slug"] == "appingos-web"
    assert response.json()["link"] == "manual"

    response = await client.put("/api/workspace/repos/appingos", json={"link": "auto"})
    assert response.json()["bb_slug"] is None
    assert response.json()["link"] == "auto"


async def test_ajuste_invalido_ou_de_repo_desconhecido(client, projects):
    await _repos(client)
    assert (
        await client.put("/api/workspace/repos/monitoria", json={"link": "manual"})
    ).status_code == 422
    assert (
        await client.put("/api/workspace/repos/monitoria", json={"base_branch": "--upload-pack=x"})
    ).status_code == 422
    assert (
        await client.put("/api/workspace/repos/monitoria", json={"base_branch": "main..develop"})
    ).status_code == 422
    assert (await client.put("/api/workspace/repos/nao-existe", json={})).status_code == 404
