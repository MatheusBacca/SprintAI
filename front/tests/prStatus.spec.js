import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import PrStatusBadge from '@/components/pr/PrStatusBadge.vue'
import { PR_STATUS, PR_STATUS_LEGEND, prStatusMeta } from '@/constants/prStatus'

// Mesmas chaves do enum PrStatus do back (services/pr_status.py).
const BACKEND_STATUSES = [
  'sem_pr',
  'branch_sem_pr',
  'ajustes_requisitados',
  'rascunho',
  'pr_aberta',
  'aprovada',
  'mergeada',
  'recusada',
  'substituida',
]

describe('constantes de status de PR', () => {
  it('cobre todos os status do back', () => {
    expect(Object.keys(PR_STATUS).sort()).toEqual([...BACKEND_STATUSES].sort())
  })

  it('status desconhecido cai em Sem PR', () => {
    expect(prStatusMeta('xpto').label).toBe('Sem PR')
  })

  it('legenda segue a ordem de atenção do back', () => {
    expect(PR_STATUS_LEGEND).toEqual(BACKEND_STATUSES.slice(0, 7))
  })
})

describe('PrStatusBadge', () => {
  it('mostra rótulo, cor do token e contador quando há mais de um PR', () => {
    const wrapper = mount(PrStatusBadge, { props: { status: 'ajustes_requisitados', prCount: 2 } })

    expect(wrapper.text()).toContain('Ajustes requisitados')
    expect(wrapper.find('.pr-badge__count').text()).toBe('2 PRs')
    expect(wrapper.attributes('style')).toContain('--badge-color: var(--pr-changes)')
    expect(wrapper.attributes('title')).toBe('Ajustes requisitados · 2 PRs')
  })

  it('não mostra contador com um PR e sinaliza build falhando', () => {
    const wrapper = mount(PrStatusBadge, { props: { status: 'pr_aberta', prCount: 1, buildFailed: true } })

    expect(wrapper.find('.pr-badge__count').exists()).toBe(false)
    expect(wrapper.find('[aria-label="build falhando"]').exists()).toBe(true)
    expect(wrapper.attributes('title')).toBe('PR aberta · build falhando')
  })
})

