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

/** Status em que a review está andando: o badge mostra a foto de cada revisor e o "N/X". */
export const REVIEW_STATUSES = new Set(['ajustes_requisitados', 'pr_aberta', 'aprovada'])

/** Estado de cada revisor (`review.people` do back), por extenso para o title. */
export const REVIEW_PERSON_LABEL = {
  approved: 'aprovou',
  changes_requested: 'pediu ajustes',
  pending: 'falta revisar',
}

/**
 * Regras de Configurações › Pull requests (`min_percent` do back). 0 é a de antes — basta
 * uma aprovação — e continua sendo o padrão, para nenhum card mudar sozinho.
 */
export const APPROVAL_RULES = [
  { percent: 0, label: 'Uma aprovação', hint: 'O PR fica "Aprovada" com a primeira aprovação, qualquer que seja o número de revisores.' },
  { percent: 50, label: 'Pelo menos 50%', hint: 'Metade dos revisores precisa aprovar — com 3 revisores, são 2 aprovações.' },
  { percent: 100, label: 'Todos', hint: 'Todos os revisores precisam aprovar.' },
]

/** Por extenso, para o title — no badge fica só o "N/X". */
export function approvalsLabel({ approvals, reviewers }) {
  return `${approvals}/${reviewers} ${reviewers === 1 ? 'aprovação' : 'aprovações'}`
}
