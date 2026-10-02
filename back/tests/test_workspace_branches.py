"""Painel de branches: todas as refs, busca no histórico, fetch --prune, avançar e apagar."""

from pathlib import Path

import pytest

from security.paths import Roots, get_roots
from services.workspace import graph_service
from tests.workspace_fakes import commit, git, make_git_repo


@pytest.fixture(autouse=True)
def _cache_limpo():
    graph_service.clear_cache()
    yield
    graph_service.clear_cache()


@pytest.fixture
def projects(tmp_path, db_app):
    root = tmp_path / "projects"
    root.mkdir()
    db_app.dependency_overrides[get_roots] = lambda: Roots(projects=root, claude=tmp_path / "c")
    return root


@pytest.fixture
async def repo(projects, client, tmp_path):
    made = make_git_repo(projects)
    git(made["repo"], "tag", "v1.0", made["first"])
    # Um colega com outro clone do mesmo origin — é por ele que o servidor "muda".
    colleague = tmp_path / "colega"
    git(tmp_path, "clone", "-q", str(tmp_path / "monitoria-origin.git"), str(colleague))
    git(colleague, "config", "user.name", "Colega")
    git(colleague, "config", "user.email", "colega@example.com")
    made["colleague"] = colleague
    assert (await client.get("/api/workspace/repos")).status_code == 200
    return made


BASE = "/api/workspace/repos/monitoria"


def _ref(refs, name):
    return next((r for r in refs if r["name"] == name), None)


