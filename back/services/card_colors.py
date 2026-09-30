"""Cor de fundo dos cards do canvas (Configurações › Cores dos cards).

Os pais — Épico, Enhancements e Feature — são pintados pelo tipo. Os outros cards, pelo
repositório entre colchetes no começo do título (`[monitoria] Enviar a coleta…`), que é
como as Tarefas fatiadas nascem. Card sem nenhum dos dois fica como sempre foi.

O título é digitado à mão e a grafia do repositório varia — `[Supervisor-Web]`,
`[MonitorIA]`, `[weaction]` para o weaction-api —, por isso o nome do colchete é
resolvido em três degraus, nesta ordem:

1. o slug, sem caixa, acento, hífen ou espaço;
2. um apelido cadastrado no repositório (`[Internal]` para o organia-configs);
3. o começo do slug até um hífen (`[weaction]`, `[supervisor]`), só quando nenhum outro
   repositório começa igual — `[api]` não é de ninguém, com api-credits e
   api-audio-transcribe na lista.

Colchete com mais de um repositório (`[supervisor / qualificai]`) pinta com um
esfumaçado por repositório com cor, na ordem do título, e cada nome dentro do colchete
vai na cor do seu repositório.
"""

import re
from dataclasses import dataclass, field
from typing import Any

import asyncpg

from repositories import settings_repo
from services.progress.stages import normalize
from services.sync.engine import load_scope

SETTING_KEY = "card_colors"

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
TITLE_TAG = re.compile(r"^\s*\[([^\]]+)\]")
# Com grupo: o `split` devolve o separador também, e o título se remonta inteiro.
TAG_SEPARATORS = re.compile(r"([/,+&|])")
SLUG_WORDS = re.compile(r"[^a-z0-9]+")

TYPE = "tipo"
REPO = "repositorio"

# Mais que três esfumaçados num card de 236px vira borrão: o quarto repositório em
# diante fica só com o nome pintado no título.
MAX_TINTS = 3
MAX_ALIASES = 10
MAX_ALIAS_LENGTH = 60


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


def leading_names(slug: str) -> list[str]:
    """Começos do slug até cada hífen: `api-audio-transcribe` → `api`, `api-audio`."""
    words = [w for w in SLUG_WORDS.split(normalize(slug)) if w]
    return ["-".join(words[:k]) for k in range(1, len(words))]


def valid_color(value: Any) -> str | None:
    return value.lower() if isinstance(value, str) and HEX_COLOR.match(value) else None


def valid_aliases(slug: str, value: Any) -> tuple[str, ...]:
    """Apelidos aproveitáveis de um repositório: sem repetição e sem o próprio slug."""
    if not isinstance(value, list | tuple):
        return ()
    seen = {repo_key(slug)}
    kept: list[str] = []
    for raw in value[:MAX_ALIASES]:
        alias = raw.strip() if isinstance(raw, str) else ""
        key = repo_key(alias)
        if key and len(alias) <= MAX_ALIAS_LENGTH and key not in seen:
            seen.add(key)
            kept.append(alias)
    return tuple(kept)


@dataclass(frozen=True)
class Tint:
    # Na ordem do título: a primeira vai no canto de cima à esquerda e dá a cor do
    # cabeçalho do card (ícone, tipo, chave, SP).
    colors: tuple[str, ...]
    source: str
    label: str


@dataclass(frozen=True)
class TitlePart:
    text: str
    color: str | None = None


@dataclass(frozen=True)
class CardPaint:
    tint: Tint | None
    # Título em pedaços, com a cor de cada repositório do colchete. Vazio quando nenhum
    # nome do colchete tem cor — o card mostra o título como sempre.
    title: tuple[TitlePart, ...] = ()


