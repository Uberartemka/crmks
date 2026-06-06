<script setup lang="ts">
import { ref, computed } from 'vue'
import { useNotesStore } from '@/stores/notes'

const notes = useNotesStore()

function normalizeBaseUrl(v: string | undefined) {
  if (!v) return ''
  return v.endsWith('/') ? v.slice(0, -1) : v
}

const apiBaseUrl = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL as string | undefined)

const bitrixWebhookUrl = computed(() => (apiBaseUrl ? `${apiBaseUrl}/api/webhooks/bitrix` : '/api/webhooks/bitrix'))
const bitrixTelephonyWebhookUrl = computed(() => (apiBaseUrl ? `${apiBaseUrl}/api/webhooks/bitrix/telephony` : '/api/webhooks/bitrix/telephony'))
const oneCWebhookUrl = computed(() => (apiBaseUrl ? `${apiBaseUrl}/api/webhooks/1c` : '/api/webhooks/1c'))

async function copyToClipboard(text: string) {
  await navigator.clipboard.writeText(text)
}

const checklist = ref([
  { item: 'Чемоданчик с образцами HHB', done: true },
  { item: 'Технические паспорта подшипников', done: true },
  { item: 'Конкурентные образцы (SKF, CRAFT)', done: false },
  { item: 'Планшет с презентацией', done: true },
  { item: 'Визитки и каталоги', done: false },
])

const reportText = ref('')
const loading = ref(false)
const error = ref<string | null>(null)
const ok = ref<string | null>(null)

const checklistMarkdown = computed(() => {
  return checklist.value
    .map((c) => `- [${c.done ? 'x' : ' '}] ${c.item}`)
    .join('\n')
})

async function saveReport() {
  error.value = null
  ok.value = null
  loading.value = true

  try {
    const now = new Date()
    const title = `Аудит: ${now.toLocaleDateString('ru-RU')}`

    const content = [
      `### Чек-лист аудита`,
      checklistMarkdown.value,
      ``,
      `### Результат визита`,
      reportText.value || '_—_',
    ].join('\n')

    await notes.create({
      title,
      content,
      color: 'yellow',
      pinned: false,
      tags: ['audit', 'чемоданчик'],
    })

    reportText.value = ''
    ok.value = 'Отчет сохранен.'
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || 'Ошибка сохранения'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Цифровой Чемоданчик</h1>

    <div class="grid md:grid-cols-2 gap-6">
      <div class="card p-5 space-y-3">
        <div class="text-xs font-bold text-neutral-500 uppercase mb-2">Чек-лист аудита</div>
        <label
          v-for="(c, i) in checklist"
          :key="i"
          class="flex items-center gap-3 p-3 rounded-xl border border-slate-100 hover:bg-slate-50 cursor-pointer transition"
        >
          <input v-model="c.done" type="checkbox" class="w-5 h-5 rounded text-brand-700" />
          <span class="text-sm font-semibold" :class="c.done ? 'line-through text-neutral-400' : 'text-neutral-800'">
            {{ c.item }}
          </span>
        </label>
      </div>

      <div class="card p-5 space-y-4">
        <div class="text-xs font-bold text-neutral-500 uppercase mb-2">Результат визита</div>
        <textarea
          v-model="reportText"
          placeholder="Описание встречи, потребности клиента..."
          rows="6"
          class="input w-full text-sm resize-none"
        />
        <button class="btn-primary w-full text-xs disabled:opacity-60" :disabled="loading" @click="saveReport">
          {{ loading ? 'Сохраняю…' : 'Сохранить отчет' }}
        </button>

        <p v-if="error" class="text-xs text-red-700">{{ error }}</p>
        <p v-if="ok" class="text-xs text-emerald-700">{{ ok }}</p>
      </div>
    </div>

    <div class="card p-5 space-y-4">
      <div class="flex items-center justify-between gap-4">
        <div>
          <div class="text-xs font-bold text-neutral-500 uppercase mb-1">Хуки Bitrix (подготовка)</div>
          <div class="text-sm font-bold">Эндпоинты для настройки в Bitrix24 / 1С</div>
        </div>
        <div class="text-[11px] text-neutral-500">
          Вставьте в Bitrix позже: <span class="font-mono">B2B_ADMIN_TOKEN</span>
        </div>
      </div>

      <div class="space-y-4">
        <div class="space-y-2">
          <div class="text-xs font-bold text-neutral-500 uppercase">Bitrix24 CRM</div>
          <div class="flex gap-2 items-center">
            <div class="flex-1 text-xs font-mono text-neutral-700 break-all">
              {{ bitrixWebhookUrl }}
            </div>
            <button class="btn-ghost text-xs" @click="copyToClipboard(bitrixWebhookUrl)" title="Скопировать URL">
              Скопировать
            </button>
          </div>
          <div class="text-xs text-neutral-500">
            Заголовок: <span class="font-mono">Authorization: Bearer B2B_ADMIN_TOKEN</span>
          </div>
          <div class="text-xs text-neutral-600 font-mono whitespace-pre-wrap bg-slate-50 border border-slate-100 rounded p-3">
{ "event": "ONCRM…", "data": { "FIELDS": { "ID": 123 } } }
          </div>
        </div>

        <div class="space-y-2">
          <div class="text-xs font-bold text-neutral-500 uppercase">Bitrix24 Телефония</div>
          <div class="flex gap-2 items-center">
            <div class="flex-1 text-xs font-mono text-neutral-700 break-all">
              {{ bitrixTelephonyWebhookUrl }}
            </div>
            <button class="btn-ghost text-xs" @click="copyToClipboard(bitrixTelephonyWebhookUrl)" title="Скопировать URL">
              Скопировать
            </button>
          </div>
          <div class="text-xs text-neutral-500">
            Заголовок: <span class="font-mono">Authorization: Bearer B2B_ADMIN_TOKEN</span>
          </div>
          <div class="text-xs text-neutral-600 font-mono whitespace-pre-wrap bg-slate-50 border border-slate-100 rounded p-3">
{ "event": "ONVOXIMPLANTCALLEND", "data": { "CALL_ID": "abc", "PHONE_NUMBER": "+7…", "CALL_STATUS": "success" } }
          </div>
        </div>

        <div class="space-y-2">
          <div class="text-xs font-bold text-neutral-500 uppercase">1С (обновление номенклатуры)</div>
          <div class="flex gap-2 items-center">
            <div class="flex-1 text-xs font-mono text-neutral-700 break-all">
              {{ oneCWebhookUrl }}
            </div>
            <button class="btn-ghost text-xs" @click="copyToClipboard(oneCWebhookUrl)" title="Скопировать URL">
              Скопировать
            </button>
          </div>
          <div class="text-xs text-neutral-500">
            Заголовок: <span class="font-mono">Authorization: Bearer B2B_ADMIN_TOKEN</span>
          </div>
          <div class="text-xs text-neutral-600 font-mono whitespace-pre-wrap bg-slate-50 border border-slate-100 rounded p-3">
{ "sku": "HHB UCP 206", "new_stock": 120, "new_price": 1180 }
          </div>
        </div>
      </div>
    </div>

  </div>
</template>