async def _refs(client, **params):
    response = await client.get(f"{BASE}/refs", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_painel_lista_locais_remotas_e_tags_com_assunto(client, repo):
    data = await _refs(client, keys="WAI-100")
    kinds = [r["kind"] for r in data["refs"]]
    assert kinds == sorted(kinds, key=["local", "remote", "tag"].index)

    feature = _ref(data["refs"], "WAI-100-chave")
    assert feature["in_feature"] is True
    assert feature["subject"] == "ajusta o consumer da fila"
    assert feature["committed_at"]
    assert _ref(data["refs"], "WAI-200-outra")["worktree"] == str(repo["worktree"])
    assert _ref(data["refs"], "origin/main")["kind"] == "remote"
    assert _ref(data["refs"], "v1.0")["kind"] == "tag"
    assert data["issue_status"]["WAI-100"]["status"] == "sem_pr"


async def test_busca_por_mensagem_autor_e_hash(client, repo):
    by_message = (await client.get(f"{BASE}/search", params={"q": "APLICA A CHAVE"})).json()
    assert [c["sha"] for c in by_message["commits"]] == [repo["feature_pushed"]]
    assert by_message["issue_status"]["WAI-100"]["status"] == "sem_pr"

    by_author = (await client.get(f"{BASE}/search", params={"q": "dev"})).json()
    assert {repo["first"], repo["hotfix"], repo["other"]} <= {c["sha"] for c in by_author["commits"]}

    by_hash = (await client.get(f"{BASE}/search", params={"q": repo["hotfix"][:8]})).json()
    assert [c["sha"] for c in by_hash["commits"]] == [repo["hotfix"]]

    # Texto literal: nada de regex vindo da tela.
    nothing = (await client.get(f"{BASE}/search", params={"q": "a.*b"})).json()
    assert nothing["commits"] == []
    assert (await client.get(f"{BASE}/search", params={"q": "x"})).status_code == 422


async def test_fetch_prune_traz_o_novo_e_apaga_o_que_sumiu_no_servidor(client, repo):
    colleague = repo["colleague"]
    git(colleague, "checkout", "-q", "-b", "WAI-300-nova")
    commit(colleague, "WAI-300 começa", "nova.txt")
    git(colleague, "push", "-q", "-u", "origin", "WAI-300-nova")
    git(colleague, "checkout", "-q", "main")
    commit(colleague, "main andou no servidor", "servidor.txt")
    git(colleague, "push", "-q", "origin", "main")
    git(colleague, "push", "-q", "origin", "--delete", "WAI-100-chave")

    response = await client.post(f"{BASE}/fetch")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["added"] == ["origin/WAI-300-nova"]
    assert result["updated"] == ["origin/main"]
    assert result["pruned"] == ["origin/WAI-100-chave"]
    assert result["fetched_at"]

    refs = (await _refs(client))["refs"]
    assert _ref(refs, "origin/WAI-100-chave") is None
    assert _ref(refs, "WAI-100-chave")["gone"] is True


async def test_avancar_branch_fechada_mexe_so_na_ref(client, repo):
    git(repo["repo"], "branch", "--track", "atras", "origin/main")
    git(repo["repo"], "branch", "-f", "atras", repo["first"])
    colleague = repo["colleague"]
    commit(colleague, "main andou no servidor", "servidor.txt")
    git(colleague, "push", "-q", "origin", "main")
    await client.post(f"{BASE}/fetch")

    response = await client.post(f"{BASE}/branches/update", json={"name": "atras"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "ref"
    assert body["before"] == repo["first"]
    assert body["after"] == git(repo["repo"], "rev-parse", "origin/main")

    again = (await client.post(f"{BASE}/branches/update", json={"name": "atras"})).json()
    assert again["mode"] == "noop"


async def test_avancar_branch_aberta_numa_worktree_faz_ff_la_dentro(client, repo):
    worktree = repo["worktree"]
    git(worktree, "push", "-q", "-u", "origin", "WAI-200-outra")
    colleague = repo["colleague"]
    git(colleague, "fetch", "-q", "origin")
    git(colleague, "checkout", "-q", "-b", "WAI-200-outra", "origin/WAI-200-outra")
    commit(colleague, "WAI-200 continua no servidor", "outra2.txt")
    git(colleague, "push", "-q", "origin", "WAI-200-outra")
    await client.post(f"{BASE}/fetch")

    response = await client.post(f"{BASE}/branches/update", json={"name": "WAI-200-outra"})
    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "worktree"
    assert (Path(worktree) / "outra2.txt").exists()


async def test_avancar_recusa_divergencia_e_branch_sem_upstream(client, repo):
    colleague = repo["colleague"]
    commit(colleague, "main andou no servidor", "servidor.txt")
    git(colleague, "push", "-q", "origin", "main")
    await client.post(f"{BASE}/fetch")

    # main tem o hotfix local e o origin tem outro commit: não dá para só avançar.
    response = await client.post(f"{BASE}/branches/update", json={"name": "main"})
    assert response.status_code == 409
    assert response.json()["code"] == "diverged"

    response = await client.post(f"{BASE}/branches/update", json={"name": "outra-coisa"})
    assert (response.status_code, response.json()["code"]) == (409, "no_upstream")


async def test_apagar_branch_local_com_as_protecoes(client, repo):
    response = await client.post(f"{BASE}/branches/delete", json={"name": "outra-coisa"})
    assert response.status_code == 200, response.text
    assert response.json() == {"name": "outra-coisa", "target": repo["hotfix"]}
    assert _ref((await _refs(client))["refs"], "outra-coisa") is None

    # Branch com commit que não está em nenhuma outra: o -d recusa, o -D (force) apaga.
    tree = git(repo["repo"], "rev-parse", f"{repo['first']}^{{tree}}")
    solta = git(repo["repo"], "commit-tree", tree, "-p", repo["first"], "-m", "trabalho solto")
    git(repo["repo"], "update-ref", "refs/heads/solta", solta)
    response = await client.post(f"{BASE}/branches/delete", json={"name": "solta"})
    assert (response.status_code, response.json()["code"]) == (409, "unmerged")
    assert "perde esses commits" in response.json()["detail"]
    response = await client.post(f"{BASE}/branches/delete", json={"name": "solta", "force": True})
    assert response.status_code == 200
    assert response.json()["target"] == solta

    cases = {
        "main": "protected",
        "WAI-200-outra": "checked_out",
        "nao-existe": "not_found",
    }
    for name, code in cases.items():
        response = await client.post(f"{BASE}/branches/delete", json={"name": name})
        assert (response.status_code, response.json()["code"]) == (409, code), name


async def test_nome_de_branch_que_viraria_opcao_e_recusado(client, repo):
    for name in ("--force", "-D", "a..b", "x/", ""):
        response = await client.post(f"{BASE}/branches/delete", json={"name": name})
        assert response.status_code == 422, name
        response = await client.post(f"{BASE}/branches/update", json={"name": name})
        assert response.status_code == 422, name


async def test_o_grafo_traz_o_status_de_pr_de_cada_chave(client, repo):
    graph = (await client.get(f"{BASE}/graph", params={"keys": "WAI-100", "scope": "all"})).json()
    assert set(graph["issue_status"]) == {"WAI-100", "WAI-200"}
    assert graph["issue_status"]["WAI-200"] == {"status": "sem_pr", "status_label": "Sem PR"}
