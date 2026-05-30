import type { NavigationGuard, RouteLocationNormalized } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { Role } from '@/types/auth'

export const roleGuard: NavigationGuard = async (to: RouteLocationNormalized) => {
  const auth = useAuthStore()
  if (to.meta.public) return true

  if (!auth.isAuthenticated) {
    await auth.fetchMe()
    if (!auth.isAuthenticated) return { path: '/login' }
  }

  const allowed = to.meta.roles as Role[] | undefined
  if (allowed && auth.role && !allowed.includes(auth.role)) {
    return { path: `/${auth.role}/dashboard` }
  }
  return true
}
