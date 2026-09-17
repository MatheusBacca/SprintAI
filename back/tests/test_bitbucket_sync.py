from datetime import UTC, datetime, timedelta

import pytest
import respx

from integrations.bitbucket_client import BitbucketClient
from integrations.errors import RateLimited
from services.sync.bitbucket_sync import BitbucketSyncer
from services.sync.scope import BitbucketScope
from tests.sync_fakes import FakeBitbucket

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


async def _no_sleep(_):
    return None


@pytest.fixture
def fake():
    bb = FakeBitbucket()
    bb.pr(
        "monitoria",
        412,
        "feature/WAI-7001",
        commit="abc",
        participants=[
            {
                "role": "REVIEWER",
                "approved": False,
                "state": "changes_requested",
                "user": {"display_name": "Revisor"},
            }
        ],
    )
    bb.pr("monitoria", 400, "WAI-6900-antigo", state="MERGED", updated="2026-09-05T10:00:00+00:00")
    bb.pr("organia-configs", 88, "release/sem-chave", state="MERGED")
    bb.statuses[("monitoria", 412)] = ["SUCCESSFUL", "FAILED"]
    bb.branches["monitoria"] = [
        {
            "name": "feature/WAI-7001",
            "target": {"hash": "abc", "date": "2026-09-12T10:00:00+00:00"},
        },
        {"name": "WAI-7050-sem-pr", "target": {"hash": "def", "date": "2026-09-11T10:00:00+00:00"}},
        {
            "name": "WAI-1000-muito-velha",
            "target": {"hash": "old", "date": "2025-01-01T10:00:00+00:00"},
        },
    ]
    return bb


async def _run(
    fake, db_pool, *, now=NOW, repos=("monitoria", "organia-configs"), my_keys=(), **scope
):
    scope = {"pr_scope": "all", **scope}
    with respx.mock(assert_all_called=False) as router:
        fake.mount(router)
        client = BitbucketClient.create(
            email="dev@weon.com.br",
            api_token="t" * 24,
            workspace="weonrepo",
            sleep=_no_sleep,
            max_retries=0,
        )
        async with client:
            syncer = BitbucketSyncer(
                client,
                db_pool,
                BitbucketScope(repo_slugs=list(repos), **scope),
                project_keys=["WAI"],
                my_issue_keys=list(my_keys),
                now=lambda: now,
            )
            await syncer.run()
            return syncer.stats


async def test_primeira_carga_dos_repos_escolhidos(fake, db_pool):
    stats = await _run(fake, db_pool)

    assert stats.repositories == 2
    prs = await db_pool.fetch(
        "SELECT repo_slug, id, issue_keys, build_status, participants "
        "FROM bb_pull_request ORDER BY id"
    )
    assert [(r["repo_slug"], r["id"], r["issue_keys"]) for r in prs] == [
        ("organia-configs", 88, []),
        ("monitoria", 400, ["WAI-6900"]),
        ("monitoria", 412, ["WAI-7001"]),
    ]
    open_pr = prs[2]
    assert open_pr["build_status"] == "FAILED"
    assert open_pr["participants"][0]["state"] == "changes_requested"
    assert fake.status_calls == [("monitoria", 412)]  # só PR aberto tem build consultado

    branches = await db_pool.fetch("SELECT name FROM bb_branch")
    # a branch de 2025 fica fora da janela inicial (60 dias)
    assert {b["name"] for b in branches} == {"WAI-7050-sem-pr", "feature/WAI-7001"}


async def test_segundo_ciclo_incremental_sem_varredura_nem_branches(fake, db_pool):
    await _run(fake, db_pool)
    fake.pr_queries.clear()
    fake.status_calls.clear()
    fake.branch_calls.clear()

    stats = await _run(fake, db_pool, now=NOW + timedelta(minutes=5))

    # só a consulta incremental (sem a varredura de abertos: 30 min ainda não passaram)
    assert all(
        q["q"] and q["state"] == ["OPEN", "MERGED", "DECLINED", "SUPERSEDED"]
        for _, q in fake.pr_queries
    )
    assert len(fake.pr_queries) == 2
    assert fake.status_calls == []  # commit não mudou
    assert fake.branch_calls == []  # repositório sem push novo
    assert stats.pull_requests == 0


async def test_aprovacao_sem_mudar_updated_entra_na_varredura_de_abertos(fake, db_pool):
    await _run(fake, db_pool)
    fake.pr(
        "monitoria",
        412,
        "feature/WAI-7001",
        commit="abc",
        updated="2026-09-12T10:00:00+00:00",
        participants=[
            {
                "role": "REVIEWER",
                "approved": True,
                "state": "approved",
                "user": {"display_name": "Revisor"},
            }
        ],
    )

    await _run(fake, db_pool, now=NOW + timedelta(minutes=31))

    participants = await db_pool.fetchval(
        "SELECT participants FROM bb_pull_request WHERE repo_slug = 'monitoria' AND id = 412"
    )
    assert participants[0]["approved"] is True


