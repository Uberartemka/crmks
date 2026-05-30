import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import type { User, Role } from '@/types/auth'

const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('ksvrn_token'))

  const isAuthenticated = computed(() => !!token.value && !!user.value)
  const role = computed<Role | null>(() => user.value?.role ?? null)

  function _save(userData: User, tok: string) {
    token.value = tok
    user.value = userData
    localStorage.setItem('ksvrn_token', tok)
    localStorage.setItem('ksvrn_user', JSON.stringify(userData))
  }

  async function login(username: string, password: string) {
    const { data } = await authApi.login(username, password)
    _save(data.user, data.token)
  }

  async function fetchMe() {
    if (!token.value) return

    // If we have a stale mock token but mocks are now disabled, clear it
    if (!USE_MOCKS && token.value.startsWith('mock-')) {
      logout()
      return
    }

    // If mock token and mocks enabled, restore from localStorage
    if (USE_MOCKS && token.value.startsWith('mock-')) {
      const saved = localStorage.getItem('ksvrn_user')
      if (saved) {
        try { user.value = JSON.parse(saved) } catch { /* ignore */ }
      }
      return
    }

    try {
      const { data } = await authApi.me()
      user.value = data
      localStorage.setItem('ksvrn_user', JSON.stringify(data))
    } catch (e: any) {
      // If backend rejects token, clear auth
      if (e?.response?.status === 401) {
        logout()
      }
      // Otherwise (network error, 404) keep token and try to restore from localStorage
      const saved = localStorage.getItem('ksvrn_user')
      if (saved) {
        try { user.value = JSON.parse(saved) } catch { /* ignore */ }
      }
    }
  }

  function logout() {
    user.value = null
    token.value = null
    localStorage.removeItem('ksvrn_token')
    localStorage.removeItem('ksvrn_user')
  }

  return { user, token, isAuthenticated, role, login, fetchMe, logout }
})
