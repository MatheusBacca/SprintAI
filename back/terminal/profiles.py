"""Perfis de processo do terminal host — o que um terminal pode ser.

A API recebe o **nome** do perfil, nunca um comando: não há rota que rode "o que vier no
corpo". Hoje é só o PowerShell (o 5.1, que é o que existe nesta máquina — não há `pwsh`).
O lançamento do Claude com skill ou prompt, quando entrar, é outro perfil daqui, com o
argumento montado e confirmado antes, e não um campo livre.
"""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Profile:
    id: str
    label: str
    argv: tuple[str, ...]


def _system_root() -> Path:
    return Path(os.environ.get("SystemRoot", r"C:\Windows"))


def powershell() -> Profile:
    exe = _system_root() / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    # Sem -NoProfile: o terminal é o do dev, com o perfil dele (conda, prompt, aliases).
    return Profile(id="powershell", label="PowerShell", argv=(str(exe), "-NoLogo"))


def profiles() -> dict[str, Profile]:
    profile = powershell()
    return {profile.id: profile}
