"""Atlassian Document Format (ADF) → texto puro.

Usado para busca e para prévias; a renderização rica fica no front (F2).
"""

from typing import Any

_BLOCKS = {
    "paragraph",
    "heading",
    "blockquote",
    "codeBlock",
    "rule",
    "panel",
    "mediaSingle",
    "table",
    "tableRow",
    "decisionItem",
    "taskItem",
    "expand",
}


def _walk(node: Any, out: list[str]) -> None:
    if isinstance(node, list):
        for child in node:
            _walk(child, out)
        return
    if not isinstance(node, dict):
        return

    node_type = node.get("type")
    attrs = node.get("attrs") or {}

    if node_type == "text":
        out.append(node.get("text", ""))
    elif node_type == "hardBreak":
        out.append("\n")
    elif node_type == "mention":
        out.append(attrs.get("text") or "@menção")
    elif node_type == "emoji":
        out.append(attrs.get("text") or attrs.get("shortName") or "")
    elif node_type in ("inlineCard", "blockCard", "embedCard"):
        out.append(attrs.get("url") or "")
    elif node_type == "status":
        out.append(f"[{attrs.get('text', '')}]")
    elif node_type == "date":
        out.append(str(attrs.get("timestamp", "")))
    elif node_type == "listItem":
        out.append("- ")

    _walk(node.get("content") or [], out)

    if node_type in _BLOCKS or node_type == "listItem":
        out.append("\n")
    elif node_type == "tableCell" or node_type == "tableHeader":
        out.append(" | ")


def adf_to_text(document: Any) -> str:
    """Aceita ADF (dict), texto simples (API v2/legado) ou None."""
    if document is None:
        return ""
    if isinstance(document, str):
        return document.strip()
    parts: list[str] = []
    _walk(document, parts)
    text = "".join(parts)
    lines = [line.rstrip() for line in text.splitlines()]
    # Colapsa linhas em branco repetidas.
    collapsed: list[str] = []
    for line in lines:
        if line or (collapsed and collapsed[-1]):
            collapsed.append(line)
    return "\n".join(collapsed).strip()
