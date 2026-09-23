from datetime import UTC, datetime, timedelta

import pytest

from services.pr_status import (
    PrStatus,
    RepoPrStatus,
    aggregate_status,
    derive_pr_status,
    summarize_issue,
)

T0 = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)

REVIEWER = {"role": "REVIEWER", "approved": False, "state": None, "name": "Revisor"}
APPROVED = {"role": "REVIEWER", "approved": True, "state": "approved", "name": "Aprovador"}
CHANGES = {"role": "REVIEWER", "approved": False, "state": "changes_requested", "name": "Crítico"}


def pr(
    repo="monitoria",
    pid=1,
    state="OPEN",
    *,
    draft=False,
    participants=(),
    branch="feature/WAI-7001",
    title="PR",
    keys=("WAI-7001",),
    updated=T0,
    build=None,
    requested_at=None,
    commit_at=None,
):
    return {
        "repo_slug": repo,
        "id": pid,
        "title": title,
        "state": state,
        "draft": draft,
        "source_branch": branch,
        "destination_branch": "main",
        "url": f"https://bitbucket.org/weonrepo/{repo}/pull-requests/{pid}",
        "participants": list(participants),
        "build_status": build,
        "comment_count": 0,
        "issue_keys": list(keys),
        "updated_on": updated,
        "last_changes_requested_at": requested_at,
        "last_commit_at": commit_at,
    }


def branch(repo="monitoria", name="WAI-7001-x", keys=("WAI-7001",), date=T0):
    return {"repo_slug": repo, "name": name, "target_date": date, "issue_keys": list(keys)}


# --- Por PR ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "draft", "participants", "expected"),
    [
        ("MERGED", False, [], PrStatus.MERGEADA),
        ("MERGED", False, [CHANGES], PrStatus.MERGEADA),
        ("DECLINED", False, [APPROVED], PrStatus.RECUSADA),
        ("SUPERSEDED", False, [], PrStatus.SUBSTITUIDA),
        ("OPEN", True, [APPROVED], PrStatus.RASCUNHO),
        ("OPEN", True, [CHANGES], PrStatus.RASCUNHO),
        ("OPEN", False, [APPROVED, CHANGES], PrStatus.AJUSTES_REQUISITADOS),
        ("OPEN", False, [CHANGES], PrStatus.AJUSTES_REQUISITADOS),
        ("OPEN", False, [REVIEWER, APPROVED], PrStatus.APROVADA),
        ("OPEN", False, [REVIEWER], PrStatus.PR_ABERTA),
        ("OPEN", False, [], PrStatus.PR_ABERTA),
    ],
)
def test_status_por_pr(state, draft, participants, expected):
    assert derive_pr_status(state=state, draft=draft, participants=participants) is expected


def test_correcao_enviada_devolve_o_pr_para_pr_aberta():
    # O revisor continua com "changes_requested" no Bitbucket: quem diz que a correção
    # subiu é o histórico.
    assert (
        derive_pr_status(state="OPEN", draft=False, participants=[CHANGES], fix_pushed=True)
        is PrStatus.PR_ABERTA
    )
    # Mesmo com outra aprovação: quem pediu o ajuste ainda não olhou a correção.
    assert (
        derive_pr_status(
            state="OPEN", draft=False, participants=[APPROVED, CHANGES], fix_pushed=True
        )
        is PrStatus.PR_ABERTA
    )


@pytest.mark.parametrize(
    ("requested_at", "commit_at", "expected"),
    [
        (T0, T0 + timedelta(hours=2), True),  # correção depois do pedido
        (T0, T0, True),  # mesmo ciclo de sync: os dois herdam o updated_on do PR
        (T0, T0 - timedelta(hours=2), False),  # commit anterior ao pedido
        (T0, None, False),
        (None, T0, False),  # pedido anterior ao histórico do espelho
        (None, None, False),
    ],
)
def test_correcao_sai_da_comparacao_das_datas(requested_at, commit_at, expected):
    summary = summarize_issue(
        "WAI-7001",
        [pr(participants=[CHANGES], requested_at=requested_at, commit_at=commit_at)],
        [],
    )

    assert summary.repos[0].pull_requests[0].fix_pushed is expected
    assert summary.status is (PrStatus.PR_ABERTA if expected else PrStatus.AJUSTES_REQUISITADOS)


# --- Por tarefa --------------------------------------------------------------------------------


