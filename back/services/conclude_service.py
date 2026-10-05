"""O "Concluir" do card: a receita do repo da tarefa (Configurações › Concluir), em dois tempos.

1. **Plano** (`plan`): o que vai acontecer, lido agora — os PRs abertos que serão mergeados, com
   os avisos (rascunho, aprovações pela regra do SprintAI, ajustes, build), e o status do Jira
   de destino, conferido contra as transições que o Jira oferece neste momento.
2. **Execução** (`run`): só o que o dev confirmou, conferido de novo contra o plano de agora.
   O merge vem primeiro; o Jira só anda se todos os merges entraram — mover a tarefa para
   testes com o PR ainda aberto contaria uma história que não aconteceu.

O repo da tarefa sai dos PRs e branches dela no espelho e do `[repo]` do título. Os avisos
não barram: quem barra é o Bitbucket, pelas merge checks do repo. O espelho do PR não é
escrito à mão — o sync roda logo depois do merge e grava a mudança (e o evento) como sempre.
"""

import uuid

import asyncpg

from core.logger import get_logger
from integrations import factory
from integrations.errors import IntegrationError, PermissionDenied
from realtime import bus
from repositories import issue_repo
from schemas.conclude_schemas import (
    ConcludeIn,
    ConcludeMergeOut,
    ConcludePlanOut,
    ConcludeResultOut,
    ConcludeStepOut,
    ConcludeTargetOut,
)
from security.credential_store import CredentialStore
from services import card_colors, conclude_settings, issue_actions, pr_status_service
from services.conclude_settings import ConcludeTask, blocked_reason, task_repos
from services.issue_actions import IssueActionConflict, IssueNotInMirror, requires_fields
from services.pr_status import FAILED_BUILDS
from services.progress.service import load_stages
from services.progress.stages import normalize
from services.sync.engine import SyncAlreadyRunning, SyncEngine

logger = get_logger(__name__)

STRATEGY_LABELS = {
    "merge_commit": "merge commit",
    "squash": "squash",
    "fast_forward": "fast-forward",
}


def merge_warnings(pr) -> list[str]:
    warnings = []
    if pr.draft:
        warnings.append("PR em rascunho")
    review = pr.review
    if review and review.required and review.approvals < review.required:
        warnings.append(
            f"{review.approvals}/{review.required} aprovações pela regra do SprintAI"
        )
    if pr.changes_requested and not pr.fix_pushed:
        warnings.append("ajustes pedidos sem correção")
    if pr.build_status in FAILED_BUILDS:
        warnings.append("build falhou")
    if pr.match == "title":
        warnings.append("o PR só cita a tarefa no título, não na branch")
    return warnings


# --- Plano ------------------------------------------------------------------------------------


async def plan(pool: asyncpg.Pool, store: CredentialStore, key: str) -> ConcludePlanOut:
    row = await issue_repo.issue(pool, key)
    if row is None:
        raise IssueNotInMirror(key)
    rules = await conclude_settings.load_rules(pool)
    summary = (await pr_status_service.summaries(pool, [key]))[key]
    colors = await card_colors.load_colors(pool)
    title_repos = colors.title_repos(row["summary"])
    repos = conclude_settings.concludable(rules, task_repos(summary, title_repos))
    blocked = blocked_reason(
        rules,
        ConcludeTask(key, row["summary"], row["status"], row["status_category"]),
        summary,
        title_repos,
        await load_stages(pool),
    )

    merges: list[ConcludeMergeOut] = []
    notes: list[str] = []
    for slug in repos:
        rule = rules[slug]
        if not rule.merge:
            continue
        open_prs = [
            pr
            for repo in summary.repos
            if repo.repo_slug == slug
            for pr in repo.pull_requests
            if pr.state == "OPEN"
        ]
        if not open_prs:
            notes.append(f"{slug} mergeia no Concluir, mas a tarefa não tem PR aberto lá.")
        for pr in open_prs:
            merges.append(
                ConcludeMergeOut(
                    repo_slug=slug,
                    pr_id=pr.id,
                    title=pr.title,
                    url=pr.url,
                    source_branch=pr.source_branch,
                    destination_branch=pr.destination_branch,
                    strategy=rule.strategy,
                    close_source_branch=rule.close_source_branch,
                    warnings=merge_warnings(pr),
                )
            )

    wanted: list[str] = []
    for slug in repos:
        status = rules[slug].jira_status
        if status and normalize(status) not in {normalize(s) for s in wanted}:
            wanted.append(status)

    current = row["status"]
    targets: list[ConcludeTargetOut] = []
    if wanted:
        # Lido agora: as transições são relativas ao status de agora, e o espelho pode estar
        # alguns minutos atrás do Jira.
        async with await factory.jira_client(store) as jira:
            issue = await jira.get_issue(key, fields=("status",))
            offered = await jira.transitions(key)
        current = ((issue.get("fields") or {}).get("status") or {}).get("name") or current
        targets = [_target(status, current, offered) for status in wanted]

    return ConcludePlanOut(
        issue_key=key,
        status=current,
        repos=repos,
        merges=merges,
        targets=targets,
        notes=notes,
        blocked=blocked,
    )


