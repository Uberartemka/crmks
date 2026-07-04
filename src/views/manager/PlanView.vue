<script setup lang="ts">
import { computed, onMounted, nextTick, ref, watch } from 'vue'
import type { Chart as ChartType } from 'chart.js/auto'
import Chart from 'chart.js/auto'

import { kpiPlansApi } from '@/api/kpiPlans'
import { useAuthStore } from '@/stores/auth'
import type { KpiPlansManager, KpiPlansPayload, KpiPlansManagerDailyDetail } from '@/api/kpiPlans'

const payload = ref<KpiPlansPayload | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const selectedIdx = ref(0)
const selectedManager = computed<KpiPlansManager | null>(() => payload.value?.managers[selectedIdx.value] || null)

const chartRef = ref<HTMLCanvasElement | null>(null)
let chart: ChartType | null = null

const NOW = new Date()
const defaultMonth = NOW.getMonth() + 1
const defaultYear = NOW.getFullYear()

const workDays = computed(() => selectedManager.value?.work_days ?? [])

function getTodayIso(): string {
  const today = new Date()
  const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  return iso
}

function getWorkDaysIso(year: number, month: number): string[] {
  const out: string[] = []
  const pad2 = (n: number) => String(n).padStart(2, '0')
  const isoDate = (d: Date) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`

  const start = new Date(year, month - 1, 1)
  const end = new Date(year, month, 1) // first day of next month
  const cur = new Date(start)

  while (cur < end) {
    // Mon-Fri
    const wd = cur.getDay() // 0..6 (Sun..Sat)
    const isWeekday = wd >= 1 && wd <= 5
    if (isWeekday) out.push(isoDate(cur))
    cur.setDate(cur.getDate() + 1)
  }

  return out
}

function dailyAt(i: number): KpiPlansManagerDailyDetail | null {
  const m = selectedManager.value
  if (!m) return null
  return m.daily_details[i] || null
}

const avgCapacityPct = computed(() => {
  const m = selectedManager.value
  if (!m) return 0
  const details = m.daily_details || []
  const passed = m.passed_days
  if (!passed || passed <= 0) return 0
  let sum = 0
  let cnt = 0
  for (let i = 0; i < passed && i < details.length; i++) {
    const d = details[i]
    if (!d) continue
    sum += d.capacity_pct
    cnt++
  }
  if (!cnt) return 0
  return Math.round(sum / cnt)
})

function destroyChart() {
  if (chart) {
    chart.destroy()
    chart = null
  }
}

function buildChart(manager: KpiPlansManager) {
  if (!chartRef.value) return

  destroyChart()

  const lastFact = (() => {
    for (let i = manager.fact_cum.length - 1; i >= 0; i--) {
      const v = manager.fact_cum[i]
      if (v !== null && v !== undefined) return v
    }
    return 0
  })()

  const planAtToday = (() => {
    const idx = manager.passed_days - 1
    if (idx < 0) return 0
    return manager.plan_cum[idx] ?? 0
  })()

  const delta = lastFact - planAtToday
  const fillGreen = 'rgba(29,158,117,0.18)'
  const fillRed = 'rgba(163,45,45,0.18)'
  const fillColor = delta >= 0 ? fillGreen : fillRed

  const factData = manager.fact_cum.map(v => (v === null ? null : v))
  const planData = manager.plan_cum

  const isDark = matchMedia && matchMedia('(prefers-color-scheme: dark)').matches
  const gridColor = isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.07)'
  const tickColor = isDark ? '#9e9e9e' : '#6b6b6b'
  const tooltipBg = isDark ? '#141414' : '#ffffff'
  const tooltipBorder = isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.08)'
  const tooltipTitle = isDark ? '#f0f0f0' : '#1a1a1a'
  const tooltipBody = isDark ? '#a0a0a0' : '#6b6b6b'

  const labels = manager.work_days.map(d => {
    const parts = d.split('-')
    if (parts.length < 3) return d
    return `${Number(parts[2])}.${Number(parts[1])}.`
  })

  chart = new Chart(chartRef.value, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Факт (ед.)',
          data: factData,
          borderColor: '#1D9E75',
          borderWidth: 2.5,
          tension: 0.35,
          pointRadius: factData.map((v, i) => (i === manager.passed_days - 1 && v !== null ? 6 : v !== null ? 2 : 0)),
          pointBackgroundColor: '#1D9E75',
          fill: '+1',
          backgroundColor: () => fillColor,
        },
        {
          label: 'Скорр. план (ед.)',
          data: planData,
          borderColor: isDark ? '#b4b2a9' : '#6b6b6b',
          borderWidth: 1.6,
          borderDash: [6, 5],
          pointRadius: 0,
          tension: 0,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: true,
          backgroundColor: tooltipBg,
          borderColor: tooltipBorder,
          borderWidth: 1,
          titleColor: tooltipTitle,
          bodyColor: tooltipBody,
          padding: 12,
          callbacks: {
            title: ctxItems => {
              const i = ctxItems?.[0]?.dataIndex ?? 0
              const d = manager.work_days[i]
              return d ? `День: ${d}` : 'День'
            },
            label: ctx => {
              const datasetIdx = ctx.datasetIndex
              const i = ctx.dataIndex
              const day = dailyAt(i)
              if (!day) return ''

              if (datasetIdx === 0) {
                const y = ctx.parsed.y
                if (y === null || y === undefined) return 'Факт: —'
                return [
                  `Факт: ${y} ед.`,
                  day.visits ? `  Выезды: ×${day.visits}` : null,
                  day.messenger ? `  Сделки: ×${day.messenger}` : null,
                  day.leads ? `  Лиды: ×${day.leads}` : null,
                  day.calls ? `  Звонки: ×${day.calls}` : null,
                ].filter(Boolean) as string[]
              }

              const y = ctx.parsed.y
              return y === null || y === undefined ? 'План: —' : `План: ${y} ед.`
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { color: tickColor, font: { size: 11 }, maxTicksLimit: 10 },
        },
        y: {
          grid: { color: gridColor },
          ticks: { color: tickColor, font: { size: 11 } },
          min: 0,
        },
      },
    },
  })
}

const tooltip = ref<{ show: boolean; x: number; y: number; text: string } | null>(null)

function showDayTooltip(e: MouseEvent, manager: KpiPlansManager, idx: number) {
  const day = manager.daily_details[idx]
  if (!day) return
  const lines = [
    `<div style="font-weight:700;margin-bottom:6px;">${day.date}</div>`,
    `<div style="display:flex;justify-content:space-between;gap:12px;color:${'#6b6b6b'};">`,
    `<span>Ёмкость:</span><span style="font-weight:700;">${day.capacity_pct}%</span>`,
    `</div>`,
    `<div style="margin-top:8px;border-top:1px solid rgba(0,0,0,0.08);padding-top:8px;font-size:12px;color:${'#6b6b6b'};">`,
    `${day.visits ? `🧳 Выезды ×${day.visits}<br/>` : ''}`,
    `${day.messenger ? `💬 Сделки ×${day.messenger}<br/>` : ''}`,
    `${day.leads ? `🎯 Лиды ×${day.leads}<br/>` : ''}`,
    `${day.calls ? `📞 Звонки ×${day.calls}<br/>` : ''}`,
    `</div>`,
  ].filter(Boolean)

  tooltip.value = {
    show: true,
    x: Math.min(e.clientX + 10, window.innerWidth - 220),
    y: Math.min(e.clientY + 10, window.innerHeight - 140),
    text: lines.join(''),
  }
}

function hideTooltip() {
  if (tooltip.value) tooltip.value.show = false
}

async function refreshChart() {
  const m = selectedManager.value
  if (!m) return
  await nextTick()
  buildChart(m)
}

watch(
  () => selectedIdx.value,
  () => {
    refreshChart()
  },
)

onMounted(async () => {
  loading.value = true
  error.value = null
  const auth = useAuthStore()

  try {
    const res = await kpiPlansApi.get({ month: defaultMonth, year: defaultYear })
    payload.value = res.data

    selectedIdx.value = 0
    await refreshChart()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || 'Ошибка загрузки KPI'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-start justify-between gap-4">
      <div>
        <h1 class="text-3xl font-extrabold font-bebas tracking-wide">План и активности менеджеров</h1>
        <div class="text-xs text-neutral-500 mt-2">
          {{ payload ? `${payload.month}.${payload.year}` : '' }}
          <span v-if="payload">· Взвешенные KPI с учётом выездов</span>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <div
          v-if="loading"
          class="text-xs font-bold text-neutral-500 bg-white border border-slate-200 rounded-xl px-3 py-2"
        >
          Загрузка…
        </div>
        <div
          v-else-if="error"
          class="text-xs font-bold text-red-700 bg-red-50 border border-red-200 rounded-xl px-3 py-2"
        >
          {{ error }}
        </div>
      </div>
    </div>

    <!-- Loading skeleton (for presentation) -->
    <div v-if="loading" class="space-y-6 animate-pulse">
      <!-- Tabs placeholders -->
      <div class="flex flex-wrap gap-2">
        <div v-for="i in 3" :key="i" class="h-10 w-28 rounded-xl border border-slate-200 bg-slate-100"></div>
      </div>

      <!-- Stats cards placeholders -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div
          v-for="i in 4"
          :key="i"
          class="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm"
        >
          <div class="h-4 w-24 bg-slate-100 rounded"></div>
          <div class="mt-3 h-10 w-16 bg-slate-100 rounded"></div>
          <div class="mt-4 h-3 w-3/4 bg-slate-100 rounded"></div>
        </div>
      </div>

      <!-- Chart placeholder -->
      <div class="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-4">
        <div class="h-4 w-64 bg-slate-100 rounded"></div>
        <div class="h-[280px] bg-slate-100 rounded-xl"></div>
      </div>

      <!-- Day grid placeholder -->
      <div class="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-3">
        <div class="h-4 w-64 bg-slate-100 rounded"></div>
        <div class="grid grid-cols-7 gap-2">
          <div v-for="i in 21" :key="i" class="h-28 bg-slate-100 rounded-xl"></div>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div v-if="payload && (payload.managers?.length ?? 0) > 0" class="flex flex-wrap gap-2">
      <button
        v-for="(m, i) in payload.managers"
        :key="m.user_id"
        @click="selectedIdx = i"
        class="px-4 py-2 rounded-xl text-xs font-bold border border-slate-200 transition"
        :class="i === selectedIdx ? 'bg-emerald-600 text-white border-emerald-700' : 'bg-white text-neutral-500 hover:bg-slate-50'"
      >
        {{ m.user_name }}
      </button>
    </div>

    <!-- Empty state -->
    <div v-else-if="payload && (payload.managers?.length ?? 0) === 0" class="bg-slate-50 border border-slate-200 rounded-2xl p-6">
      <div class="text-sm font-bold text-slate-700">Нет данных за выбранный месяц</div>
      <div class="text-xs text-slate-500 mt-2">Попробуйте изменить месяц/год или убедитесь, что для пользователя есть заполненные планы.</div>
    </div>

    <!-- Alert -->
    <div v-if="selectedManager" class="bg-amber-50 border border-amber-200 rounded-2xl p-4">
      <div class="text-xs font-bold text-amber-800">
        ⚙️ План скорректируется автоматически на основе выездных экспертиз (meeting).
      </div>
    </div>

    <!-- Stats cards -->
    <div v-if="selectedManager" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
        <div class="text-xs font-bold text-neutral-500 uppercase">Выполнение</div>
        <div class="text-4xl font-bebas font-extrabold mt-2" :class="selectedManager.stats.completion_pct >= 100 ? 'text-emerald-600' : selectedManager.stats.completion_pct < 75 ? 'text-red-600' : 'text-brand-700'">
          {{ selectedManager.stats.completion_pct }}%
        </div>
        <div class="text-xs text-neutral-500 mt-2">
          Факт: {{ selectedManager.fact_cum.filter(v => v !== null).slice(-1)[0] ?? 0 }} из {{ selectedManager.adjusted_plan_units }} ед.
        </div>
      </div>

      <div class="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
        <div class="text-xs font-bold text-neutral-500 uppercase">Ёмкость за сегодня</div>
        <div class="text-4xl font-bebas font-extrabold mt-2 text-amber-600">
          {{ selectedManager!.stats.cap_today_pct }}%
        </div>
        <div class="text-xs text-neutral-500 mt-2">Использовано: {{ Math.round((selectedManager!.daily_details?.[selectedManager!.passed_days - 1]?.used_units ?? 0) / 10 * 10) }} ед.</div>
      </div>

      <div class="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
        <div class="text-xs font-bold text-neutral-500 uppercase">Лиды за месяц</div>
        <div class="text-4xl font-bebas font-extrabold mt-2 text-teal-700">
          {{ selectedManager!.stats.leads_month_total }}
        </div>
        <div class="text-xs text-neutral-500 mt-2">Лиды = новые регистрации (call_logs.is_new_registration).</div>
      </div>

      <div class="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
        <div class="text-xs font-bold text-neutral-500 uppercase">Выезды за месяц</div>
        <div class="text-4xl font-bebas font-extrabold mt-2 text-amber-700">
          {{ selectedManager!.stats.visits_month_total }}
        </div>
        <div class="text-xs text-neutral-500 mt-2">Выезды = calendar_events.kind='meeting'.</div>
      </div>
    </div>

    <!-- Chart -->
    <div v-if="selectedManager" class="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
      <div class="flex items-center justify-between gap-4 flex-wrap">
        <div class="text-xs font-bold text-neutral-500 uppercase">Накопительный прогресс по рабочим дням</div>
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-2 text-xs text-neutral-600">
            <span class="w-4 h-1 rounded bg-emerald-600"></span> Факт (ед.)
          </div>
          <div class="flex items-center gap-2 text-xs text-neutral-600">
            <span class="w-4 h-1 rounded border border-slate-400 bg-transparent"></span> Скорр. план
          </div>
        </div>
      </div>

      <div class="mt-4 relative h-[280px]">
        <canvas ref="chartRef"></canvas>
      </div>
    </div>

    <!-- Monthly activity + capacity -->
    <div v-if="selectedManager" class="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-4">
      <div class="text-xs font-bold text-neutral-500 uppercase">Активности по типам за месяц (факт до today)</div>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div class="bg-slate-50 rounded-xl border border-slate-200 p-4">
          <div class="text-xs font-bold text-neutral-500">Выезды</div>
          <div class="text-3xl font-bebas font-extrabold text-amber-700 mt-2">×{{ selectedManager!.stats.visits_month_total }}</div>
          <div class="text-xs text-neutral-500 mt-2">Вес: ×8 ед.</div>
        </div>
        <div class="bg-slate-50 rounded-xl border border-slate-200 p-4">
          <div class="text-xs font-bold text-neutral-500">Сделки (заглушка)</div>
          <div class="text-3xl font-bebas font-extrabold text-slate-600 mt-2">×{{ selectedManager!.stats.messenger_month_total }}</div>
          <div class="text-xs text-neutral-500 mt-2">Вес: ×3 ед.</div>
        </div>
        <div class="bg-slate-50 rounded-xl border border-slate-200 p-4">
          <div class="text-xs font-bold text-neutral-500">Лиды</div>
          <div class="text-3xl font-bebas font-extrabold text-teal-700 mt-2">×{{ selectedManager!.stats.leads_month_total }}</div>
          <div class="text-xs text-neutral-500 mt-2">Вес: ×2 ед.</div>
        </div>
        <div class="bg-slate-50 rounded-xl border border-slate-200 p-4">
          <div class="text-xs font-bold text-neutral-500">Звонки</div>
          <div class="text-3xl font-bebas font-extrabold text-neutral-700 mt-2">×{{ selectedManager!.stats.calls_month_total }}</div>
          <div class="text-xs text-neutral-500 mt-2">Вес: ×1 ед.</div>
        </div>
      </div>

      <div class="pt-2">
        <div class="flex items-center justify-between text-xs text-neutral-500">
          <span>Использование дневной ёмкости (средн.)</span>
          <span class="font-bold text-brand-700">{{ avgCapacityPct }}%</span>
        </div>
        <div class="mt-2 h-3 rounded-full bg-slate-100 overflow-hidden border border-slate-200">
          <div class="h-full bg-emerald-600 rounded-full transition-all" :style="{ width: `${Math.min(100, avgCapacityPct)}%` }"></div>
        </div>
      </div>
    </div>

    <!-- Day grid -->
    <div class="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-3" v-if="selectedManager">
      <div class="flex items-center justify-between gap-4">
        <div class="text-xs font-bold text-neutral-500 uppercase">Активность по дням</div>
        <div class="text-xs text-neutral-500">
          Наведите на точку/день для тултипа с разбивкой.
        </div>
      </div>

      <div class="grid grid-cols-7 gap-2">
        <div
          v-for="(wd, i) in workDays"
          :key="wd"
          class="rounded-xl border border-slate-100 bg-slate-50 p-2 text-center relative overflow-hidden"
          :class="i < selectedManager!.passed_days ? 'opacity-100' : 'opacity-60'"
          @mouseenter="(e) => showDayTooltip(e, selectedManager!, i)"
          @mouseleave="hideTooltip"
        >
          <div class="text-[11px] font-bold text-neutral-500">{{ Number(wd.split('-')[2]) }}</div>

          <div class="mt-2 h-[72px] flex items-end justify-center gap-1">
            <div class="flex flex-col-reverse items-center gap-1">
              <div
                v-if="(dailyAt(i)?.visits ?? 0) > 0"
                class="w-3 rounded-sm"
                :style="{
                  height: `${Math.round(((dailyAt(i)?.visits ?? 0) * 8) / 10 * 26)}px`,
                  background: '#d97706'
                }"
                title="Выезды"
              />
              <div
                v-if="(dailyAt(i)?.messenger ?? 0) > 0"
                class="w-3 rounded-sm"
                :style="{
                  height: `${Math.round(((dailyAt(i)?.messenger ?? 0) * 3) / 10 * 26)}px`,
                  background: '#64748b'
                }"
                title="Сделки"
              />
              <div
                v-if="(dailyAt(i)?.leads ?? 0) > 0"
                class="w-3 rounded-sm"
                :style="{
                  height: `${Math.round(((dailyAt(i)?.leads ?? 0) * 2) / 10 * 26)}px`,
                  background: '#0f766e'
                }"
                title="Лиды"
              />
              <div
                v-if="(dailyAt(i)?.calls ?? 0) > 0"
                class="w-3 rounded-sm"
                :style="{
                  height: `${Math.round(((dailyAt(i)?.calls ?? 0) * 1) / 10 * 26)}px`,
                  background: '#94a3b8'
                }"
                title="Звонки"
              />
            </div>
          </div>

          <div class="text-[10px] mt-2 text-neutral-500 font-bold">
            <span v-if="i < selectedManager!.passed_days">{{ Math.round((dailyAt(i)?.capacity_pct ?? 0)) }}%</span>
            <span v-else>—</span>
          </div>

          <div
            v-if="wd === getTodayIso()"
            class="absolute inset-1 border border-emerald-600 rounded-lg pointer-events-none"
          ></div>
        </div>
      </div>
    </div>

    <!-- Tooltip -->
    <div
      v-if="tooltip?.show"
      class="fixed z-[50] bg-white border border-slate-200 rounded-xl shadow-lg p-3 pointer-events-none text-xs"
      :style="{ left: `${tooltip.x}px`, top: `${tooltip.y}px`, maxWidth: '240px' }"
      v-html="tooltip.text"
    ></div>
  </div>
</template>

<style scoped>
/* none */
</style>
