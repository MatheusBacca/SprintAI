"""Ações no Jira a partir do SprintAI: mover o status e mudar os Story Points.

São as duas únicas escritas do SprintAI no Jira, e cada uma sai de um gesto explícito
do dev na tela — duplo clique no status escolhido, Enter/Salvar nos pontos. Proposta →
confirmação → ação, uma tarefa por vez.

Depois que o Jira aceita, o espelho recebe o valor novo na hora e o barramento avisa as
abas abertas (`issue.changed`). A **história** da mudança — a linha de
`jira_status_transition` que segmenta a timeline e o evento do feed — chega no próximo
sync, pelo changelog, como qualquer outra mudança (ver `issue_repo.patch_status`).
"""

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

import asyncpg

from core.logger import get_logger
from integrations import factory
from integrations.errors import BadRequest, IntegrationError, PermissionDenied
from integrations.jira_client import JiraClient, JiraField, JiraFieldMap
from realtime import bus
from repositories import issue_repo
from schemas.issue_schemas import FlowStepOut, IssueFlowOut, IssueWriteOut
from security.credential_store import CredentialStore
from services import card_updates
from services.progress.service import load_stages, stage_ref
from services.progress.stages import ProgressStages, Stage, normalize
from services.sprint_service import jira_identity

logger = get_logger(__name__)

CATEGORY_RANK = {"new": 0, "indeterminate": 1, "done": 2}


class IssueNotInMirror(Exception):
    pass


