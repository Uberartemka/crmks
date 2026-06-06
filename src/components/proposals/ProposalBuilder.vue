<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useCatalogStore } from '@/stores/catalog'
import { useClientsStore } from '@/stores/clients'
import { useProposalsStore } from '@/stores/proposals'
import { proposalsApi } from '@/api/proposals'
import type { Sku } from '@/types/catalog'
import type { Client } from '@/types/client'
import type { Proposal, ProposalItem } from '@/types/proposal'

defineProps<{ title?: string }>()

const catalogStore = useCatalogStore()
const clientsStore = useClientsStore()
const proposalsStore = useProposalsStore()

const clientSearch = ref('')
const showClientDropdown = ref(false)
const selectedClient = ref<Client | null>(null)

const globalDiscount = ref(0)
const currentProposalId = ref<number | null>(null)
const currentProposal = ref<Proposal | null>(null)

const skuSearch = ref('')
const skuCategory = ref('all')
const skuDmin = ref('')
const skuDmax = ref('')

const loading = ref({ catalog: false, clients: false, proposal: false })
const generatingPdf = ref(false)

const categories = [
  { id: 'all', label: 'Все категории' },
  { id: 'housing', label: 'Корпусные' },
  { id: 'ball', label: 'Шариковые' },
  { id: 'roller', label: 'Роликовые' },
  { id: 'stainless', label: 'Нержавеющие' },
  { id: 'cuffs', label: 'Сальники' },
]

const filteredClients = computed(() => {
  if (!clientSearch.value) return clientsStore.list.slice(0, 20)
  const q = clientSearch.value.toLowerCase()
  return clientsStore.list.filter(c => c.name.toLowerCase().includes(q))
})

const filteredSkus = computed(() => {
  let list = catalogStore.items
  if (skuCategory.value !== 'all') list = list.filter(s => s.category === skuCategory.value)
  if (skuSearch.value) {
    const q = skuSearch.value.toLowerCase()
    list = list.filter(s => s.sku.toLowerCase().includes(q) || s.type.toLowerCase().includes(q))
  }
  const dmin = parseFloat(skuDmin.value)
  const dmax = parseFloat(skuDmax.value)
  if (!isNaN(dmin)) list = list.filter(s => s.d !== null && s.d >= dmin)
  if (!isNaN(dmax)) list = list.filter(s => s.d !== null && s.d <= dmax)
  return list
})

const items = computed(() => {
  const list = currentProposal.value?.items || []
  // Backend может возвращать items без гарантированного порядка.
  // Чтобы строки не "прыгали" — сортируем детерминированно.
  return [...list].sort((a, b) => a.id - b.id)
})

const subtotal = computed(() =>
  items.value.reduce((s, it) => s + it.qty * it.price_base, 0)
)

const globalDiscountValue = computed(() => {
  const fromProposal = currentProposal.value?.discount_global
  const fromDraft = globalDiscount.value
  const raw = typeof fromProposal === 'number' ? fromProposal : fromDraft
  return Math.max(0, Math.min(100, raw || 0))
})

const totalAfterDiscount = computed(() => {
  const multiplier = 1 - globalDiscountValue.value / 100
  return items.value.reduce((s, it) => s + it.qty * it.price_final * multiplier, 0)
})

function selectClient(client: Client) {
  selectedClient.value = client
  clientSearch.value = client.name
  showClientDropdown.value = false
  if (client.discount) globalDiscount.value = client.discount
}

async function createProposal() {
  if (!selectedClient.value) return
  loading.value.proposal = true
  try {
    const res = await proposalsStore.create({
      client_id: selectedClient.value.id,
      title: `КП от ${new Date().toISOString().slice(0, 10)}`,
      discount_global: globalDiscount.value,
    })
    currentProposalId.value = res.proposal_id
    await refreshProposal()
  } finally {
    loading.value.proposal = false
  }
}

