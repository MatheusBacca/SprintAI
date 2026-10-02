"""Git local só leitura — a única porta do SprintAI para o executável `git` (B15).

Tudo passa por `run_git`, que só aceita os subcomandos de leitura da lista branca e sempre
roda com:

- `--no-optional-locks` (+ `GIT_OPTIONAL_LOCKS=0`): o `git status` normal pega o
  `index.lock` para atualizar o cache de stat, e brigaria com o git que o dev roda no
  terminal ao mesmo tempo;
- `core.fsmonitor=false`: o `fsmonitor` do `.git/config` é um comando que o `status`
  executaria — leitura não pode virar execução;
- `--no-ext-diff --no-textconv` no `show`, pelo mesmo motivo;
- `GIT_TERMINAL_PROMPT=0`, timeout e sem janela (`CREATE_NO_WINDOW`).

Argumento que vem do front (hash, nome de ref) chega aqui já validado; mesmo assim, nada
que comece com `-` passa, e as revisões vão antes do `--`.

Roda por `subprocess.run` numa thread: com `reload=True` o uvicorn usa o
`SelectorEventLoop` no Windows, onde `asyncio.create_subprocess_exec` não funciona.
"""

import asyncio
import hashlib
import heapq
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ALLOWED_SUBCOMMANDS = frozenset({"for-each-ref", "log", "show", "status", "worktree"})
GIT_TIMEOUT_SECONDS = 10
SHA_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


class GitError(Exception):
    """O git não rodou ou devolveu erro. A mensagem é genérica — o stderr do git cita
    caminhos e configuração local, e não precisa ir para a tela."""


class GitUnavailable(GitError):
    """Executável `git` não encontrado no PATH."""


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_PAGER": "cat",
            "GCM_INTERACTIVE": "never",
        }
    )
    return env


