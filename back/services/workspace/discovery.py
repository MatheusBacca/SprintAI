"""Descoberta dos repositórios locais em `C:\\projects` — só leitura e sem rodar git.

De cada pasta saem o remote `origin` (`.git/config`), a branch atual (`.git/HEAD`) e um
palpite da branch base. Rodar `git` aqui custaria um processo por pasta a cada listagem; os
três arquivos dizem o mesmo e são lidos em milissegundos.

O remote é guardado **sem credencial**: um clone por https pode ter `usuario:token@` na URL, e
o token não pode ir para o banco nem para a resposta da API.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

# `git@bitbucket.org:weonrepo/monitoria.git` ou `https://bitbucket.org/weonrepo/monitoria.git`.
BITBUCKET_REMOTE = re.compile(
    r"bitbucket\.org[:/](?P<workspace>[^/\s]+)/(?P<slug>[^/\s]+?)(?:\.git)?/?$", re.IGNORECASE
)

# Ordem do palpite quando nem o Bitbucket nem o `origin/HEAD` dizem a base: os repos de
# fluxo develop (weaction-api, supervisor-web) têm `develop` e `main`; os de fluxo main não
# costumam ter `develop`.
BASE_CANDIDATES = ("develop", "main", "master")

MAX_GIT_FILE_BYTES = 1_000_000


@dataclass(frozen=True)
class LocalRepo:
    slug: str
    path: Path
    has_git: bool
    remote_url: str | None = None
    bb_slug: str | None = None
    current_branch: str | None = None
    detached: bool = False
    base_branch: str | None = None
    base_source: str | None = None  # "origin" (origin/HEAD) | "local" (palpite)


def discover(root: Path) -> list[LocalRepo]:
    """Uma entrada por pasta de primeiro nível, em ordem alfabética.

    Pasta oculta (`.worktrees`) fica de fora, e também a que é worktree de outro repo
    (`.git` arquivo): ela aparece debaixo do repo principal, não como repo próprio.
    """
    try:
        children = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []
    repos = []
    for child in children:
        if child.name.startswith(".") or not child.is_dir():
            continue
        git = child / ".git"
        if git.is_file():
            continue
        repos.append(read_repo(child))
    return repos


def read_repo(path: Path) -> LocalRepo:
    git_dir = path / ".git"
    if not git_dir.is_dir():
        return LocalRepo(slug=path.name, path=path, has_git=False)

    remote = sanitize_remote(remote_url(_read(git_dir / "config")))
    match = BITBUCKET_REMOTE.search(remote or "")
    branch, detached = parse_head(_read(git_dir / "HEAD"))
    base, source = detect_base(git_dir)
    return LocalRepo(
        slug=path.name,
        path=path,
        has_git=True,
        remote_url=remote,
        bb_slug=match["slug"].lower() if match else None,
        current_branch=branch,
        detached=detached,
        base_branch=base,
        base_source=source,
    )


def remote_url(config_text: str | None, remote: str = "origin") -> str | None:
    """`url` da seção `[remote "origin"]` — o `.git/config` é INI, mas com aspas na seção e
    chave repetida permitida, o que o `configparser` não aceita sem ajustes."""
    if not config_text:
        return None
    header = re.compile(rf'^\[\s*remote\s+"{re.escape(remote)}"\s*\]$', re.IGNORECASE)
    inside = False
    for raw in config_text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("["):
            inside = bool(header.match(line))
            continue
        if inside:
            key, sep, value = line.partition("=")
            if sep and key.strip().lower() == "url":
                return value.strip().strip('"') or None
    return None


def sanitize_remote(url: str | None) -> str | None:
    """Tira `usuario:senha@` de URL http(s). O `git@host:caminho` do ssh fica como está —
    o `git@` é o usuário fixo do ssh, não segredo."""
    if not url:
        return None
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.IGNORECASE):
        return url
    parts = urlsplit(url)
    if parts.username is None and parts.password is None:
        return url
    host = parts.hostname or ""
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def parse_head(head_text: str | None) -> tuple[str | None, bool]:
    """(branch, destacado). HEAD com hash é destacado; sem HEAD legível, nada se afirma."""
    text = (head_text or "").strip()
    if not text:
        return None, False
    if text.startswith("ref:"):
        ref = text[4:].strip()
        if ref.startswith("refs/heads/"):
            return ref.removeprefix("refs/heads/"), False
        return None, False
    return None, True


def detect_base(git_dir: Path) -> tuple[str | None, str | None]:
    """Base pelo `origin/HEAD` (o que o clone gravou do servidor); sem ele, palpite."""
    origin_head = _read(git_dir / "refs" / "remotes" / "origin" / "HEAD")
    if origin_head and origin_head.strip().startswith("ref: refs/remotes/origin/"):
        name = origin_head.strip().removeprefix("ref: refs/remotes/origin/")
        if name:
            return name, "origin"
    packed = _read(git_dir / "packed-refs") or ""
    for name in BASE_CANDIDATES:
        if _has_ref(git_dir, packed, f"refs/heads/{name}") or _has_ref(
            git_dir, packed, f"refs/remotes/origin/{name}"
        ):
            return name, "local"
    return None, None


def _has_ref(git_dir: Path, packed: str, ref: str) -> bool:
    if (git_dir / ref).is_file():
        return True
    return any(line.endswith(f" {ref}") for line in packed.splitlines())


def _read(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_GIT_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def branch_names(git_dir: Path) -> set[str]:
    """Nomes das branches locais e do `origin`, sem rodar git: `packed-refs` + arquivos
    soltos. É o que basta para achar a chave da tarefa no nome — sem um processo por repo
    a cada abertura do Workspace."""
    names: set[str] = set()
    prefixes = ("refs/heads/", "refs/remotes/origin/")
    for line in (_read(git_dir / "packed-refs") or "").splitlines():
        if line.startswith(("#", "^")):
            continue
        _, _, ref = line.partition(" ")
        for prefix in prefixes:
            if ref.startswith(prefix):
                names.add(ref.removeprefix(prefix))
    for prefix in prefixes:
        base = git_dir / prefix
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and not path.name.endswith(".lock"):
                names.add(path.relative_to(base).as_posix())
    names.discard("HEAD")
    return names
