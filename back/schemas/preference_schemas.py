from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from services.card_colors import CARD_TYPES, MAX_ALIAS_LENGTH, MAX_ALIASES, repo_key
from services.shortcuts import DEFAULT_BINDINGS, validate_bindings

HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
RepoSlug = Annotated[str, StringConstraints(min_length=1, max_length=100)]
Alias = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_ALIAS_LENGTH)
]


class ShortcutsPreferences(BaseModel):
    """Atalho por ação; ``null`` desativa a ação."""

    bindings: dict[str, str | None] = Field(default_factory=lambda: dict(DEFAULT_BINDINGS))

    @field_validator("bindings")
    @classmethod
    def _bindings(cls, value: dict[str, str | None]) -> dict[str, str | None]:
        return validate_bindings(value)


class ShortcutsOut(ShortcutsPreferences):
    defaults: dict[str, str | None] = Field(default_factory=lambda: dict(DEFAULT_BINDINGS))


class CardTypeColorOut(BaseModel):
    id: str
    label: str
    color: str | None
    default_color: str


class RepoColorOut(BaseModel):
    slug: str
    color: str | None
    # Fora de Configurações › Sincronização: continua na lista só porque ainda tem cor
    # (ou apelido).
    synced: bool
    aliases: list[str] = []
    # Começos do slug que valem sozinhos no colchete (`weaction` para weaction-api).
    automatic_aliases: list[str] = []


class CardColorsOut(BaseModel):
    types: list[CardTypeColorOut]
    repos: list[RepoColorOut]
    # Ponto de partida do "Definir cor" de um repositório — o dev troca pelo seletor.
    suggestions: list[str]


class CardColorsIn(BaseModel):
    """Cores inteiras de uma vez. ``null`` tira a cor; tipo que não vier volta ao padrão."""

    types: dict[str, HexColor | None] = Field(default_factory=dict)
    repos: dict[RepoSlug, HexColor | None] = Field(default_factory=dict, max_length=200)
    aliases: dict[RepoSlug, list[Alias]] = Field(default_factory=dict, max_length=200)

    @field_validator("types")
    @classmethod
    def _known_types(cls, value: dict[str, str | None]) -> dict[str, str | None]:
        known = {t.id for t in CARD_TYPES}
        if set(value) - known:
            raise ValueError(f"tipo desconhecido; use {', '.join(sorted(known))}")
        return value

    @field_validator("aliases")
    @classmethod
    def _few_aliases(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        if any(len(names) > MAX_ALIASES for names in value.values()):
            raise ValueError(f"no máximo {MAX_ALIASES} apelidos por repositório")
        return value

    @model_validator(mode="after")
    def _alias_of_one_repo(self) -> "CardColorsIn":
        # Apelido que vale para dois repositórios não é de nenhum: a tela avisa qual é, e
        # aqui só se recusa — a mensagem não repete o que foi digitado.
        slugs = {repo_key(slug) for slug in (*self.repos, *self.aliases)}
        owners: dict[str, str] = {}
        for slug, names in self.aliases.items():
            for name in names:
                key = repo_key(name)
                if key == repo_key(slug):
                    continue
                if key in slugs or owners.setdefault(key, slug) != slug:
                    raise ValueError("um apelido não pode valer para dois repositórios")
        return self
