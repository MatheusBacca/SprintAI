"""Erros das integrações externas.

As mensagens são pensadas para aparecer na tela: nunca carregam token, header de
autorização ou corpo cru da resposta.
"""


class IntegrationError(Exception):
    def __init__(self, service: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.service = service
        self.message = message
        self.status = status


class IntegrationNotConfigured(IntegrationError):
    def __init__(self, service: str) -> None:
        super().__init__(
            service, f"{service}: conexão não configurada em Configurações › Conexões."
        )


class AuthenticationFailed(IntegrationError):
    """401 — token inválido, expirado ou revogado."""


class PermissionDenied(IntegrationError):
    """403 — token sem o escopo ou sem acesso ao recurso."""


class ResourceNotFound(IntegrationError):
    """404."""


class RateLimited(IntegrationError):
    """429 persistente, mesmo depois das novas tentativas."""


class BadRequest(IntegrationError):
    """400 — ex.: JQL inválida, board kanban consultado por sprints."""


class IntegrationUnavailable(IntegrationError):
    """Falha de rede, timeout ou 5xx persistente."""


class SprintsNotSupported(IntegrationError):
    """Board kanban: não tem sprints."""


def error_for_status(service: str, status: int) -> IntegrationError:
    if status == 401:
        return AuthenticationFailed(
            service, f"{service}: credenciais inválidas (e-mail ou token).", 401
        )
    if status == 403:
        return PermissionDenied(
            service, f"{service}: token sem permissão — confira os escopos.", 403
        )
    if status == 404:
        return ResourceNotFound(service, f"{service}: recurso não encontrado.", 404)
    if status == 429:
        return RateLimited(
            service, f"{service}: limite de requisições atingido, tente em instantes.", 429
        )
    if status == 400:
        return BadRequest(service, f"{service}: requisição recusada (HTTP 400).", 400)
    if status >= 500:
        return IntegrationUnavailable(
            service, f"{service}: serviço indisponível (HTTP {status}).", status
        )
    return IntegrationError(service, f"{service}: resposta inesperada (HTTP {status}).", status)
