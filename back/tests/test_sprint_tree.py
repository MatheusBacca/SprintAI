from services.sprint_tree import NO_PARENT_GROUP, build_tree

ME = "acc-me"


def issue(
    key, *, type_="Tarefa", parent=None, assignee=ME, status_category="indeterminate", points=None
):
    return {
        "key": key,
        "summary": f"Resumo {key}",
        "issue_type": type_,
        "status": "Em Desenvolvimento",
        "status_category": status_category,
        "story_points": points,
        "assignee_account_id": assignee,
        "assignee_name": "Matheus Bacca" if assignee == ME else "Outro Dev",
        "parent_key": parent,
    }


def link(
    source,
    target,
    *,
    type_="Relates",
    direction="outward",
    target_type="Enhancements",
    target_status=None,
):
    return {
        "source_key": source,
        "target_key": target,
        "link_type": type_,
        "direction": direction,
        "label": "relates to",
        "target_summary": f"Resumo {target}",
        "target_status": target_status,
        "target_type": target_type,
    }


def keys_of(tree, group_key):
    return next(g.issue_keys for g in tree.groups if g.key == group_key)


def test_epico_como_raiz_com_filhas_da_sprint():
    tree = build_tree(
        sprint_issues=[
            issue("WAI-2", parent="WAI-1", points=8),
            issue("WAI-3", parent="WAI-1", points=5),
        ],
        related_issues=[issue("WAI-1", type_="Épico", assignee=None)],
        links=[],
        my_account_id=ME,
    )

    assert [g.root_key for g in tree.groups] == ["WAI-1"]
    assert keys_of(tree, "WAI-1") == ["WAI-1", "WAI-2", "WAI-3"]
    epic = tree.nodes["WAI-1"]
    assert (epic.in_sprint, epic.is_parent_type, epic.children) == (False, True, ["WAI-2", "WAI-3"])
    assert {(e.source, e.target, e.kind) for e in tree.edges} == {
        ("WAI-1", "WAI-2", "parent"),
        ("WAI-1", "WAI-3", "parent"),
    }
    assert tree.counters == {
        "tasks": 2,
        "parents": 1,
        "blocked": 0,
        "mine": 2,
        "story_points": 13,
        "done": 0,
    }


def test_enhancements_por_link_quando_nao_ha_parent():
    tree = build_tree(
        sprint_issues=[issue("WAI-10")],
        related_issues=[],
        links=[
            link("WAI-10", "WAI-99", target_type="Tarefa"),  # Relates com Tarefa não é hierarquia
            link("WAI-10", "WAI-50", type_="Divisão do ticket"),
        ],
        my_account_id=ME,
    )

    node = tree.nodes["WAI-10"]
    assert (node.parent_key, node.parent_via) == ("WAI-50", "link")
    parent = tree.nodes["WAI-50"]
    assert parent.partial and parent.summary == "Resumo WAI-50"  # veio do snapshot do link
    assert tree.edges[0].kind == "link"
    assert tree.groups[0].root_key == "WAI-50"


def test_parent_tem_prioridade_sobre_link():
    tree = build_tree(
        sprint_issues=[issue("WAI-10", parent="WAI-1")],
        related_issues=[issue("WAI-1", type_="Épico")],
        links=[link("WAI-10", "WAI-50")],
        my_account_id=ME,
    )

    assert tree.nodes["WAI-10"].parent_key == "WAI-1"
    assert "WAI-50" not in tree.nodes


def test_tarefas_sem_pai_ficam_no_grupo_sem_pai_com_subtarefas_aninhadas():
    tree = build_tree(
        sprint_issues=[
            issue("WAI-20"),
            issue("WAI-21", type_="Subtarefa", parent="WAI-20"),
            issue("WAI-30", parent="WAI-1"),
        ],
        related_issues=[issue("WAI-1", type_="Épico")],
        links=[],
        my_account_id=ME,
    )

    assert [g.key for g in tree.groups] == ["WAI-1", NO_PARENT_GROUP]  # "Sem pai" por último
    assert keys_of(tree, NO_PARENT_GROUP) == ["WAI-20", "WAI-21"]
    assert tree.nodes["WAI-21"].depth == 1
    assert tree.counters["parents"] == 1


def test_subtarefa_na_sprint_com_pai_fora_sobe_ate_o_epico():
    tree = build_tree(
        sprint_issues=[issue("WAI-41", type_="Subtarefa", parent="WAI-40")],
        related_issues=[issue("WAI-40", parent="WAI-1"), issue("WAI-1", type_="Épico")],
        links=[],
        my_account_id=ME,
    )

    assert keys_of(tree, "WAI-1") == ["WAI-1", "WAI-40", "WAI-41"]
    assert tree.nodes["WAI-41"].depth == 2
    assert tree.counters["tasks"] == 1