def run_git(repo_path: Path, *args: str, timeout: float = GIT_TIMEOUT_SECONDS) -> str:
    if not args or args[0] not in ALLOWED_SUBCOMMANDS:
        raise GitError("Subcomando do git fora da lista de leitura.")
    command = [
        "git",
        "--no-pager",
        "--no-optional-locks",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.quotepath=off",
        "-c",
        "color.ui=never",
        "-C",
        str(repo_path),
        *args,
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            env=_env(),
            creationflags=_CREATE_NO_WINDOW,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitUnavailable("git não encontrado no PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {args[0]} passou de {timeout:.0f}s.") from exc
    if result.returncode != 0:
        raise GitError(f"git {args[0]} falhou (código {result.returncode}).")
    return result.stdout.decode("utf-8", errors="replace")


async def git(repo_path: Path, *args: str) -> str:
    return await asyncio.to_thread(run_git, repo_path, *args)


# --- Refs -----------------------------------------------------------------------------------

REF_FORMAT = (
    "%(refname)%00%(objectname)%00%(*objectname)%00%(upstream:short)%00"
    "%(upstream:track,nobracket)%00%(worktreepath)%00%(committerdate:iso-strict)%00"
    "%(contents:subject)"
)
REF_NAMESPACES = ("refs/heads", "refs/remotes", "refs/tags")


@dataclass(frozen=True)
class Ref:
    full: str
    name: str
    kind: str  # local | remote | tag
    target: str
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    gone: bool = False
    worktree: str | None = None
    committed_at: datetime | None = None
    # Assunto do commit (ou da tag anotada) para onde a ref aponta.
    subject: str | None = None


def parse_refs(output: str) -> list[Ref]:
    refs = []
    for line in output.splitlines():
        parts = line.split("\0")
        if len(parts) < 7:
            continue
        full, obj, peeled, upstream, track, worktree, date = parts[:7]
        subject = parts[7] if len(parts) > 7 else ""
        if full.startswith("refs/heads/"):
            kind, name = "local", full.removeprefix("refs/heads/")
        elif full.startswith("refs/remotes/"):
            name = full.removeprefix("refs/remotes/")
            # `origin/HEAD` é um apelido da branch principal, não uma branch.
            if name.endswith("/HEAD"):
                continue
            kind = "remote"
        elif full.startswith("refs/tags/"):
            kind, name = "tag", full.removeprefix("refs/tags/")
        else:
            continue
        ahead, behind, gone = parse_track(track)
        refs.append(
            Ref(
                full=full,
                name=name,
                kind=kind,
                target=peeled or obj,
                upstream=upstream or None,
                ahead=ahead,
                behind=behind,
                gone=gone,
                worktree=_normalize_path(worktree) if worktree else None,
                committed_at=_parse_date(date),
                subject=subject or None,
            )
        )
    return refs


def parse_track(track: str) -> tuple[int, int, bool]:
    """`ahead 2, behind 1` · `gone` (upstream apagado no remoto) · vazio (em dia)."""
    if track.strip() == "gone":
        return 0, 0, True
    ahead = re.search(r"ahead (\d+)", track)
    behind = re.search(r"behind (\d+)", track)
    return int(ahead[1]) if ahead else 0, int(behind[1]) if behind else 0, False


async def list_refs(repo_path: Path) -> list[Ref]:
    output = await git(repo_path, "for-each-ref", f"--format={REF_FORMAT}", *REF_NAMESPACES)
    return parse_refs(output)


# --- Worktrees ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Worktree:
    path: str
    head: str | None
    branch: str | None
    detached: bool = False
    bare: bool = False
    locked: bool = False
    prunable: bool = False


def parse_worktrees(output: str) -> list[Worktree]:
    """`git worktree list --porcelain -z`: campos terminados em NUL, registros separados por
    um campo vazio. O primeiro registro é sempre o clone principal."""
    worktrees = []
    record: dict[str, str] = {}

    def flush() -> None:
        if "worktree" in record:
            branch = record.get("branch")
            worktrees.append(
                Worktree(
                    path=_normalize_path(record["worktree"]),
                    head=record.get("HEAD"),
                    branch=branch.removeprefix("refs/heads/") if branch else None,
                    detached="detached" in record,
                    bare="bare" in record,
                    locked="locked" in record,
                    prunable="prunable" in record,
                )
            )
        record.clear()

    for item in output.split("\0"):
        if not item:
            flush()
            continue
        key, _, value = item.partition(" ")
        record[key] = value
    flush()
    return worktrees


async def list_worktrees(repo_path: Path) -> list[Worktree]:
    return parse_worktrees(await git(repo_path, "worktree", "list", "--porcelain", "-z"))


# --- Alterações não commitadas --------------------------------------------------------------


@dataclass(frozen=True)
class Changes:
    changed: int = 0
    untracked: int = 0
    conflicted: int = 0
    upstream: str | None = None
    ahead: int | None = None
    behind: int | None = None


def parse_status(output: str) -> Changes:
    """`git status --porcelain=v2 --branch -z`. Renomeação (`2 `) traz um campo a mais — o
    caminho de origem —, que não é uma entrada própria."""
    changed = untracked = conflicted = 0
    upstream = None
    ahead = behind = None
    items = output.split("\0")
    skip_next = False
    for item in items:
        if skip_next:
            skip_next = False
            continue
        if item.startswith("# branch.upstream "):
            upstream = item.removeprefix("# branch.upstream ")
        elif item.startswith("# branch.ab "):
            match = re.match(r"# branch\.ab \+(\d+) -(\d+)", item)
            if match:
                ahead, behind = int(match[1]), int(match[2])
        elif item.startswith("1 "):
            changed += 1
        elif item.startswith("2 "):
            changed += 1
            skip_next = True
        elif item.startswith("u "):
            conflicted += 1
        elif item.startswith("? "):
            untracked += 1
    return Changes(
        changed=changed,
        untracked=untracked,
        conflicted=conflicted,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
    )


async def worktree_changes(worktree_path: Path) -> Changes:
    return parse_status(await git(worktree_path, "status", "--porcelain=v2", "--branch", "-z"))


# --- Log (o grafo) --------------------------------------------------------------------------

# O `%m` no fim é a marca do `--boundary`: `-` no commit de fronteira (o ponto da base de onde
# a feature saiu), `>` no resto.
LOG_FORMAT = "%H%x1f%P%x1f%an%x1f%aI%x1f%cI%x1f%s%x1f%m%x1e"


@dataclass(frozen=True)
class Commit:
    sha: str
    parents: tuple[str, ...]
    author: str
    authored_at: datetime | None
    committed_at: datetime | None
    subject: str
    # Commit de fronteira: não é da feature, é o ponto da base em que ela se apoia.
    boundary: bool = False


def parse_log(output: str) -> list[Commit]:
    commits = []
    for record in output.split("\x1e"):
        record = record.lstrip("\r\n")
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) < 6:
            continue
        sha, parents, author, authored, committed, subject = parts[:6]
        commits.append(
            Commit(
                sha=sha,
                parents=tuple(parents.split()),
                author=author,
                authored_at=_parse_date(authored),
                committed_at=_parse_date(committed),
                subject=subject,
                boundary=len(parts) > 6 and parts[6].strip() == "-",
            )
        )
    return commits


