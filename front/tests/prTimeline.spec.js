import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import IssuePullRequestsTab from '@/components/issue/IssuePullRequestsTab.vue'

const T0 = '2026-09-12T10:00:00Z'

function at(hours) {
  return new Date(Date.parse(T0) + hours * 3600_000).toISOString()
}

// Ajuste pedido e correção já enviada: o Bitbucket mantém o pedido do revisor em pé, e
// é o histórico que devolve o PR a "PR aberta".
const SUMMARY = {
  issue_key: 'WAI-8360',
  status: 'pr_aberta',
  status_label: 'PR aberta',
  pr_count: 1,
  open_pr_count: 1,
  build_failed: false,
  last_activity: T0,
  repos: [
    {
      repo_slug: 'weaction-api',
      status: 'pr_aberta',
      status_label: 'PR aberta',
      branches: [],
      pull_requests: [
        {
          repo_slug: 'weaction-api',
          id: 1836,
          title: 'WAI-8360 histórico de qualificação',
          state: 'OPEN',
          status: 'pr_aberta',
          status_label: 'PR aberta',
          draft: false,
          source_branch: 'WAI-8360-historico',
          destination_branch: 'develop',
          url: 'https://bitbucket.org/weonrepo/weaction-api/pull-requests/1836',
          updated_on: T0,
          approvals: 0,
          changes_requested: 1,
          reviewers: [{ name: 'Rafael', role: 'REVIEWER', approved: false, state: 'changes_requested' }],
          build_status: null,
          build_failed: false,
          comment_count: 1,
          match: 'branch',
          fix_pushed: true,
        },
      ],
    },
  ],
}

function entry(kind, extra = {}) {
  return {
    kind,
    at: T0,
    actor_name: 'Rafael',
    actor_is_me: false,
    body: null,
    comment_id: null,
    parent_id: null,
    inline_path: null,
    inline_from: null,
    inline_to: null,
    is_deleted: false,
    commit: null,
    build: null,
    after_changes_requested: false,
    ...extra,
  }
}

const TIMELINE = {
  repo_slug: 'weaction-api',
  pr_id: 1836,
  title: 'WAI-8360 histórico de qualificação',
  url: 'https://bitbucket.org/weonrepo/weaction-api/pull-requests/1836',
  pending_review: false,
  request_before_history: false,
  // Como a API devolve: da última atualização para a mais antiga.
  entries: [
    entry('pr_commit', {
      at: at(4),
      actor_name: 'Matheus',
      actor_is_me: true,
      commit: 'def1234567',
      after_changes_requested: true,
    }),
    entry('pr_changes_requested', { at: at(3) }),
    entry('comment', {
      at: at(2),
      body: 'Olha a linha 42.',
      comment_id: 9002,
      inline_path: 'src/app.php',
      inline_to: 42,
    }),
    entry('comment', {
      at: at(1),
      body: 'Registra zero quando não há MonitorIA.',
      comment_id: 9001,
    }),
  ],
}

function json(status, body) {
  return {
    ok: status < 400,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
  }
}

const TIMELINE_URL = '/api/pull-requests/weaction-api/1836/timeline'

let calls
function stubFetch(response = () => json(200, TIMELINE)) {
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url) => {
      calls.push(url)
      return response(url)
    }),
  )
}

