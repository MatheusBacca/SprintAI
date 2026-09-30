import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import CardColorsPanel from '@/components/settings/CardColorsPanel.vue'

function json(status, body) {
  return { ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => '' }
}

const TYPES = [
  { id: 'epico', label: 'Épico', color: '#7c3aed', default_color: '#7c3aed' },
  { id: 'enhancements', label: 'Enhancements', color: '#c9a227', default_color: '#c9a227' },
  { id: 'feature', label: 'Feature', color: '#15803d', default_color: '#15803d' },
]

describe('CardColorsPanel', () => {
  let calls
  let stored

  beforeEach(() => {
    setActivePinia(createPinia())
    calls = []
    stored = {
      types: TYPES,
      repos: [
        { slug: 'monitoria', color: null, synced: true },
        { slug: 'node-red4', color: '#0d9488', synced: false },
        { slug: 'qualificai', color: null, synced: true },
      ],
      suggestions: ['#2f7cf6', '#0d9488', '#ea580c'],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, init = {}) => {
        const body = init.body ? JSON.parse(init.body) : undefined
        calls.push({ method: init.method ?? 'GET', url, body })
        if (init.method === 'PUT') {
          stored = {
            ...stored,
            types: stored.types.map((t) => ({ ...t, color: body.types[t.id] })),
            repos: stored.repos.map((r) => ({ ...r, color: body.repos[r.slug] })),
          }
        }
        return json(200, stored)
      }),
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  async function mountPanel() {
    const wrapper = mount(CardColorsPanel, { global: { stubs: { RouterLink: true } } })
    await flushPromises()
    return wrapper
  }

  const row = (wrapper, attr, value) => wrapper.find(`.row[${attr}="${value}"]`)

  it('mostra os tipos com cor e os repositórios, avisando quem saiu da sincronização', async () => {
    const wrapper = await mountPanel()

    expect(row(wrapper, 'data-type', 'epico').find('.preview--tinted').attributes('style')).toContain('--tint: #7c3aed')
    expect(row(wrapper, 'data-repo', 'monitoria').find('.preview--tinted').exists()).toBe(false)
    expect(row(wrapper, 'data-repo', 'monitoria').find('.row__define').exists()).toBe(true)
    expect(row(wrapper, 'data-repo', 'node-red4').text()).toContain('fora da sincronização')
    expect(wrapper.find('.btn--primary').attributes('disabled')).toBeDefined()
  })

  it('"Definir cor" pula as sugestões já em uso e o salvar manda o mapa inteiro', async () => {
    const wrapper = await mountPanel()

    await row(wrapper, 'data-repo', 'monitoria').find('.row__define').trigger('click')
    await row(wrapper, 'data-repo', 'qualificai').find('.row__define').trigger('click')
    // #0d9488 já é do node-red4: o qualificai fica com a terceira sugestão.
    expect(row(wrapper, 'data-repo', 'monitoria').find('input[type="color"]').element.value).toBe('#2f7cf6')
    expect(row(wrapper, 'data-repo', 'qualificai').find('input[type="color"]').element.value).toBe('#ea580c')

    await row(wrapper, 'data-type', 'feature').find('.row__clear').trigger('click')
    await wrapper.find('.btn--primary').trigger('click')
    await flushPromises()

    const put = calls.find((c) => c.method === 'PUT')
    expect(put.url).toContain('/preferences/card-colors')
    expect(put.body).toEqual({
      types: { epico: '#7c3aed', enhancements: '#c9a227', feature: null },
      repos: { monitoria: '#2f7cf6', 'node-red4': '#0d9488', qualificai: '#ea580c' },
    })
    expect(row(wrapper, 'data-type', 'feature').find('.row__define').exists()).toBe(true)
    expect(wrapper.find('.colors__feedback').attributes('data-type')).toBe('success')
  })

  it('cor trocada no seletor pinta a prévia antes de salvar, e "Padrão" e "Descartar" desfazem', async () => {
    const wrapper = await mountPanel()
    const epico = () => row(wrapper, 'data-type', 'epico')

    await epico().find('input[type="color"]').setValue('#5b21b6')
    expect(epico().find('.preview').attributes('style')).toContain('--tint: #5b21b6')

    await epico().find('button[title="Voltar à cor padrão"]').trigger('click')
    expect(epico().find('.preview').attributes('style')).toContain('--tint: #7c3aed')
    expect(wrapper.find('.btn--primary').attributes('disabled')).toBeDefined()

    await row(wrapper, 'data-repo', 'node-red4').find('.row__clear').trigger('click')
    expect(wrapper.find('.btn--primary').attributes('disabled')).toBeUndefined()
    await wrapper.find('.colors__footer .btn--secondary').trigger('click')
    expect(row(wrapper, 'data-repo', 'node-red4').find('input[type="color"]').element.value).toBe('#0d9488')
    expect(calls.some((c) => c.method === 'PUT')).toBe(false)
  })

  it('sem repositório escolhido aponta para a Sincronização', async () => {
    stored.repos = []
    const wrapper = await mountPanel()

    expect(wrapper.find('.row[data-repo]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Nenhum repositório escolhido')
  })
})
