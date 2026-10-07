"""O "Concluir" do card (receita por repo, plano e execução) e os reviewers pelo SprintAI."""

import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from integrations.bitbucket_client import BitbucketClient
from repositories import bitbucket_repo
from services import conclude_settings, pr_reviewers
from services.conclude_settings import RepoConclusion
from services.sync.engine import get_sync_engine

SITE = "https://weon.atlassian.net"
BB = "https://api.bitbucket.org/2.0/repositories/weonrepo"
T0 = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


class FakeEngine:
    """O sync de verdade sairia para a rede: aqui só anota que foi pedido."""

    def __init__(self) -> None:
        self.triggers: list[str] = []

    async def trigger(self, trigger: str = "manual") -> int:
        self.triggers.append(trigger)
        return 1


# Aprovação do revisor: com a regra padrão (uma aprovação), o PR está "Aprovada" — o card está
# apto ao Concluir.
APPROVED = {
    "role": "REVIEWER", "approved": True, "state": "approved", "name": "Rafael",
    "account_id": "acc-rafa",
}


def _pr(repo, pr_id, *, state="OPEN", build=None, participants=None, key="WAI-124"):
    return {
        "repo_slug": repo,
        "id": pr_id,
        "title": f"{key} trial",
        "description": None,
        "state": state,
        "draft": False,
        "author_name": "Matheus",
        "source_branch": f"feature/{key}",
        "source_commit": "a",
        "destination_branch": "develop",
        "participants": participants or [],
        "comment_count": 0,
        "task_count": 0,
        "build_status": build,
        "issue_keys": [key],
        "url": f"https://bitbucket.org/weonrepo/{repo}/pull-requests/{pr_id}",
        "created_on": T0,
        "updated_on": T0,
    }


@pytest.fixture
def engine(db_app):
    fake = FakeEngine()
    db_app.dependency_overrides[get_sync_engine] = lambda: fake
    return fake


