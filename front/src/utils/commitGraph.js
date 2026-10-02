/**
 * Pistas da linha do tempo das branches (o grafo do `gitk --all` / GitLens) — função pura.
 *
 * Os commits chegam do mais novo para o mais antigo, sem pai antes de filho
 * (`git log --date-order`). Cada pista "espera" um commit: quando ele aparece, ocupa a
 * pista que o esperava; o primeiro pai herda a pista e cada pai a mais (merge) abre ou
 * reaproveita outra. Duas pistas esperando o mesmo commit se juntam nele — é o ponto de
 * onde uma branch saiu.
 *
 * As pistas não andam de lugar: linha que só passa por uma linha do grafo segue reta na
 * mesma coluna. Pista que fica livre é reaproveitada pela próxima branch que aparecer.
 *
 * Para cada commit sai uma linha de desenho:
 * - `lane`: a coluna do commit;
 * - `through`: colunas que passam reto (outras branches);
 * - `incoming`: colunas que chegam de cima e terminam neste commit (a da própria pista e as
 *   que se juntam nele);
 * - `outgoing`: colunas para onde descem as linhas dos pais (a primeira é a da pista);
 * - `lanes`: quantas colunas a linha ocupa (para a largura do desenho).
 */
export function layoutGraph(commits) {
  const lanes = []
  const rows = []
  let width = 0

  const freeLane = (exclude = -1) => {
    for (let i = 0; i < lanes.length; i++) if (lanes[i] == null && i !== exclude) return i
    return lanes.length
  }

  for (const commit of commits) {
    const waiting = []
    lanes.forEach((sha, index) => {
      if (sha === commit.sha) waiting.push(index)
    })
    const lane = waiting.length ? waiting[0] : freeLane()
    const through = []
    lanes.forEach((sha, index) => {
      if (sha != null && sha !== commit.sha) through.push(index)
    })

    for (const index of waiting) lanes[index] = null

    const [first, ...others] = commit.parents ?? []
    const outgoing = []
    if (first) {
      lanes[lane] = first
      outgoing.push(lane)
    }
    for (const parent of others) {
      let target = lanes.indexOf(parent)
      if (target === -1) {
        target = freeLane(lane)
        lanes[target] = parent
      }
      outgoing.push(target)
    }
    while (lanes.length && lanes[lanes.length - 1] == null) lanes.pop()

    const used = Math.max(lane, ...through, ...outgoing, ...waiting) + 1
    width = Math.max(width, used)
    rows.push({ sha: commit.sha, lane, incoming: waiting, through, outgoing, lanes: used })
  }

  return { rows, width }
}

/** Cor da pista — uma das oito do tema (`--lane-1` … `--lane-8`). */
export function laneColor(index) {
  return `var(--lane-${(index % 8) + 1})`
}

/**
 * Etiquetas por commit. A branch local e a `origin/` no mesmo commit viram uma etiqueta só
 * (a "em dia"); separadas, cada uma mostra onde está.
 */
export function labelsBySha(refs) {
  const bySha = {}
  const remoteByName = Object.fromEntries(
    refs.filter((r) => r.kind === 'remote').map((r) => [r.name.slice(r.name.indexOf('/') + 1), r]),
  )
  const merged = new Set()
  for (const ref of refs) {
    if (ref.kind !== 'local') continue
    const remote = remoteByName[ref.name]
    const synced = Boolean(remote && remote.target === ref.target)
    if (synced) merged.add(remote.name)
    ;(bySha[ref.target] ??= []).push({ ...ref, synced })
  }
  for (const ref of refs) {
    if (ref.kind === 'local' || merged.has(ref.name)) continue
    ;(bySha[ref.target] ??= []).push({ ...ref, synced: false })
  }
  const rank = (label) => (label.is_head ? 0 : label.kind === 'local' ? 1 : label.kind === 'remote' ? 2 : 3)
  for (const list of Object.values(bySha)) list.sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name))
  return bySha
}
