import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import KeyringError, PasswordDeleteError

from security.credential_store import (
    MAX_PAYLOAD_CHARS,
    CredentialStoreError,
    InMemoryCredentialStore,
    KeyringCredentialStore,
)


class FakeKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.data = {}

    def get_password(self, service, username):
        return self.data.get((service, username))

    def set_password(self, service, username, password):
        self.data[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) not in self.data:
            raise PasswordDeleteError()
        del self.data[(service, username)]


class BrokenKeyring(FakeKeyring):
    def get_password(self, service, username):
        raise KeyringError("vault locked")

    def set_password(self, service, username, password):
        raise KeyringError("vault locked")


@pytest.fixture
def fake_keyring():
    previous = keyring.get_keyring()
    backend = FakeKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


def test_grava_e_le_json_no_servico_sprintai(fake_keyring):
    store = KeyringCredentialStore()

    store.set("jira", {"email": "dev@weon.com.br", "api_token": "x" * 24})

    assert ("sprintai", "jira") in fake_keyring.data
    assert store.get("jira") == {"email": "dev@weon.com.br", "api_token": "x" * 24}


def test_get_inexistente_devolve_none(fake_keyring):
    assert KeyringCredentialStore().get("bitbucket") is None


def test_delete_inexistente_nao_falha(fake_keyring):
    KeyringCredentialStore().delete("bitbucket")


def test_entrada_corrompida_vira_erro_claro(fake_keyring):
    fake_keyring.data[("sprintai", "jira")] = "{nao-e-json"

    with pytest.raises(CredentialStoreError, match="corrompida"):
        KeyringCredentialStore().get("jira")


def test_cofre_indisponivel_vira_credential_store_error():
    previous = keyring.get_keyring()
    keyring.set_keyring(BrokenKeyring())
    try:
        with pytest.raises(CredentialStoreError):
            KeyringCredentialStore().get("jira")
        with pytest.raises(CredentialStoreError):
            KeyringCredentialStore().set("jira", {"a": 1})
    finally:
        keyring.set_keyring(previous)


def test_recusa_payload_maior_que_o_limite_do_windows():
    store = InMemoryCredentialStore()

    with pytest.raises(CredentialStoreError, match="grande demais"):
        store.set("jira", {"api_token": "x" * MAX_PAYLOAD_CHARS})
