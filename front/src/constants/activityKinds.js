/**
 * Tipos de evento do feed — espelha o `kind` gravado em `activity_event` (B8).
 * `text` é o que vai antes do título do evento; o título carrega o valor.
 */
export const ACTIVITY_KINDS = {
  status: { text: 'mudou o status para', icon: 'ArrowRightLeft', color: 'var(--color-info)' },
  assignee: { text: 'mudou o responsável para', icon: 'UserRound', color: 'var(--color-text-secondary)' },
  sprint: { text: 'moveu para', icon: 'CalendarRange', color: 'var(--color-text-secondary)' },
  story_points: { text: 'mudou os Story Points', icon: 'Hash', color: 'var(--color-text-secondary)' },
  priority: { text: 'mudou a prioridade para', icon: 'Flag', color: 'var(--color-text-secondary)' },
  comment: { text: 'comentou', icon: 'MessageSquare', color: 'var(--color-primary)' },
  comment_edited: { text: 'editou o comentário', icon: 'MessageSquare', color: 'var(--color-primary)' },

  pr_created: { text: 'abriu o PR', icon: 'GitPullRequest', color: 'var(--pr-open)' },
  pr_ready: { text: 'tirou do rascunho o PR', icon: 'GitPullRequest', color: 'var(--pr-open)' },
  pr_commit: { text: 'subiu commit no PR', icon: 'GitCommitHorizontal', color: 'var(--pr-branch)' },
  pr_comment: { text: 'comentou no PR', icon: 'MessageSquare', color: 'var(--color-primary)' },
  pr_approved: { text: 'aprovou o PR', icon: 'CircleCheck', color: 'var(--pr-approved)' },
  pr_changes_requested: { text: 'pediu ajustes no PR', icon: 'MessageSquareWarning', color: 'var(--pr-changes)' },
  pr_build_failed: { text: 'build falhou no PR', icon: 'CircleX', color: 'var(--color-error)' },
  pr_build_passed: { text: 'build passou no PR', icon: 'CircleCheck', color: 'var(--pr-approved)' },
  pr_merged: { text: 'mergeou o PR', icon: 'GitMerge', color: 'var(--pr-merged)' },
  pr_declined: { text: 'recusou o PR', icon: 'GitPullRequestClosed', color: 'var(--pr-declined)' },
  pr_superseded: { text: 'substituiu o PR', icon: 'GitPullRequestClosed', color: 'var(--pr-declined)' },
}

const FALLBACK = { text: 'mexeu', icon: 'Circle', color: 'var(--color-text-muted)' }

export function activityKindMeta(kind) {
  return ACTIVITY_KINDS[kind] ?? FALLBACK
}

/** Aba do painel da tarefa que faz sentido abrir para cada evento. */
export function activityTab(kind) {
  if (kind === 'comment' || kind === 'comment_edited') return 'historico'
  if (kind.startsWith('pr_')) return 'prs'
  return 'detalhes'
}
