"""Escrita no git local — só por gesto do dev na linha do tempo do Workspace.

São três ações, e só elas. Nenhuma escreve no Bitbucket:

- **`fetch_prune`** — `git fetch origin --prune`: traz o que mudou no servidor e apaga as
  `origin/*` que já não existem lá. É o botão do cabeçalho da linha do tempo; nunca roda
  sozinho.
- **`update_branch`** — fast-forward da branch local até o upstream, nunca merge de verdade:
  aberta numa worktree, `git merge --ff-only` lá dentro; fechada, `git fetch .
  <upstream>:<branch>`, que mexe só na ref e recusa o que não for fast-forward.
- **`delete_branch`** — `git branch -d`, que recusa a branch com commit que não está em outra
  branch. O `-D` só vai na segunda confirmação da tela, e a branch base nunca se apaga daqui.

A leitura continua em `git_local.py`, com `--no-optional-locks`. Aqui não: escrita precisa do
lock. Fica o resto — `core.fsmonitor=false`, sem prompt de credencial (`GIT_TERMINAL_PROMPT=0`,
o SSH em `BatchMode`), timeout e sem janela.

O erro do git não vai cru para a tela (cita caminho e configuração local): os casos conhecidos
viram mensagem pronta, o resto vira "falhou".
"""

import asyncio
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from schemas.workspace_schemas import safe_ref_name
from services.workspace import git_local
from services.workspace.git_local import Ref, Worktree

FETCH_TIMEOUT_SECONDS = 120
ACTION_TIMEOUT_SECONDS = 30


class GitActionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# (padrão no stderr do git, código, mensagem para a tela)
_KNOWN_ERRORS = (
    (r"not fully merged", "unmerged",
     "A branch tem commits que não estão em nenhuma outra branch. Apagar assim perde esses "
     "commits (eles ainda ficam no reflog por um tempo)."),
    (r"(checked out|used by worktree)", "checked_out",
     "A branch está aberta numa worktree — troque de branch lá antes."),
    (r"(non-fast-forward|Not possible to fast-forward|not possible to fast-forward|rejected)",
     "diverged",
     "A branch local tem commits que o upstream não tem: não dá para só avançar. Resolva no "
     "terminal (rebase ou merge)."),
    (r"(would be overwritten|Your local changes)", "dirty",
     "Há alterações não commitadas que o avanço sobrescreveria. Commite ou guarde (stash) antes."),
    (r"(Permission denied|Could not read from remote|Authentication failed|Host key verification)",
     "auth",
     "O Bitbucket recusou o acesso — confira a chave SSH no terminal (o `git fetch` lá "
     "mostra o erro)."),
    (r"(Could not resolve host|Connection timed out|Network is unreachable|unable to access)",
     "network",
     "Sem conexão com o Bitbucket agora."),
)


def _classify(stderr: str) -> GitActionError:
    for pattern, code, message in _KNOWN_ERRORS:
        if re.search(pattern, stderr, re.IGNORECASE):
            return GitActionError(code, message)
    return GitActionError("failed", "O git recusou a operação.")


