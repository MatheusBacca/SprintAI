from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from schemas.connection_schemas import (
    BitbucketConnectionIn,
    ConnectionStatus,
    ConnectionTestResult,
    JiraConnectionIn,
    Provider,
)
from security.credential_store import CredentialStore, CredentialStoreError, get_credential_store
from services import connection_service
from services.connection_service import ConnectionNotConfigured, ConnectionRejected

router = APIRouter(prefix="/connections", tags=["connections"])

Store = Annotated[CredentialStore, Depends(get_credential_store)]


def _store_unavailable(exc: CredentialStoreError) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.get("", response_model=list[ConnectionStatus])
async def list_connections(store: Store):
    try:
        return connection_service.list_statuses(store)
    except CredentialStoreError as exc:
        raise _store_unavailable(exc) from exc


@router.put("/jira", response_model=ConnectionStatus)
async def save_jira(payload: JiraConnectionIn, store: Store):
    try:
        return await connection_service.save_jira(store, payload)
    except ConnectionRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.message) from exc
    except CredentialStoreError as exc:
        raise _store_unavailable(exc) from exc


@router.put("/bitbucket", response_model=ConnectionStatus)
async def save_bitbucket(payload: BitbucketConnectionIn, store: Store):
    try:
        return await connection_service.save_bitbucket(store, payload)
    except ConnectionRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.message) from exc
    except CredentialStoreError as exc:
        raise _store_unavailable(exc) from exc


@router.post("/{provider}/test", response_model=ConnectionTestResult)
async def test_connection(provider: Provider, store: Store):
    try:
        return await connection_service.test_connection(store, provider)
    except ConnectionNotConfigured as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conexão não configurada.") from exc
    except CredentialStoreError as exc:
        raise _store_unavailable(exc) from exc


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(provider: Provider, store: Store):
    try:
        connection_service.delete_connection(store, provider)
    except CredentialStoreError as exc:
        raise _store_unavailable(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
