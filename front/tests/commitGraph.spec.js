import { describe, expect, it } from 'vitest'
import { labelsBySha, layoutGraph } from '@/utils/commitGraph'

const c = (sha, ...parents) => ({ sha, parents })

describe('layoutGraph', () => {
  it('histórico linear fica numa pista só', () => {
    const { rows, width } = layoutGraph([c('c3', 'c2'), c('c2', 'c1'), c('c1')])
    expect(width).toBe(1)
    expect(rows.map((r) => r.lane)).toEqual([0, 0, 0])
    expect(rows[0]).toMatchObject({ incoming: [], outgoing: [0], through: [] })
    expect(rows[1]).toMatchObject({ incoming: [0], outgoing: [0] })
    // O primeiro commit do repo não tem pai: a pista fecha nele.
    expect(rows[2]).toMatchObject({ incoming: [0], outgoing: [] })
  })

  it('branch que saiu da main se junta a ela no ponto de origem', () => {
    // main: m2 → m1 → base ; feature: f2 → f1 → base
    const { rows, width } = layoutGraph([c('m2', 'm1'), c('f2', 'f1'), c('m1', 'base'), c('f1', 'base'), c('base')])
    expect(width).toBe(2)
    const by = Object.fromEntries(rows.map((r) => [r.sha, r]))
    expect(by.m2.lane).toBe(0)
    expect(by.f2.lane).toBe(1)
    expect(by.f2.through).toEqual([0])
    expect(by.m1.through).toEqual([1])
    // As duas pistas esperam o `base`: ele fica na primeira e a outra chega nele.
    expect(by.base.lane).toBe(0)
    expect(by.base.incoming).toEqual([0, 1])
  })

  it('merge abre uma pista para o segundo pai e fecha quando ele aparece', () => {
    // merge M (pais: main m1 e feature f1); f1 e m1 saem de base
    const { rows } = layoutGraph([c('M', 'm1', 'f1'), c('f1', 'base'), c('m1', 'base'), c('base')])
    const by = Object.fromEntries(rows.map((r) => [r.sha, r]))
    expect(by.M.outgoing).toEqual([0, 1])
    expect(by.f1.lane).toBe(1)
    expect(by.f1.through).toEqual([0])
    expect(by.m1.lane).toBe(0)
    expect(by.base.incoming).toEqual([0, 1])
  })

  it('pista livre é reaproveitada pela próxima branch', () => {
    // a1 nasce de m2 e a pista fecha nele; b1 vem depois e cabe na pista que ficou livre
    const { rows, width } = layoutGraph([c('m3', 'm2'), c('a1', 'm2'), c('m2', 'm1'), c('b1', 'm1'), c('m1')])
    const by = Object.fromEntries(rows.map((r) => [r.sha, r]))
    expect(by.a1.lane).toBe(1)
    expect(by.m2.incoming).toEqual([0, 1])
    expect(by.b1.lane).toBe(1)
    expect(width).toBe(2)
  })

  it('commit de fronteira fecha a pista nele: os pais não são da feature', () => {
    const { rows } = layoutGraph([c('f2', 'f1'), c('f1', 'base'), { sha: 'base', parents: ['antes'], boundary: true }])
    expect(rows[2]).toMatchObject({ lane: 0, incoming: [0], outgoing: [] })
  })

  it('pai fora da página deixa a pista aberta até o fim', () => {
    const { rows } = layoutGraph([c('x2', 'x1'), c('x1', 'fora-da-pagina')])
    expect(rows[1].outgoing).toEqual([0])
  })
})

describe('labelsBySha', () => {
  it('junta a branch local com a origin no mesmo commit e separa quando divergem', () => {
    const refs = [
      { name: 'main', kind: 'local', target: 'a', is_head: true },
      { name: 'origin/main', kind: 'remote', target: 'b' },
      { name: 'WAI-1-x', kind: 'local', target: 'c', is_head: false },
      { name: 'origin/WAI-1-x', kind: 'remote', target: 'c' },
      { name: 'v1.0', kind: 'tag', target: 'c' },
    ]
    const labels = labelsBySha(refs)
    expect(labels.a.map((l) => [l.name, l.synced])).toEqual([['main', false]])
    expect(labels.b.map((l) => l.name)).toEqual(['origin/main'])
    expect(labels.c.map((l) => [l.name, l.synced])).toEqual([['WAI-1-x', true], ['v1.0', false]])
  })
})
