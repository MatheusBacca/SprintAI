"""B17 — terminal host: sessões, saída numerada, reconexão e guarda."""

import asyncio
import queue
import sys

import pytest
from httpx import ASGITransport, AsyncClient

from terminal.backend import WinPtyBackend
from terminal.profiles import powershell
from terminal.sessions import Session


class FakeHandle:
    """Um shell de mentira: devolve como saída o que recebe."""

    def __init__(self) -> None:
        self.pid = 4242
        self.out: queue.Queue[str] = queue.Queue()
        self.written: list[str] = []
        self.size: tuple[int, int] | None = None
        self.killed = False
        self._alive = True

    def read(self) -> str:
        return self.out.get()

    def write(self, data: str) -> None:
        self.written.append(data)
        self.out.put(f"eco:{data}")

    def resize(self, cols: int, rows: int) -> None:
        self.size = (cols, rows)

    def alive(self) -> bool:
        return self._alive

    def exit_code(self) -> int | None:
        return None if self._alive else 0

    def kill(self) -> None:
        self.killed = True
        self.finish()

    def finish(self) -> None:
        self._alive = False
        self.out.put("")


class FakeBackend:
    def __init__(self) -> None:
        self.spawned: list[dict] = []
        self.handles: list[FakeHandle] = []

    def spawn(self, argv, *, cwd, env, cols, rows):
        handle = FakeHandle()
        self.spawned.append({"argv": argv, "cwd": cwd, "env": env, "cols": cols, "rows": rows})
        self.handles.append(handle)
        return handle


@pytest.fixture
def projects(tmp_path):
    root = tmp_path / "projects"
    (root / "monitoria").mkdir(parents=True)
    return root


@pytest.fixture
def backend():
    return FakeBackend()


@pytest.fixture
def app(backend, projects):
    from terminal.app import create_app

    return create_app(backend=backend, projects_root=projects)


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1:8766",
        headers={"X-SprintAI": "1"},
    ) as ac:
        yield ac


async def until(condition, seconds=3.0):
    end = asyncio.get_running_loop().time() + seconds
    while not condition():
        if asyncio.get_running_loop().time() > end:
            raise AssertionError("condição não chegou a tempo")
        await asyncio.sleep(0.01)


