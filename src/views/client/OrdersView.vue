<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useOrdersStore } from '@/stores/orders'
import { useAuthStore } from '@/stores/auth'
import { useConfirm } from '@/composables/useConfirm'
import { toast } from '@/plugins/toast'
import BaseBadge from '@/components/ui/BaseBadge.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import type { Order, OrderStatus } from '@/types/order'

const store = useOrdersStore()
const auth = useAuthStore()
const { confirm } = useConfirm()

const isAdmin = computed(() => auth.role === 'admin' || auth.role === 'manager')

interface NewOrder {
  order_number: string
  name: string
  qty: number
  total: number
  status: OrderStatus
  order_date: string
}

const newOrder = ref<NewOrder>({
  order_number: '',
  name: '',
  qty: 1,
  total: 0,
  status: 'new',
  order_date: '',
})
const saving = ref(false)

const STATUS_MAP: Record<OrderStatus, { label: string; type: 'success'|'warning'|'danger'|'info'|'gray' }> = {
  new: { label: 'Новый', type: 'gray' },
  confirmed: { label: 'Подтверждён', type: 'info' },
  paid: { label: 'Оплачен', type: 'warning' },
  shipped: { label: 'В пути', type: 'info' },
  delivered: { label: 'Доставлен', type: 'success' },
  cancelled: { label: 'Отменён', type: 'danger' },
}

const STATUS_OPTIONS: { value: OrderStatus; label: string }[] = [
  { value: 'new', label: 'Новый' },
  { value: 'confirmed', label: 'Подтверждён' },
  { value: 'paid', label: 'Оплачен' },
  { value: 'shipped', label: 'В пути' },
  { value: 'delivered', label: 'Доставлен' },
  { value: 'cancelled', label: 'Отменён' },
]

/** Map an order status to a tracker step (0..3). cancelled = -1 (special). */
function statusStep(status: OrderStatus): number {
  switch (status) {
    case 'paid': return 1
    case 'shipped': return 2
    case 'delivered': return 3
    case 'cancelled': return -1
    default: return 0 // new / confirmed
  }
}

const TRACKER_STEPS = ['Заказ принят', 'Оплачен', 'В пути', 'Доставлен']

/**
 * Tracker step is computed from the most recent *active* order (cancelled
 * excluded). Falls back to the first order overall, then 0 when empty.
 */
const trackerStep = computed<number>(() => {
  const active = store.items.find((o) => o.status !== 'cancelled')
  const head = active ?? store.items[0]
  if (!head) return 0
  return statusStep(head.status as OrderStatus)
})

const trackerCancelled = computed(() => trackerStep.value === -1)

function statusType(o: Order) {
  return STATUS_MAP[o.status as OrderStatus]?.type ?? 'gray'
}
function statusLabel(o: Order) {
  return STATUS_MAP[o.status as OrderStatus]?.label ?? o.status
}

function fmtTotal(n: number): string {
  return Number(n || 0).toLocaleString('ru-RU')
}

async function addOrder() {
  if (!newOrder.value.name.trim()) {
    toast.warning('Укажите наименование заказа')
    return
  }
  saving.value = true
  try {
    await store.create({
      order_number: newOrder.value.order_number || undefined,
      name: newOrder.value.name,
      qty: newOrder.value.qty,
      total: newOrder.value.total,
      status: newOrder.value.status,
      order_date: newOrder.value.order_date || undefined,
    })
    newOrder.value = { order_number: '', name: '', qty: 1, total: 0, status: 'new', order_date: '' }
    toast.success('Заказ добавлен')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || 'Ошибка сохранения')
  } finally {
    saving.value = false
  }
}

async function removeOrder(id: number) {
  const ok = await confirm({
    title: 'Удалить заказ?',
    message: 'Запись о заказе будет удалена безвозвратно.',
    confirmText: 'Удалить',
    danger: true,
  })
  if (!ok) return
  try {
    await store.remove(id)
    toast.success('Заказ удалён')
  } catch {
    toast.error('Ошибка удаления')
  }
}

