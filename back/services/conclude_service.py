"""O "Concluir" do card: a receita do repo da tarefa (Configurações › Fluxo de trabalho ›
Concluir), em dois tempos.

1. **Plano** (`plan`): o que vai acontecer, lido agora — os PRs abertos que serão mergeados, com
   os avisos (rascunho, aprovações pela regra do SprintAI, ajustes, build), e o status do Jira
   de destino, conferido contra as transições que o Jira oferece neste momento.
2. **Execução** (`run`): só o que o dev confirmou, conferido de novo contra o plano de agora.
   O merge vem primeiro; o Jira só anda se todos os merges entraram — mover a tarefa para
   testes com o PR ainda aberto contaria uma história que não aconteceu.

Tarefa com mais de um PR aberto conclui por partes: entram os PRs aprovados, e os outros ficam
em `waiting`. Enquanto sobrar um, o Jira não anda — ele se move no Concluir do último PR.

PR em rascunho (`drafts`): o painel oferece liberar, ou liberar e concluir. O plano, aí, é o
do "Liberar e concluir" — feito com os rascunhos já liberados —, e a execução libera antes de
mergear: PR em rascunho o Bitbucket não mergeia. O botão da esquerda do plano comum faz o
caminho de volta, pondo em rascunho os PRs que iam ser mergeados (`set_drafts`).

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
    ConcludeDraftIn,
    ConcludeDraftOut,
    ConcludeIn,
    ConcludeMergeOut,
    ConcludePlanOut,
    ConcludeResultOut,
    ConcludeStepOut,
    ConcludeTargetOut,
    ConcludeWaitingOut,
)
from security.credential_store import CredentialStore
from services import card_colors, conclude_settings, issue_actions, pr_status_service
from services.conclude_settings import ConcludeTask, blocked_reason, task_repos
from services.issue_actions import IssueActionConflict, IssueNotInMirror, requires_fields
from services.pr_status import FAILED_BUILDS
from services.progress.service import load_stages
from services.progress.stages import normalize
from services.sync.engine import SyncEngine, sync_after_write

logger = get_logger(__name__)

STRATEGY_LABELS = {
    "merge_commit": "merge commit",
    "squash": "squash",
    "fast_forward": "fast-forward",
}


def merge_warnings(pr, *, released: bool = False) -> list[str]:
    warnings = []
    if pr.draft and not released:
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
    open_drafts = conclude_settings.open_drafts(summary)
    # Com rascunho, o plano é o do "Liberar e concluir".
    released = bool(open_drafts)
    blocked = blocked_reason(
        rules,
        ConcludeTask(key, row["summary"], row["status"], row["status_category"]),
        summary,
        title_repos,
        await load_stages(pool),
        release_drafts=released,
    )

    split = conclude_settings.split_open_prs(rules, repos, summary, release_drafts=released)
    merging = {(pr.repo_slug, pr.id) for pr in split.merge_now}
    reasons = {(w.pr.repo_slug, w.pr.id): w.reason for w in split.waiting}
    drafts = [
        ConcludeDraftOut(
            repo_slug=pr.repo_slug,
            pr_id=pr.id,
            title=pr.title,
            url=pr.url,
            approvals=pr.approvals,
            merges=(pr.repo_slug, pr.id) in merging,
            reason=reasons.get((pr.repo_slug, pr.id)),
        )
        for pr in open_drafts
    ]
    merges = [
        ConcludeMergeOut(
            repo_slug=pr.repo_slug,
            pr_id=pr.id,
            title=pr.title,
            url=pr.url,
            source_branch=pr.source_branch,
            destination_branch=pr.destination_branch,
            strategy=rules[pr.repo_slug].strategy,
            close_source_branch=rules[pr.repo_slug].close_source_branch,
            warnings=merge_warnings(pr, released=released),
            draft=pr.draft,
        )
        for pr in split.merge_now
    ]
    waiting = [
        ConcludeWaitingOut(
            repo_slug=w.pr.repo_slug, pr_id=w.pr.id, title=w.pr.title, url=w.pr.url,
            reason=w.reason,
        )
        for w in split.waiting
    ]
    with_open_pr = {pr.repo_slug for pr in split.merge_now} | {w.repo_slug for w in waiting}
    notes = [
        f"{slug} mergeia no Concluir, mas a tarefa não tem PR aberto lá."
        for slug in repos
        if rules[slug].merge and slug not in with_open_pr
    ]

    wanted: list[str] = []
    for slug in repos:
        status = rules[slug].jira_status
        if status and normalize(status) not in {normalize(s) for s in wanted}:
            wanted.append(status)

    current = row["status"]
    targets: list[ConcludeTargetOut] = []
    if wanted and not waiting:
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
        waiting=waiting,
        # Com PR aberto sobrando, o Jira nem é consultado: o passo dele fica para depois.
        held_statuses=wanted if waiting else [],
        drafts=drafts,
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
    release = _chosen_release(fresh, payload)
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

    # Com PR aberto sobrando, o Jira fica para o Concluir do último — mesmo que uma tela velha
    # tenha pedido o status.
    held = bool(fresh.waiting)
    target = None if held else _chosen_target(fresh, payload.jira_status)
    picked = {(m.repo_slug, m.pr_id) for m in chosen}
    missing = [m for m in fresh.merges if (m.repo_slug, m.pr_id) not in picked]
    if missing:
        # Um PR foi aprovado depois que o plano abriu: o merge dele não foi visto pelo dev, e
        # sem ele o Jira andaria com o PR aberto.
        ids = ", ".join(f"#{m.pr_id} de {m.repo_slug}" for m in missing)
        raise IssueActionConflict(f"O PR {ids} entrou no plano do Concluir — abra de novo.")
    steps: list[ConcludeStepOut] = []
    merged_any = False

    if chosen or release:
        async with factory.bitbucket_client(store) as bb:
            for draft in release:
                step = await _set_draft(bb, draft.repo_slug, draft.pr_id, draft.url, False)
                steps.append(step)
                if not step.ok:
                    break
                # Liberar já é escrita: o selo do PR muda mesmo que o merge falhe depois.
                merged_any = True
            if not steps or steps[-1].ok:
                for merge in chosen:
                    step = await _merge(bb, merge)
                    steps.append(step)
                    if not step.ok:
                        break
                    merged_any = True
        if merged_any:
            await sync_after_write(engine, "concluir")
        if not steps[-1].ok:
            return ConcludeResultOut(
                issue_key=key,
                done=False,
                steps=steps,
                write_id=_announce(key) if merged_any else None,
            )

    status = fresh.status
    write_id = None
    if held and fresh.held_statuses:
        steps.append(_hold_step(fresh))
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


def _chosen_release(fresh: ConcludePlanOut, payload: ConcludeIn) -> list[ConcludeDraftOut]:
    """Os rascunhos a liberar antes dos merges. Com rascunho no plano, o pedido precisa trazer
    todos — o plano de agora já conta com eles liberados, e um que o dev não viu ficaria de
    fora sem aviso."""
    drafts = {(d.repo_slug, d.pr_id): d for d in fresh.drafts}
    asked = {(r.repo_slug, r.pr_id) for r in payload.release}
    if asked != set(drafts):
        raise IssueActionConflict(
            "Os PRs em rascunho da tarefa mudaram desde que o painel abriu — abra de novo."
        )
    return list(drafts.values())


def _hold_step(fresh: ConcludePlanOut) -> ConcludeStepOut:
    remaining = "; ".join(f"#{w.pr_id} em {w.repo_slug} ({w.reason})" for w in fresh.waiting)
    return ConcludeStepOut(
        kind="hold",
        label=f"O Jira fica em {fresh.status} até o último PR",
        ok=True,
        message=f"Ainda aberto: {remaining}.",
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


async def set_drafts(
    pool: asyncpg.Pool,
    store: CredentialStore,
    engine: SyncEngine | None,
    key: str,
    payload: ConcludeDraftIn,
) -> ConcludeResultOut:
    """Os botões da esquerda do painel: "Rascunho" (põe os PRs do merge em rascunho) e
    "Liberar PR" (tira do rascunho, sem concluir). Só PR aberto da própria tarefa, conferido
    no espelho; o que já está no estado pedido não sai para o Bitbucket."""
    if await issue_repo.issue(pool, key) is None:
        raise IssueNotInMirror(key)
    summary = (await pr_status_service.summaries(pool, [key]))[key]
    open_prs = {
        (pr.repo_slug, pr.id): pr
        for repo in summary.repos
        for pr in repo.pull_requests
        if pr.state == "OPEN"
    }
    chosen = []
    for ref in payload.prs:
        pr = open_prs.get((ref.repo_slug, ref.pr_id))
        if pr is None:
            raise IssueActionConflict(
                f"O PR #{ref.pr_id} de {ref.repo_slug} não é um PR aberto de {key}."
            )
        chosen.append(pr)

    steps: list[ConcludeStepOut] = []
    wrote = False
    async with factory.bitbucket_client(store) as bb:
        for pr in chosen:
            if pr.draft == payload.draft:
                steps.append(_draft_step(pr.repo_slug, pr.id, pr.url, payload.draft, already=True))
                continue
            step = await _set_draft(bb, pr.repo_slug, pr.id, pr.url, payload.draft)
            steps.append(step)
            if not step.ok:
                break
            wrote = True
    if wrote:
        await sync_after_write(engine, "rascunho" if payload.draft else "liberar")
    return ConcludeResultOut(
        issue_key=key,
        done=all(step.ok for step in steps),
        steps=steps,
        write_id=_announce(key) if wrote else None,
    )


def _draft_step(
    repo_slug: str, pr_id: int, url: str | None, draft: bool, *, already: bool = False
) -> ConcludeStepOut:
    where = f"PR #{pr_id} em {repo_slug}"
    if already:
        label = f"{where} já estava {'em rascunho' if draft else 'liberado'}"
    else:
        label = f"{where} {'foi para o rascunho' if draft else 'liberado para review'}"
    return ConcludeStepOut(kind="draft" if draft else "release", label=label, ok=True, url=url)


async def _set_draft(
    bb, repo_slug: str, pr_id: int, url: str | None, draft: bool
) -> ConcludeStepOut:
    kind = "draft" if draft else "release"
    label = f"{'Pôr em rascunho' if draft else 'Liberar'} o PR #{pr_id} em {repo_slug}"
    try:
        updated = await bb.set_draft(repo_slug, pr_id, draft)
    except PermissionDenied:
        return ConcludeStepOut(
            kind=kind,
            label=label,
            ok=False,
            url=url,
            message="Bitbucket: sem permissão para editar o PR — o token precisa do escopo "
            "write:pullrequest:bitbucket, ou o seu usuário não pode editar este PR.",
        )
    except IntegrationError as exc:
        logger.info("Rascunho recusado em %s#%s: %s", repo_slug, pr_id, exc.status)
        return ConcludeStepOut(
            kind=kind,
            label=label,
            ok=False,
            url=url,
            message=f"O Bitbucket recusou a mudança (HTTP {exc.status or '?'}) — confira no PR.",
        )
    if bool(updated.get("draft")) != draft:
        # O PUT passou e o PR não mudou: melhor dizer do que contar que mudou.
        return ConcludeStepOut(
            kind=kind,
            label=label,
            ok=False,
            url=url,
            message="O Bitbucket aceitou o pedido, mas o PR continua "
            f"{'fora do' if draft else 'em'} rascunho — confira no PR.",
        )
    return _draft_step(repo_slug, pr_id, url, draft)


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
