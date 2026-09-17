from pydantic import BaseModel, Field, field_validator

from services.shortcuts import DEFAULT_BINDINGS, validate_bindings


class ShortcutsPreferences(BaseModel):
    """Atalho por ação; ``null`` desativa a ação."""

    bindings: dict[str, str | None] = Field(default_factory=lambda: dict(DEFAULT_BINDINGS))

    @field_validator("bindings")
    @classmethod
    def _bindings(cls, value: dict[str, str | None]) -> dict[str, str | None]:
        return validate_bindings(value)


class ShortcutsOut(ShortcutsPreferences):
    defaults: dict[str, str | None] = Field(default_factory=lambda: dict(DEFAULT_BINDINGS))
