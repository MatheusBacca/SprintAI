"""Etapas de progresso a partir do status do Jira (B9).

A categoria do Jira mente para este workflow: `DISPONIVEL PARA REVIEW` e
`DISPONIVEL PARA TESTES` são `new`, e contariam como "nem começou". Por isso o mapa
status → etapa é explícito e **configurável** (`app_setting.progress_stages`); a
categoria só é o plano B para um status que ninguém mapeou.

A comparação de status ignora caixa e acento — `Concluído` e `CONCLUIDO` são o mesmo.
"""

import unicodedata
from dataclasses import dataclass
from typing import Any

ANALYSIS = "analise"
DEVELOPMENT = "desenvolvimento"
REVIEW = "review"
TESTS = "testes"
DONE = "concluido"


@dataclass(frozen=True)
class Stage:
    id: str
    label: str
    order: int
    weight: float
    color: str


DEFAULT_STAGES: tuple[Stage, ...] = (
    Stage(ANALYSIS, "Análise", 0, 0.0, "#94a3b8"),
    Stage(DEVELOPMENT, "Desenvolvimento", 1, 0.4, "#2f7cf6"),
    Stage(REVIEW, "Review", 2, 0.7, "#f59e0b"),
    Stage(TESTS, "Testes", 3, 0.85, "#8a4fff"),
    Stage(DONE, "Concluído", 4, 1.0, "#10b981"),
)

# Status reais do board Engenharia (WAI). "AJUSTE" é código que voltou para a mão do
# dev, então conta como desenvolvimento, não como review.
DEFAULT_STATUS_STAGES: dict[str, str] = {
    "Disponivel para análise": ANALYSIS,
    "Backlog": ANALYSIS,
    "A fazer": ANALYSIS,
    "Em Desenvolvimento": DEVELOPMENT,
    "AJUSTE": DEVELOPMENT,
    "DISPONIVEL PARA REVIEW": REVIEW,
    "Em Review": REVIEW,
    "DISPONIVEL PARA TESTES": TESTS,
    "Em Teste": TESTS,
    "Concluído": DONE,
}

# Plano B para status desconhecido: a categoria do Jira, sem etapa nomeada.
CATEGORY_WEIGHTS = {"new": 0.0, "indeterminate": 0.5, "done": 1.0}


def normalize(status: str | None) -> str:
    if not status:
        return ""
    folded = unicodedata.normalize("NFKD", status)
    return "".join(c for c in folded if not unicodedata.combining(c)).strip().lower()


@dataclass(frozen=True)
class ProgressStages:
    stages: tuple[Stage, ...] = DEFAULT_STAGES
    statuses: dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        by_id = {s.id: s for s in self.stages}
        statuses = dict(DEFAULT_STATUS_STAGES) if self.statuses is None else dict(self.statuses)
        # Mapear um status para uma etapa que não existe mais deixaria a tarefa sem peso.
        statuses = {k: v for k, v in statuses.items() if v in by_id}
        object.__setattr__(self, "statuses", statuses)
        object.__setattr__(self, "_by_status", {normalize(k): v for k, v in statuses.items()})
        object.__setattr__(self, "_by_id", by_id)

    @property
    def by_id(self) -> dict[str, Stage]:
        return self._by_id  # type: ignore[attr-defined]

    def stage_of(self, status: str | None) -> Stage | None:
        stage_id = self._by_status.get(normalize(status))  # type: ignore[attr-defined]
        return self.by_id.get(stage_id) if stage_id else None

    def weight_of(self, status: str | None, category: str | None) -> tuple[float, Stage | None]:
        """Peso 0..1 da etapa; sem etapa mapeada, cai pela categoria do Jira."""
        stage = self.stage_of(status)
        if stage is not None:
            return stage.weight, stage
        return CATEGORY_WEIGHTS.get(category or "", 0.0), None

    # --- Persistência (app_setting) -------------------------------------------------

    @classmethod
    def from_setting(cls, value: Any) -> "ProgressStages":
        if not isinstance(value, dict):
            return cls()
        raw_stages = value.get("stages")
        stages = DEFAULT_STAGES
        if isinstance(raw_stages, list) and raw_stages:
            parsed = []
            for item in raw_stages:
                try:
                    parsed.append(
                        Stage(
                            id=str(item["id"]),
                            label=str(item.get("label") or item["id"]),
                            order=int(item.get("order", len(parsed))),
                            weight=min(1.0, max(0.0, float(item.get("weight", 0.0)))),
                            color=str(item.get("color") or "#94a3b8"),
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    continue
            if parsed:
                stages = tuple(sorted(parsed, key=lambda s: s.order))
        raw_statuses = value.get("statuses")
        known = {s.id for s in stages}
        statuses = (
            {str(k): str(v) for k, v in raw_statuses.items() if str(v) in known}
            if isinstance(raw_statuses, dict)
            else dict(DEFAULT_STATUS_STAGES)
        )
        return cls(stages=stages, statuses=statuses)

    def to_setting(self) -> dict[str, Any]:
        return {
            "stages": [
                {
                    "id": s.id,
                    "label": s.label,
                    "order": s.order,
                    "weight": s.weight,
                    "color": s.color,
                }
                for s in self.stages
            ],
            "statuses": dict(self.statuses),
        }
