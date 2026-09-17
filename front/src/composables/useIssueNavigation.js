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

  return { openIssue }
}
