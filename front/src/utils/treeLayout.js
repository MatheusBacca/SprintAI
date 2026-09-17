/**
 * Layout determinístico da árvore da sprint (sem motor de grafo):
 *
 *   [ Épico / Enhancements ]                     ← raiz do grupo, centralizada
 *   ── Onda de implementação 1 ─────────────
 *   [filha] [filha] [filha]                      ← filhas que ninguém bloqueia
 *   ── Onda de implementação 2 ─────────────
 *           [filha]                              ← cada bloqueada abaixo do bloqueador
 *   [sub  ]                                      ← descendentes empilhados abaixo da filha
 *
 * Grupo "Sem pai": sem raiz; as tarefas vão direto para a primeira onda.
 * Grupos ficam lado a lado enquanto couberem em MAX_ROW_WIDTH; um grupo mais largo que
 * isso ocupa a linha sozinho (o canvas tem pan/zoom).
 */

export const NODE_WIDTH = 236
export const NODE_HEIGHT = 132
export const COLUMN_GAP = 20
export const ROW_GAP = 56
export const STACK_GAP = 14
export const GROUP_PADDING = 24
export const GROUP_HEADER = 30
export const GROUP_GAP = 48
export const MAX_ROW_WIDTH = 2400
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
 * Só bloqueio *entre tarefas da mesma linha do grupo* conta. Um bloqueador de outro
 * épico empurraria o card para uma onda que não existe no desenho deste grupo.
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

/** Posições relativas ao canto do grupo + tamanho do grupo + as ondas desenhadas. */
export function layoutGroup(group, nodesByKey) {
  const inGroup = new Set(group.issue_keys)
  const positions = {}

  const cells = groupCells(group, nodesByKey, inGroup)
  const ondas = implementationWaves(cells, nodesByKey)
  const coluna = assignColumns(ondas, nodesByKey)
  // Sem bloqueio nenhum não há o que separar: o grupo fica com a linha única de sempre.
  const comOndas = ondas.length > 1

  let top = group.root_key ? NODE_HEIGHT + ROW_GAP : 0
  const faixas = []

  ondas.forEach((onda, indice) => {
    const divisorY = top
    const linhaY = comOndas ? top + WAVE_HEADER : top
    let alturaLinha = NODE_HEIGHT

    for (const key of onda) {
      const x = coluna[key] * (NODE_WIDTH + COLUMN_GAP)
      positions[key] = { x, y: linhaY }
      const pilha = descendants(nodesByKey, key).filter((k) => inGroup.has(k) && !positions[k])
      pilha.forEach((filho, i) => {
        positions[filho] = { x, y: linhaY + (i + 1) * (NODE_HEIGHT + STACK_GAP) }
      })
      alturaLinha = Math.max(alturaLinha, (pilha.length + 1) * NODE_HEIGHT + pilha.length * STACK_GAP)
    }

    faixas.push({ index: indice + 1, keys: onda, y: divisorY })
    top = linhaY + alturaLinha + (indice < ondas.length - 1 ? WAVE_GAP : 0)
  })

  const colunas = Math.max(1, ...cells.map((k) => coluna[k] + 1))
  const width = colunas * NODE_WIDTH + (colunas - 1) * COLUMN_GAP
  if (group.root_key) positions[group.root_key] = { x: (width - NODE_WIDTH) / 2, y: 0 }

  const onlyRoot = Object.keys(positions).length === (group.root_key ? 1 : 0)
  const height = onlyRoot ? NODE_HEIGHT : top
  return { positions, width, height, waves: comOndas ? faixas : [] }
}

/**
 * Converte a resposta de `/api/sprints/{id}/tree` em nós e arestas do Vue Flow.
 */
export function layoutTree(tree, { selectedKey = null } = {}) {
  const nodesByKey = Object.fromEntries(tree.nodes.map((n) => [n.key, n]))
  const flowNodes = []
  // Onda de cada card, para as arestas saberem se o alvo está logo abaixo da origem.
  const ondaPorKey = {}
  let cursorX = 0
  let cursorY = 0
  let rowHeight = 0

  for (const group of tree.groups) {
    const layout = layoutGroup(group, nodesByKey)
    const frameWidth = layout.width + 2 * GROUP_PADDING
    const frameHeight = layout.height + 2 * GROUP_PADDING + GROUP_HEADER

    if (cursorX > 0 && cursorX + frameWidth > MAX_ROW_WIDTH) {
      cursorX = 0
      cursorY += rowHeight + GROUP_GAP
      rowHeight = 0
    }

    const inSprint = group.issue_keys.filter((k) => nodesByKey[k]?.in_sprint).length
    flowNodes.push({
      id: `group:${group.key}`,
      type: 'group-frame',
      position: { x: cursorX, y: cursorY },
      data: {
        title: group.root_key ? null : 'Sem pai',
        count: inSprint,
        width: frameWidth,
        height: frameHeight,
      },
      draggable: false,
      selectable: false,
      focusable: false,
      zIndex: -1,
    })

    for (const faixa of layout.waves) {
      for (const key of faixa.keys) ondaPorKey[key] = { group: group.key, index: faixa.index }
      flowNodes.push({
        id: `wave:${group.key}:${faixa.index}`,
        type: 'wave-divider',
        position: {
          x: cursorX + GROUP_PADDING,
          y: cursorY + GROUP_PADDING + GROUP_HEADER + faixa.y,
        },
        data: { label: `Onda de implementação ${faixa.index}`, width: layout.width },
        draggable: false,
        selectable: false,
        focusable: false,
        zIndex: -1,
      })
    }

    for (const key of group.issue_keys) {
      const pos = layout.positions[key]
      flowNodes.push({
        id: key,
        type: 'issue',
        position: {
          x: cursorX + GROUP_PADDING + pos.x,
          y: cursorY + GROUP_PADDING + GROUP_HEADER + pos.y,
        },
        data: { issue: nodesByKey[key], selected: key === selectedKey },
        draggable: false,
      })
    }

    cursorX += frameWidth + GROUP_GAP
    rowHeight = Math.max(rowHeight, frameHeight)
  }

  /** O alvo está numa onda abaixo da origem, no mesmo grupo. */
  const empilhado = (source, target) => {
    const de = ondaPorKey[source]
    const para = ondaPorKey[target]
    return Boolean(de && para && de.group === para.group && para.index > de.index)
  }

  const flowEdges = tree.edges
    .filter((e) => nodesByKey[e.source] && nodesByKey[e.target])
    // A seta do épico até uma tarefa de onda 2+ atravessaria as ondas de cima por trás
    // dos cards. O vínculo com o épico continua legível pela moldura do grupo e pela
    // corrente de bloqueio que leva até ela.
    .filter((e) => !(e.kind === 'parent' && (ondaPorKey[e.target]?.index ?? 1) > 1))
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
