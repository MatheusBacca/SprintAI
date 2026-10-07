import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import ProgressStagesPanel from '@/components/settings/ProgressStagesPanel.vue'

function json(body, status = 200) {
  return { ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => '' }
}

const STAGES = [
  { id: 'analise', label: 'Análise', order: 0, weight: 0, color: '#94a3b8' },
  { id: 'desenvolvimento', label: 'Desenvolvimento', order: 1, weight: 0.4, color: '#2f7cf6' },
  { id: 'review', label: 'Review', order: 2, weight: 0.7, color: '#f59e0b' },
]

let puts

beforeEach(() => {
  setActivePinia(createPinia())
  puts = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, init = {}) => {
      if (init.method === 'PUT') {
        puts.push(JSON.parse(init.body))
        return json({ stages: STAGES, statuses: [] })
      }
      return json({
        stages: STAGES,
        statuses: [
          { status: 'Em Desenvolvimento', status_category: 'indeterminate', issue_count: 2, stage_id: 'desenvolvimento' },
          // Ninguém em ajuste nesta semana: o back manda a linha mesmo assim, pela etapa salva.
          { status: 'AJUSTE', status_category: null, issue_count: 0, stage_id: 'desenvolvimento' },
        ],
      })
    }),
  )
})

afterEach(() => vi.unstubAllGlobals())

describe('Configurações › Progresso', () => {
  it('status sem tarefa agora continua na tabela e não perde a etapa ao salvar', async () => {
    const wrapper = mount(ProgressStagesPanel)
    await flushPromises()

    const row = wrapper.findAll('.statuses tbody tr').find((tr) => tr.text().includes('AJUSTE'))
    expect(row.find('.statuses__category').text()).toBe('—')
    expect(row.find('select').element.value).toBe('desenvolvimento')

    // Mexer em outra coisa e salvar manda o mapa inteiro — com o AJUSTE dentro.
    await wrapper.find('.stage__label').setValue('Triagem')
    await wrapper.find('.btn--primary').trigger('click')
    await flushPromises()
    expect(puts[0].statuses).toEqual({ 'Em Desenvolvimento': 'desenvolvimento', AJUSTE: 'desenvolvimento' })
  })
})
