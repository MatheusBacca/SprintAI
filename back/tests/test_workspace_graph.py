from datetime import UTC, datetime
from pathlib import Path

import pytest

from repositories import bitbucket_repo, workspace_repo
from security.paths import Roots, get_roots
from services.workspace import git_local, graph_service
from tests.workspace_fakes import commit, git, make_git_repo

T0 = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)


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
async def repo(projects, client):
    made = make_git_repo(projects)
    # A listagem é o que grava a pasta em `workspace_repo` — a linha do tempo lê dali.
    assert (await client.get("/api/workspace/repos")).status_code == 200
    return made


async def _graph(client, **params):
    response = await client.get("/api/workspace/repos/monitoria/graph", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _ref(graph, name):
    return next(r for r in graph["refs"] if r["name"] == name)


async def test_so_da_feature_traz_a_base_e_as_branches_da_chave(client, repo):
    graph = await _graph(client, keys="WAI-100")

    assert graph["scope"] == "feature"
    assert graph["base_branch"] == "main"
    shas = [c["sha"] for c in graph["commits"]]
    assert repo["feature_local"] in shas
    assert repo["hotfix"] in shas
    assert repo["first"] in shas
    # A worktree WAI-200 é de outra tarefa: o commit dela não entra no "só da feature".
    assert repo["other"] not in shas

    feature = _ref(graph, "WAI-100-chave")
    assert feature["in_feature"] is True
    assert feature["issue_keys"] == ["WAI-100"]
    assert (feature["upstream"], feature["ahead"], feature["behind"]) == (
        "origin/WAI-100-chave",
        1,
        0,
    )
    main = _ref(graph, "main")
    assert main["is_base"] is True
    assert main["is_head"] is True
    assert main["ahead"] == 1
    assert _ref(graph, "origin/main")["is_base"] is True

    by_sha = {c["sha"]: c for c in graph["commits"]}
    assert by_sha[repo["feature_pushed"]]["parents"] == [repo["first"]]
    assert by_sha[repo["feature_pushed"]]["issue_keys"] == ["WAI-100"]
    assert by_sha[repo["feature_pushed"]]["subject"] == "WAI-100: aplica a chave na integração"


async def test_todas_as_branches_inclui_a_worktree_e_as_branches_sem_chave(client, repo):
    graph = await _graph(client, scope="all", keys="WAI-100")

    shas = [c["sha"] for c in graph["commits"]]
    assert repo["other"] in shas
    names = {r["name"] for r in graph["refs"]}
    assert {"WAI-200-outra", "outra-coisa", "origin/WAI-100-chave"} <= names
    assert _ref(graph, "WAI-200-outra")["worktree"] == str(repo["worktree"])


async def test_worktrees_com_alteracoes_nao_commitadas(client, repo):
    graph = await _graph(client, keys="WAI-100")

    main, extra = graph["worktrees"]
    assert main["is_main"] is True
    assert main["branch"] == "main"
    assert main["changes"] == {"changed": 1, "untracked": 1, "conflicted": 0}
    assert extra["branch"] == "WAI-200-outra"
    assert extra["outside_roots"] is False
    assert extra["changes"] == {"changed": 0, "untracked": 0, "conflicted": 0}


async def test_since_sem_mudanca_devolve_so_as_worktrees(client, repo):
    first = await _graph(client, keys="WAI-100")
    again = await _graph(client, keys="WAI-100", since=first["fingerprint"])

    assert again["unchanged"] is True
    assert again["commits"] == []
    assert again["refs"] == []
    assert again["worktrees"][0]["changes"]["untracked"] == 1

    new_sha = commit(repo["repo"], "WAI-100 mais um ajuste", "chave2.txt")
    changed = await _graph(client, keys="WAI-100", since=first["fingerprint"])
    assert changed["unchanged"] is False
    assert changed["fingerprint"] != first["fingerprint"]
    assert changed["commits"][0]["sha"] == new_sha


async def test_paginacao_pelo_skip(client, repo):
    page = await _graph(client, scope="all", limit=2)
    assert len(page["commits"]) == 2
    assert page["has_more"] is True
    rest = await _graph(client, scope="all", limit=50, skip=2)
    assert rest["has_more"] is False
    assert not {c["sha"] for c in page["commits"]} & {c["sha"] for c in rest["commits"]}


async def test_pr_do_espelho_etiqueta_a_branch_local_e_a_remota(client, repo, db_pool):
    # O remote do teste é uma pasta, não o Bitbucket: o vínculo vem do ajuste do dev.
    await workspace_repo.set_overrides(
        db_pool, "monitoria", link_override="monitoria", base_branch_override=None
    )
    await bitbucket_repo.upsert_pull_requests(
        db_pool,
        [
            {
                "repo_slug": "monitoria",
                "id": 397,
                "title": "WAI-100 aplica a chave",
                "description": None,
                "state": "OPEN",
                "draft": False,
                "author_name": "Dev",
                "source_branch": "WAI-100-chave",
                "source_commit": "abc",
                "destination_branch": "main",
                "participants": [],
                "comment_count": 0,
                "task_count": 0,
                "build_status": None,
                "issue_keys": ["WAI-100"],
                "url": "https://bitbucket.org/weonrepo/monitoria/pull-requests/397",
                "created_on": T0,
                "updated_on": T0,
            }
        ],
    )
    graph = await _graph(client, keys="WAI-100")

    [pr] = _ref(graph, "WAI-100-chave")["pull_requests"]
    assert (pr["id"], pr["status"]) == (397, "pr_aberta")
    assert _ref(graph, "origin/WAI-100-chave")["pull_requests"][0]["id"] == 397
    assert _ref(graph, "main")["pull_requests"] == []


async def test_detalhe_do_commit_com_arquivos(client, repo):
    response = await client.get(f"/api/workspace/repos/monitoria/commits/{repo['feature_pushed']}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["message"] == "WAI-100: aplica a chave na integração"
    assert detail["issue_keys"] == ["WAI-100"]
    assert detail["files"] == [{"path": "chave.txt", "added": 1, "deleted": 0}]
    assert detail["parents"] == [repo["first"]]


async def test_entrada_invalida_e_repo_indisponivel(client, repo):
    base = "/api/workspace/repos/monitoria"
    assert (await client.get(f"{base}/commits/--output=x")).status_code == 422
    assert (await client.get(f"{base}/commits/HEAD")).status_code == 422
    assert (await client.get(f"{base}/graph", params={"keys": "x;rm"})).status_code == 422
    assert (await client.get(f"{base}/graph", params={"scope": "tudo"})).status_code == 422
    assert (await client.get("/api/workspace/repos/nao-existe/graph")).status_code == 409


def test_lista_branca_recusa_subcomando_de_escrita(tmp_path):
    for sub in ("commit", "fetch", "push", "checkout", "config", "-c"):
        with pytest.raises(git_local.GitError, match="lista de leitura"):
            git_local.run_git(tmp_path, sub)


async def test_revisao_com_opcao_e_recusada(tmp_path):
    with pytest.raises(git_local.GitError, match="Revisão inválida"):
        await git_local.log(tmp_path, ["--output=/tmp/x"], skip=0, limit=1)


def test_status_le_renomeacao_conflito_e_nao_rastreado():
    output = "\0".join(
        [
            "# branch.oid abc",
            "# branch.head main",
            "# branch.upstream origin/main",
            "# branch.ab +2 -1",
            "1 .M N... 100644 100644 100644 a b arquivo.txt",
            "2 R. N... 100644 100644 100644 a b R100 novo.txt",
            "velho.txt",
            "u UU N... 100644 100644 100644 100644 a b c conflito.txt",
            "? solto.txt",
            "",
        ]
    )
    changes = git_local.parse_status(output)
    assert (changes.changed, changes.untracked, changes.conflicted) == (2, 1, 1)
    assert (changes.upstream, changes.ahead, changes.behind) == ("origin/main", 2, 1)


def test_track_do_upstream():
    assert git_local.parse_track("ahead 2, behind 1") == (2, 1, False)
    assert git_local.parse_track("behind 4") == (0, 4, False)
    assert git_local.parse_track("gone") == (0, 0, True)
    assert git_local.parse_track("") == (0, 0, False)


def test_impressao_muda_com_ref_nova(tmp_path):
    made = make_git_repo(tmp_path / "p")
    git_dir = Path(made["repo"]) / ".git"
    before = git_local.fingerprint(git_dir)
    assert git_local.fingerprint(git_dir) == before
    git(made["repo"], "branch", "WAI-300-nova")
    assert git_local.fingerprint(git_dir) != before
