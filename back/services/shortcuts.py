"""Atalhos de teclado globais do front (F4.1).

Formato canônico: modificadores na ordem ``Ctrl``, ``Alt``, ``Shift`` + uma tecla
(``A``-``Z``, ``0``-``9``, ``F1``-``F12`` ou ``Space``), ex.: ``Ctrl+Shift+L``.

As regras espelham ``front/src/utils/shortcuts.js`` (validação instantânea na tela);
aqui é a validação que vale para o que é salvo.
"""

import re
from typing import Final

SHORTCUT_ACTIONS: Final = ("open_reminders", "new_reminder", "global_search")

DEFAULT_BINDINGS: Final[dict[str, str | None]] = {
    "open_reminders": "Ctrl+Shift+L",
    # Ctrl+Shift+N é reservado pelo Chrome/Edge (janela anônima): a página nunca recebe.
    "new_reminder": "Ctrl+Shift+A",
    "global_search": "Ctrl+K",
}

MODIFIERS: Final = ("Ctrl", "Alt", "Shift")
_KEY = re.compile(r"^(?:[A-Z0-9]|F(?:[1-9]|1[0-2])|Space)$")

# Atalhos que o navegador/Windows não entrega à página ou que são essenciais demais.
RESERVED: Final = frozenset(
    {
        "Ctrl+Shift+N",
        "Ctrl+Shift+T",
        "Ctrl+Shift+W",
        "Ctrl+Shift+Q",
        "Ctrl+Shift+R",
        "Ctrl+Shift+I",
        "Ctrl+Shift+J",
        "Ctrl+Shift+C",
        "Ctrl+Shift+V",
        "Ctrl+Shift+Z",
        "Ctrl+F4",
        "Ctrl+F5",
        "Alt+F4",
        "Alt+D",
        "Alt+E",
        "Alt+F",
        "Alt+Space",
        "Shift+F10",
    }
)
# Ctrl + tecla sozinho é recusado, menos a convenção de busca dos apps web.
CTRL_ALLOWED: Final = frozenset({"Ctrl+K"})
RESERVED_FKEYS: Final = frozenset({"F1", "F3", "F5", "F6", "F7", "F10", "F11", "F12"})


class InvalidShortcut(ValueError):
    pass


def normalize_combo(text: str) -> str:
    """Valida e devolve o atalho no formato canônico; `InvalidShortcut` com a mensagem da tela."""
    parts = [p.strip() for p in text.split("+") if p.strip()]
    if not parts:
        raise InvalidShortcut("Atalho vazio.")
    *mods_raw, key_raw = parts
    mods: set[str] = set()
    for raw in mods_raw:
        mod = raw.capitalize()
        if mod == "Control":
            mod = "Ctrl"
        if mod not in MODIFIERS or mod in mods:
            raise InvalidShortcut(f"Modificador inválido: {raw}.")
        mods.add(mod)
    key = key_raw.capitalize() if key_raw.lower() == "space" else key_raw.upper()
    if not _KEY.match(key):
        raise InvalidShortcut("Use uma letra, um número, F1–F12 ou Espaço como tecla.")

    combo = "+".join([m for m in MODIFIERS if m in mods] + [key])
    is_fkey = key.startswith("F") and len(key) > 1

    if "Ctrl" in mods and "Alt" in mods:
        raise InvalidShortcut(
            "Ctrl+Alt equivale ao AltGr e digita caracteres (ñ, €…). Use Ctrl+Shift."
        )
    if combo in RESERVED or (not mods and key in RESERVED_FKEYS):
        raise InvalidShortcut(f"{combo} é reservado pelo navegador ou pelo Windows.")
    if not is_fkey and not ({"Ctrl", "Alt"} & mods):
        raise InvalidShortcut("Combine a tecla com Ctrl ou Alt para não atrapalhar a digitação.")
    if mods == {"Ctrl"} and not is_fkey and combo not in CTRL_ALLOWED:
        raise InvalidShortcut(
            "Ctrl + tecla é dos atalhos de edição e do navegador. Use Ctrl+Shift."
        )
    return combo


def validate_bindings(bindings: dict[str, str | None]) -> dict[str, str | None]:
    """Normaliza todos os atalhos, recusando ação desconhecida e atalho repetido."""
    unknown = set(bindings) - set(SHORTCUT_ACTIONS)
    if unknown:
        raise InvalidShortcut(f"Ação de atalho desconhecida: {', '.join(sorted(unknown))}.")

    result: dict[str, str | None] = {}
    used: dict[str, str] = {}
    for action in SHORTCUT_ACTIONS:
        raw = bindings.get(action, DEFAULT_BINDINGS[action])
        if raw is None or not raw.strip():
            result[action] = None
            continue
        combo = normalize_combo(raw)
        if combo in used:
            raise InvalidShortcut(f"{combo} já está em uso por outra ação.")
        used[combo] = action
        result[action] = combo
    return result


def merge_with_defaults(stored: dict | None) -> dict[str, str | None]:
    """Preferência salva + padrão das ações que ainda não existiam quando ela foi salva.

    Um valor salvo que deixou de ser válido (regra nova) volta ao padrão.
    """
    bindings = dict(DEFAULT_BINDINGS)
    for action in SHORTCUT_ACTIONS:
        if stored and action in stored:
            bindings[action] = stored[action]
    try:
        return validate_bindings(bindings)
    except InvalidShortcut:
        return dict(DEFAULT_BINDINGS)
