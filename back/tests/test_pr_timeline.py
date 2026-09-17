from datetime import UTC, datetime, timedelta

import pytest

from repositories import activity_repo, bitbucket_repo
from services import pr_timeline

T0 = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)


def comment(cid, body, *, at, author="Revisor", account="bb-revisor", deleted=False, path=None):
    return {
        "repo_slug": "weaction-api",
        "pr_id": 1836,
        "id": cid,
        "parent_id": None,
        "author_name": author,
        "author_account_id": account,
        "body_text": body,
        "inline_path": path,
        "inline_from": None,
        "inline_to": 42 if path else None,
        "is_deleted": deleted,
        "created_on": at,
        "updated_on": at,
    }


def event(kind, *, at, actor="Revisor", detail=None, is_me=False):
    return {
        "kind": kind,
        "occurred_at": at,
        "actor_name": actor,
        "actor_is_me": is_me,
        "detail": detail or {},
    }


# --- merge (função pura) -----------------------------------------------------------


def test_linha_do_tempo_vai_do_mais_novo_para_o_mais_antigo():
    entries = pr_timeline.merge_timeline(
        [comment(2, "segundo", at=T0 + timedelta(hours=2))],
        [
            event("pr_created", at=T0),
            event("pr_changes_requested", at=T0 + timedelta(hours=1)),
        ],
    )

    assert [e.kind for e in entries] == ["comment", "pr_changes_requested", "pr_created"]


def test_comentario_entra_com_o_corpo_inteiro_e_o_evento_dele_nao_duplica():
    entries = pr_timeline.merge_timeline(
        [comment(1, "Precisa de teste aqui.", at=T0)],
        [event("pr_comment", at=T0, detail={"comment_id": 1})],
    )

    assert [e.kind for e in entries] == ["comment"]
    assert entries[0].body == "Precisa de teste aqui."


def test_commit_depois_do_pedido_de_ajuste_e_marcado_como_correcao():
    entries = pr_timeline.merge_timeline(
        [],
        [
            event("pr_commit", at=T0, detail={"commit": "antes"}),
            event("pr_changes_requested", at=T0 + timedelta(hours=1)),
            event("pr_commit", at=T0 + timedelta(hours=2), detail={"commit": "depois"}),
        ],
    )

    marcados = {e.commit: e.after_changes_requested for e in entries if e.kind == "pr_commit"}
    assert marcados == {"antes": False, "depois": True}


def test_novo_pedido_de_ajuste_desmarca_a_correcao_antiga():
    entries = pr_timeline.merge_timeline(
        [],
        [
            event("pr_changes_requested", at=T0),
            event("pr_commit", at=T0 + timedelta(hours=1), detail={"commit": "primeira"}),
            event("pr_changes_requested", at=T0 + timedelta(hours=2)),
        ],
    )

    # A primeira correção respondeu ao pedido antigo; o último pedido continua em aberto.
    assert [e.after_changes_requested for e in entries if e.kind == "pr_commit"] == [False]
    assert pr_timeline.pending_review(entries) is True


def test_pendente_de_correcao_so_enquanto_nao_sobe_commit():
    pedido = [event("pr_changes_requested", at=T0)]
    assert pr_timeline.pending_review(pr_timeline.merge_timeline([], pedido)) is True

    respondido = pedido + [event("pr_commit", at=T0 + timedelta(hours=1), detail={"commit": "x"})]
    assert pr_timeline.pending_review(pr_timeline.merge_timeline([], respondido)) is False


def test_pr_sem_pedido_de_ajuste_nao_fica_pendente():
    entries = pr_timeline.merge_timeline([], [event("pr_approved", at=T0)])
    assert pr_timeline.pending_review(entries) is False


def test_comentario_meu_e_marcado_pelo_account_id():
    entries = pr_timeline.merge_timeline(
        [
            comment(1, "de outro", at=T0, account="bb-revisor"),
            comment(2, "meu", at=T0 + timedelta(minutes=1), account="bb-eu"),
        ],
        [],
        my_identities={"bb-eu"},
    )

    # O meu é o mais recente, então vem primeiro.
    assert [e.actor_is_me for e in entries] == [True, False]


