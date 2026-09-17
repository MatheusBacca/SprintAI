import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import MarkdownRenderer from '@/components/issue/MarkdownRenderer.js'
import { parseInline, parseMarkdown } from '@/utils/markdown'

function render(source) {
  return mount(MarkdownRenderer, { props: { source } })
}

describe('parseMarkdown', () => {
  it('título vira heading com o nível certo', () => {
    expect(parseMarkdown('# Review\n## Detalhes')).toMatchObject([
      { type: 'heading', level: 1 },
      { type: 'heading', level: 2 },
    ])
  })

  it('parágrafos são separados por linha em branco', () => {
    const blocks = parseMarkdown('primeiro\n\nsegundo')
    expect(blocks).toHaveLength(2)
    expect(blocks.every((b) => b.type === 'paragraph')).toBe(true)
  })

  it('bloco de código guarda o texto cru e a linguagem', () => {
    const [block] = parseMarkdown('```sql\nSELECT 1\n-- **não** é negrito\n```')
    expect(block).toMatchObject({ type: 'code', lang: 'sql' })
    expect(block.text).toBe('SELECT 1\n-- **não** é negrito')
  })

  it('lista com item aninhado vira lista dentro do item', () => {
    const [list] = parseMarkdown('- pai\n  - filho\n- outro')

    expect(list.type).toBe('list')
    expect(list.ordered).toBe(false)
    expect(list.items).toHaveLength(2)
    expect(list.items[0][1]).toMatchObject({ type: 'list' })
  })

  it('lista numerada guarda o início', () => {
    const [list] = parseMarkdown('3. três\n4. quatro')
    expect(list).toMatchObject({ type: 'list', ordered: true, start: 3 })
    expect(list.items).toHaveLength(2)
  })

  it('citação e regra são reconhecidas', () => {
    expect(parseMarkdown('> citado\n\n---')).toMatchObject([{ type: 'quote' }, { type: 'rule' }])
  })
})

describe('parseInline', () => {
  it('negrito, itálico, riscado e código', () => {
    expect(parseInline('**a** *b* ~~c~~ `d`').filter((n) => n.type !== 'text')).toMatchObject([
      { type: 'strong' },
      { type: 'em' },
      { type: 'strike' },
      { type: 'code', text: 'd' },
    ])
  })

  it('código inline não deixa a marcação de dentro valer', () => {
    const [node] = parseInline('`**literal**`')
    expect(node).toMatchObject({ type: 'code', text: '**literal**' })
  })

  it('underscore no meio de palavra não vira itálico', () => {
    // O caso real: nome de branch com a chave da tarefa.
    expect(parseInline('WAI_8360_api')).toEqual([{ type: 'text', text: 'WAI_8360_api' }])
    expect(parseInline('_ênfase_')).toMatchObject([{ type: 'em' }])
  })

  it('quebra simples vira quebra de linha', () => {
    expect(parseInline('a\nb')).toMatchObject([
      { type: 'text', text: 'a' },
      { type: 'break' },
      { type: 'text', text: 'b' },
    ])
  })
})

describe('MarkdownRenderer', () => {
  it('renderiza o markdown de uma review', () => {
    const wrapper = render('# Review: WAI-8360\n\n**Veredito:** mergear após ajustes\n\n- item `x`')

    expect(wrapper.find('h3').text()).toBe('Review: WAI-8360')
    expect(wrapper.find('strong').text()).toBe('Veredito:')
    expect(wrapper.find('li code').text()).toBe('x')
  })

  it('HTML no texto sai como texto, nunca como markup', () => {
    const wrapper = render('<img src=x onerror=alert(1)> e <b>não</b>')

    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('b').exists()).toBe(false)
    expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>')
  })

  it('link http abre em aba nova; javascript: perde o href mas mantém o texto', () => {
    const wrapper = render('[ok](https://bitbucket.org/x) e [mau](javascript:alert(1))')

    const links = wrapper.findAll('a')
    expect(links).toHaveLength(1)
    expect(links[0].attributes()).toMatchObject({
      href: 'https://bitbucket.org/x',
      rel: 'noopener noreferrer',
      target: '_blank',
    })
    expect(wrapper.text()).toContain('mau')
  })

  it('corpo vazio não renderiza nada', () => {
    expect(render('').html()).toBe('')
    expect(render('   \n\n  ').html()).toBe('')
  })
})