async def test_push_novo_reconsulta_branches_e_build_do_commit_novo(fake, db_pool):
    await _run(fake, db_pool)
    fake.repos["monitoria"] = "2026-09-14T12:10:00+00:00"
    fake.pr("monitoria", 412, "feature/WAI-7001", commit="zzz", updated="2026-09-14T12:10:00+00:00")
    fake.statuses[("monitoria", 412)] = ["INPROGRESS"]
    fake.branch_calls.clear()
    fake.status_calls.clear()

    await _run(fake, db_pool, now=NOW + timedelta(minutes=15))

    assert fake.branch_calls == ["monitoria"]
    assert fake.status_calls == [("monitoria", 412)]
    status = await db_pool.fetchval("SELECT build_status FROM bb_pull_request WHERE id = 412")
    assert status == "INPROGRESS"


async def test_sem_repositorios_escolhidos_nao_chama_api(fake, db_pool):
    stats = await _run(fake, db_pool, repos=())

    assert stats.repositories == 0
    assert fake.pr_queries == []


async def test_repositorio_inexistente_e_reportado(fake, db_pool):
    stats = await _run(fake, db_pool, repos=("monitoria", "nao-existe"))

    assert stats.missing_repositories == ["nao-existe"]


async def test_limite_de_requisicoes_interrompe_e_preserva_o_resto(fake, db_pool):
    fake.rate_limit_repo = "monitoria"

    with pytest.raises(RateLimited):
        await _run(fake, db_pool)

    # organia-configs pode ter terminado; monitoria não gravou cursor
    cursor = await db_pool.fetchval(
        "SELECT cursor FROM sync_state WHERE resource = 'bitbucket:repo:monitoria'"
    )
    assert cursor is None


# --- Escopo "só os meus" (padrão) --------------------------------------------------------------


async def test_so_meus_prs_autor_revisor_ou_tarefa_minha(fake, db_pool):
    fake.pr("monitoria", 500, "feature/WAI-9000", author="bb-me")  # sou autor
    fake.pr(
        "monitoria",
        501,
        "feature/WAI-9001",
        participants=[
            {
                "role": "REVIEWER",
                "approved": False,
                "state": None,
                "user": {"account_id": "bb-me", "display_name": "Eu"},
            }
        ],
    )  # sou revisor
    fake.pr("organia-configs", 502, "feature/WAI-7001")  # colega abriu, mas a tarefa é minha

    stats = await _run(fake, db_pool, pr_scope="mine", my_keys=["WAI-7001"])

    ids = {r["id"] for r in await db_pool.fetch("SELECT id FROM bb_pull_request")}
    assert ids == {412, 500, 501, 502}  # 412 também é da WAI-7001
    assert stats.skipped_not_mine == 2  # 400 (WAI-6900) e 88 (sem chave)
    assert fake.status_calls.count(("monitoria", 400)) == 0
    branches = {r["name"] for r in await db_pool.fetch("SELECT name FROM bb_branch")}
    assert branches == {"feature/WAI-7001"}  # WAI-7050 não é minha


async def test_trocar_de_todos_para_meus_poda_prs_e_repos_desmarcados(fake, db_pool):
    await _run(fake, db_pool, pr_scope="all")
    assert await db_pool.fetchval("SELECT count(*) FROM bb_pull_request") == 3

    stats = await _run(
        fake,
        db_pool,
        pr_scope="mine",
        repos=("monitoria",),
        my_keys=["WAI-7001"],
        now=NOW + timedelta(minutes=5),
    )

    rows = await db_pool.fetch("SELECT repo_slug, id FROM bb_pull_request")
    assert {(r["repo_slug"], r["id"]) for r in rows} == {("monitoria", 412)}
    assert stats.pruned_pull_requests == 2
    assert await db_pool.fetchval("SELECT count(*) FROM bb_repository") == 1


async def test_poda_remove_pr_antigo_sem_autor_gravado(fake, db_pool):
    await _run(fake, db_pool, pr_scope="all")
    # simula linhas gravadas antes da migration 0003 (sem identidade do autor)
    await db_pool.execute("UPDATE bb_pull_request SET author_account_id = NULL")

    stats = await _run(
        fake, db_pool, pr_scope="mine", my_keys=["WAI-7001"], now=NOW + timedelta(minutes=5)
    )

    ids = {r["id"] for r in await db_pool.fetch("SELECT id FROM bb_pull_request")}
    assert ids == {412}
    assert stats.pruned_pull_requests == 2