def test_sem_nada_e_sem_pr():
    summary = summarize_issue("WAI-7001", [], [])

    assert summary.status is PrStatus.SEM_PR
    assert summary.label == "Sem PR"
    assert summary.pr_count == 0
    assert summary.repos == []


def test_ignora_prs_de_outras_tarefas():
    summary = summarize_issue("WAI-7001", [pr(keys=["WAI-9999"])], [branch(keys=["WAI-9999"])])

    assert summary.status is PrStatus.SEM_PR


def test_branch_sem_pr():
    summary = summarize_issue("WAI-7001", [], [branch()])

    assert summary.status is PrStatus.BRANCH_SEM_PR
    assert summary.repos[0].branches[0].name == "WAI-7001-x"


def test_branch_do_repo_que_ja_tem_pr_nao_vira_branch_sem_pr():
    summary = summarize_issue("WAI-7001", [pr(state="MERGED")], [branch(name="feature/WAI-7001")])

    assert summary.status is PrStatus.MERGEADA
    assert summary.repos[0].branches == []


def test_mesmo_repo_pr_aberto_prevalece_sobre_mergeado():
    # Caso real WAI-7980: um PR mergeado e outro de integração em develop ainda aberto.
    summary = summarize_issue(
        "WAI-7001",
        [
            pr(pid=1, state="MERGED", updated=T0),
            pr(pid=2, state="OPEN", participants=[APPROVED], updated=T0 - timedelta(days=1)),
        ],
        [],
    )

    assert summary.status is PrStatus.APROVADA
    assert [p.id for p in summary.repos[0].pull_requests] == [2, 1]  # aberto primeiro
    assert summary.open_pr_count == 1


def test_mesmo_repo_recusado_nao_conta_se_outro_pr_foi_mergeado():
    summary = summarize_issue(
        "WAI-7001", [pr(pid=1, state="DECLINED"), pr(pid=2, state="MERGED")], []
    )

    assert summary.status is PrStatus.MERGEADA


def test_multi_repo_o_que_pede_atencao_vence():
    # Caso real WAI-8278: aberto no supervisor-web, mergeado no weaction-api.
    summary = summarize_issue(
        "WAI-7001",
        [
            pr(repo="supervisor-web", pid=10, state="OPEN", participants=[CHANGES]),
            pr(repo="weaction-api", pid=20, state="MERGED"),
        ],
        [],
    )

    assert summary.status is PrStatus.AJUSTES_REQUISITADOS
    assert summary.pr_count == 2
    # repositório que pede atenção aparece primeiro
    assert [r.repo_slug for r in summary.repos] == ["supervisor-web", "weaction-api"]


def test_repo_so_com_recusado_nao_puxa_agregado_para_baixo():
    summary = summarize_issue(
        "WAI-7001",
        [pr(repo="a", state="DECLINED"), pr(repo="b", state="MERGED", pid=2)],
        [],
    )

    assert summary.status is PrStatus.MERGEADA


def test_todos_recusados_viram_recusada():
    summary = summarize_issue(
        "WAI-7001", [pr(repo="a", state="DECLINED"), pr(repo="b", state="SUPERSEDED", pid=2)], []
    )

    assert summary.status is PrStatus.RECUSADA


def test_so_substituido_vira_substituida():
    summary = summarize_issue("WAI-7001", [pr(state="SUPERSEDED")], [])

    assert summary.status is PrStatus.SUBSTITUIDA


def test_branch_recente_em_outro_repo_pede_atencao():
    summary = summarize_issue(
        "WAI-7001",
        [pr(repo="weaction-api", state="MERGED", updated=T0)],
        [branch(repo="supervisor-web", date=T0 + timedelta(hours=2))],
    )

    assert summary.status is PrStatus.BRANCH_SEM_PR
    assert summary.repos[0].branches[0].stale is False


def test_branch_antiga_em_outro_repo_e_sobra_de_merge():
    summary = summarize_issue(
        "WAI-7001",
        [pr(repo="weaction-api", state="MERGED", updated=T0)],
        [branch(repo="supervisor-web", date=T0 - timedelta(days=3))],
    )

    assert summary.status is PrStatus.MERGEADA
    stale_repo = next(r for r in summary.repos if r.repo_slug == "supervisor-web")
    assert stale_repo.status is PrStatus.BRANCH_SEM_PR
    assert stale_repo.branches[0].stale is True


