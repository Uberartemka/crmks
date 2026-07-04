import { defineStore } from 'pinia'
import { ref } from 'vue'
import { usersApi } from '@/api/users'
import type { UserOut } from '@/api/users'

export const useUsersStore = defineStore('users', () => {
  const list = ref<UserOut[]>([])
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      const { data } = await usersApi.list()
      list.value = data
    } finally {
      loading.value = false
    }
  }

  async function create(data: {
    username: string
    password: string
    name: string
    role?: string
    client_id?: number | null
  }) {
    const { data: res } = await usersApi.create(data)
    await load()
    return res
  }

  return { list, loading, load, create }
})