async def test_comentario_novo_e_espelhado_e_vira_evento(fake, db_pool):
    await _run(fake, db_pool)
    fake.comment("monitoria", 412, 9001, "Isso aqui precisa de teste.", author="bb-revisor")

    # Comentar não mexe no `updated_on` do PR: quem o traz de volta é a varredura dos abertos.
    stats = await _run(fake, db_pool, now=NOW + timedelta(minutes=31))

    assert fake.comment_calls == [("monitoria", 412)]
    assert stats.pr_comments == 1
    row = await db_pool.fetchrow(
        "SELECT body_text, author_name FROM bb_pr_comment WHERE repo_slug = 'monitoria' AND id = 9001"
    )
    assert row["body_text"] == "Isso aqui precisa de teste."
    assert row["author_name"] == "bb-revisor"

    kinds = await db_pool.fetchval(
        "SELECT kind FROM activity_event WHERE dedupe_key = 'bb:pr:monitoria:412:comment:9001'"
    )
    assert kinds == "pr_comment"


async def test_comentario_ja_espelhado_nao_vira_evento_de_novo(fake, db_pool):
    await _run(fake, db_pool)
    fake.comment("monitoria", 412, 9001, "Primeiro apontamento.")
    await _run(fake, db_pool, now=NOW + timedelta(minutes=31))
    fake.comment("monitoria", 412, 9002, "Segundo apontamento.")

    await _run(fake, db_pool, now=NOW + timedelta(minutes=62))

    novos = await db_pool.fetchval(
        "SELECT count(*) FROM activity_event WHERE kind = 'pr_comment' AND pr_id = 412"
    )
    assert novos == 2
    espelhados = await db_pool.fetchval("SELECT count(*) FROM bb_pr_comment WHERE pr_id = 412")
    assert espelhados == 2


async def test_contagem_igual_nao_gasta_requisicao_de_comentario(fake, db_pool):
    fake.comment("monitoria", 412, 9001, "Apontamento.")
    await _run(fake, db_pool)
    fake.comment_calls.clear()

    # Varredura dos abertos: o PR volta inteiro, mas o comment_count não mudou.
    await _run(fake, db_pool, now=NOW + timedelta(minutes=31))

    assert fake.comment_calls == []


async def test_primeira_carga_espelha_comentario_sem_despejar_no_feed(fake, db_pool):
    fake.comment("monitoria", 412, 9001, "Review antiga.")

    await _run(fake, db_pool)

    assert await db_pool.fetchval("SELECT count(*) FROM bb_pr_comment WHERE pr_id = 412") == 1
    eventos = await db_pool.fetchval("SELECT count(*) FROM activity_event WHERE pr_id = 412")
    assert eventos == 0


async def test_comentario_apagado_no_bitbucket_fica_sem_corpo_na_linha(fake, db_pool):
    fake.comment("monitoria", 412, 9001, "Ignora isso.")
    fake.comment("monitoria", 412, 9002, "Esse vale.")
    await _run(fake, db_pool)

    fake.comment("monitoria", 412, 9001, "", deleted=True)  # 2 → 1 comentário

    await _run(fake, db_pool, now=NOW + timedelta(minutes=31))

    apagado = await db_pool.fetchrow(
        "SELECT is_deleted, body_text FROM bb_pr_comment WHERE id = 9001"
    )
    # Continua na linha do tempo: sumir com ele abriria um buraco entre o pedido e a correção.
    assert apagado["is_deleted"] is True
    assert apagado["body_text"] == ""


async def test_pr_podado_leva_os_comentarios_junto(fake, db_pool):
    fake.comment("monitoria", 400, 7001, "Comentário do PR antigo.")
    await _run(fake, db_pool)
    assert await db_pool.fetchval("SELECT count(*) FROM bb_pr_comment WHERE pr_id = 400") == 1

    # 'monitoria' sai do escopo: a poda apaga o PR e a FK leva o comentário.
    await _run(fake, db_pool, repos=("organia-configs",), now=NOW + timedelta(minutes=5))

    assert await db_pool.fetchval("SELECT count(*) FROM bb_pr_comment WHERE pr_id = 400") == 0


async def test_pr_com_review_anterior_a_tabela_e_preenchido_no_ciclo_seguinte(fake, db_pool):
    # Espelho antigo: o PR já tinha comentário, mas a tabela de comentários nasceu depois.
    fake.comment("monitoria", 412, 9001, "Review de antes.")
    await _run(fake, db_pool)
    await db_pool.execute("DELETE FROM bb_pr_comment")
    fake.comment_calls.clear()

    # Contagem estável: sem o backfill, esta review ficaria invisível para sempre.
    await _run(fake, db_pool, now=NOW + timedelta(minutes=31))

    assert fake.comment_calls == [("monitoria", 412)]
    assert await db_pool.fetchval("SELECT count(*) FROM bb_pr_comment WHERE pr_id = 412") == 1