def _target(status: str, current: str, offered: list[dict]) -> ConcludeTargetOut:
    if normalize(status) == normalize(current):
        return ConcludeTargetOut(status=current, current=True, available=True)
    transition = _transition_to(status, offered)
    if transition is None:
        return ConcludeTargetOut(
            status=status,
            current=False,
            available=False,
            reason=f"O Jira não oferece a ida de “{current}” para “{status}” agora.",
        )
    if requires_fields(transition):
        return ConcludeTargetOut(
            status=status,
            current=False,
            available=False,
            reason=f"A transição para “{status}” pede campos no Jira — faça por lá.",
        )
    return ConcludeTargetOut(status=status, current=False, available=True)


def _transition_to(status: str, offered: list[dict]) -> dict | None:
    wanted = normalize(status)
    return next(
        (t for t in offered if normalize((t.get("to") or {}).get("name")) == wanted), None
    )


# --- Execução ---------------------------------------------------------------------------------


async def run(
    pool: asyncpg.Pool,
    store: CredentialStore,
    engine: SyncEngine | None,
    key: str,
    payload: ConcludeIn,
) -> ConcludeResultOut:
    fresh = await plan(pool, store, key)
    if fresh.blocked:
        raise IssueActionConflict(fresh.blocked)
    planned = {(m.repo_slug, m.pr_id): m for m in fresh.merges}
    chosen = []
    for ref in payload.merges:
        merge = planned.get((ref.repo_slug, ref.pr_id))
        if merge is None:
            raise IssueActionConflict(
                f"O PR #{ref.pr_id} de {ref.repo_slug} não está mais no plano do Concluir — "
                "abra de novo."
            )
        chosen.append(merge)

    target = _chosen_target(fresh, payload.jira_status)
    steps: list[ConcludeStepOut] = []
    merged_any = False

    if chosen:
        async with factory.bitbucket_client(store) as bb:
            for merge in chosen:
                step = await _merge(bb, merge)
                steps.append(step)
                if not step.ok:
                    break
                merged_any = True
        if merged_any:
            await _resync(engine)
        if not steps[-1].ok:
            return ConcludeResultOut(
                issue_key=key,
                done=False,
                steps=steps,
                write_id=_announce(key) if merged_any else None,
            )

    status = fresh.status
    write_id = None
    if target is not None and not target.current:
        try:
            # O id da transição é relido lá dentro: entre o plano e o clique, alguém pode ter
            # mexido na tarefa.
            async with await factory.jira_client(store) as jira:
                transition = _transition_to(target.status, await jira.transitions(key))
            if transition is None:
                raise IssueActionConflict(
                    f"O Jira não oferece mais a ida para “{target.status}” — abra de novo."
                )
            written = await issue_actions.apply_transition(
                pool, store, key, str(transition["id"])
            )
        except (IssueActionConflict, IntegrationError) as exc:
            steps.append(
                ConcludeStepOut(
                    kind="transition",
                    label=f"Mover para {target.status}",
                    ok=False,
                    message=getattr(exc, "message", str(exc)),
                )
            )
            return ConcludeResultOut(
                issue_key=key,
                done=False,
                steps=steps,
                write_id=_announce(key) if merged_any else None,
            )
        status, write_id = written.status, written.write_id
        steps.append(
            ConcludeStepOut(kind="transition", label=f"Movida para {written.status}", ok=True)
        )
    elif target is not None:
        steps.append(
            ConcludeStepOut(kind="transition", label=f"Já estava em {target.status}", ok=True)
        )

    if write_id is None and merged_any:
        write_id = _announce(key)
    return ConcludeResultOut(
        issue_key=key, done=True, steps=steps, status=status, write_id=write_id
    )


