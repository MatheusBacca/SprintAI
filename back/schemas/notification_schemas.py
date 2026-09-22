from pydantic import BaseModel

from schemas.progress_schemas import SprintUpdateOut


class TaskUpdateOut(SprintUpdateOut):
    """Tarefa da sprint ativa que outra pessoa mexeu — a notificação de tarefa do sino.

    Leva a sprint junto porque o clique na notificação abre a tela da Sprint **naquela**
    sprint, e não na que o seletor tinha ficado mostrando.
    """

    sprint_id: int
    sprint_name: str


class TaskUpdatesOut(BaseModel):
    updates: list[TaskUpdateOut]
