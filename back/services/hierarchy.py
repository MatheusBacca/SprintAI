"""O que conta como "pai" de uma tarefa na WeON.

- Campo `parent` do Jira: Épico → Tarefa, Tarefa → Subtarefa.
- Links para um Enhancements (fluxo "Analisar e fatiar"): Relates, "Divisão do ticket"
  e "implements" (Polaris). Tipos e nomes medidos no Jira real em 2026-09-14.
"""

PARENT_ISSUE_TYPES = frozenset({"Épico", "Epic", "Enhancements", "Enhancement", "Feature"})
HIERARCHY_LINK_TYPES = frozenset({"Relates", "Divisão do ticket", "Polaris work item link"})
BLOCK_LINK_TYPE = "Blocks"
# "causes" / "is caused by": o Ajuste que nasceu de uma entrega aponta para ela.
CAUSE_LINK_TYPE = "Problem/Incident"


def is_hierarchy_link(link_type: str | None, target_type: str | None) -> bool:
    return link_type in HIERARCHY_LINK_TYPES and target_type in PARENT_ISSUE_TYPES
