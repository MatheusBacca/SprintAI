"""Cadastro, teste e remoção das conexões com Jira e Bitbucket.

Regra central: uma conexão só é gravada no cofre depois de testada com sucesso.
Um teste que falha não apaga o que já estava salvo.
"""

from datetime import UTC, datetime
from typing import Any

from integrations.connection_checks import ConnectionCheck, check_bitbucket, check_jira
from schemas.connection_schemas import (
    BitbucketConnectionIn,
    ConnectionStatus,
    ConnectionTestResult,
    JiraConnectionIn,
    Provider,
)
from security.credential_store import CredentialStore

PROVIDERS: tuple[Provider, ...] = ("jira", "bitbucket")
SECRET_FIELDS = {"api_token"}
STATUS_FIELDS = {"account_name", "account_id", "validated_at", "last_checked_at", "last_error"}


class ConnectionNotConfigured(Exception):
    pass


class ConnectionRejected(Exception):
    """O teste com as credenciais informadas falhou; nada foi gravado."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _now() -> str:
    return datetime.now(UTC).isoformat()


def to_status(provider: Provider, data: dict[str, Any] | None) -> ConnectionStatus:
    if not data:
        return ConnectionStatus(provider=provider, configured=False)
    settings = {k: v for k, v in data.items() if k not in SECRET_FIELDS and k not in STATUS_FIELDS}
    return ConnectionStatus(
        provider=provider,
        configured=True,
        account_name=data.get("account_name"),
        validated_at=data.get("validated_at"),
        last_checked_at=data.get("last_checked_at"),
        last_error=data.get("last_error"),
        settings=settings,
    )


def list_statuses(store: CredentialStore) -> list[ConnectionStatus]:
    return [to_status(p, store.get(p)) for p in PROVIDERS]


def _resolve_token(new_token, existing: dict[str, Any] | None) -> str:
    if new_token is not None:
        return new_token.get_secret_value()
    if existing and existing.get("api_token"):
        return existing["api_token"]
    raise ConnectionRejected("Informe o token de API.")


async def _run_check(provider: Provider, data: dict[str, Any]) -> ConnectionCheck:
    if provider == "jira":
        return await check_jira(
            site_url=data["site_url"],
            email=data["email"],
            api_token=data["api_token"],
            auth_mode=data.get("auth_mode", "classic"),
            cloud_id=data.get("cloud_id"),
        )
    return await check_bitbucket(
        email=data["email"], api_token=data["api_token"], workspace=data["workspace"]
    )


def _apply_success(data: dict[str, Any], check: ConnectionCheck) -> dict[str, Any]:
    now = _now()
    return {
        **data,
        **(check.extra or {}),
        "account_name": check.account_name,
        "account_id": check.account_id,
        "validated_at": now,
        "last_checked_at": now,
        "last_error": None,
    }


async def save_jira(store: CredentialStore, payload: JiraConnectionIn) -> ConnectionStatus:
    existing = store.get("jira")
    data = {
        "site_url": payload.site_url,
        "email": payload.email,
        "auth_mode": payload.auth_mode,
        "api_token": _resolve_token(payload.api_token, existing),
    }
    return await _save("jira", store, data)


async def save_bitbucket(
    store: CredentialStore, payload: BitbucketConnectionIn
) -> ConnectionStatus:
    existing = store.get("bitbucket")
    data = {
        "email": payload.email,
        "workspace": payload.workspace,
        "api_token": _resolve_token(payload.api_token, existing),
    }
    return await _save("bitbucket", store, data)


async def _save(
    provider: Provider, store: CredentialStore, data: dict[str, Any]
) -> ConnectionStatus:
    check = await _run_check(provider, data)
    if not check.ok:
        raise ConnectionRejected(check.message or "Falha ao testar a conexão.")
    saved = _apply_success(data, check)
    store.set(provider, saved)
    return to_status(provider, saved)


async def test_connection(store: CredentialStore, provider: Provider) -> ConnectionTestResult:
    existing = store.get(provider)
    if not existing:
        raise ConnectionNotConfigured(provider)

    check = await _run_check(provider, existing)
    if check.ok:
        updated = _apply_success(existing, check)
    else:
        updated = {**existing, "last_checked_at": _now(), "last_error": check.message}
    store.set(provider, updated)
    return ConnectionTestResult(
        ok=check.ok, message=check.message, status=to_status(provider, updated)
    )


def delete_connection(store: CredentialStore, provider: Provider) -> None:
    store.delete(provider)
