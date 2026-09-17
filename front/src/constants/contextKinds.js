import { CircleHelp, FileText, Lightbulb, Scale, Wrench } from 'lucide-vue-next'

/**
 * Tipos de contexto — mesmas chaves do CHECK da tabela `task_context`.
 * `color`/`bg` são tokens: as pastilhas precisam virar junto com o tema.
 */
export const CONTEXT_KINDS = {
  open_point: {
    label: 'Ponto em aberto',
    plural: 'Pontos em aberto',
    icon: CircleHelp,
    color: 'var(--color-warning-text)',
    bg: 'var(--color-warning-surface)',
    hint: 'Algo que ficou pendente e precisa ser resolvido nesta ou numa próxima tarefa.',
  },
  finding: {
    label: 'Achado',
    plural: 'Achados',
    icon: Lightbulb,
    color: 'var(--color-info-text)',
    bg: 'var(--color-info-surface)',
    hint: 'Algo que você descobriu sobre o código, o dado ou o comportamento.',
  },
  fix: {
    label: 'Correção',
    plural: 'Correções',
    icon: Wrench,
    color: 'var(--color-success-text)',
    bg: 'var(--color-success-surface)',
    hint: 'O que foi corrigido e como — para reaplicar quando o problema voltar.',
  },
  decision: {
    label: 'Decisão',
    plural: 'Decisões',
    icon: Scale,
    color: 'var(--color-accent-text)',
    bg: 'var(--color-accent-surface)',
    hint: 'Escolha feita e o porquê (alternativas descartadas).',
  },
  summary: {
    label: 'Resumo',
    plural: 'Resumos',
    icon: FileText,
    color: 'var(--color-neutral-text)',
    bg: 'var(--color-neutral-surface)',
    hint: 'Resumo do que a tarefa entregou.',
  },
}

export const CONTEXT_KIND_KEYS = Object.keys(CONTEXT_KINDS)

export const RELATION_LABEL = {
  relates: 'relaciona',
  continues: 'continua',
  resolves: 'resolvido em',
}
