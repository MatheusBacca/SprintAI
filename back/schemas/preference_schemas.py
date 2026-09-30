from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

from services.card_colors import CARD_TYPES
from services.shortcuts import DEFAULT_BINDINGS, validate_bindings

HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
RepoSlug = Annotated[str, StringConstraints(min_length=1, max_length=100)]


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
    # Fora de Configurações › Sincronização: continua na lista só porque ainda tem cor.
    synced: bool


class CardColorsOut(BaseModel):
    types: list[CardTypeColorOut]
    repos: list[RepoColorOut]
    # Ponto de partida do "Definir cor" de um repositório — o dev troca pelo seletor.
    suggestions: list[str]


class CardColorsIn(BaseModel):
    """Cores inteiras de uma vez. ``null`` tira a cor; tipo que não vier volta ao padrão."""

    types: dict[str, HexColor | None] = Field(default_factory=dict)
    repos: dict[RepoSlug, HexColor | None] = Field(default_factory=dict, max_length=200)

    @field_validator("types")
    @classmethod
    def _known_types(cls, value: dict[str, str | None]) -> dict[str, str | None]:
        known = {t.id for t in CARD_TYPES}
        if set(value) - known:
            raise ValueError(f"tipo desconhecido; use {', '.join(sorted(known))}")
        return value
