import { useRoute, useRouter } from 'vue-router'
import { useUiStore } from '@/stores/ui'

/**
 * Abre o painel de uma tarefa (e, se pedido, numa aba). Telas com painel (`meta.issueDrawer`)
 * abrem ali mesmo por `?tarefa=`; as demais levam para Sprints.
 */
export function useIssueNavigation() {
  const route = useRoute()
  const router = useRouter()
  const ui = useUiStore()

  function openIssue(key, tab = null) {
    ui.requestIssueTab(key, tab)
    if (route.meta?.issueDrawer) return router.replace({ query: { ...route.query, tarefa: key } })
    return router.push({ name: 'sprints', query: { tarefa: key } })
  }

  /**
   * Leva sempre ao canvas da sprint pedida, com o card em foco e o painel aberto — é o
   * destino da notificação de tarefa. Vai junto a sprint porque o seletor pode ter ficado
   * noutra, e aí o card nem estaria no desenho.
   */
  function openIssueInSprint(key, sprintId, tab = null) {
    ui.requestIssueTab(key, tab)
    const query = { tarefa: key }
    if (sprintId) query.sprint = String(sprintId)
    return router.push({ name: 'sprints', query })
  }

  return { openIssue, openIssueInSprint }
}
