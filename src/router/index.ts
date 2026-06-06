import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { roleGuard } from './guards'

const routes: RouteRecordRaw[] = [
  { path: '/login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
  { path: '/catalog', component: () => import('@/views/CatalogView.vue'), meta: { public: true } },

  {
    path: '/admin',
    component: () => import('@/layouts/AdminLayout.vue'),
    meta: { roles: ['admin'] },
    children: [
      { path: '', redirect: '/admin/dashboard' },
      { path: 'dashboard', component: () => import('@/views/admin/DashboardView.vue') },
      { path: 'proposals', component: () => import('@/views/admin/ProposalsView.vue') },
      { path: 'reports', component: () => import('@/views/admin/ReportsView.vue') },
      { path: 'parser', component: () => import('@/views/admin/ParserView.vue') },
      { path: 'audit', component: () => import('@/views/admin/AuditView.vue') },
      { path: 'clients', component: () => import('@/views/admin/ClientsView.vue') },
      { path: 'plans', component: () => import('@/views/manager/PlanView.vue') },
      { path: 'calls', component: () => import('@/views/admin/CallsView.vue') },
      { path: 'calendar', component: () => import('@/views/CalendarPage.vue') },
      { path: 'personnel', component: () => import('@/views/admin/PersonnelView.vue') },
    ],
  },

  {
    path: '/manager',
    component: () => import('@/layouts/ManagerLayout.vue'),
    meta: { roles: ['manager'] },
    children: [
      { path: '', redirect: '/manager/dashboard' },
      { path: 'dashboard', component: () => import('@/views/manager/DashboardView.vue') },
      { path: 'plan', component: () => import('@/views/manager/PlanView.vue') },
      { path: 'leads', component: () => import('@/views/manager/LeadsView.vue') },
      { path: 'calls', component: () => import('@/views/manager/CallsView.vue') },
      { path: 'proposals', component: () => import('@/views/manager/ProposalsView.vue') },
      { path: 'calendar', component: () => import('@/views/CalendarPage.vue') },
      { path: 'proposal-history', component: () => import('@/views/manager/ProposalHistoryView.vue') },
    ],
  },

  {
    path: '/employee',
    component: () => import('@/layouts/ManagerLayout.vue'),
    meta: { roles: ['employee'] },
    children: [
      { path: '', redirect: '/employee/dashboard' },
      { path: 'dashboard', component: () => import('@/views/manager/DashboardView.vue') },
      { path: 'plan', component: () => import('@/views/manager/PlanView.vue') },
    ],
  },

  {
    path: '/client',
    component: () => import('@/layouts/ClientLayout.vue'),
    meta: { roles: ['client'] },
    children: [
      { path: '', redirect: '/client/dashboard' },
      { path: 'dashboard', component: () => import('@/views/client/DashboardView.vue') },
      { path: 'orders', component: () => import('@/views/client/OrdersView.vue') },
      { path: 'calculator', component: () => import('@/views/client/CalculatorView.vue') },
      { path: 'machinery', component: () => import('@/views/client/MachineryView.vue') },
      { path: 'calendar', component: () => import('@/views/CalendarPage.vue') },
      { path: 'plan', component: () => import('@/views/manager/PlanView.vue') },
      { path: 'defects', component: () => import('@/views/client/DefectsView.vue') },
    ],
  },

  { path: '/', redirect: '/login' },
  { path: '/:pathMatch(.*)*', redirect: '/login' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(roleGuard)
