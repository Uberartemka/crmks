<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const username = ref(''); const password = ref(''); const err = ref('')

async function submit() {
  err.value = ''

  // Сбрасываем старый токен перед входом (чтобы не было закешированной сессии)
  localStorage.removeItem('ksvrn_token')
  localStorage.removeItem('ksvrn_user')

  try {
    await auth.login(username.value, password.value)
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
      <input v-model="username" class="input" placeholder="Логин" />
      <input v-model="password" type="password" class="input" placeholder="Пароль" />
      <p v-if="err" class="text-xs text-red-600">{{ err }}</p>
      <button class="btn-primary w-full">Войти</button>
    </form>
  </div>
</template>