def test_bloqueio_entre_tarefas_vira_seta_e_conta():
    tree = build_tree(
        sprint_issues=[
            issue("WAI-1"),
            issue("WAI-2"),
            issue("WAI-3", status_category="done"),
            issue("WAI-4"),
        ],
        related_issues=[],
        links=[
            link("WAI-1", "WAI-2", type_="Blocks", target_type="Tarefa"),
            # mesmo vínculo visto do outro lado: não duplica
            link("WAI-2", "WAI-1", type_="Blocks", direction="inward", target_type="Tarefa"),
            # bloqueador já concluído não conta como bloqueio
            link("WAI-3", "WAI-4", type_="Blocks", target_type="Tarefa"),
        ],
        my_account_id=ME,
    )

    blocks = [(e.source, e.target) for e in tree.edges if e.kind == "blocks"]
    assert sorted(blocks) == [("WAI-1", "WAI-2"), ("WAI-3", "WAI-4")]
    assert tree.nodes["WAI-2"].blocked_by == ["WAI-1"]
    assert tree.nodes["WAI-1"].blocks == ["WAI-2"]
    assert tree.nodes["WAI-4"].blocked is False
    assert tree.counters["blocked"] == 1


def test_bloqueador_fora_do_espelho_usa_status_do_snapshot():
    tree = build_tree(
        sprint_issues=[issue("WAI-1"), issue("WAI-2")],
        related_issues=[],
        links=[
            link(
                "WAI-1",
                "OUT-1",
                type_="Blocks",
                direction="inward",
                target_type="Tarefa",
                target_status="Em Desenvolvimento",
            ),
            link(
                "WAI-2",
                "OUT-2",
                type_="Blocks",
                direction="inward",
                target_type="Tarefa",
                target_status="Concluído",
            ),
        ],
        my_account_id=ME,
    )

    assert tree.nodes["WAI-1"].blocked_by == ["OUT-1"]
    assert tree.nodes["WAI-2"].blocked is False
    assert not [e for e in tree.edges if e.kind == "blocks"]  # bloqueador não está no grafo
    # Fora do grafo não há onda de onde empurrar.
    assert tree.nodes["WAI-1"].predecessors == []


def test_bloqueador_concluido_desbloqueia_mas_continua_antes_na_onda():
    # Caso real da Sprint 75: WAI-8548 bloqueava WAI-7889 e as duas foram concluídas.
    # Sem a ordem, a 7889 subia para a onda 1 e as ondas se desmanchavam.
    tree = build_tree(
        sprint_issues=[
            issue("WAI-8548", status_category="done"),
            issue("WAI-7889", status_category="done"),
        ],
        related_issues=[],
        links=[link("WAI-8548", "WAI-7889", type_="Blocks", target_type="Tarefa")],
        my_account_id=ME,
    )

    node = tree.nodes["WAI-7889"]
    assert (node.blocked, node.blocked_by) == (False, [])
    assert node.predecessors == ["WAI-8548"]
    assert tree.counters["blocked"] == 0


def test_is_caused_by_vira_seta_origina_e_ordem_de_onda_sem_bloquear():
    tree = build_tree(
        sprint_issues=[
            issue("WAI-7889", status_category="done"),
            issue("WAI-8694", type_="Ajuste"),
            issue("WAI-8705"),
        ],
        related_issues=[],
        links=[
            link(
                "WAI-8694",
                "WAI-7889",
                type_="Problem/Incident",
                direction="inward",
                target_type="Tarefa",
            ),
            # mesmo vínculo visto da origem: não duplica
            link("WAI-7889", "WAI-8694", type_="Problem/Incident", target_type="Ajuste"),
            # Relates entre tarefas não tem direção: não entra na ordem
            link("WAI-8705", "WAI-8694", target_type="Ajuste"),
        ],
        my_account_id=ME,
    )

    causes = [(e.source, e.target, e.label) for e in tree.edges if e.kind == "causes"]
    assert causes == [("WAI-7889", "WAI-8694", "origina")]
    assert tree.nodes["WAI-8694"].predecessors == ["WAI-7889"]
    assert tree.nodes["WAI-8694"].blocked is False
    assert tree.nodes["WAI-8705"].predecessors == []
    assert tree.nodes["WAI-8705"].parent_key is None


def test_filtro_so_minhas():
    tree = build_tree(
        sprint_issues=[
            issue("WAI-1", parent="WAI-9"),
            issue("WAI-2", parent="WAI-8", assignee="outro"),
        ],
        related_issues=[issue("WAI-9", type_="Épico"), issue("WAI-8", type_="Épico")],
        links=[],
        my_account_id=ME,
        only_mine=True,
    )

    assert {k for k, n in tree.nodes.items()} == {"WAI-1", "WAI-9"}
    assert tree.counters["tasks"] == 1


def test_ciclo_de_links_nao_trava():
    tree = build_tree(
        sprint_issues=[issue("WAI-1", type_="Enhancements"), issue("WAI-2", type_="Enhancements")],
        related_issues=[],
        links=[link("WAI-1", "WAI-2"), link("WAI-2", "WAI-1")],
        my_account_id=ME,
    )

    assert len(tree.nodes) == 2
    roots = [n for n in tree.nodes.values() if not n.parent_key]
    assert len(roots) == 1


def test_sprint_vazia():
    tree = build_tree(sprint_issues=[], related_issues=[], links=[], my_account_id=ME)

    assert tree.nodes == {} and tree.groups == [] and tree.counters["tasks"] == 0
