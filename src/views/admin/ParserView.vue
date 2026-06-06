<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { agentApi } from '@/api/agent'
import { leadsApi } from '@/api/leads'
import type { Lead } from '@/types/lead'

const router = useRouter()

// --- AI parser (верхний блок) ---
const parserQuery = ref('')
const parserLoading = ref(false)
const parserError = ref<string | null>(null)
const parserMessage = ref<string | null>(null)

const parsed = ref(0)
const created = ref(0)
const skipped = ref(0)

// --- Leads from DB (лево/ниже) ---
const dbLoading = ref(false)
const dbError = ref<string | null>(null)
const leadsFromDb = ref<Lead[]>([])

const dbQuery = ref('')
const filteredLeads = computed(() => {
  const q = dbQuery.value.trim().toLowerCase()
  if (!q) return leadsFromDb.value

  return leadsFromDb.value.filter((l) => {
    const hay = [
      l.name,
      l.city,
      l.category,
      l.contacts,
      l.need_description,
      l.query,
      l.region,
      l.status,
      l.assigned_name,
      l.call_count?.toString(),
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()

    return hay.includes(q)
  })
})

// --- Dialog + briefing ---
const dialogOpen = ref(false)
const selectedLead = ref<Lead | null>(null)

const briefingLoading = ref(false)
const briefingError = ref<string | null>(null)
const briefingResult = ref<{ created: string; task_id?: number; lead_id?: number } | null>(null)

const deletingLeadId = ref<number | null>(null)
const deleteError = ref<string | null>(null)

function clearBriefingState() {
  briefingLoading.value = false
  briefingError.value = null
  briefingResult.value = null
}

async function refreshDbLeads() {
  dbLoading.value = true
  dbError.value = null
  try {
    const { data } = await leadsApi.list()
    leadsFromDb.value = data
  } catch (e: any) {
    dbError.value = e?.response?.data?.detail || e?.message || 'Ошибка загрузки лидов'
    leadsFromDb.value = []
  } finally {
    dbLoading.value = false
  }
}

async function runParser() {
  parserError.value = null
  parserMessage.value = null

  parsed.value = 0
  created.value = 0
  skipped.value = 0

    const q = parserQuery.value.trim()
    if (!q) return

    parserLoading.value = true
    try {
      const { data } = await agentApi.parseLeads({ query: q, limit: 20 })
      parsed.value = data.parsed
      created.value = data.created
      skipped.value = data.skipped

      const msg = data.message ?? null
      // MVP: не показываем вопрос/сообщения про регион — парсим только по названию.
      const hideIfRegion =
        msg &&
        /регион|в каком регионе|укаж(ите|ите пожалуйста)|выберите регион/i.test(msg)

      parserMessage.value = hideIfRegion ? null : msg
    } catch (e: any) {
      parserError.value = e?.response?.data?.detail || e?.message || 'Ошибка парсинга'
    } finally {
      parserLoading.value = false
    }

  // Даже если AI дал ошибку — попробуем обновить БД (если хоть что-то успело сохраниться)
  await refreshDbLeads()
}

function openLeadDialog(lead: Lead) {
  dialogOpen.value = true
  selectedLead.value = lead
  clearBriefingState()
}

function closeLeadDialog() {
  dialogOpen.value = false
  selectedLead.value = null
  clearBriefingState()
}

async function doBriefing(leadId: number) {
  briefingLoading.value = true
  briefingError.value = null
  briefingResult.value = null

  try {
    const { data } = await leadsApi.briefing(leadId)
    briefingResult.value = {
      created: data.created,
      task_id: data.task_id,
      lead_id: data.lead_id,
    }

    if (data.created === 'task' && data.task_id) {
      router.push('/admin/dashboard')
      return
    }
    if (data.created === 'kp_draft') {
      router.push('/admin/proposals')
      return
    }
  } catch (e: any) {
    briefingError.value = e?.response?.data?.detail || e?.message || 'Ошибка действий по лидe'
  } finally {
    briefingLoading.value = false
  }
}

async function deleteLead(leadId: number) {
  const ok = window.confirm('Удалить лид? Это действие нельзя отменить.')
  if (!ok) return

  deleteError.value = null
  deletingLeadId.value = leadId

  try {
    await leadsApi.delete(leadId)
    if (selectedLead.value?.id === leadId) {
      closeLeadDialog()
    }
    await refreshDbLeads()
  } catch (e: any) {
    deleteError.value = e?.response?.data?.detail || e?.message || 'Ошибка удаления лида'
  } finally {
    deletingLeadId.value = null
  }
}

onMounted(() => {
  refreshDbLeads()
})
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Парсер лидов B2B</h1>

    <!-- AI parser block -->
    <div class="card p-5 space-y-3">
      <div class="flex gap-3">
        <input
          v-model="parserQuery"
          @keyup.enter="runParser"
          placeholder="Название компании, ИНН, отрасль..."
          class="input flex-1"
        />
        <button
          class="btn-primary disabled:opacity-50"
          :disabled="parserLoading"
          @click="runParser"
        >
          {{ parserLoading ? 'Парсим…' : 'Запустить парсер' }}
        </button>
      </div>

      <div v-if="parserError" class="text-sm text-red-700">
        {{ parserError }}
      </div>
      <div v-else-if="parserMessage" class="text-sm text-neutral-500">
        {{ parserMessage }}
      </div>

      <div v-if="(created || skipped || parsed) && !parserLoading" class="pt-2">
        <div class="text-xs font-bold text-neutral-500 uppercase mb-1">Итоги парсинга</div>
        <div class="flex gap-4 flex-wrap text-sm">
          <div><span class="text-neutral-500">Parsed:</span> <span class="font-bold">{{ parsed }}</span></div>
          <div><span class="text-neutral-500">Created:</span> <span class="font-bold">{{ created }}</span></div>
          <div><span class="text-neutral-500">Skipped:</span> <span class="font-bold">{{ skipped }}</span></div>
        </div>
      </div>
    </div>

    <!-- Leads from DB block -->
    <section class="card p-5 space-y-3">
      <div class="flex items-center justify-between gap-4">
        <div>
          <div class="text-xs font-bold text-neutral-500 uppercase mb-1">Лиды, сохранённые в БД</div>
          <div class="text-sm text-neutral-500">Ниже можно искать по ним (без AI-запросов).</div>
        </div>
        <div v-if="dbLoading" class="text-sm text-neutral-500">Загружаю…</div>
      </div>

      <div v-if="dbError" class="text-sm text-red-700">
        {{ dbError }}
      </div>

      <div class="flex gap-3">
        <input
          v-model="dbQuery"
          placeholder="Поиск по названию/городу/контактам/ревью..."
          class="input flex-1"
        />
        <button class="btn-ghost text-xs" @click="dbQuery = ''" :disabled="dbQuery.length === 0">
          Сбросить
        </button>
      </div>

      <div v-if="deleteError" class="text-sm text-red-700">
        {{ deleteError }}
      </div>

      <div v-if="filteredLeads.length" class="space-y-2">
        <div
          v-for="l in filteredLeads"
          :key="l.id"
          class="card p-4 flex items-start justify-between gap-4"
        >
          <div class="min-w-0">
            <div class="text-sm font-bold truncate">{{ l.name }}</div>

            <div class="text-xs text-neutral-500 mt-1">
              <span v-if="l.city">Город: {{ l.city }}</span>
              <span v-if="l.city && l.category"> · </span>
              <span v-if="l.category">Категория: {{ l.category }}</span>
            </div>

            <div v-if="l.contacts" class="text-[11px] text-neutral-600 mt-2 whitespace-pre-wrap">
              Контакты: {{ l.contacts }}
            </div>

            <div v-if="l.need_description" class="text-[11px] text-neutral-600 mt-2 whitespace-pre-wrap">
              Короткое ревью: {{ l.need_description }}
            </div>
          </div>

          <div class="flex flex-col items-end gap-2">
            <div class="text-xs text-neutral-500">ID: {{ l.id }}</div>
            <button class="btn-ghost text-xs" @click="openLeadDialog(l)">
              Открыть
            </button>

            <button
              class="btn-ghost text-xs text-red-700 hover:text-red-900 disabled:opacity-50"
              :disabled="deletingLeadId === l.id"
              @click="deleteLead(l.id)"
            >
              {{ deletingLeadId === l.id ? 'Удаляю…' : 'Удалить' }}
            </button>
          </div>
        </div>
      </div>

      <div v-else-if="!dbLoading" class="text-center text-neutral-400 text-sm py-8">
        Лиды не найдены.
      </div>
    </section>

    <!-- Dialog -->
    <div
      v-if="dialogOpen && selectedLead"
      class="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-4"
      @click.self="closeLeadDialog"
    >
      <div class="bg-white border border-slate-200 rounded-xl w-full max-w-2xl p-4 space-y-3">
        <div class="flex items-start justify-between gap-4">
          <div class="min-w-0">
            <div class="text-lg font-extrabold truncate">{{ selectedLead.name }}</div>
            <div class="text-xs text-neutral-500 mt-1">
              ID: {{ selectedLead.id }} · статус: {{ selectedLead.status }}
            </div>
          </div>
          <button class="btn-ghost text-xs" @click="closeLeadDialog">✕</button>
        </div>

        <div class="grid sm:grid-cols-2 gap-3">
          <div class="space-y-1">
            <div class="text-[11px] font-bold text-neutral-500 uppercase">Город/Категория</div>
            <div class="text-sm">
              <span v-if="selectedLead.city">{{ selectedLead.city }}</span>
              <span v-if="selectedLead.city && selectedLead.category"> · </span>
              <span v-if="selectedLead.category">{{ selectedLead.category }}</span>
            </div>
          </div>

          <div class="space-y-1">
            <div class="text-[11px] font-bold text-neutral-500 uppercase">Контакты</div>
            <div class="text-sm whitespace-pre-wrap" v-if="selectedLead.contacts">
              {{ selectedLead.contacts }}
            </div>
            <div v-else class="text-sm text-neutral-400">—</div>
          </div>
        </div>

        <div class="space-y-1">
          <div class="text-[11px] font-bold text-neutral-500 uppercase">Короткое ревью / подходит ли</div>
          <div class="text-sm whitespace-pre-wrap text-neutral-800" v-if="selectedLead.need_description">
            {{ selectedLead.need_description }}
          </div>
          <div v-else class="text-sm text-neutral-400">—</div>
        </div>

        <div class="border-t border-slate-100 pt-3 space-y-2">
          <button
            class="btn-primary w-full text-xs disabled:opacity-60"
            :disabled="briefingLoading"
            @click="doBriefing(selectedLead.id)"
          >
            {{ briefingLoading ? 'Запускаю подготовку…' : 'Дальше: подготовить КП/задачи' }}
          </button>

          <div v-if="briefingError" class="text-xs text-red-700">
            {{ briefingError }}
          </div>

          <div v-if="briefingResult" class="text-xs text-neutral-500">
            Результат: {{ briefingResult.created }}
            <span v-if="briefingResult.task_id"> · task_id: {{ briefingResult.task_id }}</span>
            <span v-if="briefingResult.lead_id"> · lead_id: {{ briefingResult.lead_id }}</span>
          </div>
        </div>

        <div class="flex justify-end">
          <button class="btn-ghost text-xs" @click="closeLeadDialog">Закрыть</button>
        </div>
      </div>
    </div>
  </div>
</template>
