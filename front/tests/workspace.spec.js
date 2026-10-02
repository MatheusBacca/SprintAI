import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import RepoTimeline from '@/components/workspace/RepoTimeline.vue'
import WorkspaceView from '@/views/WorkspaceView.vue'
import { routes } from '@/router/routes'
import { useScreenContextStore } from '@/stores/screenContext'

function json(body, status = 200) {
  return { ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => '' }
}

const NO_CONTENT = { ok: true, status: 204, headers: new Headers(), json: async () => null, text: async () => '' }

function workspace(id, extra = {}) {
  return {
    id,
    kind: 'issue',
    root_issue_key: 'WAI-8677',
    title: 'Plano gratuito do QualificAI',
    issue_type: 'Enhancements',
    status: 'Disponivel para análise',
    is_open: true,
    tab_order: 0,
    created_at: '2026-10-02T12:00:00Z',
    last_opened_at: '2026-10-02T12:00:00Z',
    ...extra,
  }
}

function repo(slug, extra = {}) {
  return {
    slug,
    path: `C:\\projects\\${slug}`,
    local: true,
    bb_slug: slug,
    base_branch: 'develop',
    current_branch: 'develop',
    sources: ['branch', 'title'],
    branches: [`feature/WAI-8792`],
    issue_keys: ['WAI-8792'],
    hidden: false,
    ...extra,
  }
}

const TREE = {
  workspace_id: 1,
  frame: { id: 'workspace:1', label: 'na feature' },
  counters: { tasks: 2, parents: 1, blocked: 0, mine: 2, story_points: 5, done: 0 },
  nodes: [
    { key: 'WAI-8677', summary: 'Plano gratuito', issue_type: 'Enhancements', in_sprint: true, title_parts: [], unseen_changes: [] },
    { key: 'WAI-8792', summary: '[weaction-api] Trial', issue_type: 'Tarefa', in_sprint: true, title_parts: [], unseen_changes: ['status'] },
  ],
  edges: [],
  groups: [],
}

const CANVAS_STUB = {
  name: 'SprintCanvas',
  props: ['tree', 'selectedKey', 'rightInset', 'flowId'],
  emits: ['select'],
  template: '<div class="canvas-stub" />',
}
const DOCK_STUB = {
  name: 'TerminalDock',
  props: ['repos', 'allRepos', 'selectedRepo', 'collapsed'],
  emits: ['toggle', 'pin-repo', 'open-folder'],
  template: '<div class="dock-stub" />',
}
const TIMELINE_STUB = {
  name: 'RepoTimeline',
  props: ['repos', 'repo', 'keys', 'highlightKeys'],
  emits: ['select-repo', 'open-issue'],
  template: '<div class="timeline-stub" />',
}

