"""Repositórios de mentira para os testes do Workspace: só a pasta `.git` com os arquivos
que a descoberta lê, sem rodar git — e um repo git de verdade para a linha do tempo."""

import itertools
import os
import shutil
import subprocess
from pathlib import Path

import pytest

CONFIG = """[core]
\trepositoryformatversion = 0
[remote "origin"]
\turl = {url}
\tfetch = +refs/heads/*:refs/remotes/origin/*
[branch "main"]
\tremote = origin
"""


def make_repo(root: Path, name: str, *, url=None, head="ref: refs/heads/main", files=None) -> Path:
    git = root / name / ".git"
    git.mkdir(parents=True)
    if url:
        (git / "config").write_text(CONFIG.format(url=url), encoding="utf-8")
    (git / "HEAD").write_text(head + "\n", encoding="utf-8")
    for rel, content in (files or {}).items():
        target = git / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root / name


# --- Repositório git de verdade ------------------------------------------------------------
#
# A linha do tempo lê o git de verdade; o teste monta um repo pequeno numa pasta temporária
# (que vira a raiz `projects` do teste), com um "origin" bare ao lado para dar upstream.

_clock = itertools.count()


def git(cwd: Path, *args: str) -> str:
    # Datas crescentes e fixas: o `--date-order` fica determinístico.
    tick = next(_clock)
    stamp = f"2026-09-{1 + tick // 24:02d}T{tick % 24:02d}:00:00-03:00"
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": stamp,
        "GIT_COMMITTER_DATE": stamp,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    result = subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, check=True, text=True
    )
    return result.stdout.strip()


def commit(repo: Path, message: str, filename: str = "arquivo.txt") -> str:
    target = repo / filename
    previous = target.read_text(encoding="utf-8") if target.exists() else ""
    target.write_text(previous + message + "\n", encoding="utf-8")
    git(repo, "add", filename)
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def make_git_repo(root: Path, name: str = "monitoria") -> dict[str, Path | str]:
    """main com um commit à frente do origin, `WAI-100-chave` com um commit local a mais,
    `outra-coisa` sem chave, uma worktree em `WAI-200-outra` e alterações não commitadas no
    clone principal."""
    if shutil.which("git") is None:
        pytest.skip("git não está instalado")
    origin = root.parent / f"{name}-origin.git"
    git(root.parent, "init", "-q", "--bare", "-b", "main", str(origin))
    repo = root / name
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Dev")
    git(repo, "config", "user.email", "dev@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    first = commit(repo, "Primeiro commit")
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "-u", "origin", "main")

    git(repo, "checkout", "-q", "-b", "WAI-100-chave")
    feature_pushed = commit(repo, "WAI-100: aplica a chave na integração", "chave.txt")
    git(repo, "push", "-q", "-u", "origin", "WAI-100-chave")
    feature_local = commit(repo, "ajusta o consumer da fila", "chave.txt")

    git(repo, "checkout", "-q", "main")
    hotfix = commit(repo, "Hotfix na main")
    git(repo, "branch", "outra-coisa")

    worktree = root / ".worktrees" / f"{name}-WAI-200"
    git(repo, "worktree", "add", "-q", "-b", "WAI-200-outra", str(worktree), first)
    other = commit(worktree, "WAI-200 começa outra coisa", "outra.txt")

    (repo / "arquivo.txt").write_text("mexido sem commit\n", encoding="utf-8")
    (repo / "novo.txt").write_text("não rastreado\n", encoding="utf-8")
    return {
        "repo": repo,
        "worktree": worktree,
        "first": first,
        "feature_pushed": feature_pushed,
        "feature_local": feature_local,
        "hotfix": hotfix,
        "other": other,
    }
