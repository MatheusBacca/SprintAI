from datetime import date, datetime

from pydantic import BaseModel, Field


class StageIn(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=60)
    order: int = Field(ge=0, le=99)
    weight: float = Field(ge=0, le=1)
    color: str = Field(min_length=4, max_length=32)


class StageOut(StageIn):
    pass


class StageRefOut(BaseModel):
    """Etapa em que o status de uma tarefa cai — a cor do card e do painel sai daqui."""

    id: str
    label: str
    color: str


class StatusStageOut(BaseModel):
    status: str
    status_category: str
    issue_count: int
    stage_id: str | None


class ProgressStagesOut(BaseModel):
    stages: list[StageOut]
    # Status do espelho com a etapa em que cada um cai hoje (None = cai pela categoria).
    statuses: list[StatusStageOut]


class ProgressStagesIn(BaseModel):
    stages: list[StageIn] = Field(min_length=1, max_length=12)
    statuses: dict[str, str] = Field(default_factory=dict)


class ProgressOut(BaseModel):
    value: float
    source: str
    stage_id: str | None
    stage_label: str | None
    stage_color: str | None
    done: int | None = None
    total: int | None = None


class SprintUpdateOut(BaseModel):
    """Tarefa da sprint que outra pessoa mexeu há pouco — o card da linha da Home."""

    key: str
    summary: str
    status: str
    status_category: str
    story_points: float | None
    url: str | None
    # Último evento da tarefa na janela, e quantos houve.
    kind: str
    source: str
    title: str
    actor_name: str | None
    occurred_at: datetime
    event_count: int


class SprintProgressOut(BaseModel):
    sprint_id: int
    name: str
    state: str
    squad: str | None
    start: date | None
    end: date | None
    real: float
    expected: float | None
    overdue_active: bool
    issue_count: int
    done_count: int
    story_points: float
    updates: list[SprintUpdateOut] = []
