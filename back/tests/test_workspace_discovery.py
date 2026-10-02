from services.workspace.discovery import (
    branch_names,
    discover,
    parse_head,
    remote_url,
    sanitize_remote,
)
from tests.workspace_fakes import make_repo


def test_casa_o_remote_do_bitbucket_e_le_a_branch_atual(tmp_path):
    make_repo(
        tmp_path,
        "monitoria",
        url="git@bitbucket.org:weonrepo/monitoria.git",
        head="ref: refs/heads/WAI-8790-rota-unica",
        files={"refs/remotes/origin/HEAD": "ref: refs/remotes/origin/main\n"},
    )
    [repo] = discover(tmp_path)
    assert repo.slug == "monitoria"
    assert repo.has_git
    assert repo.bb_slug == "monitoria"
    assert repo.current_branch == "WAI-8790-rota-unica"
    assert not repo.detached
    assert (repo.base_branch, repo.base_source) == ("main", "origin")


def test_remote_https_perde_a_credencial(tmp_path):
    make_repo(
        tmp_path,
        "api-credits",
        url="https://dev:tok3n-secreto@bitbucket.org/weonrepo/api-credits.git",
    )
    [repo] = discover(tmp_path)
    assert repo.remote_url == "https://bitbucket.org/weonrepo/api-credits.git"
    assert "tok3n" not in repo.remote_url
    assert repo.bb_slug == "api-credits"


def test_github_e_pasta_sem_git_ficam_sem_vinculo(tmp_path):
    make_repo(tmp_path, "appingos", url="https://github.com/MatheusBacca/APPingos.git")
    (tmp_path / "mcp").mkdir()
    repos = {r.slug: r for r in discover(tmp_path)}
    assert repos["appingos"].bb_slug is None
    assert repos["appingos"].has_git
    assert repos["mcp"].has_git is False
    assert repos["mcp"].bb_slug is None


def test_pasta_oculta_e_worktree_de_outro_repo_ficam_de_fora(tmp_path):
    make_repo(tmp_path, "weaction-api", url="git@bitbucket.org:weonrepo/weaction-api.git")
    (tmp_path / ".worktrees" / "weaction-api-WAI-8857").mkdir(parents=True)
    worktree = tmp_path / "solta"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: C:/projects/weaction-api/.git/worktrees/solta\n")
    (tmp_path / "arquivo.txt").write_text("x")
    assert [r.slug for r in discover(tmp_path)] == ["weaction-api"]


def test_base_pelo_palpite_quando_nao_ha_origin_head(tmp_path):
    make_repo(
        tmp_path,
        "supervisor-web",
        url="git@bitbucket.org:weonrepo/supervisor-web.git",
        files={"packed-refs": "# pack-refs\nabc123 refs/remotes/origin/develop\n"},
    )
    make_repo(
        tmp_path,
        "qualificai",
        url="git@bitbucket.org:weonrepo/qualificai.git",
        files={"refs/heads/main": "abc\n"},
    )
    repos = {r.slug: r for r in discover(tmp_path)}
    assert (repos["supervisor-web"].base_branch, repos["supervisor-web"].base_source) == (
        "develop",
        "local",
    )
    assert repos["qualificai"].base_branch == "main"


def test_head_destacado_e_head_ilegivel():
    assert parse_head("451df6f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6\n") == (None, True)
    assert parse_head(None) == (None, False)
    assert parse_head("ref: refs/heads/feature/WAI-8792") == ("feature/WAI-8792", False)


def test_remote_le_so_a_secao_do_origin():
    text = '[remote "upstream"]\n\turl = git@x:a/b.git\n[remote "origin"]\n\turl = "git@y:c/d.git"\n'
    assert remote_url(text) == "git@y:c/d.git"
    assert remote_url("[core]\n\tbare = false\n") is None
    assert sanitize_remote("git@bitbucket.org:weonrepo/x.git") == "git@bitbucket.org:weonrepo/x.git"


def test_nomes_de_branch_do_packed_refs_e_dos_arquivos_soltos(tmp_path):
    repo = make_repo(
        tmp_path,
        "weaction-api",
        files={
            "packed-refs": (
                "# pack-refs with: peeled fully-peeled sorted\n"
                "abc refs/heads/develop\n"
                "def refs/remotes/origin/feature/WAI-8792\n"
                "^123\n"
                "fed refs/tags/v1.0\n"
            ),
            "refs/heads/ajuste/WAI-8857": "abc\n",
            "refs/remotes/origin/HEAD": "ref: refs/remotes/origin/develop\n",
            "refs/remotes/upstream/outra": "abc\n",
        },
    )
    assert branch_names(repo / ".git") == {"develop", "feature/WAI-8792", "ajuste/WAI-8857"}
