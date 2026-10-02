from datetime import UTC, datetime
from pathlib import Path

import pytest

from repositories import bitbucket_repo
from security.paths import Roots, get_roots
from security.process_env import clean_environment
from services.workspace import launcher
from tests.workspace_fakes import make_repo

T0 = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)


async def _issue(pool, key, summary, *, type_="Tarefa", parent=None, assignee="acc-me"):
    await pool.execute(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, summary, status, status_category,
                                assignee_account_id, assignee_name, parent_key, story_points,
                                created_at, updated_at, raw)
        VALUES ($1, $1, 'WAI', $2, $3, 'Em Desenvolvimento', 'indeterminate', $4, 'Dev', $5, 3,
                now(), now(), '{}')
        """,
        key,
        type_,
        summary,
        assignee,
        parent,
    )


async def _link(pool, link_id, source, target, link_type, target_type, **snapshot):
    await pool.execute(
        """
        INSERT INTO jira_issue_link (id, source_key, target_key, link_type, direction, label,
                                     target_type, target_summary, target_status)
        VALUES ($1, $2, $3, $4, 'outward', $4, $5, $6, $7)
        """,
        link_id,
        source,
        target,
        link_type,
        target_type,
        snapshot.get("summary"),
        snapshot.get("status"),
    )


@pytest.fixture
async def seeded(db_app, db_pool, credential_store):
    """Épico WAI-7326 → Tarefas fatiadas WAI-8790 (monitoria) e WAI-8791 (qualificai), as duas
    ligadas por Relates ao Enhancements WAI-8677; WAI-8790 bloqueia WAI-8791 e tem uma
    subtarefa; a "Analisar e fatiar" WAI-8680 aponta para o Enhancements; WAI-9001 é de outro
    dev e só existe no snapshot do link do Enhancements."""
    credential_store.set(
        "jira",
        {
            "site_url": "https://weon.atlassian.net",
            "email": "d@w.com",
            "api_token": "t" * 24,
            "account_id": "acc-me",
        },
    )
    await _issue(db_pool, "WAI-7326", "OrganIA na WeON", type_="Épico", assignee=None)
    await _issue(db_pool, "WAI-8677", "Fonte única do cliente", type_="Enhancements", assignee=None)
    await _issue(db_pool, "WAI-8680", "Analisar e fatiar a: fonte única")
    await _issue(db_pool, "WAI-8790", "[monitoria] Rota única de cadastro", parent="WAI-7326")
    await _issue(db_pool, "WAI-8791", "[QualificAI] Trial pelo WeON", parent="WAI-7326")
    await _issue(db_pool, "WAI-8795", "Migration da rota", type_="Subtarefa", parent="WAI-8790")
    await _issue(db_pool, "WAI-5000", "[monitoria] Outra coisa")
    await _link(db_pool, "1", "WAI-8790", "WAI-8677", "Relates", "Enhancements")
    await _link(db_pool, "2", "WAI-8791", "WAI-8677", "Relates", "Enhancements")
    await _link(db_pool, "3", "WAI-8790", "WAI-8791", "Blocks", "Tarefa")
    await _link(db_pool, "4", "WAI-8680", "WAI-8677", "Divisão do ticket", "Enhancements")
    await _link(
        db_pool,
        "5",
        "WAI-8677",
        "WAI-9001",
        "Relates",
        "Tarefa",
        summary="[qualificai] Parte de outro dev",
        status="Em Review",
    )


@pytest.fixture
def projects(tmp_path, db_app):
    root = tmp_path / "projects"
    root.mkdir()
    make_repo(
        root,
        "monitoria",
        url="git@bitbucket.org:weonrepo/monitoria.git",
        files={"refs/heads/WAI-8790-rota-unica": "abc\n"},
    )
    make_repo(root, "qualificai", url="git@bitbucket.org:weonrepo/qualificai.git")
    make_repo(root, "supervisor-web", url="git@bitbucket.org:weonrepo/supervisor-web.git")
    db_app.dependency_overrides[get_roots] = lambda: Roots(projects=root, claude=tmp_path / "c")
    return root


async def _open(client, **payload):
    response = await client.post("/api/workspaces", json=payload)
    assert response.status_code in (200, 201), response.text
    return response


async def test_abrir_a_mesma_tarefa_reabre_o_workspace(client, seeded):
    first = await _open(client, root_issue_key="wai-8677")
    assert first.status_code == 201
    body = first.json()
    assert (body["kind"], body["root_issue_key"], body["title"]) == (
        "issue",
        "WAI-8677",
        "Fonte única do cliente",
    )

    response = await client.patch(f"/api/workspaces/{body['id']}", json={"is_open": False})
    assert response.json()["is_open"] is False

    again = await _open(client, root_issue_key="WAI-8677")
    assert again.status_code == 200
    assert again.json()["id"] == body["id"]
    assert again.json()["is_open"] is True


async def test_tarefa_fora_do_espelho_nao_abre(client, seeded):
    response = await client.post("/api/workspaces", json={"root_issue_key": "WAI-1"})
    assert response.status_code == 404
    assert (await client.post("/api/workspaces", json={})).status_code == 422


async def test_arvore_do_enhancements_desce_as_fatias_e_a_parte_de_outro_dev(client, seeded):
    workspace = (await _open(client, root_issue_key="WAI-8677")).json()
    response = await client.get(f"/api/workspaces/{workspace['id']}/tree")
    assert response.status_code == 200
    tree = response.json()
    nodes = {n["key"]: n for n in tree["nodes"]}

    assert tree["frame"] == {"id": f"workspace:{workspace['id']}", "label": "na feature"}
    in_frame = {k for k, n in nodes.items() if n["in_sprint"]}
    assert in_frame == {"WAI-8677", "WAI-8680", "WAI-8790", "WAI-8791", "WAI-8795", "WAI-9001"}
    assert "WAI-5000" not in nodes
    # O Épico entra só como contexto, pela subida dos pais das fatias.
    assert nodes["WAI-7326"]["in_sprint"] is False
    assert nodes["WAI-8790"]["parent_key"] == "WAI-7326"
    assert nodes["WAI-8790"]["co_parents"] == ["WAI-8677"]
    assert nodes["WAI-8795"]["parent_key"] == "WAI-8790"

    other = nodes["WAI-9001"]
    assert other["partial"] is True
    assert other["summary"] == "[qualificai] Parte de outro dev"
    assert other["parent_key"] == "WAI-8677"

    assert {"source": "WAI-8790", "target": "WAI-8791", "kind": "blocks", "label": "bloqueia"} in (
        tree["edges"]
    )
    assert nodes["WAI-8791"]["predecessors"] == ["WAI-8790"]


async def test_arvore_de_uma_tarefa_traz_subtarefa_e_vizinhas(client, seeded):
    workspace = (await _open(client, root_issue_key="WAI-8790")).json()
    tree = (await client.get(f"/api/workspaces/{workspace['id']}/tree")).json()
    nodes = {n["key"]: n for n in tree["nodes"]}

    assert {k for k, n in nodes.items() if n["in_sprint"]} == {"WAI-8790", "WAI-8791", "WAI-8795"}
    assert nodes["WAI-7326"]["in_sprint"] is False
    assert "WAI-8680" not in nodes


async def test_repos_envolvidos_pela_branch_pelo_pr_e_pelo_titulo(client, seeded, projects, db_pool):
    await bitbucket_repo.upsert_pull_requests(
        db_pool,
        [
            {
                "repo_slug": "qualificai",
                "id": 88,
                "title": "Trial",
                "description": None,
                "state": "OPEN",
                "draft": False,
                "author_name": "Dev",
                "source_branch": "WAI-8791-trial",
                "source_commit": "a",
                "destination_branch": "main",
                "participants": [],
                "comment_count": 0,
                "task_count": 0,
                "build_status": None,
                "issue_keys": ["WAI-8791"],
                "url": "https://bitbucket.org/weonrepo/qualificai/pull-requests/88",
                "created_on": T0,
                "updated_on": T0,
            }
        ],
    )
    workspace = (await _open(client, root_issue_key="WAI-8677")).json()
    response = await client.get(f"/api/workspaces/{workspace['id']}")
    assert response.status_code == 200
    detail = response.json()
    assert "WAI-9001" in detail["keys"]
    repos = {r["slug"]: r for r in detail["repos"]}

    assert set(repos) == {"monitoria", "qualificai"}
    monitoria = repos["monitoria"]
    assert monitoria["sources"] == ["branch", "title"]
    assert monitoria["branches"] == ["WAI-8790-rota-unica"]
    assert monitoria["issue_keys"] == ["WAI-8790"]
    assert monitoria["local"] is True
    assert monitoria["path"] == str(projects / "monitoria")

    qualificai = repos["qualificai"]
    assert qualificai["sources"] == ["pr", "title"]
    assert qualificai["issue_keys"] == ["WAI-8791", "WAI-9001"]


async def test_fixar_e_esconder_repo(client, seeded, projects):
    workspace = (await _open(client, root_issue_key="WAI-8790")).json()
    base = f"/api/workspaces/{workspace['id']}"

    assert (await client.put(f"{base}/repos/supervisor-web", json={"mode": "add"})).status_code == 204
    assert (await client.put(f"{base}/repos/api-credits", json={"mode": "add"})).status_code == 204
    assert (await client.put(f"{base}/repos/monitoria", json={"mode": "hide"})).status_code == 204
    repos = {r["slug"]: r for r in (await client.get(base)).json()["repos"]}
    assert repos["supervisor-web"]["sources"] == ["pin"]
    assert repos["supervisor-web"]["local"] is True
    assert repos["api-credits"]["local"] is False
    assert repos["api-credits"]["path"] is None
    assert repos["monitoria"]["hidden"] is True

    await client.put(f"{base}/repos/monitoria", json={"mode": "auto"})
    repos = {r["slug"]: r for r in (await client.get(base)).json()["repos"]}
    assert repos["monitoria"]["hidden"] is False

    assert (await client.put(f"{base}/repos/x", json={"mode": "fixar"})).status_code == 422
    assert (await client.put("/api/workspaces/999/repos/x", json={"mode": "add"})).status_code == 404


async def test_workspace_livre_lista_so_os_fixados(client, seeded, projects):
    workspace = (await _open(client, title="Testes de carga", repos=["qualificai"])).json()
    assert (workspace["kind"], workspace["root_issue_key"]) == ("free", None)

    tree = (await client.get(f"/api/workspaces/{workspace['id']}/tree")).json()
    assert tree["nodes"] == []
    detail = (await client.get(f"/api/workspaces/{workspace['id']}")).json()
    assert [(r["slug"], r["sources"]) for r in detail["repos"]] == [("qualificai", ["pin"])]

    listed = (await client.get("/api/workspaces")).json()
    assert [w["title"] for w in listed] == ["Testes de carga"]
    assert (await client.delete(f"/api/workspaces/{workspace['id']}")).status_code == 204
    assert (await client.get(f"/api/workspaces/{workspace['id']}")).status_code == 404


async def test_abrir_pasta_no_vscode_so_dentro_de_projects(client, projects, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(launcher, "launch", lambda target, folder: calls.append((target, folder)))

    ok = await client.post(
        "/api/workspace/open", json={"target": "ide", "path": str(projects / "monitoria")}
    )
    assert ok.status_code == 204
    assert calls == [("ide", (projects / "monitoria").resolve())]

    outside = tmp_path / "fora"
    outside.mkdir()
    response = await client.post("/api/workspace/open", json={"target": "ide", "path": str(outside)})
    assert response.status_code == 422
    response = await client.post(
        "/api/workspace/open", json={"target": "explorer", "path": str(projects / "monitoria")}
    )
    assert response.status_code == 422
    assert len(calls) == 1


async def test_programa_ausente_vira_409(client, projects, monkeypatch):
    monkeypatch.setattr(launcher, "windows_terminal_executable", lambda: None)
    response = await client.post(
        "/api/workspace/open", json={"target": "terminal", "path": str(projects / "monitoria")}
    )
    assert response.status_code == 409


def test_comandos_sao_executaveis_e_recusam_ponto_e_virgula(monkeypatch):
    monkeypatch.setattr(launcher, "vscode_executable", lambda: Path(r"C:\VS Code\Code.exe"))
    monkeypatch.setattr(launcher, "windows_terminal_executable", lambda: Path(r"C:\wt.exe"))
    folder = Path(r"C:\projects\monitoria")
    assert launcher.command_for("ide", folder) == [r"C:\VS Code\Code.exe", str(folder)]
    assert launcher.command_for("terminal", folder) == [r"C:\wt.exe", "-d", str(folder)]
    with pytest.raises(launcher.LauncherUnavailable):
        launcher.command_for("terminal", Path(r"C:\projects\a;b"))


def test_ambiente_do_processo_sai_sem_a_configuracao_do_sprintai(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "senha-do-banco")
    monkeypatch.setenv("SPRINTAI_QUALQUER", "x")
    monkeypatch.setenv("PATH_DO_DEV", "fica")
    env = clean_environment({"TERM": "xterm-256color"})
    assert "DB_PASSWORD" not in env
    assert "SPRINTAI_QUALQUER" not in env
    assert env["PATH_DO_DEV"] == "fica"
    assert env["TERM"] == "xterm-256color"
