"""Monta os clientes a partir das credenciais do cofre.

Uso: `async with await jira_client(store) as jira: ...`
"""

from integrations.bitbucket_client import BitbucketClient
from integrations.errors import IntegrationNotConfigured
from integrations.jira_client import JiraClient
from security.credential_store import CredentialStore


async def jira_client(store: CredentialStore) -> JiraClient:
    data = store.get("jira")
    if not data or not data.get("api_token"):
        raise IntegrationNotConfigured("Jira")
    return await JiraClient.create(
        site_url=data["site_url"],
        email=data["email"],
        api_token=data["api_token"],
        auth_mode=data.get("auth_mode", "classic"),
        cloud_id=data.get("cloud_id"),
    )


def bitbucket_client(store: CredentialStore) -> BitbucketClient:
    data = store.get("bitbucket")
    if not data or not data.get("api_token"):
        raise IntegrationNotConfigured("Bitbucket")
    return BitbucketClient.create(
        email=data["email"], api_token=data["api_token"], workspace=data["workspace"]
    )
