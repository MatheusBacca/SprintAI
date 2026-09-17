"""Fontes de progresso de uma tarefa (B9).

Hoje só existe a fonte `status`. A fonte `checklist` (itens feitos/total do PROGRESS.md)
entra na F13 e passa a ter prioridade quando a tarefa tem checklist — por isso o
resultado carrega qual fonte respondeu, e a Home/timeline mostram o ícone certo.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from services.progress.stages import ProgressStages, Stage


@dataclass(frozen=True)
class Progress:
    value: float
    source: str
    stage_id: str | None = None
    stage_label: str | None = None
    stage_color: str | None = None
    done: int | None = None
    total: int | None = None


class ProgressSource(Protocol):
    name: str

    def of(self, issue: dict[str, Any]) -> Progress | None:
        """Progresso da tarefa, ou None quando esta fonte não sabe responder."""


def _from_stage(value: float, stage: Stage | None) -> Progress:
    return Progress(
        value=value,
        source="status",
        stage_id=stage.id if stage else None,
        stage_label=stage.label if stage else None,
        stage_color=stage.color if stage else None,
    )


class StatusSource:
    """Etapa do status atual, pelo mapa configurável."""

    name = "status"

    def __init__(self, stages: ProgressStages) -> None:
        self.stages = stages

    def of(self, issue: dict[str, Any]) -> Progress:
        value, stage = self.stages.weight_of(issue.get("status"), issue.get("status_category"))
        return _from_stage(value, stage)


def resolve(issue: dict[str, Any], sources: list[ProgressSource]) -> Progress:
    """Primeira fonte que sabe responder vence; a de status sempre responde."""
    for source in sources:
        progress = source.of(issue)
        if progress is not None:
            return progress
    return Progress(value=0.0, source="none")
