/**
 * Marcas de tela dos cards — resultado de busca e destaque de status (Alt + clique).
 *
 * Vão por `provide`/`inject` e **não** pelos objetos de nó do Vue Flow: remontar o
 * array de nós a cada tecla digitada faz a biblioteca recriar e remedir cada card,
 * e enquanto a medida não volta o `fitView({ nodes })` não acha dimensão nenhuma e
 * não sai do lugar — que foi exatamente o bug ao ligar a busca pela primeira vez.
 */
export const CANVAS_MARKS = Symbol('sprint-canvas-marks')

/** Flags de um card. `issue` é o nó da árvore; `marks`, o que o canvas forneceu. */
export function nodeMarks(issue, marks = {}) {
  const { matchKeys = [], focusKey = null, highlightStatus = null } = marks
  // Status do Jira vale para todo card, pai e fora da sprint inclusive: um épico em
  // desenvolvimento também é trabalho naquele status. Caixa não conta ("Concluído" do
  // espelho e "CONCLUÍDO" do snapshot de um link são o mesmo).
  const highlighting = Boolean(highlightStatus)
  const same = highlighting && (issue.status ?? '').toLowerCase() === highlightStatus.toLowerCase()

  return {
    match: matchKeys.includes(issue.key),
    active: issue.key === focusKey,
    emphasized: same,
    muted: highlighting && !same,
  }
}