async function addSku(sku: Sku) {
  if (!currentProposalId.value) {
    await createProposal()
    if (!currentProposalId.value) return
  }
  loading.value.proposal = true
  try {
    await proposalsStore.addItem(currentProposalId.value, {
      sku_id: sku.id,
      qty: 1,
      discount_item: 0,
    })
    await refreshProposal()
  } finally {
    loading.value.proposal = false
  }
}

async function removeItem(itemId: number) {
  if (!currentProposalId.value) return
  await proposalsStore.removeItem(currentProposalId.value, itemId)
  await refreshProposal()
}

async function updateQty(item: ProposalItem, newQty: number) {
  if (!currentProposalId.value) return
  const qty = Math.max(1, newQty)
  await proposalsStore.updateItem(currentProposalId.value, item.id, {
    sku_id: item.sku_id,
    qty,
    discount_item: item.discount_item,
  })
  await refreshProposal()
}

async function updateDiscount(item: ProposalItem, newDisc: number) {
  if (!currentProposalId.value) return
  const disc = Math.max(0, Math.min(100, newDisc))
  await proposalsStore.updateItem(currentProposalId.value, item.id, {
    sku_id: item.sku_id,
    qty: item.qty,
    discount_item: disc,
  })
  await refreshProposal()
}

async function applyGlobalDiscount() {
  if (!currentProposalId.value) {
    alert('Сначала создайте КП')
    return
  }
  await proposalsStore.setDiscount(currentProposalId.value, { discount_global: globalDiscount.value })
  await refreshProposal()
}

async function refreshProposal() {
  if (!currentProposalId.value) return
  await proposalsStore.get(currentProposalId.value)
  currentProposal.value = proposalsStore.current
}