async def log(repo_path: Path, revisions: list[str], *, skip: int, limit: int) -> list[Commit]:
    """Commits alcançáveis das revisões, do mais novo para o mais antigo, sem quebrar a
    regra de nunca mostrar o pai antes do filho (`--date-order`)."""
    for rev in revisions:
        if rev.startswith("-") and rev not in ("--branches", "--remotes", "--tags"):
            raise GitError("Revisão inválida.")
    if not revisions:
        return []
    output = await git(
        repo_path,
        "log",
        "--date-order",
        f"--format={LOG_FORMAT}",
        f"--max-count={limit}",
        f"--skip={skip}",
        *revisions,
        "--",
    )
    return parse_log(output)


# --- Só da feature ---------------------------------------------------------------------------


async def feature_history(
    repo_path: Path, feature_refs: list[str], base_refs: list[str], *, limit: int
) -> list[Commit]:
    """O que as branches da feature carregam, desde a base — e não o histórico inteiro.

    Para cada branch da feature:

    - **ainda não entrou na base:** os commits que só ela tem (`<branch> ^<base>`) e o commit
      de fronteira, que é o ponto da base de onde ela saiu (ou o último merge da base nela);
    - **já entrou por merge:** o merge que a levou para a base e os commits que ela trouxe
      (`<branch> ^<primeiro pai do merge>`), com a base daquele momento como fronteira;
    - **nasceu agora (ou entrou por fast-forward):** só o commit em que ela está.

    O resultado volta numa ordem só, filho antes de pai, do mais novo para o mais antigo.
    """
    for rev in (*feature_refs, *base_refs):
        if rev.startswith("-"):
            raise GitError("Revisão inválida.")
    negatives = [f"^{ref}" for ref in base_refs]
    found: dict[str, Commit] = {}

    def add(commits: list[Commit]) -> None:
        for commit in commits:
            known = found.get(commit.sha)
            # O mesmo commit pode vir como fronteira de uma branch e próprio de outra: vale o
            # "próprio", que desenha os pais.
            if known is None or (known.boundary and not commit.boundary):
                found[commit.sha] = commit

    common = ["--boundary", "--date-order", f"--format={LOG_FORMAT}", f"--max-count={limit}"]
    for ref in dict.fromkeys(feature_refs):
        own = parse_log(await git(repo_path, "log", *common, ref, *negatives, "--"))
        if any(not c.boundary for c in own):
            add(own)
            continue
        merge = await _merge_into_base(repo_path, ref, base_refs)
        if merge is not None:
            add([merge])
            add(parse_log(await git(repo_path, "log", *common, ref, f"^{merge.parents[0]}", "--")))
            # A base de antes do merge: é nela que a linha do merge pousa.
            add(await _as_boundary(repo_path, merge.parents[0]))
            continue
        add(await _as_boundary(repo_path, ref))
    return _topological(list(found.values()))[:limit]


async def commits_mentioning(repo_path: Path, keys: list[str], *, limit: int) -> list[Commit]:
    """A feature cuja branch já foi apagada (o normal depois do merge pelo Bitbucket): os
    commits que citam a chave na mensagem — `feat(WAI-8790): …`, "Merged in WAI-8790-…" — em
    qualquer branch, remota ou tag, mais o ponto da base de onde eles partem."""
    for key in keys:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{1,9}-\d{1,7}", key):
            raise GitError("Chave inválida.")
    if not keys:
        return []
    output = await git(
        repo_path,
        "log",
        "--date-order",
        f"--format={LOG_FORMAT}",
        f"--max-count={limit}",
        "-i",
        "-F",
        *(f"--grep={key}" for key in keys),
        *SEARCH_REVISIONS,
        "--",
    )
    commits = parse_log(output)
    return _topological(commits + await _missing_parents(repo_path, commits))


