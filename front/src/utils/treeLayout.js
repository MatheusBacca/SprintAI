/**
 * Layout determinístico da árvore da sprint (sem motor de grafo):
 *
 *   [ Épico A ]        [ Épico B ]       ← fileira das raízes, cada uma sobre as suas
 *   ── Onda de implementação 1 ─────────────
 *   [filha A] [filha A] [filha B] [sem pai]   ← quem ninguém bloqueia, de todos os épicos
 *   ── Onda de implementação 2 ─────────────
 *             [filha A]                   ← cada bloqueada abaixo do bloqueador
 *   [sub    ]                             ← descendentes empilhados abaixo da filha
 *
 * É **uma moldura só para a sprint inteira**. Antes cada épico tinha a sua caixa e as
 * tarefas sem pai ficavam numa caixa à parte: a sprint virava um punhado de desenhos
 * que não se comparavam entre si, e a tarefa sem pai parecia de outro lugar. Agora
 * todas dividem as mesmas ondas, e o que diz de quem a tarefa é continua sendo a seta
 * que desce do épico.
 */

export const NODE_WIDTH = 236
export const NODE_HEIGHT = 132
export const COLUMN_GAP = 20
export const ROW_GAP = 56
export const STACK_GAP = 14
export const GROUP_PADDING = 24
export const GROUP_HEADER = 30
/** Faixa reservada acima de cada onda para a linha pontilhada e o rótulo. */
export const WAVE_HEADER = 34
/** Respiro entre o fim de uma onda e o pontilhado da seguinte. */
export const WAVE_GAP = 40

export const NO_PARENT_GROUP = '__sem_pai__'

function descendants(nodesByKey, key) {
  const out = []
  const walk = (k) => {
    for (const child of nodesByKey[k]?.children ?? []) {
      if (!nodesByKey[child]) continue
      out.push(child)
      walk(child)
    }
  }
  walk(key)
  return out
}

/** Tarefas que ocupam uma coluna própria no grupo (as demais ficam empilhadas sob elas). */
function groupCells(group, nodesByKey, inGroup) {
  let cells
  if (group.root_key) {
    cells = (nodesByKey[group.root_key]?.children ?? []).filter((k) => inGroup.has(k))
  } else {
    cells = group.issue_keys.filter((k) => {
      const parent = nodesByKey[k]?.parent_key
      return !parent || !inGroup.has(parent)
    })
  }

  // Sobras (ex.: nó do grupo sem caminho até a raiz) viram célula própria, no fim.
  const cobertos = new Set()
  for (const cell of cells) {
    cobertos.add(cell)
    for (const filho of descendants(nodesByKey, cell)) cobertos.add(filho)
  }
  const sobras = group.issue_keys.filter((k) => k !== group.root_key && !cobertos.has(k))
  return [...cells, ...sobras]
}

/**
 * Ondas de implementação: a onda 1 são as tarefas que ninguém bloqueia; cada outra
 * entra uma onda depois do seu bloqueador mais tardio. É o que dá a leitura de "isto
 * só começa quando aquilo terminar" sem precisar seguir seta por seta.
 *
 * Só bloqueio *entre tarefas que estão no desenho* conta: um bloqueador fora da sprint
 * não tem onda de onde empurrar o card. Como a sprint hoje é um desenho só, bloqueio
 * entre épicos diferentes vale — e é justamente o que a onda existe para mostrar.
 */
export function implementationWaves(cells, nodesByKey) {
  const naLinha = new Set(cells)
  const nivel = {}

  const resolver = (key, caminho) => {
    if (nivel[key] !== undefined) return nivel[key]
    // Ciclo de bloqueio (A bloqueia B, B bloqueia A) existe no Jira e não é erro de
    // dado nosso: fecha em 0 para não entrar em recursão infinita.
    if (caminho.has(key)) return 0
    caminho.add(key)
    const anteriores = (nodesByKey[key]?.blocked_by ?? [])
      .filter((b) => b !== key && naLinha.has(b))
      .map((b) => resolver(b, caminho))
    caminho.delete(key)
    nivel[key] = anteriores.length ? Math.max(...anteriores) + 1 : 0
    return nivel[key]
  }

  for (const key of cells) resolver(key, new Set())

  const total = cells.length ? Math.max(...cells.map((k) => nivel[k])) + 1 : 1
  const ondas = Array.from({ length: total }, () => [])
  for (const key of cells) ondas[nivel[key]].push(key)
  return ondas
}

