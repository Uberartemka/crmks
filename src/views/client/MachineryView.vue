<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useMachineryStore } from '@/stores/machinery'
import { useConfirm } from '@/composables/useConfirm'
import { toast } from '@/plugins/toast'
import BaseBadge from '@/components/ui/BaseBadge.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import type { Machine, MachineryStatus } from '@/types/machinery'

const store = useMachineryStore()
const { confirm } = useConfirm()

interface NewMachine {
  name: string
  node: string
  bearing: string
  brand: string
  install_date: string
  wear: number
  status: MachineryStatus
}

const newMachine = ref<NewMachine>({
  name: '',
  node: '',
  bearing: '',
  brand: '',
  install_date: '',
  wear: 0,
  status: 'normal',
})
const saving = ref(false)

const STATUS_MAP: Record<MachineryStatus, { label: string; type: 'success'|'warning'|'danger'|'info'|'gray' }> = {
  normal: { label: 'Норма', type: 'success' },
  warning: { label: 'Предельный', type: 'warning' },
  critical: { label: 'Заменить!', type: 'danger' },
  replaced: { label: 'Заменено', type: 'info' },
}

const STATUS_OPTIONS: { value: MachineryStatus; label: string }[] = [
  { value: 'normal', label: 'Норма' },
  { value: 'warning', label: 'Предельный' },
  { value: 'critical', label: 'Заменить!' },
  { value: 'replaced', label: 'Заменено' },
]

function wearClass(wear: number): string {
  return wear > 90 ? 'bg-red-500' : wear > 70 ? 'bg-yellow-500' : 'bg-green-500'
}

function wearTextClass(wear: number): string {
  return wear > 90 ? 'text-red-600' : wear > 70 ? 'text-yellow-600' : 'text-green-600'
}

function statusType(m: Machine) {
  return STATUS_MAP[m.status as MachineryStatus]?.type ?? 'gray'
}

function statusLabel(m: Machine) {
  return STATUS_MAP[m.status as MachineryStatus]?.label ?? m.status
}

async function addMachine() {
  if (!newMachine.value.name.trim()) {
    toast.warning('Укажите оборудование')
    return
  }
  saving.value = true
  try {
    await store.create({
      name: newMachine.value.name,
      node: newMachine.value.node || undefined,
      bearing: newMachine.value.bearing || undefined,
      brand: newMachine.value.brand || undefined,
      install_date: newMachine.value.install_date || undefined,
      wear: newMachine.value.wear,
      status: newMachine.value.status,
    })
    newMachine.value = {
      name: '',
      node: '',
      bearing: '',
      brand: '',
      install_date: '',
      wear: 0,
      status: 'normal',
    }
    toast.success('Узел добавлен')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || 'Ошибка сохранения')
  } finally {
    saving.value = false
  }
}

async function orderReplacement(m: Machine) {
  const ok = await confirm({
    title: 'Заказать замену?',
    message: `Отметить «${m.name}» как ожидающий замены (статус «Заменить!»)?`,
    confirmText: 'Заказать',
  })
  if (!ok) return
  try {
    await store.update(m.id, { status: 'critical' })
    toast.success('Статус обновлён: Заменить!')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || 'Ошибка обновления')
  }
}

async function removeMachine(id: number) {
  const ok = await confirm({
    title: 'Удалить узел?',
    message: 'Запись об оборудовании будет удалена безвозвратно.',
    confirmText: 'Удалить',
    danger: true,
  })
  if (!ok) return
  try {
    await store.remove(id)
    toast.success('Узел удалён')
  } catch {
    toast.error('Ошибка удаления')
  }
}

