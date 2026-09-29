/**
 * Recorte da árvore da sprint pelas etapas ligadas nos chips (Configurações › Progresso):
 * ficam as tarefas da sprint que caem numa delas e a hierarquia acima de cada uma — pai,
 * co-pai (o Enhancements de uma fatia) e assim por diante até o topo. Bloqueador e origem
 * de outra etapa saem: o filtro responde "o que está nesta etapa", e a tarefa sobe de onda
 * sem eles, que é o que as ondas já fazem com antecessora fora do desenho.
 *
 * Sem etapa ligada devolve a própria árvore, sem cópia: o canvas não tem o que redesenhar.
 */
export function filterTreeByStages(tree, stageIds) {
  if (!tree || !stageIds?.length) return tree

  const ligadas = new Set(stageIds)
  const porChave = Object.fromEntries(tree.nodes.map((n) => [n.key, n]))
  const ficam = new Set()

  const subir = (key) => {
    const node = porChave[key]
    if (!node || ficam.has(key)) return
    ficam.add(key)
    if (node.parent_key) subir(node.parent_key)
    for (const coPai of node.co_parents ?? []) subir(coPai)
  }
  for (const node of tree.nodes) {
    if (node.in_sprint && ligadas.has(node.stage?.id)) subir(node.key)
  }

  return {
    ...tree,
    nodes: tree.nodes.filter((n) => ficam.has(n.key)),
    edges: tree.edges.filter((e) => ficam.has(e.source) && ficam.has(e.target)),
    groups: tree.groups
      .map((g) => ({ ...g, issue_keys: g.issue_keys.filter((k) => ficam.has(k)) }))
      .filter((g) => g.issue_keys.length),
    // A moldura diz "N de M": sem o total, o recorte parecia a sprint inteira.
    total_tasks: tree.nodes.filter((n) => n.in_sprint).length,
  }
}

/** Quantas tarefas da sprint caem em cada etapa — o número de cada chip. */
export function countByStage(tree) {
  const contagem = {}
  for (const node of tree?.nodes ?? []) {
    if (node.in_sprint && node.stage?.id) contagem[node.stage.id] = (contagem[node.stage.id] ?? 0) + 1
  }
  return contagem
}