async function sendEmail() {
  if (!currentProposalId.value) return
  await proposalsStore.send(currentProposalId.value)
  await refreshProposal()
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

function openPublicLink() {
  if (!currentProposalId.value) return
  window.open(`${API_BASE}/kp/${currentProposalId.value}`, '_blank')
}

function sleep(ms: number) {
  return new Promise<void>(resolve => window.setTimeout(resolve, ms))
}

async function downloadPdf() {
  if (!currentProposalId.value) return

  generatingPdf.value = true
  try {
    const proposalId = currentProposalId.value

    const genRes = await proposalsApi.generatePdf(proposalId)
    const data = genRes.data
    if (!data) throw new Error('Ответ генерации PDF пустой')

    const maxWaitMs = 15000
    const startedAt = Date.now()

    while (Date.now() - startedAt < maxWaitMs) {
      const stRes = await proposalsApi.getPdfStatus(proposalId)
      const st = stRes.data

      if (st.status === 'ready' && st.download_url) {
        window.open(st.download_url, '_blank')
        return
      }

      if (st.status === 'failed') {
        alert(st.error || 'Ошибка генерации PDF')
        return
      }

      await sleep(2000)
    }

    alert('PDF не успел подготовиться за 15 секунд. Попробуйте ещё раз.')
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'Ошибка генерации PDF'
    alert(msg)
  } finally {
    generatingPdf.value = false
  }
}

function hideDropdownSoon() {
  window.setTimeout(() => {
    showClientDropdown.value = false
  }, 200)
}

function printPage() {
  window.print()
}

function reset() {
  currentProposalId.value = null
  currentProposal.value = null
  selectedClient.value = null
  clientSearch.value = ''
  globalDiscount.value = 0
}

onMounted(() => {
  clientsStore.load()
  catalogStore.load()
})
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-3xl font-extrabold font-bebas tracking-wide">{{ title || 'Умная система КП' }}</h1>
      <div class="flex items-center gap-3">
        <span
          class="text-xs font-bold px-3 py-1.5 rounded-full border"
          :class="currentProposalId ? 'text-amber-700 bg-amber-50 border-amber-200' : 'text-neutral-500 bg-neutral-100 border-neutral-200'"
        >
          {{ currentProposalId ? `Черновик #${currentProposalId}` : 'Новое КП' }}
        </span>
        <span class="text-xs text-neutral-500 font-semibold">1C / Битрикс интеграция</span>
      </div>
    </div>

    <!-- Top Controls -->
    <div class="card p-5 grid lg:grid-cols-4 gap-4 items-start">
      <!-- Client Select -->
      <div class="lg:col-span-2 relative">
        <label class="block text-xs font-bold text-neutral-500 uppercase mb-2">Клиент из CRM</label>
        <div class="flex gap-2">
          <input
            v-model="clientSearch"
            @focus="showClientDropdown = true"
            @blur="hideDropdownSoon()"
            type="text"
            placeholder="Введите название клиента..."
            class="input flex-1"
          />
        </div>
        <div
          v-if="showClientDropdown && filteredClients.length"
          class="absolute z-20 w-full bg-white border border-slate-200 rounded-xl max-h-60 overflow-y-auto shadow-lg mt-1"
        >
          <div
            v-for="c in filteredClients"
            :key="c.id"
            class="px-4 py-2.5 hover:bg-slate-50 cursor-pointer transition"
            @mousedown="selectClient(c)"
          >
            <div class="text-sm font-medium">{{ c.name }}</div>
            <div class="text-[10px] text-neutral-400">{{ c.city || '' }}{{ c.discount ? ` · Скидка ${c.discount}%` : '' }}</div>
          </div>
        </div>
        <div v-if="selectedClient?.email" class="text-[11px] text-neutral-500 mt-1.5">
          Email: {{ selectedClient.email }}
        </div>
      </div>

      <!-- Global Discount -->
      <div>
        <label class="block text-xs font-bold text-neutral-500 uppercase mb-2">Общая скидка КП</label>
        <div class="flex gap-2">
          <input v-model.number="globalDiscount" type="number" min="0" max="50" class="input w-full" />
          <button @click="applyGlobalDiscount" class="btn-primary text-xs px-3">Применить</button>
        </div>
      </div>

      <!-- Actions -->
      <div class="flex gap-2 pt-6">
        <button @click="reset" class="flex-1 btn-ghost text-xs">Новое КП</button>
        <button
          @click="sendEmail"
          :disabled="!currentProposalId"
          class="flex-1 btn-primary text-xs disabled:opacity-40 flex items-center justify-center gap-1"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
            <polyline points="22,6 12,13 2,6" />
          </svg>
          Отправить
        </button>
      </div>
    </div>

    <!-- Secondary actions -->
    <div class="flex gap-2">
      <button
        @click="openPublicLink"
        :disabled="!currentProposalId"
        class="btn-ghost text-xs disabled:opacity-40 flex items-center gap-1"
      >
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </svg>
        Открыть ссылку
      </button>

      <button
        @click="downloadPdf"
        :disabled="!currentProposalId || generatingPdf"
        class="btn-ghost text-xs disabled:opacity-40 flex items-center gap-1"
      >
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
        {{ generatingPdf ? 'Генерация...' : 'Скачать PDF' }}
      </button>
    </div>

    <!-- Main Grid -->
    <div class="grid lg:grid-cols-5 gap-6 items-start">
      <!-- LEFT: SKU Catalog -->
      <div class="lg:col-span-3 card p-5 space-y-4">
        <div class="flex items-center justify-between border-b border-slate-100 pb-3">
          <h2 class="text-lg font-bold font-bebas tracking-wider">Каталог SKU (Выбор позиций)</h2>
          <span class="text-[10px] font-bold text-neutral-500 bg-neutral-100 px-2 py-1 rounded">{{ filteredSkus.length }} позиций</span>
        </div>

        <!-- Filters -->
        <div class="grid sm:grid-cols-4 gap-2">
          <input v-model="skuSearch" type="text" placeholder="Поиск по артикулу..." class="input text-xs" />
          <select v-model="skuCategory" class="input text-xs">
            <option v-for="cat in categories" :key="cat.id" :value="cat.id">{{ cat.label }}</option>
          </select>
          <input v-model="skuDmin" type="number" placeholder="d мин (мм)" class="input text-xs" />
          <input v-model="skuDmax" type="number" placeholder="d макс (мм)" class="input text-xs" />
        </div>

        <!-- Table -->
        <div class="overflow-x-auto max-h-[420px] overflow-y-auto">
          <table class="w-full text-[11px] text-left min-w-[650px]">
            <thead class="bg-slate-50 text-neutral-500 uppercase text-[9px] font-bold sticky top-0 z-10">
              <tr class="border-b border-neutral-200">
                <th class="px-3 py-2">Артикул</th>
                <th class="px-3 py-2">Тип</th>
                <th class="px-3 py-2 text-center">d×D×B</th>
                <th class="px-3 py-2 text-center">Бренд</th>
                <th class="px-3 py-2 text-right">Цена</th>
                <th class="px-3 py-2 text-center">Добавить</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-neutral-100">
              <tr v-for="s in filteredSkus" :key="s.id" class="hover:bg-slate-50 transition">
                <td class="px-3 py-2 font-semibold text-neutral-800">{{ s.sku }}</td>
                <td class="px-3 py-2 text-neutral-600">{{ s.type }}</td>
                <td class="px-3 py-2 text-center text-[10px] font-bold text-neutral-500">{{ s.d }}×{{ s.D }}×{{ s.B }}</td>
                <td class="px-3 py-2 text-center text-[10px] font-bold uppercase" :class="s.brand==='HHB'?'text-brand-700':'text-neutral-600'">{{ s.brand }}</td>
                <td class="px-3 py-2 text-right font-bold whitespace-nowrap">{{ Math.round(s.price).toLocaleString('ru-RU') }} ₽</td>
                <td class="px-3 py-2 text-center">
                  <button @click="addSku(s)" class="btn-primary text-[10px] px-2 py-1">+</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- RIGHT: Current Proposal -->
      <div class="lg:col-span-2 card p-5 space-y-4">
        <div class="flex items-center justify-between border-b border-slate-100 pb-3">
          <h2 class="text-lg font-bold font-bebas tracking-wider">Текущее КП <span class="text-neutral-400 text-sm">#{{ currentProposalId || '---' }}</span></h2>
          <button @click="printPage" class="text-[10px] text-brand-700 hover:underline flex items-center gap-1 font-semibold">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6 9V2h12v7M6 18H4a2 2 0 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2M6 14h12v8H6z" />
            </svg>
            Печать
          </button>
        </div>

        <!-- Items -->
        <div class="overflow-x-auto max-h-[320px] overflow-y-auto">
          <table class="w-full text-[11px] text-left">
            <thead class="bg-slate-50 text-neutral-500 uppercase text-[9px] font-bold">
              <tr class="border-b border-neutral-200">
                <th class="px-2 py-2">Артикул</th>
                <th class="px-2 py-2 text-center">Кол</th>
                <th class="px-2 py-2 text-right">Скидка</th>
                <th class="px-2 py-2 text-right">Цена</th>
                <th class="px-2 py-2 text-center">✕</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-neutral-100">
              <tr v-if="items.length === 0">
                <td colspan="5" class="py-6 text-center text-neutral-400 text-[10px]">Выберите SKU из каталога слева</td>
              </tr>
              <tr v-for="it in items" :key="it.id" class="hover:bg-slate-50 transition">
                <td class="px-2 py-2 font-semibold text-neutral-800">{{ it.sku }}</td>
                <td class="px-2 py-2 text-center">
                  <input type="number" min="1" :value="it.qty" @change="e => updateQty(it, +(e.target as HTMLInputElement).value)" class="w-12 text-center text-[10px] border border-neutral-200 rounded py-0.5" />
                </td>
                <td class="px-2 py-2 text-center">
                  <input type="number" min="0" max="50" :value="it.discount_item" @change="e => updateDiscount(it, +(e.target as HTMLInputElement).value)" class="w-10 text-center text-[10px] border border-neutral-200 rounded py-0.5" />
                </td>
                <td class="px-2 py-2 text-right font-bold text-neutral-800">{{ Math.round(it.price_final * (1 - globalDiscountValue / 100)).toLocaleString('ru-RU') }} ₽</td>
                <td class="px-2 py-2 text-center">
                  <button @click="removeItem(it.id)" class="text-neutral-400 hover:text-red-500 font-bold">✕</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Totals -->
        <div class="border-t border-neutral-200 pt-4 space-y-2">
          <div class="flex justify-between text-xs">
            <span class="text-neutral-500">Сумма без скидки:</span>
            <span class="font-bold">{{ Math.round(subtotal).toLocaleString('ru-RU') }} ₽</span>
          </div>
          <div class="flex justify-between text-xs">
            <span class="text-neutral-500">Глобальная скидка:</span>
            <span class="font-bold text-brand-700">{{ currentProposal?.discount_global || 0 }}%</span>
          </div>
          <div class="flex justify-between text-sm font-extrabold font-bebas tracking-wide border-t border-neutral-100 pt-2">
            <span>ИТОГО КП:</span>
            <span class="text-brand-700">{{ Math.round(totalAfterDiscount).toLocaleString('ru-RU') }} ₽</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Print Preview -->
    <div class="hidden print:block bg-white p-8 border border-neutral-300 rounded-xl space-y-6 text-sm shadow-lg">
      <div class="flex items-start justify-between border-b-2 border-brand-700 pb-6">
        <div>
          <div class="flex items-center gap-2">
            <span class="inline-block w-6 h-6 rounded-full bg-brand-700" />
            <span class="font-extrabold tracking-wide font-bebas text-xl text-neutral-900">КОМПОНЕНТ СЕРВИС<span class="text-brand-700">.</span></span>
          </div>
          <div class="text-[10px] text-neutral-500 font-bold uppercase tracking-wider mt-1">Официальный Дистрибьютор HHB & FKD в России</div>
          <div class="text-[10px] text-neutral-400 mt-1">г. Воронеж, ул. Промышленная, 1 · Тел: +7 (473) 255-00-00 · csbrg.ru</div>
        </div>
        <div class="text-right text-xs">
          <div class="text-white bg-brand-700 px-3 py-1 font-bold rounded uppercase tracking-wider text-[10px]">КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ</div>
          <div class="font-bold text-neutral-800 mt-2 text-sm">Бланк № {{ currentProposalId || '---' }}</div>
          <div class="text-neutral-500 font-medium mt-0.5">Дата: {{ new Date().toLocaleDateString('ru-RU') }}</div>
        </div>
      </div>
      <div class="space-y-2">
        <div class="font-bold text-neutral-900">Клиент: {{ selectedClient?.name || '---' }}</div>
        <table class="w-full text-xs border-collapse">
          <thead class="bg-brand-700 text-white">
            <tr>
              <th class="px-2 py-1 text-left">Артикул</th>
              <th class="px-2 py-1 text-center">Кол</th>
              <th class="px-2 py-1 text-right">Цена</th>
              <th class="px-2 py-1 text-right">Сумма</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="it in items" :key="it.id" class="border-b border-neutral-200">
              <td class="px-2 py-1">{{ it.sku }}</td>
              <td class="px-2 py-1 text-center">{{ it.qty }}</td>
              <td class="px-2 py-1 text-right">{{ Math.round(it.price_final * (1 - globalDiscountValue / 100)).toLocaleString('ru-RU') }} ₽</td>
              <td class="px-2 py-1 text-right">{{ Math.round(it.price_final * it.qty * (1 - globalDiscountValue / 100)).toLocaleString('ru-RU') }} ₽</td>
            </tr>
          </tbody>
        </table>
        <div class="text-right font-extrabold text-lg font-bebas">ИТОГО: {{ Math.round(totalAfterDiscount).toLocaleString('ru-RU') }} ₽</div>
      </div>
    </div>
  </div>
</template>