class IssueActionConflict(Exception):
    """O Jira não deixa seguir por um motivo que o dev resolve — a mensagem vai para a tela."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# --- Linha de fluxo (funções puras) ---------------------------------------------------


@dataclass(frozen=True)
class FlowStep:
    status: str
    category: str
    stage: Stage | None
    current: bool
    transition_id: str | None = None
    transition_name: str | None = None
    requires_fields: bool = False


def _category(raw: dict[str, Any]) -> str:
    return (raw.get("statusCategory") or {}).get("key") or "undefined"


def requires_fields(transition: dict[str, Any]) -> bool:
    """Tela de transição com campo obrigatório sem valor padrão: o POST sem campos seria
    recusado com 400, então a transição fica para o Jira."""
    return any(
        field.get("required") and not field.get("hasDefaultValue")
        for field in (transition.get("fields") or {}).values()
    )


def workflow_statuses(project_statuses: list[dict[str, Any]], issue_type: str | None) -> list[dict]:
    """Status do workflow do tipo da tarefa. Tipo não achado devolve vazio — a linha fica
    só com o status atual e os de destino das transições."""
    wanted = normalize(issue_type)
    for item in project_statuses:
        if wanted and normalize(item.get("name")) == wanted:
            return item.get("statuses") or []
    return []


def _flow_order(step: FlowStep, index: int) -> tuple:
    """Ordem das etapas de progresso (Configurações › Progresso), que é a linha que o dev
    já desenhou para o board. Status sem etapa ficam nas pontas pela categoria: o que é
    "a fazer" abre a linha, o resto a fecha.

    Dentro de uma etapa, a categoria desempata antes da ordem do workflow —
    `DISPONIVEL PARA REVIEW` (`new`) vem antes de `Em Review` (`indeterminate`).
    """
    rank = CATEGORY_RANK.get(step.category, 1)
    name = normalize(step.status)
    if step.stage is not None:
        return (1, step.stage.order, rank, index, name)
    if rank == 0:
        return (0, 0, rank, index, name)
    return (2, rank, 0, index, name)


def build_flow(
    *,
    current: dict[str, Any],
    transitions: list[dict[str, Any]],
    statuses: list[dict[str, Any]],
    stages: ProgressStages,
) -> list[FlowStep]:
    """Os passos do workflow com o que dá para fazer a partir do status atual.

    Aparecem todos os status do workflow do tipo da tarefa — os sem transição a partir
    daqui também, apagados, para a linha mostrar onde a tarefa está e o que o workflow
    não deixa pular. Transição de volta para o próprio status não entra: não move nada.
    Duas transições para o mesmo status viram um passo só (vale a primeira).
    """
    current_key = normalize(current.get("name"))
    by_target: dict[str, dict[str, Any]] = {}
    for transition in transitions:
        target_key = normalize((transition.get("to") or {}).get("name"))
        if target_key and target_key != current_key and target_key not in by_target:
            by_target[target_key] = transition

    found: dict[str, tuple[int, dict[str, Any]]] = {}
    # O status fora da lista do workflow vai para o fim dele, na ordem em que apareceu.
    raws = [*statuses, current, *((t.get("to") or {}) for t in by_target.values())]
    for index, raw in enumerate(raws):
        key = normalize(raw.get("name"))
        if key and key not in found:
            found[key] = (index, raw)

    ordered = []
    for key, (index, raw) in found.items():
        transition = by_target.get(key)
        step = FlowStep(
            status=raw["name"],
            category=_category(raw),
            stage=stages.stage_of(raw["name"]),
            current=key == current_key,
            transition_id=str(transition["id"]) if transition else None,
            transition_name=transition.get("name") if transition else None,
            requires_fields=requires_fields(transition) if transition else False,
        )
        ordered.append((_flow_order(step, index), step))
    return [step for _, step in sorted(ordered, key=lambda pair: pair[0])]


def editable_points_field(field_map: JiraFieldMap, edit_meta: dict[str, Any]) -> JiraField | None:
    """O primeiro campo de Story Points (na prioridade do sync) que a tela de edição da
    tarefa aceita. Projeto team-managed usa "Story point estimate" no lugar do clássico."""
    editable = (edit_meta or {}).get("fields") or {}
    candidates = field_map.story_point_candidates or tuple(filter(None, [field_map.story_points]))
    return next((field for field in candidates if field.id in editable), None)


def jira_number(value: float | None) -> int | float | None:
    """5.0 vai como 5: é assim que o Jira mostra e devolve no histórico."""
    if value is None:
        return None
    return int(value) if float(value).is_integer() else value


# --- Leitura do fluxo -----------------------------------------------------------------


async def _project_statuses(jira: JiraClient, project_key: str) -> list[dict[str, Any]]:
    # A linha completa é um bônus: sem ela, as transições continuam valendo.
    try:
        return await jira.project_statuses(project_key)
    except IntegrationError:
        logger.warning("Status do projeto %s não puderam ser lidos", project_key)
        return []


async def get_flow(pool: asyncpg.Pool, store: CredentialStore, key: str) -> IssueFlowOut:
    row = await issue_repo.issue(pool, key)
    if row is None:
        raise IssueNotInMirror(key)
    _, site_url = jira_identity(store)

    # Status atual lido agora: as transições são relativas a ele, e o espelho pode estar
    # alguns minutos atrás do Jira.
    async with await factory.jira_client(store) as jira:
        issue, transitions, project = await asyncio.gather(
            jira.get_issue(key, fields=("status", "issuetype")),
            jira.transitions(key),
            _project_statuses(jira, row["project_key"]),
        )

    fields = issue.get("fields") or {}
    current = fields.get("status") or {"name": row["status"]}
    issue_type = (fields.get("issuetype") or {}).get("name") or row["issue_type"]
    stages = await load_stages(pool)
    steps = build_flow(
        current=current,
        transitions=transitions,
        statuses=workflow_statuses(project, issue_type),
        stages=stages,
    )
    mirror_differs = normalize(row["status"]) != normalize(current.get("name"))
    return IssueFlowOut(
        issue_key=key,
        url=f"{site_url.rstrip('/')}/browse/{key}" if site_url else None,
        status=current.get("name") or row["status"],
        mirror_status=row["status"] if mirror_differs else None,
        steps=[
            FlowStepOut(
                status=s.status,
                category=s.category,
                stage=stage_ref(s.stage),
                current=s.current,
                transition_id=s.transition_id,
                transition_name=s.transition_name,
                requires_fields=s.requires_fields,
            )
            for s in steps
        ],
    )


# --- Escrita --------------------------------------------------------------------------


async def _written(pool: asyncpg.Pool, key: str, field: str) -> IssueWriteOut:
    row = await issue_repo.issue(pool, key)
    stages = await load_stages(pool)
    write_id = uuid.uuid4().hex
    bus.publish(bus.ISSUE_CHANGED, {"key": key, "field": field, "write_id": write_id})
    points = row["story_points"]
    return IssueWriteOut(
        issue_key=key,
        status=row["status"],
        status_category=row["status_category"],
        story_points=float(points) if points is not None else None,
        stage=stage_ref(stages.stage_of(row["status"])),
        write_id=write_id,
    )


async def apply_transition(
    pool: asyncpg.Pool, store: CredentialStore, key: str, transition_id: str
) -> IssueWriteOut:
    if await issue_repo.issue(pool, key) is None:
        raise IssueNotInMirror(key)

    async with await factory.jira_client(store) as jira:
        # Relido na hora: é o Jira quem diz para onde a transição leva, e ela pode ter
        # deixado de existir se alguém mexeu na tarefa depois que a lista abriu.
        offered = await jira.transitions(key)
        transition = next((t for t in offered if str(t.get("id")) == transition_id), None)
        if transition is None:
            raise IssueActionConflict(
                f"O Jira não oferece mais essa transição para {key} — o status pode ter "
                "mudado. Abra a lista de novo."
            )
        if requires_fields(transition):
            raise IssueActionConflict(
                f"A transição “{transition.get('name')}” pede campos no Jira — faça por lá."
            )
        try:
            await jira.transition_issue(key, transition_id)
        except PermissionDenied as exc:
            raise PermissionDenied(
                "Jira",
                f"Jira: sem permissão para mover {key} — o token precisa do escopo "
                "write:jira-work, ou o seu usuário não pode fazer essa transição.",
                403,
            ) from exc
        except BadRequest as exc:
            raise BadRequest(
                "Jira",
                "Jira: a transição foi recusada (HTTP 400) — ela pode pedir campos "
                "obrigatórios; faça pelo Jira.",
                400,
            ) from exc

    target = transition.get("to") or {}
    status = target.get("name") or "?"
    await issue_repo.patch_status(pool, key, status=status, status_category=_category(target))
    await card_updates.acknowledge_own_change(pool, key, {"status": status})
    return await _written(pool, key, "status")


async def set_story_points(
    pool: asyncpg.Pool, store: CredentialStore, key: str, story_points: float | None
) -> IssueWriteOut:
    if await issue_repo.issue(pool, key) is None:
        raise IssueNotInMirror(key)

    async with await factory.jira_client(store) as jira:
        field_map, meta = await asyncio.gather(jira.discover_fields(), jira.edit_meta(key))
        field = editable_points_field(field_map, meta)
        if field is None:
            raise IssueActionConflict(
                f"O campo Story Points não está na tela de edição de {key} no Jira."
            )
        try:
            await jira.edit_issue(key, {field.id: jira_number(story_points)})
        except PermissionDenied as exc:
            raise PermissionDenied(
                "Jira",
                f"Jira: sem permissão para editar {key} — o token precisa do escopo "
                "write:jira-work, ou o seu usuário não pode editar a tarefa.",
                403,
            ) from exc
        except BadRequest as exc:
            raise BadRequest(
                "Jira", "Jira: o valor de Story Points foi recusado (HTTP 400).", 400
            ) from exc

    await issue_repo.patch_story_points(pool, key, story_points)
    await card_updates.acknowledge_own_change(pool, key, {"story_points": story_points})
    return await _written(pool, key, "story_points")
