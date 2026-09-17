/**
 * Status de PR — espelha `services/pr_status.py` do back (mesmas chaves e ordem de atenção).
 * Cores vêm dos tokens `--pr-*` (legenda do print de referência).
 */
export const PR_STATUS = {
  sem_pr: { label: 'Sem PR', color: 'var(--pr-none)', icon: 'CircleDashed' },
  branch_sem_pr: { label: 'Branch sem PR', color: 'var(--pr-branch)', icon: 'GitBranch' },
  ajustes_requisitados: { label: 'Ajustes requisitados', color: 'var(--pr-changes)', icon: 'MessageSquareWarning' },
  rascunho: { label: 'Rascunho', color: 'var(--pr-draft)', icon: 'FilePen' },
  pr_aberta: { label: 'PR aberta', color: 'var(--pr-open)', icon: 'GitPullRequest' },
  aprovada: { label: 'Aprovada', color: 'var(--pr-approved)', icon: 'CircleCheck' },
  mergeada: { label: 'Mergeada', color: 'var(--pr-merged)', icon: 'GitMerge' },
  recusada: { label: 'Recusada', color: 'var(--pr-declined)', icon: 'GitPullRequestClosed' },
  substituida: { label: 'Substituída', color: 'var(--pr-declined)', icon: 'GitPullRequestClosed' },
}

/** Ordem da legenda: do que pede mais atenção ao concluído. */
export const PR_STATUS_LEGEND = [
  'sem_pr',
  'branch_sem_pr',
  'ajustes_requisitados',
  'rascunho',
  'pr_aberta',
  'aprovada',
  'mergeada',
]

export function prStatusMeta(status) {
  return PR_STATUS[status] ?? PR_STATUS.sem_pr
}
