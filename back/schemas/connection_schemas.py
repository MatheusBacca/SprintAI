import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, SecretStr, field_validator

Provider = Literal["jira", "bitbucket"]

_ATLASSIAN_SITE = re.compile(r"^https://[a-z0-9][a-z0-9-]*\.atlassian\.net$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_WORKSPACE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,61}$")


def _validate_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL.match(value):
        raise ValueError("E-mail inválido.")
    return value


def _validate_token(value: SecretStr | None) -> SecretStr | None:
    if value is None:
        return None
    raw = value.get_secret_value().strip()
    if not raw:
        return None  # vazio = manter o token já salvo
    if len(raw) < 16 or any(c.isspace() for c in raw):
        raise ValueError("Token inválido: confira se colou o valor completo.")
    return SecretStr(raw)


class JiraConnectionIn(BaseModel):
    site_url: str
    email: str
    api_token: SecretStr | None = None
    auth_mode: Literal["classic", "scoped"] = "classic"

    @field_validator("site_url")
    @classmethod
    def _site(cls, value: str) -> str:
        value = value.strip().lower().rstrip("/")
        if not _ATLASSIAN_SITE.match(value):
            # Restringe o destino do token a sites Atlassian Cloud.
            raise ValueError("Use o endereço do Jira Cloud, ex.: https://weon.atlassian.net")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _validate_email(value)

    @field_validator("api_token")
    @classmethod
    def _token(cls, value: SecretStr | None) -> SecretStr | None:
        return _validate_token(value)


class BitbucketConnectionIn(BaseModel):
    email: str
    api_token: SecretStr | None = None
    workspace: str = "weonrepo"

    @field_validator("workspace")
    @classmethod
    def _workspace(cls, value: str) -> str:
        value = value.strip().lower()
        if not _WORKSPACE.match(value):
            raise ValueError("Workspace inválido.")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _validate_email(value)

    @field_validator("api_token")
    @classmethod
    def _token(cls, value: SecretStr | None) -> SecretStr | None:
        return _validate_token(value)


class ConnectionStatus(BaseModel):
    provider: Provider
    configured: bool
    account_name: str | None = None
    validated_at: datetime | None = None
    last_checked_at: datetime | None = None
    last_error: str | None = None
    # Só campos NÃO secretos (site, e-mail, workspace, modo de auth).
    settings: dict[str, Any] = {}


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str | None = None
    status: ConnectionStatus
