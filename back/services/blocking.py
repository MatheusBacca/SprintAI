"""Quando um bloqueio ainda segura a tarefa — regra única do card do canvas e do painel.

O bloqueio só "pesa" enquanto o bloqueador não abriu PR: com a PR aberta já há código
de onde partir. Rascunho ainda não conta — é PR que o próprio autor diz não estar
pronta. Bloqueador concluído nem chega aqui (sai antes, em quem monta a lista).
"""

from collections.abc import Iterable, Mapping

from services.pr_status import IssuePrSummary, PrStatus

PR_RELEASES_BLOCK = frozenset(
    {PrStatus.PR_ABERTA, PrStatus.AJUSTES_REQUISITADOS, PrStatus.APROVADA, PrStatus.MERGEADA}
)


def blockers_without_pr(
    blocker_keys: Iterable[str], summaries: Mapping[str, IssuePrSummary]
) -> list[str]:
    """Bloqueadores que ainda não abriram PR. Sem resumo (fora do espelho) conta como sem PR."""
    return [
        key
        for key in blocker_keys
        if key not in summaries or summaries[key].status not in PR_RELEASES_BLOCK
    ]
