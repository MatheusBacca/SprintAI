"""Cor de fundo dos cards do canvas (Configurações › Cores dos cards).

Os pais — Épico, Enhancements e Feature — são pintados pelo tipo. Os outros cards, pelo
repositório entre colchetes no começo do título (`[monitoria] Enviar a coleta…`), que é
como as Tarefas fatiadas nascem. Card sem nenhum dos dois fica como sempre foi.

O título é digitado à mão e a grafia do repositório varia — `[Supervisor-Web]`,
`[MonitorIA]`, `[Weaction-Api]` —, por isso a comparação ignora caixa, acento, hífen e
espaço. Colchete com mais de um repositório (`[Supervisor-Web / QualificAI]`) fica com a
cor do primeiro que tiver cor.
"""

import re
from dataclasses import dataclass, field
from typing import Any

import asyncpg

from repositories import settings_repo
from services.progress.stages import normalize

SETTING_KEY = "card_colors"

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
TITLE_TAG = re.compile(r"^\s*\[([^\]]+)\]")
TAG_SEPARATORS = re.compile(r"[/,+&|]")

TYPE = "tipo"
REPO = "repositorio"


@dataclass(frozen=True)
class CardType:
    id: str
    label: str
    aliases: frozenset[str]
    default_color: str


# Os mesmos tipos de pai de `services/hierarchy.py`, com a grafia normalizada.
CARD_TYPES: tuple[CardType, ...] = (
    CardType("epico", "Épico", frozenset({"epico", "epic"}), "#7c3aed"),
    CardType("enhancements", "Enhancements", frozenset({"enhancements", "enhancement"}), "#c9a227"),
    CardType("feature", "Feature", frozenset({"feature"}), "#15803d"),
)

# Sugestões para o "Definir cor" de um repositório: longe do roxo, do dourado e do verde
# dos tipos, para a tarefa não se confundir com um pai.
SUGGESTED_COLORS: tuple[str, ...] = (
    "#2f7cf6",
    "#0d9488",
    "#ea580c",
    "#db2777",
    "#0891b2",
    "#dc2626",
    "#65a30d",
    "#4f46e5",
    "#b45309",
    "#475569",
)


def type_of(issue_type: str | None) -> CardType | None:
    name = normalize(issue_type)
    return next((t for t in CARD_TYPES if name in t.aliases), None)


def repo_key(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize(name))


def title_repos(summary: str | None) -> list[str]:
    """Repositórios do colchete que abre o título, na ordem em que aparecem."""
    match = TITLE_TAG.match(summary or "")
    if not match:
        return []
    return [part.strip() for part in TAG_SEPARATORS.split(match.group(1)) if part.strip()]


def valid_color(value: Any) -> str | None:
    return value.lower() if isinstance(value, str) and HEX_COLOR.match(value) else None


@dataclass(frozen=True)
class Tint:
    color: str
    source: str
    label: str


@dataclass(frozen=True)
class CardColors:
    # Tipo sem cor (None) fica fora da pintura; tipo ausente não acontece — `from_setting`
    # completa com o padrão.
    types: dict[str, str | None] = field(
        default_factory=lambda: {t.id: t.default_color for t in CARD_TYPES}
    )
    repos: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        by_key = {repo_key(slug): (slug, color) for slug, color in self.repos.items()}
        object.__setattr__(self, "_by_key", by_key)

    def tint_for(self, issue_type: str | None, summary: str | None) -> Tint | None:
        kind = type_of(issue_type)
        if kind is not None and (color := self.types.get(kind.id)):
            return Tint(color=color, source=TYPE, label=kind.label)
        for name in title_repos(summary):
            hit = self._by_key.get(repo_key(name))  # type: ignore[attr-defined]
            if hit:
                return Tint(color=hit[1], source=REPO, label=hit[0])
        return None

    # --- Persistência (app_setting) -------------------------------------------------

    @classmethod
    def from_setting(cls, value: Any) -> "CardColors":
        types: dict[str, str | None] = {t.id: t.default_color for t in CARD_TYPES}
        repos: dict[str, str] = {}
        if isinstance(value, dict):
            raw_types = value.get("types")
            if isinstance(raw_types, dict):
                for kind in CARD_TYPES:
                    if kind.id not in raw_types:
                        continue
                    raw = raw_types[kind.id]
                    types[kind.id] = None if raw is None else valid_color(raw) or kind.default_color
            raw_repos = value.get("repos")
            if isinstance(raw_repos, dict):
                repos = {
                    str(slug): color
                    for slug, raw in raw_repos.items()
                    if (color := valid_color(raw))
                }
        return cls(types=types, repos=repos)

    def to_setting(self) -> dict[str, Any]:
        return {"types": dict(self.types), "repos": dict(self.repos)}


async def load_colors(pool: asyncpg.Pool) -> CardColors:
    return CardColors.from_setting(await settings_repo.get_setting(pool, SETTING_KEY))


async def save_colors(pool: asyncpg.Pool, colors: CardColors) -> CardColors:
    await settings_repo.set_setting(pool, SETTING_KEY, colors.to_setting())
    return colors
