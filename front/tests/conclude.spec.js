import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import ConcludeButton from '@/components/jira/ConcludeButton.vue'
import JiraActionPopover from '@/components/jira/JiraActionPopover.vue'
import PrReviewers from '@/components/pr/PrReviewers.vue'
import ConcludeSettingsPanel from '@/components/settings/ConcludeSettingsPanel.vue'
import IssueNode from '@/components/sprint/IssueNode.vue'
import { useJiraActionsStore } from '@/stores/jiraActions'

function json(body, status = 200) {
  return { ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => '' }
}

let calls
let routes

beforeEach(() => {
  setActivePinia(createPinia())
  calls = []
  routes = {}
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, init = {}) => {
      const method = init.method ?? 'GET'
      const body = init.body ? JSON.parse(init.body) : undefined
      calls.push({ method, url, body })
      const reply = routes[`${method} ${url}`]
      if (!reply) throw new Error(`não mockado: ${method} ${url}`)
      return typeof reply === 'function' ? reply(body) : reply
    }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const MERGE = {
  repo_slug: 'monitoria',
  pr_id: 412,
  title: 'WAI-1 trial',
  url: 'https://bitbucket.org/weonrepo/monitoria/pull-requests/412',
  source_branch: 'feature/WAI-1',
  destination_branch: 'develop',
  strategy: 'squash',
  close_source_branch: true,
  warnings: ['build falhou'],
}

function plan(extra = {}) {
  return {
    issue_key: 'WAI-1',
    status: 'Em Review',
    repos: ['monitoria'],
    merges: [MERGE],
    targets: [{ status: 'DISPONIVEL PARA TESTES', current: false, available: true, reason: null }],
    notes: [],
    ...extra,
  }
}

async function openPlan(data) {
  routes['GET /api/issues/WAI-1/conclude'] = json(data)
  const popover = mount(JiraActionPopover, { attachTo: document.body })
  const button = mount(ConcludeButton, { props: { issueKey: 'WAI-1' }, attachTo: document.body })
  await button.find('button').trigger('click')
  await flushPromises()
  return { popover, button, panel: () => document.body.querySelector('.conclude') }
}

const click = (el) => el.dispatchEvent(new MouseEvent('click', { bubbles: true }))

describe('Concluir', () => {
  it('o botão abre o plano no painel único: merge com avisos e o status do Jira', async () => {
    const { panel } = await openPlan(plan())

    expect(useJiraActionsStore().open.kind).toBe('conclude')
    const text = panel().textContent
    expect(text).toContain('Mergear o PR #412 em monitoria')
    expect(text).toContain('feature/WAI-1 → develop')
    expect(text).toContain('squash · fecha a branch')
    expect(text).toContain('build falhou')
    expect(text).toContain('Mover para DISPONIVEL PARA TESTES')
    expect(text).toContain('só depois que o merge entrar')
    // Nada roda antes da confirmação.
    expect(calls.filter((c) => c.method === 'POST')).toEqual([])
  })

  it('confirmar manda o que o plano mostrou e fica com o resultado de cada passo', async () => {
    routes['POST /api/issues/WAI-1/conclude'] = json({
      issue_key: 'WAI-1',
      done: true,
      status: 'DISPONIVEL PARA TESTES',
      write_id: 'w1',
      steps: [
        { kind: 'merge', label: 'PR #412 em monitoria mergeado (squash)', ok: true, url: MERGE.url },
        { kind: 'transition', label: 'Movida para DISPONIVEL PARA TESTES', ok: true },
      ],
    })
    const { panel } = await openPlan(plan())

    click(panel().querySelector('.conclude__confirm'))
    await flushPromises()

    expect(calls.at(-1)).toEqual({
      method: 'POST',
      url: '/api/issues/WAI-1/conclude',
      body: { jira_status: 'DISPONIVEL PARA TESTES', merges: [{ repo_slug: 'monitoria', pr_id: 412 }] },
    })
    const steps = [...panel().querySelectorAll('.conclude__step')].map((li) => li.dataset.ok)
    expect(steps).toEqual(['true', 'true'])
    expect(panel().textContent).toContain('Concluída')
    expect(useJiraActionsStore().lastWrite).toMatchObject({ id: 'w1', key: 'WAI-1' })
  })

  it('merge recusado mostra o passo que falhou e diz que o resto não rodou', async () => {
    routes['POST /api/issues/WAI-1/conclude'] = json({
      issue_key: 'WAI-1',
      done: false,
      status: null,
      write_id: null,
      steps: [{ kind: 'merge', label: 'Merge do PR #412 em monitoria', ok: false, message: 'O Bitbucket recusou o merge (HTTP 400)', url: MERGE.url }],
    })
    const { panel } = await openPlan(plan())

    click(panel().querySelector('.conclude__confirm'))
    await flushPromises()

    expect(panel().querySelector('.conclude__step').dataset.ok).toBe('false')
    expect(panel().textContent).toContain('recusou o merge')
    expect(panel().textContent).toContain('o que vinha depois não rodou')
    expect(panel().querySelector('.conclude__link').getAttribute('href')).toBe(MERGE.url)
    expect(useJiraActionsStore().lastWrite).toBeNull()
  })

  it('dois status pedem escolha antes de confirmar; o indisponível não se escolhe', async () => {
    routes['POST /api/issues/WAI-1/conclude'] = json({ issue_key: 'WAI-1', done: true, steps: [], write_id: null })
    const { panel } = await openPlan(
      plan({
        merges: [],
        targets: [
          { status: 'DISPONIVEL PARA TESTES', current: false, available: true, reason: null },
          { status: 'Concluído', current: false, available: false, reason: 'O Jira não oferece' },
        ],
      }),
    )

    const confirm = panel().querySelector('.conclude__confirm')
    expect(confirm.disabled).toBe(true)
    const [testes, concluido] = panel().querySelectorAll('.conclude__choice input')
    expect(concluido.disabled).toBe(true)
    testes.click()
    await flushPromises()
    expect(confirm.disabled).toBe(false)
    click(confirm)
    await flushPromises()
    expect(calls.at(-1).body).toEqual({ jira_status: 'DISPONIVEL PARA TESTES', merges: [] })
  })

  it('card que deixou de estar apto mostra o motivo e não confirma', async () => {
    const { panel } = await openPlan(plan({ blocked: 'PR #412 ainda não está aprovado pela regra de Configurações › Pull requests.' }))

    expect(panel().querySelector('.conclude__error').textContent).toContain('ainda não está aprovado')
    expect(panel().querySelector('.conclude__confirm').disabled).toBe(true)
  })

  it('status que o Jira não oferece bloqueia, com o motivo na tela', async () => {
    const { panel } = await openPlan(
      plan({ targets: [{ status: 'Concluído', current: false, available: false, reason: 'O Jira não oferece a ida para “Concluído” agora.' }] }),
    )

    expect(panel().textContent).toContain('O Jira não oferece a ida')
    expect(panel().querySelector('.conclude__confirm').disabled).toBe(true)
  })

  it('o card mostra o Concluir à direita do selo do PR só quando o repo tem receita', () => {
    const issue = {
      key: 'WAI-9',
      summary: 'Trial',
      issue_type: 'Tarefa',
      status: 'Em Review',
      status_category: 'indeterminate',
      story_points: 3,
      in_sprint: true,
      partial: false,
      blocked_by: [],
      blockers_without_pr: [],
      children: [],
      pr: { status: 'aprovada', status_label: 'Aprovada', pr_count: 1, build_failed: false },
    }
    const mountNode = (extra) =>
      mount(IssueNode, { props: { data: { issue: { ...issue, ...extra }, selected: false } }, global: { stubs: { Handle: true } } })

    const footer = mountNode({ conclude: true }).find('.node__footer')
    const parts = footer.findAll('.pr-badge, .conclude-btn').map((el) => el.classes()[0])
    expect(parts).toEqual(['pr-badge', 'conclude-btn'])
    expect(footer.find('.conclude-btn').classes()).toContain('nodrag')
    expect(mountNode({ conclude: false }).find('.conclude-btn').exists()).toBe(false)
    expect(mountNode({ conclude: true, in_sprint: false }).find('.conclude-btn').exists()).toBe(false)
  })
})

describe('reviewers do PR', () => {
  const PR = {
    repo_slug: 'monitoria',
    id: 412,
    state: 'OPEN',
    reviewers: [
      { name: 'Rafael', role: 'REVIEWER', approved: true, state: 'approved', account_id: 'acc-rafa' },
      { name: 'Ju', role: 'REVIEWER', approved: false, state: null, account_id: 'acc-ju' },
      // Aprovou sem ser revisor designado: aparece, mas não tem o que tirar.
      { name: 'Bia', role: 'PARTICIPANT', approved: true, state: 'approved', account_id: 'acc-bia' },
    ],
  }

  const chip = (wrapper, name) => wrapper.findAll('.reviewers__chip').find((c) => c.text().startsWith(name))

  it('tirar pede o segundo clique e avisa que a aprovação sai junto', async () => {
    routes['PUT /api/pull-requests/monitoria/412/reviewers'] = json({
      repo_slug: 'monitoria',
      pr_id: 412,
      reviewers: [{ account_id: 'acc-ju', uuid: '{j}', name: 'Ju', approved: false, state: null }],
    })
    const wrapper = mount(PrReviewers, { props: { pr: PR } })

    expect(chip(wrapper, 'Bia').find('.reviewers__remove').exists()).toBe(false)
    const remove = chip(wrapper, 'Rafael').find('.reviewers__remove')
    await remove.trigger('click')
    expect(remove.text()).toBe('Tirar?')
    expect(remove.attributes('title')).toContain('aprovação dele sai junto')
    expect(calls).toEqual([])

    await remove.trigger('click')
    await flushPromises()
    expect(calls).toEqual([{ method: 'PUT', url: '/api/pull-requests/monitoria/412/reviewers', body: { add: [], remove: ['acc-rafa'] } }])
    // A lista que o Bitbucket devolveu fica na tela até o espelho chegar.
    expect(wrapper.findAll('.reviewers__chip').map((c) => c.text())).toEqual(['Ju'])
  })

  it('pôr escolhe entre os membros do workspace (sem quem já está e sem o próprio dev) e confirma', async () => {
    routes['GET /api/bitbucket/members'] = json({
      members: [
        { account_id: 'acc-me', uuid: '{m}', name: 'Matheus', is_me: true },
        { account_id: 'acc-rafa', uuid: '{r}', name: 'Rafael', is_me: false },
        { account_id: 'acc-carla', uuid: '{c}', name: 'Carla Souza', nickname: 'carla', is_me: false },
        { account_id: 'acc-du', uuid: '{d}', name: 'Eduardo', is_me: false },
      ],
    })
    routes['PUT /api/pull-requests/monitoria/412/reviewers'] = json({ repo_slug: 'monitoria', pr_id: 412, reviewers: [] })
    const wrapper = mount(PrReviewers, { props: { pr: PR } })

    await wrapper.find('.reviewers__add').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.reviewers__option').map((o) => o.text())).toEqual(['Carla Souzacarla', 'Eduardo'])

    await wrapper.find('.reviewers__search').setValue('carla')
    expect(wrapper.findAll('.reviewers__option')).toHaveLength(1)
    await wrapper.find('.reviewers__option').trigger('click')
    expect(wrapper.find('.reviewers__ask').text()).toBe('Adicionar Carla Souza como reviewer do PR #412?')
    expect(calls.filter((c) => c.method === 'PUT')).toEqual([])

    await wrapper.find('.reviewers__actions .btn--primary').trigger('click')
    await flushPromises()
    expect(calls.at(-1)).toEqual({ method: 'PUT', url: '/api/pull-requests/monitoria/412/reviewers', body: { add: ['acc-carla'], remove: [] } })
    expect(wrapper.find('.reviewers__picker').exists()).toBe(false)
  })

  it('o erro do Bitbucket aparece no PR, e PR fechado não edita', async () => {
    routes['PUT /api/pull-requests/monitoria/412/reviewers'] = json({ detail: 'Bitbucket: sem permissão para mudar os reviewers' }, 502)
    const wrapper = mount(PrReviewers, { props: { pr: PR } })
    const remove = chip(wrapper, 'Ju').find('.reviewers__remove')
    await remove.trigger('click')
    await remove.trigger('click')
    await flushPromises()
    expect(wrapper.find('.reviewers__error').text()).toContain('sem permissão')

    const merged = mount(PrReviewers, { props: { pr: { ...PR, state: 'MERGED' } } })
    expect(merged.find('.reviewers__remove').exists()).toBe(false)
    expect(merged.find('.reviewers__add').exists()).toBe(false)
  })
})

describe('Configurações › Concluir', () => {
  it('lista os repos da Sincronização e salva só quem tem receita', async () => {
    routes['GET /api/preferences/conclude'] = json({
      repos: { monitoria: { jira_status: 'DISPONIVEL PARA TESTES', merge: true, strategy: 'squash', close_source_branch: true } },
      known_repos: ['monitoria', 'qualificai'],
      statuses: ['Em Review', 'Concluído'],
    })
    routes['PUT /api/preferences/conclude'] = (body) =>
      json({ repos: body.repos, known_repos: ['monitoria', 'qualificai'], statuses: ['Em Review', 'Concluído'] })
    const wrapper = mount(ConcludeSettingsPanel)
    await flushPromises()

    const row = (slug) => wrapper.find(`tr[data-repo="${slug}"]`)
    expect(row('monitoria').text()).toContain('mergeia (squash) e leva a “DISPONIVEL PARA TESTES”')
    expect(row('qualificai').text()).toContain('sem Concluir')
    expect(row('qualificai').find('select').attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('#conclude-statuses option').map((o) => o.attributes('value'))).toEqual(['Em Review', 'Concluído'])

    await row('qualificai').find('input[type="text"]').setValue('Concluído')
    await wrapper.find('.btn--primary').trigger('click')
    await flushPromises()
    expect(calls.at(-1).body).toEqual({
      repos: {
        monitoria: { jira_status: 'DISPONIVEL PARA TESTES', merge: true, strategy: 'squash', close_source_branch: true },
        qualificai: { jira_status: 'Concluído', merge: false, strategy: 'merge_commit', close_source_branch: true },
      },
    })
    expect(wrapper.find('.conclude-settings__feedback').attributes('data-type')).toBe('success')
  })
})
