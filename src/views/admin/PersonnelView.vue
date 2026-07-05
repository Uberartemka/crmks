<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useUsersStore } from '@/stores/users'
import { useClientsStore } from '@/stores/clients'
import { toast } from '@/plugins/toast'
import BaseButton from '@/components/ui/BaseButton.vue'
import Avatar from '@/components/ui/Avatar.vue'
import { Plus, X } from 'lucide-vue-next'

const store = useUsersStore()
const clientsStore = useClientsStore()
onMounted(() => {
  store.load()
  clientsStore.load()
})

const modalOpen = ref(false)
const form = ref({
  username: '',
  name: '',
  password: '',
  role: 'employee' as 'employee' | 'manager' | 'admin' | 'client',
  client_id: null as number | null,
})

// Show the company picker only for the client role.
const isClientRole = computed(() => form.value.role === 'client')

const ROLE_LABELS: Record<string, string> = {
  employee: 'Сотрудник',
  manager: 'Менеджер',
  admin: 'Администратор',
  client: 'Клиент',
}

function openModal() {
  form.value = { username: '', name: '', password: '', role: 'employee', client_id: null }
  modalOpen.value = true
}

async function save() {
  if (!form.value.username.trim() || !form.value.name.trim() || !form.value.password.trim()) {
    toast.error('Заполните все поля')
    return
  }
  if (isClientRole.value && !form.value.client_id) {
    toast.error('Выберите компанию для пользователя-клиента')
    return
  }
  try {
    await store.create({
      username: form.value.username.trim(),
      name: form.value.name.trim(),
      password: form.value.password,
      role: form.value.role,
      // Send client_id only for the client role; keep null otherwise.
      client_id: isClientRole.value ? form.value.client_id : null,
    })
    toast.success('Сотрудник добавлен')
    modalOpen.value = false
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'Ошибка создания')
  }
}
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Персонал</h1>
      <BaseButton variant="primary" @click="openModal">
        <Plus :size="14" class="mr-1" /> Добавить сотрудника
      </BaseButton>
    </div>

    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-neutral-500 text-[10px] uppercase font-bold">
          <tr>
            <th class="px-4 py-3"></th>
            <th class="px-4 py-3 text-left">ФИО</th>
            <th class="px-4 py-3 text-left">Должность</th>
            <th class="px-4 py-3 text-left">Логин</th>
            <th class="px-4 py-3 text-left">Компания</th>
            <th class="px-4 py-3 text-center">Статус</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="e in store.list" :key="e.id" class="hover:bg-slate-50 transition">
            <td class="px-3 py-2">
              <Avatar :name="e.name" :src="e.avatar_url" :size="32" />
            </td>
            <td class="px-4 py-3 font-bold text-neutral-900">{{ e.name }}</td>
            <td class="px-4 py-3 text-xs">{{ ROLE_LABELS[e.role] ?? e.role }}</td>
            <td class="px-4 py-3 text-xs text-neutral-500">{{ e.username }}</td>
            <td class="px-4 py-3 text-xs text-neutral-700">{{ e.client_name ?? '—' }}</td>
            <td class="px-4 py-3 text-center">
              <span class="px-2 py-1 rounded-full text-[9px] font-bold bg-green-100 text-green-700">Активен</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal -->
    <div
      v-if="modalOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      @click.self="modalOpen = false"
    >
      <div class="card w-full max-w-sm p-4 space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="font-semibold">Новый сотрудник</h3>
          <BaseButton variant="ghost" class="!p-1" @click="modalOpen = false">
            <X :size="16" />
          </BaseButton>
        </div>

        <input v-model="form.username" class="input" placeholder="Логин (email)" />
        <input v-model="form.name" class="input" placeholder="ФИО" />
        <input v-model="form.password" type="password" class="input" placeholder="Пароль" />
        <select v-model="form.role" class="input">
          <option value="employee">Сотрудник</option>
          <option value="manager">Менеджер</option>
          <option value="admin">Администратор</option>
          <option value="client">Клиент</option>
        </select>

        <select v-if="isClientRole" v-model="form.client_id" class="input">
          <option :value="null" disabled>Выберите компанию…</option>
          <option v-for="c in clientsStore.list" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>

        <div class="flex gap-2 justify-end">
          <BaseButton variant="ghost" @click="modalOpen = false">Отмена</BaseButton>
          <BaseButton variant="primary" @click="save">Сохранить</BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>