describe('WorkspaceView', () => {
  let calls
  let list
  let detail

  beforeEach(() => {
    setActivePinia(createPinia())
    calls = []
    list = [workspace(1), workspace(2, { root_issue_key: null, kind: 'free', title: 'Testes', is_open: false })]
    detail = {
      workspace: workspace(1),
      keys: ['WAI-8677', 'WAI-8792'],
      repos: [repo('weaction-api'), repo('qualificai', { sources: ['pr'], branches: [] }), repo('monitoria', { hidden: true })],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, init = {}) => {
        const method = init.method ?? 'GET'
        const body = init.body ? JSON.parse(init.body) : undefined
        calls.push({ method, url, body })
        if (url === '/api/workspaces' && method === 'GET') return json(list)
        if (url === '/api/workspaces' && method === 'POST') {
          const created = workspace(3, { root_issue_key: body.root_issue_key, title: 'Nova feature' })
          list = [...list, created]
          return json(created, 201)
        }
        if (url.match(/^\/api\/workspaces\/\d+$/) && method === 'PATCH') {
          const id = Number(url.split('/').pop())
          list = list.map((w) => (w.id === id ? { ...w, ...body } : w))
          return json(list.find((w) => w.id === id))
        }
        if (url === '/api/workspaces/1') return json(detail)
        if (url === '/api/workspaces/1/tree') return json(TREE)
        if (url.startsWith('/api/workspaces/1/repos/')) return NO_CONTENT
        if (url === '/api/workspace/repos') return json({ root: 'C:\\projects', repos: [] })
        if (url === '/api/workspace/open') return NO_CONTENT
        if (url.startsWith('/api/issues/') && url.endsWith('/seen')) return NO_CONTENT
        if (url.startsWith('/api/issues/WAI-8677')) return json({ key: 'WAI-8677', summary: 'Plano gratuito do QualificAI', status: 'Disponivel para análise', issue_type: 'Enhancements', story_points: null, updated_at: '2026-09-24T12:00:00Z', description_text: 'Toda empresa ganha 7 dias.', pull_requests: { status: 'sem_pr', pr_count: 0, build_failed: false, links: [], review: null } })
        throw new Error(`não mockado: ${method} ${url}`)
      }),
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  async function mountView(query = '') {
    const router = createRouter({ history: createMemoryHistory(), routes })
    router.push(`/workspace${query}`)
    await router.isReady()
    const wrapper = mount(WorkspaceView, {
      global: { plugins: [router], stubs: { SprintCanvas: CANVAS_STUB, RepoTimeline: TIMELINE_STUB, TerminalDock: DOCK_STUB, IssueDrawer: true } },
    })
    await flushPromises()
    return { wrapper, router }
  }

  it('sem workspace na URL abre a primeira aba aberta', async () => {
    const { wrapper, router } = await mountView()
    expect(router.currentRoute.value.query.ws).toBe('1')
    expect(wrapper.findAll('.tabs__item').map((t) => t.attributes('data-id'))).toEqual(['1'])
  })

  it('mostra a tarefa raiz, os repos com a fonte e a árvore no canvas da feature', async () => {
    const { wrapper } = await mountView('?ws=1')

    expect(wrapper.find('.side__title').text()).toBe('Plano gratuito do QualificAI')
    expect(wrapper.find('.side__desc').text()).toBe('Toda empresa ganha 7 dias.')
    const repos = wrapper.findAll('.repo').map((r) => r.attributes('data-repo'))
    expect(repos).toEqual(['weaction-api', 'qualificai'])
    expect(wrapper.find('.repo[data-repo="weaction-api"]').text()).toContain('branch local · título')
    expect(wrapper.find('.repo[data-repo="weaction-api"]').text()).toContain('feature/WAI-8792')
    expect(wrapper.find('.side__toggle').text()).toBe('1 escondido(s)')

    const canvas = wrapper.findComponent({ name: 'SprintCanvas' })
    expect(canvas.props('flowId')).toBe('workspace-tree')
    expect(canvas.props('tree').frame.label).toBe('na feature')
    expect(useScreenContextStore().view).toBe('workspace')
    expect(useScreenContextStore().visibleIssueKeys).toEqual(['WAI-8677', 'WAI-8792'])
  })

  it('card aberto vai para a URL e apaga a bolinha; repo escolhido leva à linha do tempo', async () => {
    const { wrapper, router } = await mountView('?ws=1')

    wrapper.findComponent({ name: 'SprintCanvas' }).vm.$emit('select', 'WAI-8792')
    await flushPromises()
    expect(router.currentRoute.value.query.tarefa).toBe('WAI-8792')
    expect(calls.some((c) => c.method === 'POST' && c.url === '/api/issues/WAI-8792/seen')).toBe(true)

    await wrapper.find('.repo[data-repo="qualificai"] .repo__main').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toMatchObject({ aba: 'linha', repo: 'qualificai' })
    const timeline = wrapper.findComponent({ name: 'RepoTimeline' })
    expect(timeline.props('repo')).toBe('qualificai')
    expect(timeline.props('keys')).toEqual(['WAI-8677', 'WAI-8792'])
    expect(timeline.props('highlightKeys')).toEqual(['WAI-8792'])
    // Os terminais acompanham o repo escolhido e só os repos com clone local.
    const dock = wrapper.findComponent({ name: 'TerminalDock' })
    expect(dock.props('selectedRepo')).toBe('qualificai')
    expect(dock.props('repos').map((r) => r.slug)).toEqual(['weaction-api', 'qualificai'])

    dock.vm.$emit('pin-repo', 'supervisor-web')
    dock.vm.$emit('toggle')
    await flushPromises()
    expect(calls).toContainEqual({ method: 'PUT', url: '/api/workspaces/1/repos/supervisor-web', body: { mode: 'add' } })
    expect(dock.props('collapsed')).toBe(true)
  })

  it('lado a lado mostra as duas telas, a divisão ajusta e fica salva', async () => {
    localStorage.removeItem('sprintai.workspace.split')
    const { wrapper, router } = await mountView('?ws=1&aba=lado')

    expect(wrapper.find('.canvas-stub').exists()).toBe(true)
    expect(wrapper.find('.timeline-stub').exists()).toBe(true)
    const tasks = () => wrapper.find('.ws-main__pane--tasks').attributes('style')
    expect(tasks()).toContain('flex-basis: 50%')

    const splitter = wrapper.find('.ws-main__splitter')
    await splitter.trigger('keydown', { key: 'ArrowRight' })
    await splitter.trigger('keydown', { key: 'ArrowRight' })
    expect(tasks()).toContain('flex-basis: 60%')
    expect(localStorage.getItem('sprintai.workspace.split')).toBe('0.6')
    await splitter.trigger('dblclick')
    expect(tasks()).toContain('flex-basis: 50%')

    // Trocar de repo pela coluna não tira o canvas da tela.
    await wrapper.find('.repo[data-repo="qualificai"] .repo__main').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toMatchObject({ aba: 'lado', repo: 'qualificai' })
    expect(wrapper.find('.canvas-stub').exists()).toBe(true)
  })

  it('esconder repo, abrir no VS Code e fechar a aba', async () => {
    const { wrapper, router } = await mountView('?ws=1')

    await wrapper.find('.repo[data-repo="qualificai"] .repo__action[title="Esconder deste workspace"]').trigger('click')
    await wrapper.find('.repo[data-repo="weaction-api"] .repo__action[title="Abrir no VS Code"]').trigger('click')
    await flushPromises()
    expect(calls).toContainEqual({ method: 'PUT', url: '/api/workspaces/1/repos/qualificai', body: { mode: 'hide' } })
    expect(calls).toContainEqual({ method: 'POST', url: '/api/workspace/open', body: { target: 'ide', path: 'C:\\projects\\weaction-api' } })

    await wrapper.find('.tabs__close').trigger('click')
    await flushPromises()
    expect(calls).toContainEqual({ method: 'PATCH', url: '/api/workspaces/1', body: { is_open: false } })
    expect(router.currentRoute.value.query.ws).toBeUndefined()
    expect(wrapper.find('.start').exists()).toBe(true)
  })

  it('o começo abre pela chave e lista os fechados', async () => {
    list = list.map((w) => ({ ...w, is_open: false }))
    const { wrapper, router } = await mountView()

    expect(wrapper.findAll('.start__closed li').map((li) => li.attributes('data-id'))).toEqual(['1', '2'])
    await wrapper.find('input[aria-label="Chave da tarefa"]').setValue('wai-8790')
    await wrapper.find('.start__card').trigger('submit')
    await flushPromises()
    expect(calls).toContainEqual({ method: 'POST', url: '/api/workspaces', body: { root_issue_key: 'WAI-8790' } })
    expect(router.currentRoute.value.query.ws).toBe('3')
  })
})

const PAD_C2 = 'c2'.padEnd(40, '0')
const PAD_C3 = 'c3'.padEnd(40, '0')

describe('RepoTimeline', () => {
  let calls
  let graph
  let posts
  let deleteReplies
  let panelRefs

  const refs = [
    { name: 'feature/WAI-8792', kind: 'local', target: 'c3', upstream: 'origin/feature/WAI-8792', ahead: 1, behind: 0, gone: false, worktree: 'C:\\projects\\weaction-api', is_head: true, is_base: false, in_feature: true, issue_keys: ['WAI-8792'], pull_requests: [{ repo_slug: 'weaction-api', id: 9, title: 'Trial', status: 'pr_aberta', status_label: 'PR aberta', url: 'https://bitbucket.org/weonrepo/weaction-api/pull-requests/9', review: null }] },
    { name: 'origin/feature/WAI-8792', kind: 'remote', target: 'c2', upstream: null, ahead: 0, behind: 0, gone: false, worktree: null, is_head: false, is_base: false, in_feature: true, issue_keys: ['WAI-8792'], pull_requests: [] },
    { name: 'develop', kind: 'local', target: 'c1', upstream: 'origin/develop', ahead: 0, behind: 0, gone: false, worktree: null, is_head: false, is_base: true, in_feature: false, issue_keys: [], pull_requests: [] },
    { name: 'origin/develop', kind: 'remote', target: 'c1', upstream: null, ahead: 0, behind: 0, gone: false, worktree: null, is_head: false, is_base: true, in_feature: false, issue_keys: [], pull_requests: [] },
  ]
  const commit = (sha, parents, subject, keys = []) => ({ sha: sha.padEnd(40, '0'), parents: parents.map((p) => p.padEnd(40, '0')), author: 'Dev', authored_at: '2026-10-02T10:00:00Z', committed_at: '2026-10-02T10:00:00Z', subject, issue_keys: keys })

  beforeEach(() => {
    setActivePinia(createPinia())
    calls = []
    graph = {
      repo: 'weaction-api',
      path: 'C:\\projects\\weaction-api',
      base_branch: 'develop',
      scope: 'feature',
      keys: ['WAI-8792'],
      fingerprint: 'a'.repeat(20),
      fetched_at: '2026-10-02T09:00:00Z',
      unchanged: false,
      refs: refs.map((r) => ({ ...r, target: r.target.padEnd(40, '0') })),
      worktrees: [
        { path: 'C:\\projects\\weaction-api', head: 'c3', branch: 'feature/WAI-8792', detached: false, is_main: true, locked: false, prunable: false, outside_roots: false, changes: { changed: 2, untracked: 1, conflicted: 0 } },
        { path: 'C:\\Users\\dev\\AppData\\Local\\Temp\\wt', head: 'ff00aa1', branch: null, detached: true, is_main: false, locked: false, prunable: false, outside_roots: true, changes: null },
      ],
      commits: [
        commit('c3', ['c2'], 'ajusta o consumer', []),
        commit('c2', ['c1'], 'WAI-8792: inicia o trial', ['WAI-8792']),
        commit('c1', [], 'base da develop'),
      ],
      skip: 0,
      limit: 300,
      has_more: false,
    }
    posts = []
    deleteReplies = []
    panelRefs = [
      { ...refs[0], target: 'c3'.padEnd(40, '0'), committed_at: '2026-10-02T10:00:00Z', subject: 'ajusta o consumer' },
      { ...refs[2], name: 'velha', target: 'c1'.padEnd(40, '0'), is_base: false, upstream: 'origin/velha', behind: 2, committed_at: '2026-09-01T10:00:00Z', subject: 'base' },
      { ...refs[2], target: 'c1'.padEnd(40, '0'), committed_at: '2026-09-01T10:00:00Z' },
      { ...refs[3], target: 'c1'.padEnd(40, '0'), committed_at: '2026-09-01T10:00:00Z' },
      { name: 'v1.42', kind: 'tag', target: 'c1'.padEnd(40, '0'), upstream: null, ahead: 0, behind: 0, gone: false, worktree: null, is_head: false, is_base: false, in_feature: false, issue_keys: [], pull_requests: [], committed_at: null, subject: 'release' },
    ]
    graph.issue_status = { 'WAI-8792': { status: 'mergeada', status_label: 'Mergeada' } }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, init = {}) => {
        calls.push(url)
        if (init.method === 'POST') {
          const body = init.body ? JSON.parse(init.body) : null
          posts.push({ url, body })
          if (url.endsWith('/fetch')) return json({ added: ['origin/WAI-9000'], updated: [], pruned: ['origin/velha'], tags: [], fetched_at: '2026-10-02T15:00:00Z' })
          if (url.endsWith('/branches/update')) return json({ name: body.name, before: 'a', after: 'b', mode: 'ref' })
          if (url.endsWith('/branches/delete')) return deleteReplies.shift() ?? json({ name: body.name, target: 'c1'.padEnd(40, '0') })
        }
        if (url.includes('/refs')) return json({ repo: 'weaction-api', base_branch: 'develop', fetched_at: null, refs: panelRefs, issue_status: {} })
        if (url.includes('/search?')) return json({ query: 'trial', commits: [graph.commits[1]], issue_status: { 'WAI-8792': { status: 'mergeada', status_label: 'Mergeada' } } })
        if (url.includes('/graph?')) {
          if (url.includes('since=')) return json({ ...graph, unchanged: true, refs: [], commits: [], worktrees: [{ ...graph.worktrees[0], changes: { changed: 0, untracked: 0, conflicted: 0 } }] })
          return json(graph)
        }
        if (url.includes('/commits/')) return json({ sha: 'c2'.padEnd(40, '0'), parents: ['c1'.padEnd(40, '0')], author: 'Dev', authored_at: null, committer: 'Dev', committed_at: '2026-10-02T10:00:00Z', message: 'WAI-8792: inicia o trial\n\ncorpo <b>não</b> vira HTML', issue_keys: ['WAI-8792'], files: [{ path: 'app/Trial.php', added: 10, deleted: 2 }, { path: 'logo.png', added: null, deleted: null }], files_truncated: false })
        throw new Error(`não mockado: ${url}`)
      }),
    )
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  async function mountTimeline(props = {}) {
    const wrapper = mount(RepoTimeline, {
      props: { repos: [{ slug: 'weaction-api' }, { slug: 'qualificai' }], repo: 'weaction-api', keys: ['WAI-8792'], highlightKeys: [], ...props },
      global: { stubs: { PrStatusBadge: { name: 'PrStatusBadge', props: ['status', 'links'], template: '<span class="pr-stub" />' } } },
    })
    await flushPromises()
    return wrapper
  }

  it('desenha os commits com etiquetas, o "não commitado" e as worktrees de fora', async () => {
    const wrapper = await mountTimeline()

    expect(calls[0]).toContain('/workspace/repos/weaction-api/graph?scope=feature')
    expect(calls[0]).toContain('keys=WAI-8792')
    const rows = wrapper.findAll('.commit')
    expect(rows).toHaveLength(3)
    const head = rows[0].findAll('.label').map((l) => l.text())
    expect(head[0]).toContain('HEAD')
    expect(head[0]).toContain('feature/WAI-8792')
    expect(rows[0].find('.pr-stub').exists()).toBe(true)
    // develop e origin/develop no mesmo commit viram uma etiqueta só.
    expect(rows[2].findAll('.label').map((l) => l.find('.label__name').text())).toEqual(['develop'])
    expect(rows[2].find('.label__synced').exists()).toBe(true)
    expect(wrapper.find('.pending').text()).toContain('2 alterado(s) · 1 não rastreado(s)')
    expect(wrapper.find('.worktree--outside').text()).toContain('fora de C:\\projects')
    expect(wrapper.text()).toContain('base develop')
  })

  it('clicar no commit traz o detalhe com a mensagem como texto', async () => {
    const wrapper = await mountTimeline()
    await wrapper.findAll('.commit')[1].trigger('click')
    await flushPromises()

    expect(calls.at(-1)).toBe(`/api/workspace/repos/weaction-api/commits/${'c2'.padEnd(40, '0')}`)
    const message = wrapper.find('.detail__message')
    expect(message.text()).toContain('corpo <b>não</b> vira HTML')
    expect(message.find('b').exists()).toBe(false)
    expect(wrapper.findAll('.detail__files li').map((li) => li.text())).toEqual(['app/Trial.php+10−2', 'logo.pngbinário'])

    await wrapper.find('.detail__key').trigger('click')
    expect(wrapper.emitted('open-issue')).toEqual([['WAI-8792']])
  })

  it('chave na cor do PR da tarefa e tag em amarelo', async () => {
    const wrapper = await mountTimeline()
    const key = wrapper.findAll('.commit')[1].find('.key')
    expect(key.text()).toBe('WAI-8792')
    expect(key.attributes('data-status')).toBe('mergeada')
    expect(key.attributes('style')).toContain('--pr: var(--pr-merged)')
    expect(key.attributes('title')).toContain('Mergeada')
    // Tags e remotas começam fechadas: são muitas no weaction-api.
    await wrapper.find('.panel .group[data-group="tag"] .group__head').trigger('click')
    expect(wrapper.find('.panel .item--tag').text()).toContain('v1.42')
  })

  it('painel lista locais, remotas e tags, e clicar numa branch abre o commit dela', async () => {
    const wrapper = await mountTimeline()
    const counts = Object.fromEntries(wrapper.findAll('.panel .group').map((g) => [g.attributes('data-group'), g.find('.group__count').text()]))
    expect(counts).toEqual({ local: '3', remote: '1', tag: '1' })

    await wrapper.find('.panel .item[data-ref="feature/WAI-8792"] .item__main').trigger('click')
    await flushPromises()
    expect(calls.at(-1)).toBe('/api/workspace/repos/weaction-api/commits/' + PAD_C3)
    expect(wrapper.find('.commit--selected').attributes('data-sha')).toBe(PAD_C3)
  })

  it('a busca filtra o painel na hora e procura commits no histórico', async () => {
    vi.useFakeTimers()
    const wrapper = await mountTimeline()
    const box = () => wrapper.find('input[aria-label="Buscar na linha do tempo"]')

    await box().setValue('velha')
    expect(wrapper.findAll('.panel .group[data-group="local"] .item').map((i) => i.attributes('data-ref'))).toEqual(['velha'])

    await box().setValue('trial')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()
    expect(calls.some((u) => u.includes('/search?q=trial'))).toBe(true)
    expect(wrapper.findAll('.panel .group[data-group="commits"] .item')).toHaveLength(1)
    expect(wrapper.find('.commit--match').attributes('data-sha')).toBe(PAD_C2)
  })

  it('fetch pelo botão do cabeçalho mostra o que mudou e relê grafo e painel', async () => {
    const wrapper = await mountTimeline()
    const before = calls.length
    await wrapper.find('.timeline__fetch').trigger('click')
    await flushPromises()

    expect(posts.map((x) => x.url)).toEqual(['/api/workspace/repos/weaction-api/fetch'])
    expect(wrapper.find('.panel__feedback').text()).toBe('Fetch: 1 nova(s), 1 removida(s) do remoto.')
    const after = calls.slice(before)
    expect(after.some((u) => u.includes('/graph?'))).toBe(true)
    expect(after.some((u) => u.includes('/refs'))).toBe(true)
  })

  it('avançar só aparece com a branch atrás, e apagar pede confirmação — e de novo se tiver commit só nela', async () => {
    deleteReplies = [json({ detail: 'A branch tem commits que não estão em nenhuma outra branch.', code: 'unmerged' }, 409)]
    const wrapper = await mountTimeline()
    const row = () => wrapper.find('.panel .item[data-ref="velha"]')

    expect(wrapper.find('.panel .item[data-ref="feature/WAI-8792"] [aria-label="Avançar até o upstream"]').exists()).toBe(false)
    await row().find('[aria-label="Avançar até o upstream"]').trigger('click')
    await flushPromises()
    expect(posts.at(-1)).toEqual({ url: '/api/workspace/repos/weaction-api/branches/update', body: { name: 'velha' } })

    const trash = () => row().find('.item__action--danger')
    await trash().trigger('click')
    expect(trash().text()).toBe('Apagar?')
    expect(posts.filter((x) => x.url.endsWith('/delete'))).toHaveLength(0)

    await trash().trigger('click')
    await flushPromises()
    expect(posts.at(-1).body).toEqual({ name: 'velha', force: false })
    expect(trash().text()).toBe('Mesmo assim?')
    expect(wrapper.find('.panel__feedback').attributes('data-type')).toBe('error')

    await trash().trigger('click')
    await flushPromises()
    expect(posts.at(-1).body).toEqual({ name: 'velha', force: true })

    // A branch aberta no clone principal (HEAD) e a base não se apagam.
    expect(wrapper.find('.panel .item[data-ref="feature/WAI-8792"] .item__action--danger').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.panel .item[data-ref="develop"] .item__action--danger').attributes('disabled')).toBeDefined()
  })

  it('"Todas" pede o --all e a consulta periódica sem mudança só anda as worktrees', async () => {
    vi.useFakeTimers()
    const wrapper = await mountTimeline()

    await wrapper.find('input[value="all"]').setValue(true)
    await flushPromises()
    expect(calls.at(-1)).toContain('scope=all')

    await vi.advanceTimersByTimeAsync(5000)
    await flushPromises()
    expect(calls.at(-1)).toContain(`since=${'a'.repeat(20)}`)
    expect(wrapper.findAll('.commit')).toHaveLength(3)
    expect(wrapper.find('.pending').exists()).toBe(false)
  })
})
