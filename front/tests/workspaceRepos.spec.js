import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import WorkspaceReposPanel from '@/components/settings/WorkspaceReposPanel.vue'

function json(status, body) {
  return { ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => '' }
}

function repo(slug, extra = {}) {
  return {
    slug,
    path: `C:\\projects\\${slug}`,
    present: true,
    has_git: true,
    remote_url: `git@bitbucket.org:weonrepo/${slug}.git`,
    bb_slug: slug,
    link: 'auto',
    in_mirror: true,
    base_branch: 'main',
    base_source: 'bitbucket',
    current_branch: 'main',
    detached: false,
    detected_at: '2026-10-02T12:00:00Z',
    ...extra,
  }
}

describe('WorkspaceReposPanel', () => {
  let calls
  let repos

  beforeEach(() => {
    setActivePinia(createPinia())
    calls = []
    repos = [
      repo('monitoria', { current_branch: 'WAI-8790-rota' }),
      repo('appingos', { bb_slug: null, in_mirror: false, remote_url: 'https://github.com/x/y.git', base_source: 'origin' }),
      repo('mcp', { has_git: false, bb_slug: null, in_mirror: false, base_branch: null, base_source: null, current_branch: null }),
      repo('antigo', { present: false, link: 'auto' }),
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, init = {}) => {
        const body = init.body ? JSON.parse(init.body) : undefined
        calls.push({ method: init.method ?? 'GET', url, body })
        if (init.method === 'PUT') {
          const slug = url.split('/').pop()
          const updated = repo(slug, {
            link: body.link,
            bb_slug: body.link === 'none' ? null : body.bb_slug ?? slug,
            base_branch: body.base_branch ?? 'main',
            base_source: body.base_branch ? 'manual' : 'bitbucket',
          })
          repos = repos.map((r) => (r.slug === slug ? updated : r))
          return json(200, updated)
        }
        return json(200, { root: 'C:\\projects', repos })
      }),
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  async function mountPanel() {
    const wrapper = mount(WorkspaceReposPanel)
    await flushPromises()
    return wrapper
  }

  const row = (wrapper, slug) => wrapper.find(`.row[data-repo="${slug}"]`)

  it('lista as pastas presentes com vínculo, base e branch atual, e esconde a que sumiu sem ajuste', async () => {
    const wrapper = await mountPanel()

    expect(row(wrapper, 'monitoria').text()).toContain('no espelho')
    expect(row(wrapper, 'monitoria').text()).toContain('WAI-8790-rota')
    expect(row(wrapper, 'monitoria').text()).toContain('do Bitbucket')
    expect(row(wrapper, 'monitoria').find('select option').text()).toBe('Automático (monitoria)')
    expect(row(wrapper, 'appingos').find('select option').text()).toBe('Automático (nenhum)')
    expect(row(wrapper, 'mcp').text()).toContain('sem git')
    expect(row(wrapper, 'mcp').find('select').attributes('disabled')).toBeDefined()
    expect(row(wrapper, 'antigo').exists()).toBe(false)
    expect(row(wrapper, 'monitoria').find('.btn--primary').exists()).toBe(false)
  })

  it('ajustar a base e desligar o vínculo manda o PUT só da linha mexida', async () => {
    const wrapper = await mountPanel()
    const monitoria = () => row(wrapper, 'monitoria')

    await monitoria().find('select').setValue('none')
    await monitoria().find('.row__base').setValue('release/1.0')
    await monitoria().find('.btn--primary').trigger('click')
    await flushPromises()

    const put = calls.find((c) => c.method === 'PUT')
    expect(put.url).toContain('/workspace/repos/monitoria')
    expect(put.body).toEqual({ link: 'none', bb_slug: null, base_branch: 'release/1.0' })
    expect(monitoria().text()).toContain('definida aqui')
    expect(monitoria().find('.row__feedback').attributes('data-type')).toBe('success')
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(1)
  })

  it('vínculo manual pede o slug e "Descartar" volta ao que está salvo', async () => {
    const wrapper = await mountPanel()
    const appingos = () => row(wrapper, 'appingos')

    await appingos().find('select').setValue('manual')
    expect(appingos().find('.row__slug').exists()).toBe(true)
    await appingos().find('.btn--secondary').trigger('click')
    expect(appingos().find('select').element.value).toBe('auto')
    expect(appingos().find('.row__slug').exists()).toBe(false)
    expect(calls.some((c) => c.method === 'PUT')).toBe(false)
  })
})