@dataclass(frozen=True)
class CardColors:
    # Tipo sem cor (None) fica fora da pintura; tipo ausente não acontece — `from_setting`
    # completa com o padrão.
    types: dict[str, str | None] = field(
        default_factory=lambda: {t.id: t.default_color for t in CARD_TYPES}
    )
    repos: dict[str, str] = field(default_factory=dict)
    aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Repositórios de Sincronização. Não são pintados por si, mas contam para saber se um
    # começo de slug é de um repositório só.
    known: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        slugs = sorted(set(self.known) | set(self.repos) | set(self.aliases))
        exact = {repo_key(slug): slug for slug in slugs}
        named: dict[str, set[str]] = {}
        for slug, names in self.aliases.items():
            for name in names:
                if (key := repo_key(name)) not in exact:
                    named.setdefault(key, set()).add(slug)
        leading: dict[str, set[str]] = {}
        shown: dict[str, str] = {}
        for slug in slugs:
            for name in leading_names(slug):
                key = repo_key(name)
                if key not in exact and key not in named:
                    leading.setdefault(key, set()).add(slug)
                    shown[key] = name
        automatic = _single_owner(leading)

        object.__setattr__(self, "_resolve", {**automatic, **_single_owner(named), **exact})
        object.__setattr__(
            self,
            "_automatic",
            {slug: [shown[k] for k, owner in automatic.items() if owner == slug] for slug in slugs},
        )

    def resolve(self, name: str) -> str | None:
        """Slug do repositório que um nome do colchete quer dizer."""
        return self._resolve.get(repo_key(name))  # type: ignore[attr-defined]

    def automatic_aliases(self, slug: str) -> list[str]:
        """Começos do slug que valem sozinhos — a tela mostra como "também vale"."""
        return list(self._automatic.get(slug, []))  # type: ignore[attr-defined]

    def paint(self, issue_type: str | None, summary: str | None) -> CardPaint:
        title, hits = self._title(summary or "")
        kind = type_of(issue_type)
        if kind is not None and (color := self.types.get(kind.id)):
            return CardPaint(Tint(colors=(color,), source=TYPE, label=kind.label), title)
        if hits:
            tint = Tint(
                colors=tuple(color for _, color in hits[:MAX_TINTS]),
                source=REPO,
                label=", ".join(slug for slug, _ in hits),
            )
            return CardPaint(tint, title)
        return CardPaint(None, title)

    def _title(self, summary: str) -> tuple[tuple[TitlePart, ...], list[tuple[str, str]]]:
        match = TITLE_TAG.match(summary)
        if not match:
            return (), []
        parts = [TitlePart(summary[: match.start(1)])]
        hits: list[tuple[str, str]] = []
        for token in TAG_SEPARATORS.split(match.group(1)):
            name = token.strip()
            slug = self.resolve(name) if name else None
            color = self.repos.get(slug) if slug else None
            if not color:
                parts.append(TitlePart(token))
                continue
            # Só o nome ganha cor: o espaço em volta dele fica com o resto do título.
            start = token.index(name)
            parts += [
                TitlePart(token[:start]),
                TitlePart(name, color),
                TitlePart(token[start + len(name) :]),
            ]
            if all(slug != seen for seen, _ in hits):
                hits.append((slug, color))
        parts.append(TitlePart(summary[match.end(1) :]))
        return (_merge(parts) if hits else ()), hits

    # --- Persistência (app_setting) -------------------------------------------------

    @classmethod
    def from_setting(cls, value: Any, known: tuple[str, ...] = ()) -> "CardColors":
        types: dict[str, str | None] = {t.id: t.default_color for t in CARD_TYPES}
        repos: dict[str, str] = {}
        aliases: dict[str, tuple[str, ...]] = {}
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
            raw_aliases = value.get("aliases")
            if isinstance(raw_aliases, dict):
                aliases = {
                    str(slug): names
                    for slug, raw in raw_aliases.items()
                    if (names := valid_aliases(str(slug), raw))
                }
        return cls(types=types, repos=repos, aliases=aliases, known=tuple(known))

    def to_setting(self) -> dict[str, Any]:
        return {
            "types": dict(self.types),
            "repos": dict(self.repos),
            "aliases": {slug: list(names) for slug, names in self.aliases.items()},
        }


def _single_owner(candidates: dict[str, set[str]]) -> dict[str, str]:
    """Nome que dois repositórios reclamam não é de nenhum."""
    return {key: next(iter(owners)) for key, owners in candidates.items() if len(owners) == 1}


def _merge(parts: list[TitlePart]) -> tuple[TitlePart, ...]:
    """Junta os pedaços sem cor vizinhos e tira os vazios."""
    merged: list[TitlePart] = []
    for part in parts:
        if not part.text:
            continue
        if merged and part.color is None and merged[-1].color is None:
            merged[-1] = TitlePart(merged[-1].text + part.text)
        else:
            merged.append(part)
    return tuple(merged)


async def load_colors(pool: asyncpg.Pool) -> CardColors:
    known = tuple((await load_scope(pool)).bitbucket.repo_slugs)
    return CardColors.from_setting(await settings_repo.get_setting(pool, SETTING_KEY), known)


async def save_colors(pool: asyncpg.Pool, colors: CardColors) -> CardColors:
    await settings_repo.set_setting(pool, SETTING_KEY, colors.to_setting())
    return colors