def _env(ssh_command: str | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GIT_PAGER": "cat"})
    if ssh_command:
        env["GIT_SSH_COMMAND"] = ssh_command
    return env


def _ssh_command(cwd: Path) -> str:
    """O ssh que o git já usaria (o `core.sshCommand` do dev, ou o `ssh`), em `BatchMode`: chave
    com senha e sem agente falha na hora, em vez de abrir um pedido de senha que ninguém vê —
    a API roda sem janela."""
    try:
        configured = _run(cwd, "config", "--get", "core.sshCommand", timeout=5).strip()
    except GitActionError:
        configured = ""
    return f"{configured or os.environ.get('GIT_SSH_COMMAND') or 'ssh'} -o BatchMode=yes"


def _run(cwd: Path, *args: str, timeout: float, ssh_command: str | None = None) -> str:
    command = ["git", "--no-pager", "-c", "core.fsmonitor=false", "-C", str(cwd), *args]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            env=_env(ssh_command),
            creationflags=git_local._CREATE_NO_WINDOW,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitActionError("unavailable", "git não encontrado no PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitActionError(
            "timeout", f"O git passou de {timeout:.0f}s e foi interrompido."
        ) from exc
    if result.returncode != 0:
        raise _classify(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout.decode("utf-8", errors="replace")


async def _git(cwd: Path, *args: str, seconds: float = ACTION_TIMEOUT_SECONDS) -> str:
    return await asyncio.to_thread(_run, cwd, *args, timeout=seconds)


async def _git_remote(cwd: Path, *args: str, seconds: float) -> str:
    """Git que fala com o servidor (o `fetch`): com o ssh em `BatchMode`."""
    ssh = await asyncio.to_thread(_ssh_command, cwd)
    return await asyncio.to_thread(_run, cwd, *args, timeout=seconds, ssh_command=ssh)


# --- fetch --prune ------------------------------------------------------------------------


@dataclass
class FetchResult:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def _remote_targets(refs: list[Ref]) -> dict[str, str]:
    return {r.name: r.target for r in refs if r.kind == "remote" and r.name.startswith("origin/")}


async def fetch_prune(repo_path: Path) -> FetchResult:
    before = await git_local.list_refs(repo_path)
    await _git_remote(repo_path, "fetch", "origin", "--prune", seconds=FETCH_TIMEOUT_SECONDS)
    after = await git_local.list_refs(repo_path)

    old, new = _remote_targets(before), _remote_targets(after)
    old_tags = {r.name for r in before if r.kind == "tag"}
    return FetchResult(
        added=sorted(set(new) - set(old)),
        updated=sorted(name for name in set(new) & set(old) if new[name] != old[name]),
        pruned=sorted(set(old) - set(new)),
        tags=sorted({r.name for r in after if r.kind == "tag"} - old_tags),
    )


# --- Avançar a branch ---------------------------------------------------------------------


@dataclass
class UpdateResult:
    name: str
    before: str
    after: str
    # "worktree": merge --ff-only na worktree que está com ela · "ref": só a ref andou.
    mode: str


def _local(refs: list[Ref], name: str) -> Ref:
    ref = next((r for r in refs if r.kind == "local" and r.name == name), None)
    if ref is None:
        raise GitActionError("not_found", "Branch local não encontrada.")
    return ref


def _upstream_full(refs: list[Ref], upstream: str) -> str | None:
    for ref in refs:
        if ref.name == upstream and ref.kind in ("remote", "local"):
            return ref.full
    return None


async def update_branch(
    repo_path: Path, name: str, *, worktree_allowed
) -> UpdateResult:
    """`worktree_allowed(path) -> Path | None`: a worktree só é usada se a guarda de caminho
    deixar — uma worktree na pasta temp do Claude não vira `cwd` de git daqui."""
    safe_ref_name(name)
    refs = await git_local.list_refs(repo_path)
    ref = _local(refs, name)
    if not ref.upstream or ref.gone:
        raise GitActionError(
            "no_upstream", "A branch não tem upstream (ou ele foi apagado no Bitbucket)."
        )
    upstream = _upstream_full(refs, ref.upstream)
    if upstream is None:
        raise GitActionError("no_upstream", "O upstream da branch não está nas refs locais.")
    if ref.behind == 0:
        return UpdateResult(name=name, before=ref.target, after=ref.target, mode="noop")

    if ref.worktree:
        folder = worktree_allowed(ref.worktree)
        if folder is None:
            raise GitActionError(
                "outside", "A branch está aberta numa worktree fora de C:\\projects."
            )
        await _git(folder, "merge", "--ff-only", upstream)
        mode = "worktree"
    else:
        await _git(repo_path, "fetch", ".", f"{upstream}:refs/heads/{name}")
        mode = "ref"
    after = _local(await git_local.list_refs(repo_path), name).target
    return UpdateResult(name=name, before=ref.target, after=after, mode=mode)


# --- Apagar branch local ------------------------------------------------------------------


async def delete_branch(
    repo_path: Path, name: str, *, force: bool, base_branch: str | None, worktrees: list[Worktree]
) -> str:
    """Apaga a branch local e devolve o hash para onde ela apontava (para desfazer no
    terminal: `git branch <nome> <hash>`)."""
    safe_ref_name(name)
    if base_branch and name == base_branch:
        raise GitActionError("protected", "A branch base do repositório não se apaga por aqui.")
    refs = await git_local.list_refs(repo_path)
    ref = _local(refs, name)
    if ref.worktree or any(w.branch == name for w in worktrees):
        raise GitActionError(
            "checked_out", "A branch está aberta numa worktree — troque de branch lá antes."
        )
    await _git(repo_path, "branch", "-D" if force else "-d", name)
    return ref.target
