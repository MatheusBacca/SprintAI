"""Guarda de caminho: todo caminho que chega do front passa por aqui antes de ser lido,
virar `cwd` de um processo ou ser entregue ao `code`/`wt`.

Só valem as raízes do dev (`C:\\projects` e `~\\.claude`). Symlink e junção são resolvidos
antes da comparação — uma junção dentro de `C:\\projects` apontando para `Z:\\` cai fora — e
`..` é recusado mesmo quando resolveria para dentro: caminho torto vindo do front é erro, não
algo a consertar em silêncio. A mensagem de erro não repete o caminho recebido.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from config import get_settings


class PathNotAllowed(ValueError):
    """Caminho relativo, com `..`, inexistente ou fora das raízes permitidas."""


@dataclass(frozen=True)
class Roots:
    projects: Path
    claude: Path

    def all(self) -> tuple[Path, ...]:
        return (self.projects, self.claude)


def get_roots() -> Roots:
    """Dependência do FastAPI — os testes trocam pelas raízes de uma pasta temporária."""
    settings = get_settings()
    return Roots(projects=settings.projects_root, claude=settings.claude_home)


def resolve_allowed(raw: str | Path, roots: Iterable[Path]) -> Path:
    """Caminho real (symlinks resolvidos) se ele existe e mora abaixo de uma das raízes."""
    text = str(raw)
    if not text or "\x00" in text:
        raise PathNotAllowed("Caminho vazio ou inválido.")
    # UNC (`\\servidor\pasta`) é absoluto para o pathlib, mas é rede — nunca é raiz do dev.
    if text.startswith(("\\\\", "//")):
        raise PathNotAllowed("Caminho de rede não é aceito.")
    path = Path(text)
    if not path.is_absolute():
        raise PathNotAllowed("O caminho precisa ser absoluto.")
    if ".." in path.parts:
        raise PathNotAllowed("Caminho com '..' não é aceito.")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PathNotAllowed("Caminho não encontrado.") from exc
    if is_under(resolved, roots):
        return resolved
    raise PathNotAllowed("Caminho fora das pastas permitidas.")


def is_under(resolved: Path, roots: Iterable[Path]) -> bool:
    """`resolved` já resolvido está numa das raízes (a comparação do Windows ignora caixa)."""
    for root in roots:
        try:
            real_root = root.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved == real_root or resolved.is_relative_to(real_root):
            return True
    return False
