/**
 * Rotas e itens da navegação lateral. `issueDrawer` marca as telas que abrem o painel da
 * tarefa por `?tarefa=` (a busca global abre ali mesmo).
 */
export const routes = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: 'Home', icon: 'House', nav: true, issueDrawer: true },
  },
  {
    path: '/sprints',
    name: 'sprints',
    component: () => import('@/views/SprintView.vue'),
    meta: { title: 'Sprints', icon: 'Workflow', nav: true, fullHeight: true, issueDrawer: true },
  },
  {
    path: '/semana',
    name: 'week',
    component: () => import('@/views/WeekView.vue'),
    meta: { title: 'Semana', icon: 'CalendarDays', nav: true, issueDrawer: true },
  },
  {
    path: '/lembretes',
    name: 'notes',
    component: () => import('@/views/NotesView.vue'),
    meta: { title: 'Lembretes', icon: 'StickyNote', nav: true, issueDrawer: true },
  },
  {
    path: '/contextos',
    name: 'contexts',
    component: () => import('@/views/ContextsView.vue'),
    meta: { title: 'Contextos', icon: 'BookOpenText', nav: true, issueDrawer: true },
  },
  {
    path: '/configuracoes',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { title: 'Configurações', icon: 'Settings', nav: true },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    redirect: '/',
  },
]

export const navItems = routes.filter((r) => r.meta?.nav)