def test_pedido_anterior_ao_historico_e_sinalizado():
    pediu = [{"role": "REVIEWER", "state": "changes_requested", "approved": False}]

    # Revisor pedindo ajuste, mas o espelho nunca viu a transição acontecer.
    sem_evento = pr_timeline.merge_timeline([], [event("pr_created", at=T0)])
    assert pr_timeline.request_before_history(sem_evento, pediu) is True

    # Com o evento na linha, não há o que avisar.
    com_evento = pr_timeline.merge_timeline([], [event("pr_changes_requested", at=T0)])
    assert pr_timeline.request_before_history(com_evento, pediu) is False

    # Ninguém pediu ajuste: nada a sinalizar.
    assert pr_timeline.request_before_history(sem_evento, []) is False


def test_comentario_sem_data_fica_de_fora():
    entries = pr_timeline.merge_timeline([comment(1, "órfão", at=None)], [])
    assert entries == []


# --- API ---------------------------------------------------------------------------


@pytest.fixture
async def seeded(db_pool):
    await bitbucket_repo.upsert_pull_requests(
        db_pool,
        [
            {
                "repo_slug": "weaction-api",
                "id": 1836,
                "title": "WAI-8360 histórico de qualificação",
                "description": None,
                "state": "OPEN",
                "draft": False,
                "author_name": "Matheus",
                "author_account_id": "bb-eu",
                "source_branch": "WAI-8360-historico",
                "source_commit": "abc",
                "destination_branch": "develop",
                "participants": [],
                "comment_count": 2,
                "task_count": 0,
                "build_status": None,
                "issue_keys": ["WAI-8360"],
                "url": "https://bitbucket.org/weonrepo/weaction-api/pull-requests/1836",
                "created_on": T0,
                "updated_on": T0,
            }
        ],
    )
    await bitbucket_repo.upsert_pr_comments(
        db_pool,
        [
            comment(9001, "Registra zero quando não há MonitorIA.", at=T0 + timedelta(hours=1)),
            comment(9002, "Ver a linha 42.", at=T0 + timedelta(hours=2), path="src/app.php"),
        ],
    )
    await activity_repo.insert_events(
        db_pool,
        [
            {
                "dedupe_key": "bb:pr:weaction-api:1836:changes_requested:bb-revisor",
                "source": "bitbucket",
                "kind": "pr_changes_requested",
                "issue_key": "WAI-8360",
                "repo_slug": "weaction-api",
                "pr_id": 1836,
                "actor_name": "Rafael",
                "actor_is_me": False,
                "occurred_at": T0 + timedelta(hours=3),
                "title": "PR 1836",
                "detail": {},
            },
            {
                "dedupe_key": "bb:pr:weaction-api:1836:commit:def",
                "source": "bitbucket",
                "kind": "pr_commit",
                "issue_key": "WAI-8360",
                "repo_slug": "weaction-api",
                "pr_id": 1836,
                "actor_name": "Matheus",
                "actor_is_me": True,
                "occurred_at": T0 + timedelta(hours=4),
                "title": "PR 1836",
                "detail": {"commit": "def"},
            },
        ],
    )


async def test_timeline_junta_comentarios_e_eventos(db_app, client, seeded):
    response = await client.get("/api/pull-requests/weaction-api/1836/timeline")

    assert response.status_code == 200
    body = response.json()
    # Última atualização primeiro.
    assert [e["kind"] for e in body["entries"]] == [
        "pr_commit",
        "pr_changes_requested",
        "comment",
        "comment",
    ]
    assert body["entries"][2]["inline_path"] == "src/app.php"
    assert body["entries"][3]["body"] == "Registra zero quando não há MonitorIA."
    # O commit veio depois do pedido: é a correção, e o PR deixa de estar pendente.
    assert body["entries"][0]["after_changes_requested"] is True
    assert body["pending_review"] is False


async def test_timeline_de_pr_fora_do_espelho_da_404(db_app, client, seeded):
    response = await client.get("/api/pull-requests/weaction-api/9999/timeline")
    assert response.status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/api/pull-requests/repo;drop/1/timeline",
        "/api/pull-requests/weaction-api/0/timeline",
        "/api/pull-requests/weaction-api/abc/timeline",
    ],
)
async def test_parametros_invalidos_dao_422(db_app, client, path):
    response = await client.get(path)
    assert response.status_code == 422