async function mountTab(summary = SUMMARY) {
  const wrapper = mount(IssuePullRequestsTab, { props: { summary } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  setActivePinia(createPinia())
  stubFetch()
})

describe('histórico da PR', () => {
  it('já vem aberto: busca o histórico de cada PR ao entrar na aba', async () => {
    const wrapper = await mountTab()

    expect(calls).toEqual([TIMELINE_URL])
    expect(wrapper.find('.tl__list').exists()).toBe(true)
  })

  it('mostra a última atualização primeiro', async () => {
    const wrapper = await mountTab()

    const items = wrapper.findAll('.tl__item')
    expect(items.map((i) => i.attributes('data-kind'))).toEqual([
      'pr_commit',
      'pr_changes_requested',
      'comment',
      'comment',
    ])
    expect(items[2].text()).toContain('src/app.php:42')
    expect(items[3].text()).toContain('Registra zero quando não há MonitorIA.')
  })

  it('o commit que responde ao pedido de ajuste aparece como correção', async () => {
    const wrapper = await mountTab()

    const commit = wrapper.find('.tl__item')
    expect(commit.attributes('data-fix')).toBeDefined()
    expect(commit.text()).toContain('subiu a correção')
    expect(commit.text()).toContain('def1234')
  })

  it('commit sem pedido de ajuste antes não vira correção', async () => {
    stubFetch(() =>
      json(200, { ...TIMELINE, entries: [entry('pr_commit', { commit: 'abc1234567' })] }),
    )
    const wrapper = await mountTab()

    const commit = wrapper.find('.tl__item')
    expect(commit.attributes('data-fix')).toBeUndefined()
    expect(commit.text()).toContain('subiu commit')
  })

  it('avisa quando o ajuste foi pedido e ainda não veio commit', async () => {
    stubFetch(() =>
      json(200, { ...TIMELINE, pending_review: true, entries: [entry('pr_changes_requested')] }),
    )
    const wrapper = await mountTab()

    expect(wrapper.find('.tl__pending').text()).toContain('ainda sem commit')
  })

  it('avisa quando o pedido de ajuste é anterior ao histórico local', async () => {
    stubFetch(() =>
      json(200, {
        ...TIMELINE,
        request_before_history: true,
        entries: [entry('pr_commit', { commit: 'abc1234567' })],
      }),
    )
    const wrapper = await mountTab()

    expect(wrapper.find('.tl__note').text()).toContain('anterior ao histórico local')
    // Sem o evento do pedido, o commit não pode ser chamado de correção.
    expect(wrapper.find('.tl__item').attributes('data-fix')).toBeUndefined()
  })

  it('comentário apagado continua na linha, sem corpo e sem copiar', async () => {
    stubFetch(() =>
      json(200, {
        ...TIMELINE,
        entries: [entry('comment', { body: '', is_deleted: true, comment_id: 1 })],
      }),
    )
    const wrapper = await mountTab()

    expect(wrapper.find('.tl__gone').text()).toBe('comentário apagado no Bitbucket')
    expect(wrapper.find('.tl__copy').exists()).toBe(false)
  })

  it('erro mostra o motivo e deixa tentar de novo', async () => {
    stubFetch(() => json(500, { detail: 'Banco indisponível' }))
    const wrapper = await mountTab()

    expect(wrapper.find('.tl__note--error').text()).toContain('Banco indisponível')

    stubFetch()
    await wrapper.find('.tl__note--error button').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.tl__item')).toHaveLength(4)
  })

  it('remontar a aba aproveita o que o store já carregou', async () => {
    await mountTab()
    const wrapper = await mountTab()

    expect(calls).toEqual([TIMELINE_URL])
    expect(wrapper.findAll('.tl__item')).toHaveLength(4)
  })
})

describe('correção enviada', () => {
  it('o PR com correção no ar volta a "PR aberta" e diz por que o pedido ainda aparece', async () => {
    const wrapper = await mountTab()

    const text = wrapper.find('.pr').text()
    expect(text).toContain('1 pedido(s) de ajuste')
    expect(text).toContain('correção enviada')
    expect(wrapper.find('.pr .pr-badge').text()).toContain('PR aberta')
  })

  it('sem correção, nada de marca', async () => {
    const pr = { ...SUMMARY.repos[0].pull_requests[0], fix_pushed: false }
    const summary = { ...SUMMARY, repos: [{ ...SUMMARY.repos[0], pull_requests: [pr] }] }
    const wrapper = await mountTab(summary)

    expect(wrapper.find('.pr').text()).not.toContain('correção enviada')
  })
})

describe('minimizar a review', () => {
  it('a review abre e fecha pelo cabeçalho, que conta o que tem dentro', async () => {
    const wrapper = await mountTab()
    const toggle = () => wrapper.find('.tl__toggle')

    expect(toggle().attributes('aria-expanded')).toBe('true')
    expect(toggle().text()).toContain('4 atualizações')

    await toggle().trigger('click')
    expect(toggle().attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.tl__list').exists()).toBe(false)

    await toggle().trigger('click')
    expect(wrapper.findAll('.tl__item')).toHaveLength(4)
  })

  it('minimizar um PR não mexe no outro', async () => {
    const outro = { ...SUMMARY.repos[0].pull_requests[0], id: 1840 }
    const summary = {
      ...SUMMARY,
      repos: [{ ...SUMMARY.repos[0], pull_requests: [SUMMARY.repos[0].pull_requests[0], outro] }],
    }
    const wrapper = await mountTab(summary)

    await wrapper.findAll('.tl__toggle')[0].trigger('click')

    expect(wrapper.findAll('.tl__toggle').map((t) => t.attributes('aria-expanded'))).toEqual([
      'false',
      'true',
    ])
    expect(wrapper.findAll('.tl__list')).toHaveLength(1)
  })

  it('o aviso de ajuste pendente continua à vista com a review minimizada', async () => {
    stubFetch(() => json(200, { ...TIMELINE, pending_review: true }))
    const wrapper = await mountTab()

    await wrapper.find('.tl__toggle').trigger('click')

    expect(wrapper.find('.tl__list').exists()).toBe(false)
    expect(wrapper.find('.tl__pending').text()).toContain('ainda sem commit')
  })
})

describe('markdown do comentário', () => {
  it('o corpo é renderizado, não mostrado como markdown cru', async () => {
    stubFetch(() =>
      json(200, {
        ...TIMELINE,
        entries: [
          entry('comment', {
            comment_id: 1,
            body: '# Review\n\n**Veredito:** ajustes\n\n- olhar `app.php`',
          }),
        ],
      }),
    )
    const wrapper = await mountTab()

    // Dentro de `.md`: o `strong` de fora é o nome de quem comentou.
    const body = wrapper.find('.tl__comment .md')
    expect(body.find('h3').text()).toBe('Review')
    expect(body.find('strong').text()).toBe('Veredito:')
    expect(body.find('li code').text()).toBe('app.php')
    expect(body.text()).not.toContain('**')
  })
})

describe('copiar o comentário', () => {
  function stubClipboard() {
    const written = []
    vi.stubGlobal('ClipboardItem', class ClipboardItemStub {
      constructor(items) {
        this.items = items
      }
    })
    vi.stubGlobal('navigator', {
      clipboard: {
        write: vi.fn(async (items) => written.push(items[0].items)),
        writeText: vi.fn(async (text) => written.push({ 'text/plain': text })),
      },
    })
    return written
  }

  it('copia o HTML renderizado e o markdown original', async () => {
    const written = stubClipboard()
    const wrapper = await mountTab()

    await wrapper.find('.tl__copy').trigger('click')
    await flushPromises()

    expect(written).toHaveLength(1)
    expect(Object.keys(written[0])).toEqual(['text/html', 'text/plain'])
    expect(wrapper.find('.tl__copy--ok').exists()).toBe(true)
  })

  it('sem suporte aos dois formatos, cai no markdown como texto', async () => {
    const written = []
    vi.stubGlobal('navigator', {
      clipboard: { writeText: vi.fn(async (text) => written.push(text)) },
    })
    const wrapper = await mountTab()

    await wrapper.find('.tl__copy').trigger('click')
    await flushPromises()

    // O primeiro botão é o do comentário mais recente.
    expect(written).toEqual(['Olha a linha 42.'])
  })

  it('Clipboard API negada cai na seleção temporária', async () => {
    vi.stubGlobal('navigator', {
      clipboard: { writeText: vi.fn(async () => { throw new Error('negado') }) },
    })
    const execCommand = vi.fn(() => true)
    document.execCommand = execCommand
    const wrapper = await mountTab()

    await wrapper.find('.tl__copy').trigger('click')
    await flushPromises()

    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(wrapper.find('.tl__copy--ok').exists()).toBe(true)
    delete document.execCommand
  })

  it('sem nenhum caminho de cópia, avisa em vez de fingir que copiou', async () => {
    vi.stubGlobal('navigator', {
      clipboard: { writeText: vi.fn(async () => { throw new Error('negado') }) },
    })
    const wrapper = await mountTab()

    await wrapper.find('.tl__copy').trigger('click')
    await flushPromises()

    expect(wrapper.find('.tl__copy--ok').exists()).toBe(false)
    expect(wrapper.find('.tl__copy').attributes('title')).toBe('Não deu para copiar')
  })
})