onMounted(() => store.load().catch(() => toast.error('Не удалось загрузить оборудование')))
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Карта оборудования</h1>

    <!-- Form -->
    <div class="card p-5 space-y-3">
      <div class="text-xs font-bold text-neutral-500 uppercase mb-1">Добавить узел</div>
      <div class="grid md:grid-cols-2 gap-3">
        <input v-model="newMachine.name" class="input" placeholder="Оборудование (напр. Нория №1)" />
        <input v-model="newMachine.node" class="input" placeholder="Узел (напр. Приводной вал головки)" />
        <input v-model="newMachine.bearing" class="input" placeholder="Установленная модель (напр. HHB UCP 208 LS3)" />
        <input v-model="newMachine.brand" class="input" placeholder="Бренд (напр. HHB)" />
        <input v-model="newMachine.install_date" class="input" placeholder="Дата установки (напр. 10.05.2025)" />
        <div class="flex gap-3">
          <div class="flex-1">
            <label class="block text-[10px] font-bold text-neutral-500 uppercase mb-1">Износ, %</label>
            <input v-model.number="newMachine.wear" type="number" min="0" max="100" class="input" />
          </div>
          <div class="flex-1">
            <label class="block text-[10px] font-bold text-neutral-500 uppercase mb-1">Статус</label>
            <select v-model="newMachine.status" class="input">
              <option v-for="s in STATUS_OPTIONS" :key="s.value" :value="s.value">{{ s.label }}</option>
            </select>
          </div>
        </div>
      </div>
      <div class="flex justify-end">
        <BaseButton variant="primary" :disabled="saving" @click="addMachine">
          {{ saving ? 'Сохраняю…' : '+ Добавить' }}
        </BaseButton>
      </div>
    </div>

    <!-- List -->
    <div v-if="store.items.length === 0" class="card p-8 text-center">
      <div class="text-sm font-bold text-neutral-700">Оборудования пока нет</div>
      <div class="text-xs text-neutral-500 mt-1">Добавьте первый узел через форму выше.</div>
    </div>

    <div v-else class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-sm text-left">
        <thead class="bg-slate-50 text-neutral-500 uppercase text-[10px] font-bold tracking-wider border-b border-slate-200">
          <tr>
            <th class="px-6 py-4">Оборудование</th>
            <th class="px-6 py-4">Узел</th>
            <th class="px-6 py-4">Установленная модель</th>
            <th class="px-6 py-4 text-center">Дата установки</th>
            <th class="px-6 py-4 text-center">Износ</th>
            <th class="px-6 py-4 text-center">Статус</th>
            <th class="px-6 py-4 text-center">Замена</th>
            <th class="px-6 py-4"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-200 text-xs font-semibold text-neutral-700">
          <tr v-for="m in store.items" :key="m.id" class="hover:bg-slate-50 transition">
            <td class="px-6 py-4 font-bold text-neutral-900">{{ m.name }}</td>
            <td class="px-6 py-4 text-neutral-500">{{ m.node || '—' }}</td>
            <td class="px-6 py-4 font-bold" :class="m.brand === 'HHB' ? 'text-brand-700' : 'text-neutral-500'">
              {{ m.bearing || '—' }}
            </td>
            <td class="px-6 py-4 text-center">{{ m.install_date || (m.created_at || '').slice(0, 10) || '—' }}</td>
            <td class="px-6 py-4 text-center">
              <div class="w-24 bg-slate-100 rounded-full h-2.5 mx-auto overflow-hidden">
                <div class="h-2.5" :class="wearClass(m.wear)" :style="{ width: m.wear + '%' }" />
              </div>
              <span class="text-[10px] mt-1 block" :class="wearTextClass(m.wear)">{{ m.wear }}%</span>
            </td>
            <td class="px-6 py-4 text-center">
              <BaseBadge :type="statusType(m)">{{ statusLabel(m) }}</BaseBadge>
            </td>
            <td class="px-6 py-4 text-center">
              <button v-if="m.wear > 70 && m.status !== 'replaced'" class="btn-primary text-[9px] px-2 py-1" @click="orderReplacement(m)">
                Заказать замену
              </button>
              <span v-else class="text-neutral-400 text-[10px] font-bold">Не требуется</span>
            </td>
            <td class="px-6 py-4 text-center">
              <button class="text-red-500 hover:text-red-700 transition" title="Удалить" @click="removeMachine(m.id)">
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
