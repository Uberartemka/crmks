<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useDefectsStore } from '@/stores/defects'
import { useConfirm } from '@/composables/useConfirm'
import { toast } from '@/plugins/toast'
import BaseBadge from '@/components/ui/BaseBadge.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import type { DefectStatus } from '@/types/defect'

const store = useDefectsStore()
const { confirm } = useConfirm()

const newDefect = ref({ equipment: '', bearing: '', description: '', status: 'new' as DefectStatus })
const saving = ref(false)

const STATUS_MAP: Record<DefectStatus, { label: string; type: 'success'|'warning'|'danger'|'info'|'gray' }> = {
  new: { label: 'Новый', type: 'gray' },
  critical: { label: 'Критично', type: 'danger' },
  replacement_ordered: { label: 'Заказана замена', type: 'warning' },
  resolved: { label: 'Решено', type: 'success' },
}

const STATUS_OPTIONS: { value: DefectStatus; label: string }[] = [
  { value: 'new', label: 'Новый' },
  { value: 'critical', label: 'Критично' },
  { value: 'replacement_ordered', label: 'Заказана замена' },
  { value: 'resolved', label: 'Решено' },
]

async function addDefect() {
  if (!newDefect.value.equipment.trim()) {
    toast.warning('Укажите оборудование')
    return
  }
  saving.value = true
  try {
    await store.create({
      equipment: newDefect.value.equipment,
      bearing: newDefect.value.bearing || undefined,
      description: newDefect.value.description,
      status: newDefect.value.status,
    })
    newDefect.value = { equipment: '', bearing: '', description: '', status: 'new' }
    toast.success('Дефект добавлен')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || 'Ошибка сохранения')
  } finally {
    saving.value = false
  }
}

async function removeDefect(id: number) {
  const ok = await confirm({
    title: 'Удалить дефект?',
    message: 'Запись о дефекте будет удалена безвозвратно.',
    confirmText: 'Удалить',
    danger: true,
  })
  if (!ok) return
  try {
    await store.remove(id)
    toast.success('Дефект удалён')
  } catch {
    toast.error('Ошибка удаления')
  }
}

onMounted(() => store.load().catch(() => toast.error('Не удалось загрузить дефекты')))
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Дефектовка оборудования</h1>

    <!-- Form -->
    <div class="card p-5 space-y-3">
      <div class="text-xs font-bold text-neutral-500 uppercase mb-1">Добавить дефект</div>
      <div class="grid md:grid-cols-2 gap-3">
        <input v-model="newDefect.equipment" class="input" placeholder="Оборудование (напр. Нория №1)" />
        <input v-model="newDefect.bearing" class="input" placeholder="Подшипник (напр. HHB 6205)" />
      </div>
      <textarea v-model="newDefect.description" class="input w-full resize-none" rows="2" placeholder="Описание дефекта"></textarea>
      <div class="flex gap-3 items-end">
        <div class="flex-1">
          <label class="block text-[10px] font-bold text-neutral-500 uppercase mb-1">Статус</label>
          <select v-model="newDefect.status" class="input">
            <option v-for="s in STATUS_OPTIONS" :key="s.value" :value="s.value">{{ s.label }}</option>
          </select>
        </div>
        <BaseButton variant="primary" :disabled="saving" @click="addDefect">
          {{ saving ? 'Сохраняю…' : 'Добавить' }}
        </BaseButton>
      </div>
    </div>

    <!-- List -->
    <div v-if="store.items.length === 0" class="card p-8 text-center">
      <div class="text-sm font-bold text-neutral-700">Дефектов пока нет</div>
      <div class="text-xs text-neutral-500 mt-1">Добавьте первый дефект через форму выше.</div>
    </div>

    <div v-else class="card overflow-hidden">
      <table class="w-full text-xs text-left">
        <thead class="bg-neutral-900 text-white font-bebas text-sm tracking-wider uppercase">
          <tr>
            <th class="px-4 py-3">Оборудование</th>
            <th class="px-4 py-3">Подшипник</th>
            <th class="px-4 py-3">Описание</th>
            <th class="px-4 py-3 text-center">Статус</th>
            <th class="px-4 py-3 text-center">Дата</th>
            <th class="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-neutral-100 font-medium">
          <tr v-for="d in store.items" :key="d.id" class="hover:bg-slate-50 transition">
            <td class="px-4 py-3 font-bold text-neutral-900">{{ d.equipment }}</td>
            <td class="px-4 py-3 text-neutral-600">{{ d.bearing || '—' }}</td>
            <td class="px-4 py-3 text-neutral-600 max-w-xs">{{ d.description || '—' }}</td>
            <td class="px-4 py-3 text-center">
              <BaseBadge :type="STATUS_MAP[d.status as DefectStatus].type">
                {{ STATUS_MAP[d.status as DefectStatus].label }}
              </BaseBadge>
            </td>
            <td class="px-4 py-3 text-center text-neutral-500">{{ (d.detected_at || d.created_at || '').slice(0, 10) }}</td>
            <td class="px-4 py-3 text-center">
              <button class="text-red-500 hover:text-red-700 transition" title="Удалить" @click="removeDefect(d.id)">
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