async def _missing_parents(repo_path: Path, commits: list[Commit]) -> list[Commit]:
    """Os pais que ficaram de fora, como fronteira: é neles que as linhas pousam."""
    known = {c.sha for c in commits}
    missing = sorted({p for c in commits if not c.boundary for p in c.parents} - known)
    if not missing:
        return []
    output = await git(repo_path, "log", "--no-walk", f"--format={LOG_FORMAT}", *missing, "--")
    return [Commit(**{**vars(c), "boundary": True}) for c in parse_log(output)]


async def _as_boundary(repo_path: Path, rev: str) -> list[Commit]:
    output = await git(repo_path, "log", "-1", f"--format={LOG_FORMAT}", rev, "--")
    return [Commit(**{**vars(c), "boundary": True}) for c in parse_log(output)]


async def _merge_into_base(repo_path: Path, ref: str, base_refs: list[str]) -> Commit | None:
    """O merge que levou a branch para a base: o mais antigo no caminho dela até a base. Os
    merges do Bitbucket ("Merged in …") têm a base como primeiro pai."""
    for base in base_refs:
        output = await git(
            repo_path,
            "log",
            "--ancestry-path",
            "--merges",
            f"--format={LOG_FORMAT}",
            f"{ref}..{base}",
            "--",
        )
        merges = parse_log(output)
        if merges:
            return merges[-1]
    return None


def _topological(commits: list[Commit]) -> list[Commit]:
    """Filho antes de pai e, entre os prontos, o mais novo primeiro — a mesma regra do
    `--date-order`, para juntar o que veio de vários `git log`."""
    by_sha = {c.sha: c for c in commits}
    children = {sha: 0 for sha in by_sha}
    for commit in commits:
        if commit.boundary:
            continue
        for parent in commit.parents:
            if parent in children:
                children[parent] += 1

    def key(commit: Commit) -> tuple[float, str]:
        return (-(commit.committed_at.timestamp() if commit.committed_at else 0), commit.sha)

    ready = [(key(c), c.sha) for c in commits if children[c.sha] == 0]
    heapq.heapify(ready)
    ordered: list[Commit] = []
    while ready:
        _, sha = heapq.heappop(ready)
        commit = by_sha[sha]
        ordered.append(commit)
        if commit.boundary:
            continue
        for parent in commit.parents:
            if parent in children:
                children[parent] -= 1
                if children[parent] == 0:
                    heapq.heappush(ready, (key(by_sha[parent]), parent))
    return ordered


# --- Busca -----------------------------------------------------------------------------------

SEARCH_REVISIONS = ["--branches", "--remotes", "--tags"]


async def search(repo_path: Path, text: str, *, limit: int) -> list[Commit]:
    """Commits de qualquer branch, remota ou tag cuja mensagem ou autor contém o texto (sem
    caixa, texto literal — `-F`, nada de regex vindo da tela), mais o commit cujo hash começa
    com ele. O resultado vem do mais novo para o mais antigo."""
    common = ["--date-order", f"--format={LOG_FORMAT}", f"--max-count={limit}", "-i", "-F"]
    by_message, by_author = await asyncio.gather(
        git(repo_path, "log", *common, f"--grep={text}", *SEARCH_REVISIONS, "--"),
        git(repo_path, "log", *common, f"--author={text}", *SEARCH_REVISIONS, "--"),
    )
    found: dict[str, Commit] = {}
    for commit in parse_log(by_message) + parse_log(by_author):
        found.setdefault(commit.sha, commit)
    if re.fullmatch(r"[0-9a-fA-F]{4,40}", text):
        try:
            output = await git(repo_path, "log", "-1", f"--format={LOG_FORMAT}", text.lower(), "--")
            for commit in parse_log(output):
                found.setdefault(commit.sha, commit)
        except GitError:
            pass  # não é o começo de hash nenhum
    ordered = sorted(
        found.values(),
        key=lambda c: c.committed_at.timestamp() if c.committed_at else 0,
        reverse=True,
    )
    return ordered[:limit]