async def _open(client, projects, **extra):
    response = await client.post(
        "/api/terminal/sessions", json={"cwd": str(projects / "monitoria"), **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_abre_o_powershell_na_pasta_com_o_ambiente_limpo(
    client, backend, projects, monkeypatch
):
    monkeypatch.setenv("DB_PASSWORD", "senha-do-banco")
    session = await _open(client, projects, cols=100, rows=40)

    assert session["profile"] == "powershell"
    assert session["label"] == "monitoria"
    assert session["alive"] is True
    [spawned] = backend.spawned
    assert spawned["argv"][0].lower().endswith("powershell.exe")
    assert spawned["argv"][1:] == ["-NoLogo"]
    assert spawned["cwd"] == str((projects / "monitoria").resolve())
    assert (spawned["cols"], spawned["rows"]) == (100, 40)
    assert "DB_PASSWORD" not in spawned["env"]

    listed = (await client.get("/api/terminal/sessions")).json()
    assert [s["id"] for s in listed] == [session["id"]]


async def test_pasta_fora_de_projects_perfil_desconhecido_e_comando_sao_recusados(
    client, projects, tmp_path
):
    fora = tmp_path / "fora"
    fora.mkdir()
    cases = [
        {"cwd": str(fora)},
        {"cwd": str(projects / "nao-existe")},
        {"cwd": str(projects / "monitoria" / ".." / "monitoria")},
        {"cwd": str(projects / "monitoria"), "profile": "cmd"},
    ]
    for payload in cases:
        response = await client.post("/api/terminal/sessions", json=payload)
        assert response.status_code == 422, payload
    # Não existe campo de comando: o que vier a mais é ignorado e o perfil continua o fixo.
    response = await client.post(
        "/api/terminal/sessions",
        json={"cwd": str(projects / "monitoria"), "command": "rm -rf C:\\"},
    )
    assert response.status_code == 201
    assert response.json()["profile"] == "powershell"


async def test_entrada_vira_saida_numerada_e_redimensiona(client, app, backend, projects):
    session = await _open(client, projects)
    manager = app.state.manager

    for text in ("dir\r", "git status\r"):
        response = await client.post(
            f"/api/terminal/sessions/{session['id']}/input", json={"data": text}
        )
        assert response.status_code == 204
    await until(lambda: manager.get(session["id"]).offset == len("eco:dir\reco:git status\r"))
    assert backend.handles[0].written == ["dir\r", "git status\r"]

    response = await client.post(
        f"/api/terminal/sessions/{session['id']}/resize", json={"cols": 90, "rows": 20}
    )
    assert response.status_code == 204
    assert backend.handles[0].size == (90, 20)


async def test_reconexao_recebe_so_o_que_falta_ou_o_buffer_inteiro(client, app, projects):
    session = await _open(client, projects)
    manager = app.state.manager
    sid = session["id"]
    await manager.write(sid, "abc")
    await until(lambda: manager.get(sid).offset == 7)

    hello, reset = manager.catch_up({})
    assert hello["type"] == "hello"
    assert [s["id"] for s in hello["sessions"]] == [sid]
    assert reset == {"type": "reset", "s": sid, "o": 0, "d": "eco:abc"}

    assert manager.catch_up({sid: 7})[1:] == []
    assert manager.catch_up({sid: 4})[1:] == [{"type": "out", "s": sid, "o": 4, "d": "abc"}]


def test_buffer_circular_esquece_o_comeco_e_pede_reset():
    session = Session(
        id="a" * 16,
        profile=powershell(),
        label="x",
        cwd="C:\\x",
        cols=80,
        rows=24,
        created_at=None,
        handle=None,
        buffer_chars=10,
    )
    for chunk in ("0123", "4567", "89ab", "cdef"):
        session.append(chunk)
    assert session.offset == 16
    assert session.buffer_start >= 6
    reset, offset, text = session.since(2)
    assert reset is True
    assert offset == session.buffer_start
    assert text == "0123456789abcdef"[session.buffer_start :]
    assert session.since(14) == (False, 14, "ef")


async def test_stream_ao_vivo_e_cliente_lento_volta_pelo_since(client, app, projects):
    session = await _open(client, projects)
    manager = app.state.manager
    with manager.subscribe() as subscriber:
        await manager.write(session["id"], "x")
        frame = await asyncio.wait_for(subscriber.queue.get(), 2)
        assert frame == {"type": "out", "s": session["id"], "o": 0, "d": "eco:x"}

        for i in range(subscriber.queue.maxsize + 5):
            manager._publish({"type": "out", "s": session["id"], "o": i, "d": "."})
        assert subscriber.overflowed is True


async def test_fechar_mata_a_arvore_e_avisa_o_stream(client, app, backend, projects):
    session = await _open(client, projects)
    manager = app.state.manager
    with manager.subscribe() as subscriber:
        response = await client.delete(f"/api/terminal/sessions/{session['id']}")
        assert response.status_code == 204
        assert backend.handles[0].killed is True
        frame = await asyncio.wait_for(subscriber.queue.get(), 2)
        assert frame == {"type": "closed", "s": session["id"]}
    assert (await client.delete(f"/api/terminal/sessions/{session['id']}")).status_code == 404
    response = await client.post(f"/api/terminal/sessions/{session['id']}/input", json={"data": "x"})
    assert response.status_code == 404


async def test_shell_que_sai_sozinho_fica_listado_como_encerrado(client, app, backend, projects):
    session = await _open(client, projects)
    manager = app.state.manager
    backend.handles[0].finish()
    await until(lambda: not manager.get(session["id"]).alive)

    [listed] = (await client.get("/api/terminal/sessions")).json()
    assert (listed["alive"], listed["exit_code"]) == (False, 0)
    assert manager.catch_up({session["id"]: 0})[-1] == {
        "type": "exit",
        "s": session["id"],
        "code": 0,
    }


async def test_teto_de_sessoes(client, app, projects):
    app.state.manager.max_sessions = 2
    await _open(client, projects)
    await _open(client, projects)
    response = await client.post(
        "/api/terminal/sessions", json={"cwd": str(projects / "monitoria")}
    )
    assert response.status_code == 409


async def test_guarda_local_vale_no_terminal_host(app, projects):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://127.0.0.1:8766"
    ) as raw:
        payload = {"cwd": str(projects / "monitoria")}
        assert (await raw.post("/api/terminal/sessions", json=payload)).status_code == 403
        response = await raw.post(
            "/api/terminal/sessions",
            json=payload,
            headers={"X-SprintAI": "1", "Origin": "https://site-malicioso.example"},
        )
        assert response.status_code == 403
        response = await raw.get(
            "/api/terminal/sessions", headers={"X-SprintAI": "1", "Host": "evil.example"}
        )
        assert response.status_code == 403
        assert (await raw.get("/docs")).status_code == 404


def test_since_ignora_o_que_nao_e_sessao():
    from terminal.app import parse_since

    sid = "0123456789abcdef"
    assert parse_since(f"{sid}:42,lixo,{'f' * 16}:x, {sid}:7") == {sid: 7}
    assert parse_since(None) == {}


@pytest.mark.skipif(sys.platform != "win32", reason="WinPTY é do Windows")
def test_winpty_de_verdade_le_a_saida_de_um_comando(tmp_path):
    handle = WinPtyBackend().spawn(
        ["cmd.exe", "/c", "echo marca-do-terminal"],
        cwd=str(tmp_path),
        env={"SystemRoot": "C:\\Windows", "PATH": "C:\\Windows\\System32"},
        cols=80,
        rows=24,
    )
    output = ""
    for _ in range(200):
        chunk = handle.read()
        output += chunk
        if "marca-do-terminal" in output or (not chunk and not handle.alive()):
            break
    handle.kill()
    assert "marca-do-terminal" in output
