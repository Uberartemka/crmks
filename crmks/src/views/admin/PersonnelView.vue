<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useUsersStore } from '@/stores/users'
import { Plus, X } from 'lucide-vue-next'

const store = useUsersStore()
onMounted(() => store.load())

const modalOpen = ref(false)
const err = ref('')
const form = ref({ username: '', name: '', password: '', role: 'employee' })

async function save() {
  err.value = ''
  if (!form.value.username.trim() || !form.value.name.trim() || !form.value.password.trim()) {
    err.value = 'Заполните все поля'
    return
  }
  try {
    await store.create({
      username: form.value.username.trim(),
      name: form.value.name.trim(),
      password: form.value.password,
      role: form.value.role,
    })
    modalOpen.value = false
    form.value = { username: '', name: '', password: '', role: 'employee' }
  } catch (e: any) {
    err.value = e?.response?.data?.detail ?? 'Ошибка создания'
  }
}
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Персонал</h1>
      <button class="btn-primary text-sm" @click="modalOpen = true">
        <Plus :size="14" /> Добавить сотрудника
      </button>
    </div>

    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-neutral-500 text-[10px] uppercase font-bold">
          <tr>
            <th class="px-4 py-3 text-left">ФИО</th>
            <th class="px-4 py-3 text-left">Должность</th>
            <th class="px-4 py-3 text-left">Email</th>
            <th class="px-4 py-3 text-center">Статус</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="e in store.list" :key="e.id" class="hover:bg-slate-50 transition">
            <td class="px-4 py-3 font-bold text-neutral-900">{{ e.name }}</td>
            <td class="px-4 py-3 text-xs">{{ e.role }}</td>
            <td class="px-4 py-3 text-xs text-neutral-500">{{ e.username }}</td>
            <td class="px-4 py-3 text-center">
              <span class="px-2 py-1 rounded-full text-[9px] font-bold bg-green-100 text-green-700">Активен</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal -->
    <div v-if="modalOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="modalOpen = false">
      <div class="card w-full max-w-sm p-4 space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="font-semibold">Новый сотрудник</h3>
          <button class="btn-ghost !p-1" @click="modalOpen = false"><X :size="16" /></button>
        </div>

        <input v-model="form.username" class="input" placeholder="Логин (email)" />
        <input v-model="form.name" class="input" placeholder="ФИО" />
        <input v-model="form.password" type="password" class="input" placeholder="Пароль" />
        <select v-model="form.role" class="input">
          <option value="employee">Сотрудник</option>
          <option value="manager">Менеджер</option>
          <option value="admin">Администратор</option>
        </select>

        <p v-if="err" class="text-xs text-red-600">{{ err }}</p>

        <div class="flex gap-2 justify-end">
          <button class="btn-ghost text-sm" @click="modalOpen = false">Отмена</button>
          <button class="btn-primary text-sm" @click="save">Сохранить</button>
        </div>
      </div>
    </div>
  </div>
</template>
