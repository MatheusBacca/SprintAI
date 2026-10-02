import sys

import pytest

from security.paths import PathNotAllowed, resolve_allowed


@pytest.fixture
def roots(tmp_path):
    projects = tmp_path / "projects"
    (projects / "monitoria" / "src").mkdir(parents=True)
    claude = tmp_path / ".claude"
    claude.mkdir()
    return projects, claude


def test_caminho_dentro_da_raiz_volta_resolvido(roots):
    projects, claude = roots
    assert resolve_allowed(projects / "monitoria", [projects, claude]) == (
        projects / "monitoria"
    ).resolve()
    assert resolve_allowed(str(projects / "monitoria" / "src"), [projects, claude]).name == "src"


def test_a_propria_raiz_vale(roots):
    projects, claude = roots
    assert resolve_allowed(projects, [projects, claude]) == projects.resolve()


def test_caminho_fora_das_raizes_e_recusado(roots, tmp_path):
    projects, claude = roots
    outside = tmp_path / "fora"
    outside.mkdir()
    with pytest.raises(PathNotAllowed, match="fora das pastas"):
        resolve_allowed(outside, [projects, claude])


def test_ponto_ponto_e_recusado_mesmo_resolvendo_para_dentro(roots):
    projects, claude = roots
    with pytest.raises(PathNotAllowed, match=r"\.\."):
        resolve_allowed(projects / "monitoria" / ".." / "monitoria", [projects, claude])


def test_relativo_vazio_e_inexistente_sao_recusados(roots):
    projects, claude = roots
    for raw in ("monitoria", "", "x\x00y"):
        with pytest.raises(PathNotAllowed):
            resolve_allowed(raw, [projects, claude])
    with pytest.raises(PathNotAllowed, match="não encontrado"):
        resolve_allowed(projects / "nao-existe", [projects, claude])


def test_caminho_de_rede_e_recusado(roots):
    projects, claude = roots
    with pytest.raises(PathNotAllowed, match="rede"):
        resolve_allowed(r"\\servidor\projetos\monitoria", [projects, claude])


def test_mensagem_de_erro_nao_repete_o_caminho(roots):
    projects, claude = roots
    with pytest.raises(PathNotAllowed) as info:
        resolve_allowed(r"C:\segredo-do-dev\token.txt", [projects, claude])
    assert "segredo" not in str(info.value)


@pytest.mark.skipif(sys.platform != "win32", reason="junção é do NTFS")
def test_juncao_dentro_da_raiz_apontando_para_fora_e_recusada(roots, tmp_path):
    import _winapi

    projects, claude = roots
    outside = tmp_path / "fora"
    outside.mkdir()
    _winapi.CreateJunction(str(outside), str(projects / "atalho"))
    with pytest.raises(PathNotAllowed, match="fora das pastas"):
        resolve_allowed(projects / "atalho", [projects, claude])