def _chosen_target(fresh: ConcludePlanOut, wanted: str | None) -> ConcludeTargetOut | None:
    if not fresh.targets:
        if wanted:
            raise IssueActionConflict("Nenhum repo da tarefa move o Jira no Concluir.")
        return None
    if wanted is None:
        if len(fresh.targets) > 1:
            raise IssueActionConflict("Os repos da tarefa levam a status diferentes — escolha um.")
        wanted = fresh.targets[0].status
    target = next((t for t in fresh.targets if normalize(t.status) == normalize(wanted)), None)
    if target is None:
        raise IssueActionConflict(f"“{wanted}” não está entre os status do Concluir desta tarefa.")
    if not target.available:
        raise IssueActionConflict(target.reason or f"Não dá para mover para “{wanted}”.")
    return target


async def _merge(bb, merge: ConcludeMergeOut) -> ConcludeStepOut:
    label = f"Merge do PR #{merge.pr_id} em {merge.repo_slug}"
    try:
        result = await bb.merge_pull_request(
            merge.repo_slug,
            merge.pr_id,
            strategy=merge.strategy,
            close_source_branch=merge.close_source_branch,
        )
    except PermissionDenied:
        return ConcludeStepOut(
            kind="merge",
            label=label,
            ok=False,
            url=merge.url,
            message="Bitbucket: sem permissão para mergear — o token precisa do escopo "
            "write:pullrequest:bitbucket, ou o seu usuário não pode mergear neste repo.",
        )
    except IntegrationError as exc:
        # O corpo da resposta não vem para a tela (ver `integrations/errors.py`): o motivo
        # exato fica no PR, e o link vai junto.
        logger.info("Merge recusado em %s#%s: %s", merge.repo_slug, merge.pr_id, exc.status)
        return ConcludeStepOut(
            kind="merge",
            label=label,
            ok=False,
            url=merge.url,
            message=f"O Bitbucket recusou o merge (HTTP {exc.status or '?'}) — confira no PR "
            "as merge checks (aprovações, build, tarefas abertas) e se há conflito.",
        )
    if result.get("state") == "MERGING":
        return ConcludeStepOut(
            kind="merge",
            label=label,
            ok=True,
            url=merge.url,
            message="O Bitbucket ainda está mergeando — confira no PR em instantes.",
        )
    return ConcludeStepOut(
        kind="merge",
        label=f"PR #{merge.pr_id} em {merge.repo_slug} mergeado "
        f"({STRATEGY_LABELS.get(merge.strategy, merge.strategy)})",
        ok=True,
        url=merge.url,
    )


def _announce(key: str) -> str:
    """Avisa as abas abertas (o card troca o selo do PR no próximo sync)."""
    write_id = uuid.uuid4().hex
    bus.publish(bus.ISSUE_CHANGED, {"key": key, "field": "pr", "write_id": write_id})
    return write_id


async def _resync(engine: SyncEngine | None) -> None:
    """O espelho do PR é do sync: ele roda agora (em segundo plano) e grava o merge — e o
    evento — como sempre. Com um sync no meio do caminho, o próximo pega."""
    if engine is None:
        return
    try:
        await engine.trigger("concluir")
    except SyncAlreadyRunning:
        pass
    except Exception:  # noqa: BLE001 — sync que falha ao disparar não desfaz o merge
        logger.exception("Sync depois do Concluir não disparou")
