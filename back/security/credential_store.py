"""Cofre de credenciais das integrações.

Cada provedor vira UMA entrada no Cofre do Windows (serviço `sprintai`, usuário =
provedor) com um JSON que junta o segredo e os metadados da conexão. Nada disso
vai para banco, `.env` ou log; a API só devolve o status mascarado.

O Windows limita o blob de uma credencial a 2560 bytes (~1280 caracteres UTF-16):
o payload é validado antes de gravar para falhar com mensagem clara.
"""

import json
from typing import Any, Protocol

import keyring
from keyring.errors import KeyringError, NoKeyringError, PasswordDeleteError

SERVICE_NAME = "sprintai"
MAX_PAYLOAD_CHARS = 1200


class CredentialStoreError(Exception):
    """O cofre não está disponível ou recusou a operação."""


class CredentialStore(Protocol):
    def get(self, provider: str) -> dict[str, Any] | None: ...

    def set(self, provider: str, data: dict[str, Any]) -> None: ...

    def delete(self, provider: str) -> None: ...


def _serialize(data: dict[str, Any]) -> str:
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    if len(payload) > MAX_PAYLOAD_CHARS:
        raise CredentialStoreError(
            "Credencial grande demais para o Cofre do Windows "
            f"({len(payload)} caracteres; limite {MAX_PAYLOAD_CHARS})."
        )
    return payload


class KeyringCredentialStore:
    """Implementação sobre o `keyring` (WinVaultKeyring no Windows)."""

    def __init__(self, service_name: str = SERVICE_NAME) -> None:
        self._service = service_name

    def get(self, provider: str) -> dict[str, Any] | None:
        try:
            raw = keyring.get_password(self._service, provider)
        except (KeyringError, NoKeyringError) as exc:
            raise CredentialStoreError("Cofre de credenciais indisponível.") from exc
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CredentialStoreError(
                f"Entrada '{provider}' do cofre está corrompida; remova e cadastre de novo."
            ) from exc

    def set(self, provider: str, data: dict[str, Any]) -> None:
        payload = _serialize(data)
        try:
            keyring.set_password(self._service, provider, payload)
        except (KeyringError, NoKeyringError) as exc:
            raise CredentialStoreError("Não foi possível gravar no cofre de credenciais.") from exc

    def delete(self, provider: str) -> None:
        try:
            keyring.delete_password(self._service, provider)
        except PasswordDeleteError:
            return  # já não existia
        except (KeyringError, NoKeyringError) as exc:
            raise CredentialStoreError("Não foi possível remover do cofre de credenciais.") from exc


class InMemoryCredentialStore:
    """Usado nos testes. Aplica o mesmo limite de tamanho do cofre real."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get(self, provider: str) -> dict[str, Any] | None:
        raw = self._data.get(provider)
        return json.loads(raw) if raw is not None else None

    def set(self, provider: str, data: dict[str, Any]) -> None:
        self._data[provider] = _serialize(data)

    def delete(self, provider: str) -> None:
        self._data.pop(provider, None)


_store: CredentialStore = KeyringCredentialStore()


def get_credential_store() -> CredentialStore:
    """Dependência FastAPI; os testes sobrescrevem com `InMemoryCredentialStore`."""
    return _store