@pytest.fixture
async def seeded(db_pool, credential_store):
    pr_reviewers.clear_members_cache()
    credential_store.set(
        "jira",
        {
            "site_url": SITE,
            "email": "d@w.com",
            "api_token": "t" * 24,
            "auth_mode": "classic",
            "account_id": "acc-me",
        },
    )
    credential_store.set(
        "bitbucket",
        {"email": "d@w.com", "api_token": "b" * 24, "workspace": "weonrepo", "account_id": "acc-me"},
    )
    await db_pool.execute(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, summary, status,
            status_category, assignee_account_id, assignee_name, created_at, updated_at, raw)
        VALUES ('WAI-124', '10124', 'WAI', 'Tarefa', 'Trial', 'Em Review', 'indeterminate',
            'acc-me', 'Matheus Bacca', $1, $1, '{}')
        """,
        T0,
    )
    await bitbucket_repo.upsert_pull_requests(
        db_pool,
        [
            _pr(
                "monitoria",
                412,
                build="FAILED",
                participants=[APPROVED],
            ),
            _pr("monitoria", 400, state="MERGED"),
        ],
    )
    yield db_pool
    pr_reviewers.clear_members_cache()


def _mock_jira(current="Em Review", targets=("DISPONIVEL PARA TESTES",)):
    respx.get(f"{SITE}/rest/api/3/issue/WAI-124").mock(
        return_value=httpx.Response(
            200, json={"key": "WAI-124", "fields": {"status": {"name": current}}}
        )
    )
    respx.get(f"{SITE}/rest/api/3/issue/WAI-124/transitions").mock(
        return_value=httpx.Response(
            200,
            json={
                "transitions": [
                    {"id": str(30 + i), "name": f"Ir para {t}", "to": {"name": t,
                     "statusCategory": {"key": "new"}}, "fields": {}}
                    for i, t in enumerate(targets)
                ]
            },
        )
    )


async def _rules(pool, **rules):
    await conclude_settings.save_rules(pool, {slug: RepoConclusion(**r) for slug, r in rules.items()})


# --- Configurações › Concluir --------------------------------------------------------------------


async def test_receita_por_repo_guarda_so_o_que_faz_algo(db_app, client, seeded):
    response = await client.put(
        "/api/preferences/conclude",
        json={
            "repos": {
                "monitoria": {"jira_status": " DISPONIVEL PARA TESTES ", "merge": True,
                              "strategy": "squash"},
                "qualificai": {"jira_status": "Concluído"},
                "vazio": {"jira_status": "", "merge": False},
            }
        },
    )
    assert response.status_code == 200, response.text
    body = (await client.get("/api/preferences/conclude")).json()
    assert body["repos"] == {
        "monitoria": {"jira_status": "DISPONIVEL PARA TESTES", "merge": True,
                      "strategy": "squash", "close_source_branch": True},
        "qualificai": {"jira_status": "Concluído", "merge": False,
                       "strategy": "merge_commit", "close_source_branch": True},
    }
    assert {"monitoria", "qualificai"} <= set(body["known_repos"])
    assert "Em Review" in body["statuses"]

    bad = await client.put(
        "/api/preferences/conclude", json={"repos": {"x": {"merge": True, "strategy": "rebase"}}}
    )
    assert bad.status_code == 422


def test_receita_lida_do_banco_descarta_o_que_nao_presta():
    rules = conclude_settings.from_setting(
        {"repos": {"a": {"merge": True, "strategy": "inventada"}, "b": {"merge": "sim"}, "c": 3}}
    )
    assert rules == {"a": RepoConclusion(merge=True, strategy="merge_commit")}


async def test_detalhe_marca_a_tarefa_apta_ao_concluir(db_app, client, seeded):
    assert (await client.get("/api/issues/WAI-124")).json()["conclude"] is False
    await _rules(seeded, monitoria={"jira_status": "DISPONIVEL PARA TESTES"})
    assert (await client.get("/api/issues/WAI-124")).json()["conclude"] is True


async def _set_participants(pool, participants):
    await pool.execute(
        "UPDATE bb_pull_request SET participants = $1 WHERE repo_slug = 'monitoria' AND id = 412",
        participants,
    )


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("sem_aprovacao", "não está aprovado pela regra"),
        ("ajuste_pedido", "não está aprovado pela regra"),
        ("em_testes", "antes dos testes"),
        ("concluida", "já está concluída"),
        ("sem_pr", "não tem PR"),
    ],
)
@respx.mock
async def test_card_fora_da_regra_nao_tem_concluir(db_app, client, seeded, engine, change, reason):
    _mock_jira()
    await _rules(seeded, monitoria={"jira_status": "DISPONIVEL PARA TESTES", "merge": True})
    if change == "sem_aprovacao":
        await _set_participants(seeded, [{**APPROVED, "approved": False, "state": None}])
    elif change == "ajuste_pedido":
        await _set_participants(
            seeded, [{**APPROVED}, {**APPROVED, "approved": False, "state": "changes_requested",
                                    "name": "Ju", "account_id": "acc-ju"}]
        )
    elif change == "em_testes":
        await seeded.execute(
            "UPDATE jira_issue SET status = 'DISPONIVEL PARA TESTES', status_category = 'new'"
        )
    elif change == "concluida":
        await seeded.execute("UPDATE jira_issue SET status = 'Feito', status_category = 'done'")
    else:
        # Sem PR, o repo vem do [repo] do título — e ainda assim não há o que concluir.
        await client.put("/api/preferences/card-colors", json={"repos": {"monitoria": "#2f7cf6"}})
        await seeded.execute("UPDATE jira_issue SET summary = '[monitoria] Trial'")
        await seeded.execute("DELETE FROM bb_pull_request")

    assert (await client.get("/api/issues/WAI-124")).json()["conclude"] is False
    plan = (await client.get("/api/issues/WAI-124/conclude")).json()
    assert reason in plan["blocked"]
    # Mesmo vindo de uma tela desatualizada, a execução recusa.
    response = await client.post(
        "/api/issues/WAI-124/conclude",
        json={"jira_status": "DISPONIVEL PARA TESTES",
              "merges": [{"repo_slug": "monitoria", "pr_id": 412}]},
    )
    assert response.status_code == 409
    assert reason in response.json()["detail"]
    assert engine.triggers == []


async def test_pr_ja_mergeado_deixa_concluir_so_o_jira(db_app, client, seeded):
    await seeded.execute("UPDATE bb_pull_request SET state = 'MERGED' WHERE id = 412")
    await _rules(seeded, monitoria={"jira_status": "DISPONIVEL PARA TESTES", "merge": True})
    assert (await client.get("/api/issues/WAI-124")).json()["conclude"] is True


# --- Plano -------------------------------------------------------------------------------------


@respx.mock
async def test_plano_traz_o_merge_com_avisos_e_o_status_do_jira(db_app, client, seeded):
    _mock_jira()
    await _rules(
        seeded,
        monitoria={"jira_status": "DISPONIVEL PARA TESTES", "merge": True, "strategy": "squash"},
    )

    plan = (await client.get("/api/issues/WAI-124/conclude")).json()
    assert plan["status"] == "Em Review"
    assert plan["repos"] == ["monitoria"]
    # Só o PR aberto entra; o mergeado fica de fora.
    assert [(m["repo_slug"], m["pr_id"], m["strategy"]) for m in plan["merges"]] == [
        ("monitoria", 412, "squash")
    ]
    assert plan["merges"][0]["warnings"] == ["build falhou"]
    assert plan["blocked"] is None
    assert plan["targets"] == [
        {"status": "DISPONIVEL PARA TESTES", "current": False, "available": True, "reason": None}
    ]


@respx.mock
async def test_plano_avisa_transicao_que_o_jira_nao_oferece(db_app, client, seeded):
    _mock_jira(targets=())
    await _rules(seeded, monitoria={"jira_status": "Concluído"})

    target = (await client.get("/api/issues/WAI-124/conclude")).json()["targets"][0]
    assert (target["available"], target["status"]) == (False, "Concluído")
    assert "não oferece" in target["reason"]


# --- Execução ----------------------------------------------------------------------------------


@respx.mock
async def test_concluir_mergeia_e_depois_move_no_jira(db_app, client, seeded, engine):
    _mock_jira()
    merge = respx.post(f"{BB}/monitoria/pullrequests/412/merge").mock(
        return_value=httpx.Response(200, json={"id": 412, "state": "MERGED"})
    )
    move = respx.post(f"{SITE}/rest/api/3/issue/WAI-124/transitions").mock(
        return_value=httpx.Response(204)
    )
    await _rules(
        seeded,
        monitoria={"jira_status": "DISPONIVEL PARA TESTES", "merge": True, "strategy": "squash"},
    )

    response = await client.post(
        "/api/issues/WAI-124/conclude",
        json={"jira_status": "DISPONIVEL PARA TESTES",
              "merges": [{"repo_slug": "monitoria", "pr_id": 412}]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["done"] is True
    assert [s["kind"] for s in body["steps"]] == ["merge", "transition"]
    assert body["status"] == "DISPONIVEL PARA TESTES"
    assert body["write_id"]
    assert json.loads(merge.calls.last.request.read()) == {
        "type": "pullrequest",
        "merge_strategy": "squash",
        "close_source_branch": True,
    }
    assert move.called
    assert await seeded.fetchval("SELECT status FROM jira_issue WHERE key = 'WAI-124'") == (
        "DISPONIVEL PARA TESTES"
    )
    # O espelho do PR é do sync: ele é chamado, não escrito à mão.
    assert engine.triggers == ["concluir"]
    state = await seeded.fetchval(
        "SELECT state FROM bb_pull_request WHERE repo_slug = 'monitoria' AND id = 412"
    )
    assert state == "OPEN"


@respx.mock
async def test_merge_recusado_nao_move_o_jira(db_app, client, seeded, engine):
    _mock_jira()
    respx.post(f"{BB}/monitoria/pullrequests/412/merge").mock(return_value=httpx.Response(400))
    move = respx.post(f"{SITE}/rest/api/3/issue/WAI-124/transitions")
    await _rules(seeded, monitoria={"jira_status": "DISPONIVEL PARA TESTES", "merge": True})

    body = (
        await client.post(
            "/api/issues/WAI-124/conclude",
            json={"jira_status": "DISPONIVEL PARA TESTES",
                  "merges": [{"repo_slug": "monitoria", "pr_id": 412}]},
        )
    ).json()
    assert body["done"] is False
    assert [(s["kind"], s["ok"]) for s in body["steps"]] == [("merge", False)]
    assert "merge checks" in body["steps"][0]["message"]
    assert body["steps"][0]["url"].endswith("/pull-requests/412")
    assert not move.called
    assert engine.triggers == []
    assert await seeded.fetchval("SELECT status FROM jira_issue WHERE key = 'WAI-124'") == (
        "Em Review"
    )


@respx.mock
async def test_merge_sem_escopo_de_escrita_explica_o_token(db_app, client, seeded, engine):
    _mock_jira()
    respx.post(f"{BB}/monitoria/pullrequests/412/merge").mock(return_value=httpx.Response(403))
    await _rules(seeded, monitoria={"merge": True})

    body = (
        await client.post(
            "/api/issues/WAI-124/conclude",
            json={"merges": [{"repo_slug": "monitoria", "pr_id": 412}]},
        )
    ).json()
    assert "write:pullrequest:bitbucket" in body["steps"][0]["message"]


@respx.mock
async def test_concluir_confere_o_pedido_contra_o_plano(db_app, client, seeded, engine):
    _mock_jira(targets=("DISPONIVEL PARA TESTES", "Concluído"))
    await bitbucket_repo.upsert_pull_requests(seeded, [_pr("qualificai", 9, participants=[APPROVED])])
    await _rules(
        seeded,
        monitoria={"jira_status": "DISPONIVEL PARA TESTES", "merge": True},
        qualificai={"jira_status": "Concluído"},
    )

    # PR que não está no plano (o mergeado, um de outro repo) não roda.
    for ref in ({"repo_slug": "monitoria", "pr_id": 400}, {"repo_slug": "qualificai", "pr_id": 9}):
        response = await client.post(
            "/api/issues/WAI-124/conclude", json={"jira_status": "Concluído", "merges": [ref]}
        )
        assert response.status_code == 409, ref

    # Dois repos, dois status: sem escolha não roda; status fora da receita também não.
    plan = (await client.get("/api/issues/WAI-124/conclude")).json()
    assert [t["status"] for t in plan["targets"]] == ["DISPONIVEL PARA TESTES", "Concluído"]
    response = await client.post("/api/issues/WAI-124/conclude", json={})
    assert response.status_code == 409
    assert "escolha" in response.json()["detail"]
    response = await client.post("/api/issues/WAI-124/conclude", json={"jira_status": "Cruzeiro"})
    assert response.status_code == 409
    # Pedido sem o merge que o plano de agora traz: o plano mudou, o dev abre de novo.
    response = await client.post("/api/issues/WAI-124/conclude", json={"jira_status": "Concluído"})
    assert response.status_code == 409
    assert "#412 de monitoria" in response.json()["detail"]
    assert engine.triggers == []


@respx.mock
async def test_ja_no_status_de_destino_so_mergeia(db_app, client, seeded, engine):
    _mock_jira(current="DISPONIVEL PARA TESTES", targets=())
    respx.post(f"{BB}/monitoria/pullrequests/412/merge").mock(
        return_value=httpx.Response(200, json={"id": 412, "state": "MERGED"})
    )
    await _rules(seeded, monitoria={"jira_status": "DISPONIVEL PARA TESTES", "merge": True})

    body = (
        await client.post(
            "/api/issues/WAI-124/conclude",
            json={"merges": [{"repo_slug": "monitoria", "pr_id": 412}]},
        )
    ).json()
    assert body["done"] is True
    assert body["steps"][-1]["label"] == "Já estava em DISPONIVEL PARA TESTES"
    assert body["write_id"]


@respx.mock
async def test_merge_demorado_acompanha_a_tarefa_do_bitbucket():
    respx.post(f"{BB}/monitoria/pullrequests/5/merge").mock(
        return_value=httpx.Response(
            202,
            json={
                "task_status": "PENDING",
                "links": {"self": {"href": f"{BB}/monitoria/pullrequests/5/merge/task-status/7"}},
            },
        )
    )
    respx.get(f"{BB}/monitoria/pullrequests/5/merge/task-status/7").mock(
        return_value=httpx.Response(
            200, json={"task_status": "SUCCESS", "merge_result": {"id": 5, "state": "MERGED"}}
        )
    )
    waits = []

    async def sleep(seconds):
        waits.append(seconds)

    async with BitbucketClient.create(email="e", api_token="t", workspace="weonrepo") as bb:
        result = await bb.merge_pull_request(
            "monitoria", 5, strategy="merge_commit", close_source_branch=False, sleep=sleep
        )
    assert result == {"id": 5, "state": "MERGED"}
    assert waits == [2.0]


# --- Reviewers -----------------------------------------------------------------------------------


def _user(uid, account, name):
    return {"type": "user", "uuid": uid, "account_id": account, "display_name": name}


@respx.mock
async def test_membros_do_workspace_ficam_guardados(db_app, client, seeded):
    members = respx.get("https://api.bitbucket.org/2.0/workspaces/weonrepo/members").mock(
        return_value=httpx.Response(
            200,
            json={
                "values": [
                    {"user": _user("{b}", "acc-rafa", "Rafael")},
                    {"user": _user("{a}", "acc-me", "Matheus")},
                    {"user": {"type": "team", "display_name": "Time"}},
                ]
            },
        )
    )
    first = (await client.get("/api/bitbucket/members")).json()["members"]
    assert [(m["name"], m["is_me"]) for m in first] == [("Matheus", True), ("Rafael", False)]
    await client.get("/api/bitbucket/members")
    assert members.call_count == 1
    await client.get("/api/bitbucket/members", params={"refresh": "true"})
    assert members.call_count == 2


@respx.mock
async def test_membros_sem_escopo_dizem_qual_falta(db_app, client, seeded):
    respx.get("https://api.bitbucket.org/2.0/workspaces/weonrepo/members").mock(
        return_value=httpx.Response(403)
    )
    response = await client.get("/api/bitbucket/members")
    assert response.status_code == 502
    assert "read:workspace:bitbucket" in response.json()["detail"]


@respx.mock
async def test_reviewers_poe_e_tira_mantendo_os_outros(db_app, client, seeded, engine):
    respx.get("https://api.bitbucket.org/2.0/workspaces/weonrepo/members").mock(
        return_value=httpx.Response(
            200, json={"values": [{"user": _user("{c}", "acc-carla", "Carla")}]}
        )
    )
    respx.get(f"{BB}/monitoria/pullrequests/412").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 412,
                "state": "OPEN",
                "title": "WAI-124 trial",
                "reviewers": [_user("{r}", "acc-rafa", "Rafael"), _user("{j}", "acc-ju", "Ju")],
            },
        )
    )
    put = respx.put(f"{BB}/monitoria/pullrequests/412").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 412,
                "reviewers": [_user("{r}", "acc-rafa", "Rafael"), _user("{c}", "acc-carla", "Carla")],
                "participants": [
                    {"role": "REVIEWER", "approved": True, "state": "approved",
                     "user": _user("{r}", "acc-rafa", "Rafael")},
                ],
            },
        )
    )

    response = await client.put(
        "/api/pull-requests/monitoria/412/reviewers",
        json={"add": ["acc-carla", "acc-rafa"], "remove": ["acc-ju"]},
    )
    assert response.status_code == 200, response.text
    assert json.loads(put.calls.last.request.read()) == {
        "title": "WAI-124 trial",
        "reviewers": [{"uuid": "{r}"}, {"uuid": "{c}"}],
    }
    reviewers = response.json()["reviewers"]
    assert [(r["name"], r["approved"]) for r in reviewers] == [("Rafael", True), ("Carla", False)]
    assert engine.triggers == ["reviewers"]


@respx.mock
async def test_reviewers_so_em_pr_aberto_do_espelho(db_app, client, seeded, engine):
    respx.get("https://api.bitbucket.org/2.0/workspaces/weonrepo/members").mock(
        return_value=httpx.Response(200, json={"values": []})
    )
    response = await client.put("/api/pull-requests/monitoria/999/reviewers", json={"add": ["x"]})
    assert response.status_code == 404

    respx.get(f"{BB}/monitoria/pullrequests/400").mock(
        return_value=httpx.Response(200, json={"id": 400, "state": "MERGED", "title": "x"})
    )
    response = await client.put("/api/pull-requests/monitoria/400/reviewers", json={"add": ["x"]})
    assert response.status_code == 409

    respx.get(f"{BB}/monitoria/pullrequests/412").mock(
        return_value=httpx.Response(200, json={"id": 412, "state": "OPEN", "title": "x"})
    )
    respx.put(f"{BB}/monitoria/pullrequests/412").mock(return_value=httpx.Response(403))
    response = await client.put("/api/pull-requests/monitoria/412/reviewers", json={"add": ["x"]})
    assert response.status_code == 502
    assert "write:pullrequest:bitbucket" in response.json()["detail"]
    assert engine.triggers == []


async def test_reviewer_do_espelho_leva_o_account_id_e_a_foto(db_app, client, seeded):
    photo = "https://avatar-management.example/RS-2.png"
    await _set_participants(seeded, [{**APPROVED, "avatar_url": photo}])
    detail = (await client.get("/api/issues/WAI-124")).json()
    pr = detail["pull_requests"]["repos"][0]["pull_requests"][0]
    assert pr["reviewers"][0]["account_id"] == "acc-rafa"
    assert pr["reviewers"][0]["avatar_url"] == photo


# --- Vários PRs abertos: um de cada vez, o Jira no último ----------------------------------------


async def _second_pr(pool, *, approved, repo="monitoria", pr_id=413):
    participants = [APPROVED] if approved else [{**APPROVED, "approved": False, "state": None}]
    await bitbucket_repo.upsert_pull_requests(pool, [_pr(repo, pr_id, participants=participants)])


@respx.mock
async def test_pr_sem_aprovacao_ao_lado_de_um_aprovado_nao_barra_e_segura_o_jira(
    db_app, client, seeded, engine
):
    jira = respx.get(f"{SITE}/rest/api/3/issue/WAI-124/transitions")
    move = respx.post(f"{SITE}/rest/api/3/issue/WAI-124/transitions")
    respx.post(f"{BB}/monitoria/pullrequests/412/merge").mock(
        return_value=httpx.Response(200, json={"id": 412, "state": "MERGED"})
    )
    await _second_pr(seeded, approved=False)
    await _rules(seeded, monitoria={"jira_status": "DISPONIVEL PARA TESTES", "merge": True})

    assert (await client.get("/api/issues/WAI-124")).json()["conclude"] is True
    plan = (await client.get("/api/issues/WAI-124/conclude")).json()
    assert plan["blocked"] is None
    assert [m["pr_id"] for m in plan["merges"]] == [412]
    assert [(w["pr_id"], w["reason"]) for w in plan["waiting"]] == [(413, "sem a aprovação da regra")]
    # Com PR sobrando, o passo do Jira fica para depois — nem se consulta o Jira.
    assert plan["targets"] == []
    assert plan["held_statuses"] == ["DISPONIVEL PARA TESTES"]
    assert not jira.called

    # Uma tela velha pedindo o status também não move: o Jira espera o último PR.
    body = (
        await client.post(
            "/api/issues/WAI-124/conclude",
            json={"jira_status": "DISPONIVEL PARA TESTES",
                  "merges": [{"repo_slug": "monitoria", "pr_id": 412}]},
        )
    ).json()
    assert body["done"] is True
    assert [(s["kind"], s["ok"]) for s in body["steps"]] == [("merge", True), ("hold", True)]
    assert "#413 em monitoria" in body["steps"][1]["message"]
    assert not move.called
    assert engine.triggers == ["concluir"]
    assert await seeded.fetchval("SELECT status FROM jira_issue WHERE key = 'WAI-124'") == (
        "Em Review"
    )


@respx.mock
async def test_concluir_do_ultimo_pr_move_o_jira(db_app, client, seeded, engine):
    _mock_jira()
    respx.post(f"{BB}/monitoria/pullrequests/413/merge").mock(
        return_value=httpx.Response(200, json={"id": 413, "state": "MERGED"})
    )
    move = respx.post(f"{SITE}/rest/api/3/issue/WAI-124/transitions").mock(
        return_value=httpx.Response(204)
    )
    # O primeiro PR já entrou num Concluir anterior; o segundo foi aprovado depois.
    await seeded.execute("UPDATE bb_pull_request SET state = 'MERGED' WHERE id = 412")
    await _second_pr(seeded, approved=True)
    await _rules(seeded, monitoria={"jira_status": "DISPONIVEL PARA TESTES", "merge": True})

    plan = (await client.get("/api/issues/WAI-124/conclude")).json()
    assert [m["pr_id"] for m in plan["merges"]] == [413]
    assert plan["waiting"] == []
    assert [t["status"] for t in plan["targets"]] == ["DISPONIVEL PARA TESTES"]

    body = (
        await client.post(
            "/api/issues/WAI-124/conclude",
            json={"jira_status": "DISPONIVEL PARA TESTES",
                  "merges": [{"repo_slug": "monitoria", "pr_id": 413}]},
        )
    ).json()
    assert [s["kind"] for s in body["steps"]] == ["merge", "transition"]
    assert move.called


@respx.mock
async def test_pr_aberto_em_repo_sem_receita_tambem_segura_o_jira(db_app, client, seeded, engine):
    respx.post(f"{BB}/monitoria/pullrequests/412/merge").mock(
        return_value=httpx.Response(200, json={"id": 412, "state": "MERGED"})
    )
    await _second_pr(seeded, approved=True, repo="qualificai", pr_id=9)
    await _rules(seeded, monitoria={"jira_status": "DISPONIVEL PARA TESTES", "merge": True})

    plan = (await client.get("/api/issues/WAI-124/conclude")).json()
    assert [m["pr_id"] for m in plan["merges"]] == [412]
    assert [w["reason"] for w in plan["waiting"]] == [
        "aprovado, mas qualificai não tem receita no Concluir"
    ]

    # Depois do merge, sobra só o PR que o Concluir não mergeia: nada a fazer, o card sai.
    await seeded.execute("UPDATE bb_pull_request SET state = 'MERGED' WHERE id = 412")
    assert (await client.get("/api/issues/WAI-124")).json()["conclude"] is False
    plan = (await client.get("/api/issues/WAI-124/conclude")).json()
    assert "#9 em qualificai" in plan["blocked"]


@respx.mock
async def test_receita_sem_merge_com_pr_aprovado_nao_segura_o_jira(db_app, client, seeded, engine):
    _mock_jira(targets=("DISPONIVEL PARA TESTES", "Concluído"))
    await _second_pr(seeded, approved=True, repo="qualificai", pr_id=9)
    await _rules(
        seeded,
        monitoria={"jira_status": "DISPONIVEL PARA TESTES", "merge": True},
        qualificai={"jira_status": "Concluído"},
    )
    plan = (await client.get("/api/issues/WAI-124/conclude")).json()
    assert plan["waiting"] == []
    assert [t["status"] for t in plan["targets"]] == ["DISPONIVEL PARA TESTES", "Concluído"]


class BrokenEngine:
    """O registro do sync recusado (era o CHECK de `sync_run.trigger`)."""

    async def trigger(self, trigger: str = "manual") -> int:
        raise RuntimeError("sync_run_trigger_check")


@respx.mock
async def test_reviewer_posto_no_bitbucket_nao_vira_500_se_o_sync_nao_dispara(
    db_app, client, seeded
):
    db_app.dependency_overrides[get_sync_engine] = BrokenEngine
    respx.get("https://api.bitbucket.org/2.0/workspaces/weonrepo/members").mock(
        return_value=httpx.Response(200, json={"values": []})
    )
    respx.get(f"{BB}/monitoria/pullrequests/412").mock(
        return_value=httpx.Response(200, json={"id": 412, "state": "OPEN", "title": "x"})
    )
    photo = "https://avatar-management.example/RS-2.png"
    respx.put(f"{BB}/monitoria/pullrequests/412").mock(
        return_value=httpx.Response(
            200,
            json={"id": 412, "reviewers": [
                {**_user("{c}", "acc-carla", "Carla"), "links": {"avatar": {"href": photo}}}
            ]},
        )
    )
    response = await client.put("/api/pull-requests/monitoria/412/reviewers", json={"add": ["acc-carla"]})
    assert response.status_code == 200, response.text
    assert response.json()["reviewers"][0]["avatar_url"] == photo
