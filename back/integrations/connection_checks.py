"""Testes de conexão com Jira e Bitbucket, feitos com os próprios clientes.

Só leem a identidade da conta (e, no Bitbucket, o acesso ao workspace). Sem novas
tentativas: o dev está esperando a resposta na tela.
"""

from dataclasses import dataclass

import httpx

from integrations.bitbucket_client import BitbucketClient
from integrations.errors import (
    IntegrationError,
    IntegrationUnavailable,
    PermissionDenied,
    ResourceNotFound,
)
from integrations.jira_client import JiraClient

CHECK_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


@dataclass(frozen=True)
class ConnectionCheck:
    ok: bool
    account_name: str | None = None
    account_id: str | None = None
    message: str | None = None
    extra: dict | None = None


async def check_jira(
    *,
    site_url: str,
    email: str,
    api_token: str,
    auth_mode: str,
    cloud_id: str | None = None,
) -> ConnectionCheck:
    """`classic`: token clássico direto no site. `scoped`: token com escopos, via gateway."""
    async with httpx.AsyncClient(timeout=CHECK_TIMEOUT) as http:
        try:
            jira = await JiraClient.create(
                site_url=site_url,
                email=email,
                api_token=api_token,
                auth_mode=auth_mode,
                cloud_id=cloud_id,
                client=http,
                max_retries=0,
            )
            body = await jira.myself()
        except IntegrationUnavailable:
            return ConnectionCheck(
                ok=False, message="Jira: não foi possível conectar ao site informado."
            )
        except IntegrationError as exc:
            return ConnectionCheck(ok=False, message=exc.message)

    extra = {"cloud_id": jira.cloud_id} if jira.cloud_id else {}
    return ConnectionCheck(
        ok=True,
        account_name=body.get("displayName"),
        account_id=body.get("accountId"),
        extra=extra,
    )


async def check_bitbucket(*, email: str, api_token: str, workspace: str) -> ConnectionCheck:
    async with httpx.AsyncClient(timeout=CHECK_TIMEOUT) as http:
        bitbucket = BitbucketClient.create(
            email=email, api_token=api_token, workspace=workspace, client=http, max_retries=0
        )
        try:
            body = await bitbucket.current_user()
        except IntegrationUnavailable:
            return ConnectionCheck(ok=False, message="Bitbucket: não foi possível conectar à API.")
        except IntegrationError as exc:
            return ConnectionCheck(ok=False, message=exc.message)

        try:
            repository_count = await bitbucket.repository_count()
        except (PermissionDenied, ResourceNotFound):
            return ConnectionCheck(
                ok=False,
                message=(
                    f"Bitbucket: conta ok, mas sem acesso aos repositórios do workspace "
                    f"'{workspace}'. Confira o nome e o escopo de leitura de repositórios."
                ),
            )
        except IntegrationUnavailable:
            return ConnectionCheck(ok=False, message="Bitbucket: não foi possível conectar à API.")
        except IntegrationError as exc:
            return ConnectionCheck(ok=False, message=exc.message)

    return ConnectionCheck(
        ok=True,
        account_name=body.get("display_name"),
        account_id=body.get("account_id") or body.get("uuid"),
        extra={"repository_count": repository_count},
    )