/**
 * Coluna de cada célula. A partir da segunda onda cada tarefa tenta a coluna do seu
 * bloqueador, para cair logo abaixo dele; quem disputa a mesma coluna (duas tarefas
 * liberadas pela mesma) vai para a primeira livre à direita.
 */
function assignColumns(ondas, nodesByKey) {
  const coluna = {}

  ondas.forEach((onda, indice) => {
    if (indice === 0) {
      onda.forEach((key, i) => {
        coluna[key] = i
      })
      return
    }

    const ocupadas = new Set()
    const disputadas = []
    for (const key of onda) {
      const doBloqueador = (nodesByKey[key]?.blocked_by ?? [])
        .map((b) => coluna[b])
        .filter((c) => c !== undefined)
      const desejada = doBloqueador.length ? Math.min(...doBloqueador) : 0
      if (ocupadas.has(desejada)) {
        disputadas.push([key, desejada])
        continue
      }
      coluna[key] = desejada
      ocupadas.add(desejada)
    }
    for (const [key, desejada] of disputadas) {
      let livre = desejada
      while (ocupadas.has(livre)) livre += 1
      coluna[key] = livre
      ocupadas.add(livre)
    }
  })

  return coluna
}

const colunaX = (indice) => indice * (NODE_WIDTH + COLUMN_GAP)
const larguraAte = (colunas) => (colunas ? colunas * NODE_WIDTH + (colunas - 1) * COLUMN_GAP : 0)

/**
 * Fileira das raízes: cada épico centralizado sobre as suas próprias tarefas, e quem
 * não tem nenhuma no desenho entra numa coluna livre à direita. Depois um passe da
 * esquerda para a direita empurra quem encavalou — dois épicos de uma tarefa cada,
 * em colunas vizinhas, cairiam no mesmo lugar.
 */
function layoutRoots(grupos, positions, colunasUsadas) {
  const fileira = []
  let livre = colunasUsadas

  for (const { group, cells } of grupos) {
    if (!group.root_key) continue
    const xs = cells.map((k) => positions[k]?.x).filter((x) => x !== undefined)
    if (xs.length) fileira.push({ key: group.root_key, x: (Math.min(...xs) + Math.max(...xs)) / 2 })
    else {
      fileira.push({ key: group.root_key, x: colunaX(livre) })
      livre += 1
    }
  }

  let limite = -Infinity
  let direita = 0
  for (const raiz of [...fileira].sort((a, b) => a.x - b.x)) {
    const x = Math.max(raiz.x, limite)
    positions[raiz.key] = { x, y: 0 }
    limite = x + NODE_WIDTH + COLUMN_GAP
    direita = x + NODE_WIDTH
  }
  return { width: direita, hasRoots: fileira.length > 0 }
}

/** Posições de toda a sprint + tamanho do desenho + as ondas desenhadas. */
export function layoutSprint(groups, nodesByKey) {
  const grupos = groups.map((group) => {
    const inGroup = new Set(group.issue_keys)
    return { group, inGroup, cells: groupCells(group, nodesByKey, inGroup) }
  })
  const conhecidos = new Set(groups.flatMap((g) => g.issue_keys))
  const temRaiz = grupos.some((g) => g.group.root_key)

  const cells = grupos.flatMap((g) => g.cells)
  const ondas = implementationWaves(cells, nodesByKey)
  const coluna = assignColumns(ondas, nodesByKey)
  // Sem bloqueio nenhum não há o que separar: a sprint fica com a linha única de sempre.
  const comOndas = ondas.length > 1

  const positions = {}
  let top = temRaiz ? NODE_HEIGHT + ROW_GAP : 0
  const faixas = []

  ondas.forEach((onda, indice) => {
    const divisorY = top
    const linhaY = comOndas ? top + WAVE_HEADER : top
    let alturaLinha = NODE_HEIGHT

    for (const key of onda) {
      const x = colunaX(coluna[key])
      positions[key] = { x, y: linhaY }
      const pilha = descendants(nodesByKey, key).filter((k) => conhecidos.has(k) && !positions[k])
      pilha.forEach((filho, i) => {
        positions[filho] = { x, y: linhaY + (i + 1) * (NODE_HEIGHT + STACK_GAP) }
      })
      alturaLinha = Math.max(alturaLinha, (pilha.length + 1) * NODE_HEIGHT + pilha.length * STACK_GAP)
    }

    faixas.push({ index: indice + 1, keys: onda, y: divisorY })
    top = linhaY + alturaLinha + (indice < ondas.length - 1 ? WAVE_GAP : 0)
  })

  const colunasUsadas = cells.length ? Math.max(...cells.map((k) => coluna[k] + 1)) : 0
  const raizes = layoutRoots(grupos, positions, colunasUsadas)

  const width = Math.max(larguraAte(colunasUsadas), raizes.width)
  const height = cells.length ? top : raizes.hasRoots ? NODE_HEIGHT : 0
  return { positions, width, height, waves: comOndas ? faixas : [] }
}

