<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { chatApi } from '@/api/chat'
import BaseButton from '@/components/ui/BaseButton.vue'
import { toast } from '@/plugins/toast'
import { X } from 'lucide-vue-next'

interface StaffUser {
  id: number
  username: string
  name: string
}

const emit = defineEmits<{ close: []; created: [] }>()
const users = ref<StaffUser[]>([])
const name = ref('')
const selected = ref<number[]>([])

onMounted(async () => {
  try {
    const { data } = await chatApi.staffUsers()
    users.value = data
  } catch (e) {
    toast.error('Не удалось загрузить сотрудников')
  }
})

function toggle(id: number) {
  if (selected.value.includes(id)) selected.value = selected.value.filter((x) => x !== id)
  else selected.value = [...selected.value, id]
}

async function submit() {
  if (!name.value.trim()) {
    toast.error('Введите название канала')
    return
  }
  try {
    await chatApi.createTopic({ name: name.value.trim(), member_ids: selected.value })
    toast.success('Канал создан')
    emit('created')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'Ошибка создания')
  }
}
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    @click.self="emit('close')"
  >
    <div class="card w-full max-w-md p-4 space-y-3">
      <div class="flex items-center justify-between">
        <h3 class="font-semibold">Новый канал</h3>
        <BaseButton variant="ghost" class="!p-1" @click="emit('close')">
          <X :size="16" />
        </BaseButton>
      </div>
      <input v-model="name" class="input" placeholder="Название канала" />
      <div>
        <p class="text-xs text-neutral-500 mb-1">Участники</p>
        <div
          class="max-h-48 overflow-y-auto border border-slate-200 rounded-lg divide-y divide-slate-100"
        >
          <label
            v-for="u in users"
            :key="u.id"
            class="flex items-center gap-2 px-3 py-2 hover:bg-slate-50 cursor-pointer"
          >
            <input
              type="checkbox"
              :checked="selected.includes(u.id)"
              @change="toggle(u.id)"
            />
            <span class="text-sm">{{ u.name }}</span>
          </label>
        </div>
      </div>
      <div class="flex gap-2 justify-end">
        <BaseButton variant="ghost" @click="emit('close')">Отмена</BaseButton>
        <BaseButton variant="primary" @click="submit">Создать</BaseButton>
      </div>
    </div>
  </div>
</template>