def test_pr_com_varias_tarefas_marca_origem_do_vinculo():
    # Caso real: branch task/WAI-8279, título "WAI-8279 / WAI-8305 / WAI-8306".
    row = pr(branch="task/WAI-8279", title="WAI-8279 / WAI-8305", keys=["WAI-8279", "WAI-8305"])

    principal = summarize_issue("WAI-8279", [row], [])
    citada = summarize_issue("WAI-8305", [row], [])

    assert principal.repos[0].pull_requests[0].match == "branch"
    assert citada.repos[0].pull_requests[0].match == "title"
    assert citada.status is PrStatus.PR_ABERTA


def test_build_falhou_so_em_pr_aberto():
    open_failed = summarize_issue("WAI-7001", [pr(build="FAILED")], [])
    merged_failed = summarize_issue("WAI-7001", [pr(state="MERGED", build="FAILED")], [])

    assert open_failed.build_failed is True
    assert merged_failed.build_failed is False


def test_contagem_de_aprovacoes_e_revisores():
    summary = summarize_issue(
        "WAI-7001",
        [
            pr(
                participants=[
                    REVIEWER,
                    APPROVED,
                    CHANGES,
                    {"role": "PARTICIPANT", "approved": False, "state": None},
                ]
            )
        ],
        [],
    )
    link = summary.repos[0].pull_requests[0]

    assert (link.approvals, link.changes_requested) == (1, 1)
    # participante que só comentou não entra como revisor
    assert [r.name for r in link.reviewers] == ["Revisor", "Aprovador", "Crítico"]


def test_rascunho_e_aberta_em_repos_diferentes():
    summary = summarize_issue("WAI-7001", [pr(repo="a", draft=True), pr(repo="b", pid=2)], [])

    assert summary.status is PrStatus.RASCUNHO


def test_last_activity_considera_prs_e_branches():
    summary = summarize_issue(
        "WAI-7001",
        [pr(repo="a", updated=T0)],
        [branch(repo="b", date=T0 + timedelta(days=1))],
    )

    assert summary.last_activity == T0 + timedelta(days=1)


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([PrStatus.MERGEADA, PrStatus.APROVADA], PrStatus.APROVADA),
        ([PrStatus.MERGEADA, PrStatus.PR_ABERTA, PrStatus.RASCUNHO], PrStatus.RASCUNHO),
        ([PrStatus.AJUSTES_REQUISITADOS, PrStatus.BRANCH_SEM_PR], PrStatus.BRANCH_SEM_PR),
        ([PrStatus.RECUSADA, PrStatus.PR_ABERTA], PrStatus.PR_ABERTA),
        ([], PrStatus.SEM_PR),
    ],
)
def test_ordem_de_atencao_do_agregado(statuses, expected):
    repos = [RepoPrStatus(repo_slug=f"r{i}", status=s) for i, s in enumerate(statuses)]
    assert aggregate_status(repos) is expected


# --- Links do badge ----------------------------------------------------------------------------


def test_badge_abre_primeiro_o_pr_que_decide_o_status():
    from services.pr_status_service import badge_links

    summary = summarize_issue(
        "WAI-7001",
        [
            pr(repo="weaction-api", pid=20, state="MERGED"),
            pr(repo="supervisor-web", pid=10, state="OPEN", participants=[CHANGES]),
        ],
        [],
    )

    links = badge_links(summary)

    assert [(link.repo_slug, link.id) for link in links] == [
        ("supervisor-web", 10),
        ("weaction-api", 20),
    ]
    assert links[0].status is PrStatus.AJUSTES_REQUISITADOS
    assert links[0].url == "https://bitbucket.org/weonrepo/supervisor-web/pull-requests/10"


def test_badge_nao_abre_pr_recusado_quando_ha_outro():
    from services.pr_status_service import badge_links, to_badge

    summary = summarize_issue(
        "WAI-7001", [pr(repo="a", state="DECLINED"), pr(repo="b", pid=2, state="MERGED")], []
    )

    assert [link.id for link in to_badge(summary).links] == [2]
    # Só recusado: é o que o badge mostra, então é o que ele abre.
    only_declined = summarize_issue("WAI-7001", [pr(state="DECLINED")], [])
    assert [link.status for link in badge_links(only_declined)] == [PrStatus.RECUSADA]


def test_badge_sem_pr_nao_tem_link():
    from services.pr_status_service import to_badge

    assert to_badge(summarize_issue("WAI-7001", [], [branch()])).links == []
