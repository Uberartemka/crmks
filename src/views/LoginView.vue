<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const username = ref(''); const password = ref(''); const err = ref('')

const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true'

async function submit() {
  err.value = ''

  // Сбрасываем старый токен перед входом (чтобы не было закешированной сессии)
  localStorage.removeItem('ksvrn_token')
  localStorage.removeItem('ksvrn_user')

  try {
    if (USE_MOCKS) {
      const role = username.value.startsWith('admin') ? 'admin'
        : username.value.startsWith('manager') ? 'manager' : 'client'
      const mockUser: any = { id: 1, username: username.value, name: 'Test', role }
      auth.$patch({
        token: 'mock-token',
        user: mockUser,
      })
      localStorage.setItem('ksvrn_token', 'mock-token')
      localStorage.setItem('ksvrn_user', JSON.stringify(mockUser))
    } else {
      await auth.login(username.value, password.value)
    }
    router.push(`/${auth.role}/dashboard`)
  } catch (e: any) {
    err.value = e?.response?.data?.detail ?? 'Ошибка входа'
  }
}
</script>

<template>
  <div class="h-full flex items-center justify-center bg-slate-100">
    <form class="card p-6 w-80 space-y-3" @submit.prevent="submit">
      <h1 class="text-xl font-bold">Вход HHB B2B</h1>
      <p class="text-xs text-slate-500">
        Для презентации: <code>admin / admin</code> или <code>admin / admin123</code>
      </p>
      <p class="text-xs text-slate-500">
        Демо: <code>manager1 / pass123</code>
      </p>
      <input v-model="username" class="input" placeholder="Логин" />
      <input v-model="password" type="password" class="input" placeholder="Пароль" />
      <p v-if="err" class="text-xs text-red-600">{{ err }}</p>
      <button class="btn-primary w-full">Войти</button>
    </form>
  </div>
</template>
