import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent


def load(name: str):
    """`load("jira/fields.json")` — respostas no formato real das APIs, com dados fictícios."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))
