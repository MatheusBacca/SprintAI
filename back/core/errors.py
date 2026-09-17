import re

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from database.pool import DatabaseUnavailable
from integrations.errors import (
    IntegrationError,
    IntegrationNotConfigured,
    IntegrationUnavailable,
    RateLimited,
    ResourceNotFound,
)
from security.credential_store import CredentialStoreError


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Erro de validação sem ecoar o valor enviado.

    O handler padrão do FastAPI devolve `input` de cada campo inválido — para um
    token malformado, isso devolveria (e poderia logar) o próprio segredo.
    """
    errors = [
        {"loc": err.get("loc"), "msg": err.get("msg"), "type": err.get("type")}
        for err in exc.errors()
    ]
    return JSONResponse({"detail": errors}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)


async def integration_error_handler(request: Request, exc: IntegrationError) -> JSONResponse:
    """Falha em Jira/Bitbucket vira resposta com mensagem pronta para a tela.

    401/403 do provedor NÃO são repassados como 401/403: para o front isso pareceria
    falha de acesso à própria API local. Viram 502 (dependência externa recusou).
    """
    status_code = {
        IntegrationNotConfigured: status.HTTP_409_CONFLICT,
        ResourceNotFound: status.HTTP_404_NOT_FOUND,
        RateLimited: status.HTTP_503_SERVICE_UNAVAILABLE,
        IntegrationUnavailable: status.HTTP_503_SERVICE_UNAVAILABLE,
    }.get(type(exc), status.HTTP_502_BAD_GATEWAY)
    code = re.sub(r"(?<!^)(?=[A-Z])", "_", type(exc).__name__).lower()
    return JSONResponse({"detail": exc.message, "code": code}, status_code=status_code)


async def credential_store_error_handler(
    request: Request, exc: CredentialStoreError
) -> JSONResponse:
    return JSONResponse(
        {"detail": str(exc), "code": "credential_store_unavailable"},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


async def database_unavailable_handler(request: Request, exc: DatabaseUnavailable) -> JSONResponse:
    return JSONResponse(
        {"detail": str(exc), "code": "database_unavailable"},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )
