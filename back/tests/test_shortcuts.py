import pytest

from services.shortcuts import (
    DEFAULT_BINDINGS,
    InvalidShortcut,
    merge_with_defaults,
    normalize_combo,
    validate_bindings,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Ctrl+Shift+L", "Ctrl+Shift+L"),
        ("shift+ctrl+l", "Ctrl+Shift+L"),
        ("Control + Shift + 7", "Ctrl+Shift+7"),
        ("Alt+N", "Alt+N"),
        ("Alt+Shift+space", "Alt+Shift+Space"),
        ("F2", "F2"),
        ("Shift+F9", "Shift+F9"),
        ("Ctrl+F8", "Ctrl+F8"),
        ("ctrl+k", "Ctrl+K"),
    ],
)
def test_normaliza_atalhos_validos(raw, expected):
    assert normalize_combo(raw) == expected


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        ("", "vazio"),
        ("Ctrl+Shift+Enter", "tecla"),
        ("Meta+L", "Modificador inválido"),
        ("Ctrl+Ctrl+L", "Modificador inválido"),
        ("Ctrl+Alt+N", "AltGr"),
        ("Ctrl+Shift+N", "reservado"),
        ("Alt+F4", "reservado"),
        ("F5", "reservado"),
        ("Shift+L", "Ctrl ou Alt"),
        ("L", "Ctrl ou Alt"),
        ("Ctrl+C", "edição"),
    ],
)
def test_recusa_atalhos_invalidos(raw, fragment):
    with pytest.raises(InvalidShortcut, match=fragment):
        normalize_combo(raw)


def test_conflito_entre_acoes_e_acao_desconhecida():
    with pytest.raises(InvalidShortcut, match="já está em uso"):
        validate_bindings({"open_reminders": "ctrl+shift+l", "new_reminder": "Ctrl+Shift+L"})
    with pytest.raises(InvalidShortcut, match="desconhecida"):
        validate_bindings({"abrir_tudo": "Alt+J"})


def test_desativar_e_merge_com_padrao():
    assert validate_bindings({"open_reminders": None, "new_reminder": ""}) == {
        "open_reminders": None,
        "new_reminder": None,
        "global_search": "Ctrl+K",
    }
    assert merge_with_defaults(None) == DEFAULT_BINDINGS
    assert merge_with_defaults({"open_reminders": "Alt+J"}) == {
        **DEFAULT_BINDINGS,
        "open_reminders": "Alt+J",
    }
    # Valor salvo que ficou inválido volta ao padrão em vez de quebrar a tela.
    assert merge_with_defaults({"open_reminders": "Ctrl+Shift+N"}) == DEFAULT_BINDINGS


async def test_api_le_salva_e_valida(db_app, client):
    response = await client.get("/api/preferences/shortcuts")
    assert response.status_code == 200
    assert response.json() == {"bindings": DEFAULT_BINDINGS, "defaults": DEFAULT_BINDINGS}

    response = await client.put(
        "/api/preferences/shortcuts",
        json={"bindings": {"open_reminders": "alt+j", "new_reminder": None}},
    )
    assert response.status_code == 200, response.text
    saved = {"open_reminders": "Alt+J", "new_reminder": None, "global_search": "Ctrl+K"}
    assert response.json()["bindings"] == saved
    assert (await client.get("/api/preferences/shortcuts")).json()["bindings"] == saved

    response = await client.put(
        "/api/preferences/shortcuts",
        json={"bindings": {"open_reminders": "Alt+J", "new_reminder": "Alt+J"}},
    )
    assert response.status_code == 422
    assert "já está em uso" in response.text
    # A tentativa recusada não altera o que estava salvo.
    assert (await client.get("/api/preferences/shortcuts")).json()["bindings"] == saved