# --- Detalhe do commit ----------------------------------------------------------------------

SHOW_FORMAT = "%H%x1f%P%x1f%an%x1f%aI%x1f%cn%x1f%cI%x1f%B%x1e"
MAX_FILES = 300


@dataclass(frozen=True)
class CommitFile:
    path: str
    added: int | None
    deleted: int | None


@dataclass(frozen=True)
class CommitDetail:
    sha: str
    parents: tuple[str, ...]
    author: str
    authored_at: datetime | None
    committer: str
    committed_at: datetime | None
    message: str
    files: list[CommitFile] = field(default_factory=list)
    files_truncated: bool = False


def parse_show(output: str) -> CommitDetail:
    header, _, numstat = output.partition("\x1e")
    parts = header.split("\x1f")
    if len(parts) < 7:
        raise GitError("Saída inesperada do git show.")
    sha, parents, author, authored, committer, committed, message = parts[:7]
    files = []
    truncated = False
    for line in numstat.splitlines():
        if not line.strip():
            continue
        added, _, rest = line.partition("\t")
        deleted, _, path = rest.partition("\t")
        if len(files) >= MAX_FILES:
            truncated = True
            break
        files.append(
            CommitFile(
                path=path,
                added=int(added) if added.isdigit() else None,
                deleted=int(deleted) if deleted.isdigit() else None,
            )
        )
    return CommitDetail(
        sha=sha,
        parents=tuple(parents.split()),
        author=author,
        authored_at=_parse_date(authored),
        committer=committer,
        committed_at=_parse_date(committed),
        message=message.strip(),
        files=files,
        files_truncated=truncated,
    )


async def show(repo_path: Path, sha: str) -> CommitDetail:
    if not SHA_PATTERN.match(sha):
        raise GitError("Hash de commit inválido.")
    output = await git(
        repo_path,
        "show",
        "--no-ext-diff",
        "--no-textconv",
        "--diff-merges=first-parent",
        "--numstat",
        f"--format={SHOW_FORMAT}",
        sha,
        "--",
    )
    return parse_show(output)


# --- Impressão digital ----------------------------------------------------------------------

_FINGERPRINT_FILES = ("HEAD", "index", "packed-refs", "FETCH_HEAD", "ORIG_HEAD", "logs/HEAD")


def fingerprint(git_dir: Path) -> str:
    """Muda quando qualquer ref, HEAD ou index muda — de qualquer worktree. Só `stat`: é o que
    a tela consulta a cada poucos segundos para saber se precisa rodar o git de novo.

    Alteração no arquivo de trabalho não passa por `.git` e não muda a impressão; por isso
    o "não commitado" tem a sua própria validade curta (ver `graph_service`).
    """
    entries: list[str] = []

    def add(path: Path) -> None:
        try:
            st = path.stat()
        except OSError:
            return
        entries.append(f"{path.relative_to(git_dir).as_posix()}:{st.st_mtime_ns}:{st.st_size}")

    for name in _FINGERPRINT_FILES:
        add(git_dir / name)
    refs = git_dir / "refs"
    if refs.is_dir():
        for path in sorted(refs.rglob("*")):
            if path.is_file():
                add(path)
    worktrees = git_dir / "worktrees"
    if worktrees.is_dir():
        for wt in sorted(worktrees.iterdir()):
            for name in ("HEAD", "index", "logs/HEAD"):
                add(wt / name)
    return hashlib.blake2b("\n".join(entries).encode(), digest_size=10).hexdigest()


def fetched_at(git_dir: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp((git_dir / "FETCH_HEAD").stat().st_mtime).astimezone()
    except OSError:
        return None


# --- Utilidades -----------------------------------------------------------------------------


def _parse_date(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _normalize_path(raw: str) -> str:
    """O git escreve `C:/projects/x`; a tela e a guarda de caminho falam `C:\\projects\\x`."""
    return str(Path(raw))