/**
 * Converte a resposta de `/api/sprints/{id}/tree` em nós e arestas do Vue Flow.
 */
export function layoutTree(tree, { selectedKey = null } = {}) {
  const nodesByKey = Object.fromEntries(tree.nodes.map((n) => [n.key, n]))
  const layout = layoutSprint(tree.groups, nodesByKey)
  const flowNodes = []
  // Onda de cada card, para as arestas saberem se o alvo está logo abaixo da origem.
  const ondaPorKey = {}

  flowNodes.push({
    id: 'group:sprint',
    type: 'group-frame',
    position: { x: 0, y: 0 },
    data: {
      title: null,
      count: tree.nodes.filter((n) => n.in_sprint).length,
      width: layout.width + 2 * GROUP_PADDING,
      height: layout.height + 2 * GROUP_PADDING + GROUP_HEADER,
    },
    draggable: false,
    selectable: false,
    focusable: false,
    zIndex: -1,
  })

  for (const faixa of layout.waves) {
    for (const key of faixa.keys) ondaPorKey[key] = faixa.index
    flowNodes.push({
      id: `wave:${faixa.index}`,
      type: 'wave-divider',
      position: { x: GROUP_PADDING, y: GROUP_PADDING + GROUP_HEADER + faixa.y },
      data: { label: `Onda de implementação ${faixa.index}`, width: layout.width },
      draggable: false,
      selectable: false,
      focusable: false,
      zIndex: -1,
    })
  }

  for (const group of tree.groups) {
    for (const key of group.issue_keys) {
      const pos = layout.positions[key]
      flowNodes.push({
        id: key,
        type: 'issue',
        position: { x: GROUP_PADDING + pos.x, y: GROUP_PADDING + GROUP_HEADER + pos.y },
        data: { issue: nodesByKey[key], selected: key === selectedKey },
        draggable: false,
      })
    }
  }

  /** O alvo está numa onda abaixo da origem. */
  const empilhado = (source, target) => {
    const de = ondaPorKey[source]
    const para = ondaPorKey[target]
    return Boolean(de && para && para > de)
  }

  const flowEdges = tree.edges
    .filter((e) => nodesByKey[e.source] && nodesByKey[e.target])
    // A seta do épico até uma tarefa de onda 2+ atravessaria as ondas de cima por trás
    // dos cards. O vínculo com o épico continua legível pela corrente de bloqueio que
    // leva da onda 1 até ela.
    .filter((e) => !(e.kind === 'parent' && (ondaPorKey[e.target] ?? 1) > 1))
    .map((e) => {
      const vertical = e.kind !== 'blocks' || empilhado(e.source, e.target)
      return {
        id: `${e.kind}:${e.source}->${e.target}`,
        source: e.source,
        target: e.target,
        type: e.kind === 'blocks' && !vertical ? 'default' : 'smoothstep',
        sourceHandle: vertical ? 'bottom' : 'right',
        targetHandle: vertical ? 'top' : 'left',
        label: e.kind === 'blocks' ? 'bloqueia' : undefined,
        animated: e.kind === 'blocks',
        class: `edge edge--${e.kind}`,
        markerEnd: 'arrowclosed',
      }
    })

  return { nodes: flowNodes, edges: flowEdges }
}
