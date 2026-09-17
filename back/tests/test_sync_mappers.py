from datetime import UTC, date, datetime

import pytest

from services.sync.mappers import build_status, issue_rows, pull_request_row, sprint_row
from services.sync.scope import JiraScope, SyncScope, sprint_in_scope
from tests.fixtures import load
from utils.adf import adf_to_text
from utils.issue_keys import extract_issue_keys

# --- ADF ---------------------------------------------------------------------------------


def test_adf_para_texto_com_paragrafos_listas_e_mencoes():
    doc = {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "heading", "content": [{"type": "text", "text": "Contexto"}]},
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Falar com "},
                    {"type": "mention", "attrs": {"text": "@Maycon"}},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "sobre a integração"},
                ],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "item 1"}]}
                        ],
                    }
                ],
            },
            {
                "type": "paragraph",
                "content": [{"type": "inlineCard", "attrs": {"url": "https://x.y"}}],
            },
        ],
    }

    assert (
        adf_to_text(doc)
        == "Contexto\nFalar com @Maycon\nsobre a integração\n- item 1\n\nhttps://x.y"
    )


@pytest.mark.parametrize("value", [None, ""])
def test_adf_vazio(value):
    assert adf_to_text(value) == ""


def test_adf_aceita_texto_legado():
    assert adf_to_text("  texto simples ") == "texto simples"


# --- Chaves em branches e títulos -------------------------------------------------------


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        (("WAI-7120-camada-integracao",), ["WAI-7120"]),
        (("feature/WAI-7120",), ["WAI-7120"]),
        (("bugfix/wai-0712-x",), ["WAI-712"]),
        (("hotfix/WAI-1-WAI-2",), ["WAI-1", "WAI-2"]),
        (("release/2026-09", "WAI-10 e MON-5"), ["WAI-10"]),
        (("SWAI-99", "xWAI-98"), []),
        (("feature/WAI-7120", "WAI-7120 ajuste"), ["WAI-7120"]),
    ],
)
def test_extrai_chaves_so_do_projeto(texts, expected):
    assert extract_issue_keys(*texts, project_keys=["WAI"]) == expected


# --- Escopo --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("board_id", "squad", "expected"),
    [
        (144, "Growth", True),
        (144, "growth", True),
        (144, "Core", False),
        (144, None, True),  # balde sem squad
        (610, "Growth", False),
    ],
)
def test_sprint_no_escopo_padrao(board_id, squad, expected):
    assert sprint_in_scope(board_id=board_id, squad=squad, scope=JiraScope()) is expected


def test_escopo_sem_squads_aceita_todas_e_pode_excluir_baldes():
    scope = JiraScope(squads=[], include_unsquadded=False)
    assert sprint_in_scope(board_id=144, squad="Core", scope=scope)
    assert not sprint_in_scope(board_id=144, squad=None, scope=scope)


def test_escopo_normaliza_listas():
    scope = SyncScope.model_validate(
        {
            "jira": {"project_keys": ["wai", " WAI "]},
            "bitbucket": {"repo_slugs": ["Monitoria", "monitoria"]},
        }
    )
    assert scope.jira.project_keys == ["WAI"]
    assert scope.bitbucket.repo_slugs == ["monitoria"]


# --- Issues, sprints, PRs --------------------------------------------------------------------


def test_issue_rows_extrai_campos_links_comentarios_e_sprints():
    raw = load("jira/search_page_1.json")["issues"][0]
    raw["fields"].update(
        {
            "description": {
                "type": "doc",
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "Descrição"}]}
                ],
            },
            "assignee": {"accountId": "acc-1", "displayName": "Matheus Bacca"},
            "reporter": {"displayName": "Maycon"},
            "priority": {"name": "High"},
            "labels": ["backend"],
            "components": [{"name": "monitoria"}],
            "created": "2026-09-01T10:00:00.000-0300",
            "updated": "2026-09-12T15:30:00.000-0300",
            "duedate": "2026-09-19",
            "issuelinks": [
                {
                    "id": "900",
                    "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
                    "outwardIssue": {
                        "key": "WAI-7003",
                        "fields": {
                            "summary": "Testes",
                            "status": {"name": "To Do"},
                            "issuetype": {"name": "Tarefa"},
                        },
                    },
                },
                {
                    "id": "901",
                    "type": {"name": "Relates", "inward": "relates to", "outward": "relates to"},
                    "inwardIssue": {"key": "WAI-6000", "fields": {"summary": "Enhancement"}},
                },
            ],
            "comment": {
                "total": 3,
                "maxResults": 1,
                "comments": [load("jira/comments_page_1.json")["comments"][0]],
            },
        }
    )

    rows = issue_rows(raw, sprint_field="customfield_10020", story_points_field="customfield_10026")

    issue = rows.issue
    assert issue["key"] == "WAI-7001"
    assert issue["project_key"] == "WAI"
    assert issue["parent_key"] == "WAI-6900"
    assert issue["story_points"] == 8
    assert issue["description_text"] == "Descrição"
    assert issue["status_category"] == "indeterminate"
    assert issue["due_date"] == date(2026, 9, 19)
    assert issue["updated_at"] == datetime(2026, 9, 12, 18, 30, tzinfo=UTC)
    assert issue["components"] == ["monitoria"]
    assert [s["id"] for s in rows.sprints] == [3995]
    assert rows.sprints[0]["squad"] == "Growth"
    assert [(link["target_key"], link["direction"], link["label"]) for link in rows.links] == [
        ("WAI-7003", "outward", "blocks"),
        ("WAI-6000", "inward", "relates to"),
    ]
    assert rows.comments[0]["body_text"] == "Primeiro achado"
    assert rows.comments_complete is False  # total 3, veio 1


def test_sprint_row_do_campo_da_issue_usa_board_id():
    row = sprint_row({"id": 1, "name": "Sprint 9 - Growth", "state": "closed", "boardId": 144})
    assert row["board_id"] == 144
    assert row["squad"] == "Growth"


def test_pull_request_row_extrai_chaves_e_participantes():
    raw = load("bitbucket/pullrequests.json")["values"][0]
    raw["source"]["branch"]["name"] = "feature/WAI-7120"
    raw["title"] = "WAI-7121 ajuste"

    row = pull_request_row("monitoria", raw, project_keys=["WAI"])

    assert row["issue_keys"] == ["WAI-7120", "WAI-7121"]
    assert row["participants"][0] == {
        "role": "REVIEWER",
        "approved": False,
        "state": "changes_requested",
        "name": "Revisor",
        "account_id": None,
    }
    assert row["url"].endswith("/pull-requests/412")


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        (["SUCCESSFUL", "FAILED"], "FAILED"),
        (["SUCCESSFUL", "INPROGRESS"], "INPROGRESS"),
        (["SUCCESSFUL"], "SUCCESSFUL"),
        ([], None),
    ],
)
def test_build_status_pega_o_pior(states, expected):
    assert build_status([{"state": s} for s in states]) == expected