onMounted(() => store.load().catch(() => toast.error('Не удалось загрузить заказы')))
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Мои заказы и статусы</h1>
      <span class="text-xs font-bold text-emerald-700 bg-green-50 px-3 py-1.5 rounded-full border border-green-200">Всего: {{ store.items.length }}</span>
    </div>

    <!-- Tracker (4-step progress bar) -->
    <div v-if="store.items.length > 0" class="card p-6 space-y-6">
      <div class="flex items-center justify-between">
        <h2 class="text-lg font-bold font-bebas tracking-wider">Активное отслеживание</h2>
        <BaseBadge v-if="trackerCancelled" type="danger">Заказ отменён</BaseBadge>
      </div>
      <div class="relative flex flex-col md:flex-row md:items-center justify-between gap-6 md:gap-4">
        <div v-if="!trackerCancelled" class="hidden md:block absolute left-4 right-4 top-5 h-1 bg-slate-200 -z-0" />
        <div v-if="!trackerCancelled" class="hidden md:block absolute left-4 top-5 h-1 bg-brand-700 transition-all duration-500 -z-0" :style="{ width: (trackerStep / 3 * 100) + '%' }" />
        <div v-for="(step, i) in TRACKER_STEPS" :key="i" class="flex items-center md:flex-col gap-3 md:gap-2 relative z-10 text-xs text-center md:w-32">
          <div v-if="trackerCancelled" class="w-10 h-10 rounded-full flex items-center justify-center font-bold shadow-md bg-red-100 text-red-600">✕</div>
          <div v-else class="w-10 h-10 rounded-full flex items-center justify-center font-bold shadow-md"
            :class="i < trackerStep ? 'bg-brand-700 text-white shadow-brand-700/20' : i === trackerStep ? 'bg-brand-700 text-white animate-pulse shadow-brand-700/20' : 'bg-slate-200 text-slate-500'">
            {{ i < trackerStep ? '✓' : i === trackerStep ? '🚚' : i === 3 ? '🏁' : '○' }}
          </div>
          <div><div class="font-bold" :class="trackerCancelled ? 'text-neutral-400' : i <= trackerStep ? 'text-neutral-900' : 'text-neutral-400'">{{ step }}</div></div>
        </div>
      </div>
    </div>

    <!-- Add form (admin/manager only) -->
    <div v-if="isAdmin" class="card p-5 space-y-3">
      <div class="text-xs font-bold text-neutral-500 uppercase mb-1">Добавить заказ</div>
      <div class="grid md:grid-cols-2 gap-3">
        <input v-model="newOrder.order_number" class="input" placeholder="Номер заказа (напр. 104-M)" />
        <input v-model="newOrder.order_date" class="input" placeholder="Дата (напр. 26.05.2026)" />
      </div>
      <input v-model="newOrder.name" class="input w-full" placeholder="Номенклатура (напр. HHB UCP206 + UCF208)" />
      <div class="grid md:grid-cols-3 gap-3">
        <div>
          <label class="block text-[10px] font-bold text-neutral-500 uppercase mb-1">Кол-во</label>
          <input v-model.number="newOrder.qty" type="number" min="1" class="input" />
        </div>
        <div>
          <label class="block text-[10px] font-bold text-neutral-500 uppercase mb-1">Сумма, ₽</label>
          <input v-model.number="newOrder.total" type="number" min="0" class="input" />
        </div>
        <div>
          <label class="block text-[10px] font-bold text-neutral-500 uppercase mb-1">Статус</label>
          <select v-model="newOrder.status" class="input">
            <option v-for="s in STATUS_OPTIONS" :key="s.value" :value="s.value">{{ s.label }}</option>
          </select>
        </div>
      </div>
      <div class="flex justify-end">
        <BaseButton variant="primary" :disabled="saving" @click="addOrder">
          {{ saving ? 'Сохраняю…' : '+ Добавить' }}
        </BaseButton>
      </div>
    </div>

    <!-- Orders table -->
    <div v-if="store.items.length === 0" class="card p-8 text-center">
      <div class="text-sm font-bold text-neutral-700">Заказов пока нет</div>
      <div class="text-xs text-neutral-500 mt-1">
        <template v-if="isAdmin">Добавьте первый заказ через форму выше.</template>
        <template v-else>Здесь появятся ваши заказы.</template>
      </div>
    </div>

    <div v-else class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50">
        <h2 class="text-base font-bold text-neutral-800">Архив заказов</h2>
        <span class="text-xs text-neutral-400 font-medium">Всего: {{ store.items.length }}</span>
      </div>
      <table class="w-full text-sm text-left">
        <thead class="bg-slate-100 text-neutral-500 uppercase text-[10px] font-bold tracking-wider border-b border-slate-200">
          <tr>
            <th class="px-6 py-3.5">Заказ №</th>
            <th class="px-6 py-3.5">Дата</th>
            <th class="px-6 py-3.5">Номенклатура</th>
            <th class="px-6 py-3.5 text-center">Кол-во</th>
            <th class="px-6 py-3.5 text-right">Сумма</th>
            <th class="px-6 py-3.5 text-center">Статус</th>
            <th v-if="isAdmin" class="px-6 py-3.5"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-200 text-xs font-semibold text-neutral-700">
          <tr v-for="o in store.items" :key="o.id" class="hover:bg-slate-50 transition">
            <td class="px-6 py-4 font-bold text-neutral-900">{{ o.order_number || '—' }}</td>
            <td class="px-6 py-4 text-neutral-500">{{ o.order_date || (o.created_at || '').slice(0, 10) }}</td>
            <td class="px-6 py-4">{{ o.name }}</td>
            <td class="px-6 py-4 text-center font-bold">{{ o.qty }}</td>
            <td class="px-6 py-4 text-right font-extrabold text-neutral-900">{{ fmtTotal(o.total) }} ₽</td>
            <td class="px-6 py-4 text-center">
              <BaseBadge :type="statusType(o)">{{ statusLabel(o) }}</BaseBadge>
            </td>
            <td v-if="isAdmin" class="px-6 py-4 text-center">
              <button class="text-red-500 hover:text-red-700 transition" title="Удалить" @click="removeOrder(o.id)">
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
