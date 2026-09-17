"""Extração de chaves Jira (WAI-1234) de nomes de branch e títulos de PR.

Branches reais do weonrepo: `WAI-7120-slug`, `feature/WAI-7120`, `bugfix/wai-7120-x`.
"""

import re
from collections.abc import Iterable

_KEY = re.compile(r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]{1,9})-(\d{1,7})(?![0-9])")


def extract_issue_keys(*texts: str | None, project_keys: Iterable[str]) -> list[str]:
    """Chaves únicas, em maiúsculas, na ordem em que aparecem; só dos projetos informados."""
    allowed = {k.upper() for k in project_keys}
    found: list[str] = []
    for text in texts:
        for project, number in _KEY.findall(text or ""):
            key = f"{project.upper()}-{int(number)}"
            if project.upper() in allowed and key not in found:
                found.append(key)
    return found
