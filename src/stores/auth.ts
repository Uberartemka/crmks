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

  let fetchMeInFlight: Promise<void> | null = null

  async function login(username: string, password: string) {
    const { data } = await authApi.login(username, password)
    _save(data.user, data.token)
  }

  async function _doFetchMe(retries: number): Promise<boolean> {
    // If we have a stale mock token but mocks are now disabled, clear it
    if (!USE_MOCKS && token.value?.startsWith('mock-')) {
      logout()
      return false
    }

    // If mock token and mocks enabled, restore from localStorage
    if (USE_MOCKS && token.value?.startsWith('mock-')) {
      const saved = localStorage.getItem('ksvrn_user')
      if (saved) {
        try { user.value = JSON.parse(saved) } catch { /* ignore */ }
      }
      return true
    }

    try {
      const { data } = await authApi.me()
      user.value = data
      localStorage.setItem('ksvrn_user', JSON.stringify(data))
      return true
    } catch (e: any) {
      // 401 — retry with backoff before clearing token (race: server restart)
      if (e?.response?.status === 401 && retries > 0) {
        await new Promise(r => setTimeout(r, 2000))
        return _doFetchMe(retries - 1)
      }
      // If backend explicitly says 401 after all retries, clear auth
      if (e?.response?.status === 401) {
        logout()
        return false
      }
      // Network error, 404, etc — keep token, try to restore from localStorage
      const saved = localStorage.getItem('ksvrn_user')
      if (saved) {
        try { user.value = JSON.parse(saved) } catch { /* ignore */ }
      }
      return false
    }
  }

  async function fetchMe() {
    if (!token.value) return
    if (fetchMeInFlight) return await fetchMeInFlight

    fetchMeInFlight = (async () => {
      await _doFetchMe(2) // 2 retries ≈ 4 seconds of backoff
    })()

    try {
      await fetchMeInFlight
    } finally {
      fetchMeInFlight = null
    }
  }

  async function logout() {
    // Best-effort server-side invalidation (ignore network/401)
    try {
      await authApi.logout()
    } catch {
      // ignore
    }

    user.value = null
    token.value = null
    localStorage.removeItem('ksvrn_token')
    localStorage.removeItem('ksvrn_user')
  }

  return { user, token, isAuthenticated, role, login, fetchMe, logout }
})
