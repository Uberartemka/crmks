<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { reportsApi, type ReportMetrics } from '@/api/reports'
import { toast } from '@/plugins/toast'

const period = ref('month')
const metrics = ref<ReportMetrics | null>(null)
const loading = ref(false)

async function loadMetrics() {
  loading.value = true
  try {
    const { data } = await reportsApi.metrics(period.value)
    metrics.value = data
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || 'Не удалось загрузить отчёт')
    metrics.value = null
  } finally {
    loading.value = false
  }
}

function formatMoney(v: number) {
  return v.toLocaleString('ru-RU') + ' ₽'
}

const maxDynamic = ref(1)
watch(
  metrics,
  (m) => {
    if (m && m.dynamics.values.length > 0) {
      maxDynamic.value = Math.max(...m.dynamics.values, 1)
    } else {
      maxDynamic.value = 1
    }
  },
  { immediate: true },
)

onMounted(loadMetrics)
watch(period, loadMetrics)
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Отчеты по закупкам</h1>
      <select v-model="period" class="input text-xs w-40">
        <option value="week">Неделя</option>
        <option value="month">Месяц</option>
        <option value="quarter">Квартал</option>
      </select>
    </div>

    <div v-if="loading" class="card p-12 text-center">
      <div class="text-sm font-bold text-neutral-500">Загрузка отчёта...</div>
    </div>

    <div v-else-if="metrics">
      <div class="grid md:grid-cols-3 gap-6 mb-6">
        <div class="card p-6 space-y-3">
          <div class="text-xs font-bold text-neutral-500 uppercase">Оборот</div>
          <div class="text-4xl font-bold font-bebas text-brand-700">{{ formatMoney(metrics.revenue) }}</div>
          <div class="text-xs text-neutral-500 font-bold">{{ metrics.order_count }} заказов</div>
        </div>
        <div class="card p-6 space-y-3">
          <div class="text-xs font-bold text-neutral-500 uppercase">Средний чек</div>
          <div class="text-4xl font-bold font-bebas text-brand-700">{{ formatMoney(metrics.avg_check) }}</div>
        </div>
        <div class="card p-6 space-y-3">
          <div class="text-xs font-bold text-neutral-500 uppercase">Конверсия КП</div>
          <div class="text-4xl font-bold font-bebas text-brand-700">{{ metrics.conversion }}%</div>
          <div class="text-xs text-neutral-500 font-bold">{{ metrics.delivered_count }} из {{ metrics.proposals_count }} КП</div>
        </div>
      </div>

      <div class="card p-5">
        <div class="text-lg font-bold font-bebas tracking-wider mb-4">Динамика выручки (6 месяцев)</div>
        <div
          v-if="metrics.dynamics.values.every((v) => v === 0)"
          class="text-center py-12 text-sm text-neutral-400 font-semibold"
        >
          Нет данных за период
        </div>
        <div v-else class="h-48 flex items-end gap-4">
          <div
            v-for="(val, i) in metrics.dynamics.values"
            :key="i"
            class="flex-1 flex flex-col items-center gap-2"
          >
            <div
              class="w-full bg-slate-100 rounded-t-xl h-32 relative flex items-end justify-center overflow-hidden"
            >
              <div
                class="bg-brand-700 w-full transition-all duration-500"
                :style="{ height: (val / maxDynamic * 100) + '%' }"
              />
            </div>
            <span class="text-[10px] text-neutral-500 font-bold">{{ metrics.dynamics.labels[i] }}</span>
            <span class="text-[9px] text-neutral-400">{{ val > 0 ? Math.round(val / 1000) + 'k' : '—' }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="card p-12 text-center">
      <div class="text-sm font-bold text-neutral-400">Нет данных за период</div>
    </div>
  </div>
</template>
