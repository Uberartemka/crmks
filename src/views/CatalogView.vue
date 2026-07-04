<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useCatalogStore } from '@/stores/catalog'
import { toast } from '@/plugins/toast'
import type { Sku } from '@/types/catalog'

const store = useCatalogStore()
const loadError = ref(false)

const categories = [
  { id: 'all', label: 'Все категории' },
  { id: 'housing', label: 'Корпусные подшипники' },
  { id: 'ball', label: 'Шариковые радиальные' },
  { id: 'roller', label: 'Сферические роликовые' },
  { id: 'stainless', label: 'Нержавеющая сталь' },
  { id: 'cuffs', label: 'Сальники и манжеты' },
]

const activeCategory = ref('all')
const search = ref('')
const filterD = ref('')
const filterDOut = ref('')
const filterB = ref('')

const items = computed(() => store.items)

const filtered = computed(() => {
  let list = items.value
  if (activeCategory.value !== 'all') {
    list = list.filter((i: Sku) => i.category === activeCategory.value)
  }
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter((i: Sku) =>
      i.sku.toLowerCase().includes(q) ||
      i.gost.toLowerCase().includes(q) ||
      i.type.toLowerCase().includes(q)
    )
  }
  if (filterD.value) {
    const d = parseFloat(filterD.value)
    if (!isNaN(d)) list = list.filter((i: Sku) => i.d === d)
  }
  if (filterDOut.value) {
    const D = parseFloat(filterDOut.value)
    if (!isNaN(D)) list = list.filter((i: Sku) => i.D === D)
  }
  if (filterB.value) {
    const B = parseFloat(filterB.value)
    if (!isNaN(B)) list = list.filter((i: Sku) => i.B === B)
  }
  return list
})

const selectedItem = ref<Sku | null>(null)

onMounted(async () => {
  try {
    await store.load()
  } catch {
    loadError.value = true
    toast.error('Не удалось загрузить каталог')
  }
})
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <!-- Header -->
    <header class="fixed top-0 inset-x-0 z-50 bg-neutral-950/90 backdrop-blur border-b border-white/10 py-4">
      <div class="mx-auto max-w-7xl px-6 flex items-center justify-between">
        <RouterLink to="/" class="flex items-center gap-2">
          <span class="inline-block w-8 h-8 rounded-full bg-hhb" />
          <span class="font-extrabold tracking-wide text-white font-bebas text-2xl">HHB<span class="text-hhb">.</span>RU</span>
        </RouterLink>
        <div class="flex items-center gap-4">
          <RouterLink to="/login" class="text-xs font-bold uppercase tracking-wider text-neutral-400 hover:text-white transition">Кабинет</RouterLink>
        </div>
      </div>
    </header>

    <main class="flex-1 pt-24 pb-20">
      <div class="mx-auto max-w-7xl px-6">
        <div class="flex flex-col md:flex-row md:items-end justify-between border-b border-neutral-200 pb-6 mb-8 gap-4">
          <div>
            <div class="text-xs font-bold tracking-widest text-brand-700 mb-2 uppercase">Официальный дистрибьютор Hebei Hailan в РФ</div>
            <h1 class="text-4xl font-extrabold font-bebas tracking-wide text-neutral-900">Инженерный Каталог HHB & FKD</h1>
          </div>
        </div>

        <div class="grid lg:grid-cols-4 gap-8">
          <!-- Sidebar -->
          <aside class="space-y-6">
            <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
              <div class="bg-neutral-900 text-white px-5 py-4 font-bebas tracking-wider text-base uppercase">Разделы каталога</div>
              <div class="p-2 space-y-1">
                <button
                  v-for="cat in categories" :key="cat.id"
                  class="w-full text-left text-xs font-bold uppercase tracking-wider px-4 py-3 rounded-xl transition hover:bg-slate-100"
                  :class="activeCategory === cat.id ? 'bg-brand-50 text-brand-700' : 'text-neutral-600'"
                  @click="activeCategory = cat.id"
                >
                  {{ cat.label }}
                </button>
              </div>
            </div>

            <div class="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-5">
              <h3 class="text-xs font-bold uppercase tracking-wider text-neutral-800 border-b border-neutral-100 pb-2">Поиск по размерам</h3>
              <div class="grid grid-cols-3 gap-2">
                <div><label class="block text-[9px] font-bold text-neutral-500 uppercase mb-1">d</label><input v-model="filterD" type="text" placeholder="25" class="w-full rounded-lg bg-neutral-50 border border-neutral-200 p-2 text-center text-xs font-semibold outline-none focus:border-hhb" /></div>
                <div><label class="block text-[9px] font-bold text-neutral-500 uppercase mb-1">D</label><input v-model="filterDOut" type="text" placeholder="52" class="w-full rounded-lg bg-neutral-50 border border-neutral-200 p-2 text-center text-xs font-semibold outline-none focus:border-hhb" /></div>
                <div><label class="block text-[9px] font-bold text-neutral-500 uppercase mb-1">B</label><input v-model="filterB" type="text" placeholder="15" class="w-full rounded-lg bg-neutral-50 border border-neutral-200 p-2 text-center text-xs font-semibold outline-none focus:border-hhb" /></div>
              </div>
              <div class="flex gap-2">
                <button @click="" class="flex-1 bg-neutral-900 hover:bg-black text-white text-[10px] font-bold py-2 rounded-lg uppercase tracking-wider transition">Применить</button>
                <button @click="filterD=''; filterDOut=''; filterB=''; activeCategory='all'; search=''" class="bg-neutral-100 hover:bg-neutral-200 text-neutral-700 text-[10px] font-bold px-3 py-2 rounded-lg uppercase tracking-wider transition">Сброс</button>
              </div>
            </div>
          </aside>

          <!-- Main -->
          <div class="lg:col-span-3 space-y-6">
            <div class="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex items-center gap-3">
              <svg class="w-5 h-5 text-neutral-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.3-4.3"/></svg>
              <input v-model="search" type="text" placeholder="Поиск по ГОСТ, ISO, или размерам..." class="w-full text-sm outline-none font-semibold text-neutral-800 placeholder-neutral-400" />
            </div>

            <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
              <table class="w-full text-xs text-left">
                <thead class="bg-neutral-900 text-white font-bebas text-sm tracking-wider uppercase">
                  <tr>
                    <th class="px-5 py-3.5">Артикул</th>
                    <th class="px-4 py-3.5 text-center">ГОСТ</th>
                    <th class="px-4 py-3.5 text-center">d x D x B</th>
                    <th class="px-4 py-3.5 text-center">Бренд</th>
                    <th class="px-4 py-3.5 text-center">Наличие</th>
                    <th class="px-4 py-3.5 text-right">Цена</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-neutral-100 font-medium">
                  <tr v-for="item in filtered" :key="item.sku" class="hover:bg-slate-50 transition cursor-pointer" @click="selectedItem = item">
                    <td class="px-5 py-3.5 font-bold text-neutral-900">{{ item.sku }}</td>
                    <td class="px-4 py-3.5 text-center text-neutral-500">{{ item.gost }}</td>
                    <td class="px-4 py-3.5 text-center font-bold">{{ item.d }} x {{ item.D }} x {{ item.B }}</td>
                    <td class="px-4 py-3.5 text-center font-bold uppercase" :class="item.brand==='HHB' ? 'text-brand-700' : 'text-neutral-600'">{{ item.brand }}</td>
                    <td class="px-4 py-3.5 text-center text-emerald-600 font-bold">{{ item.stock }}</td>
                    <td class="px-4 py-3.5 text-right font-extrabold">{{ item.price }}</td>
                  </tr>
                  <tr v-if="loadError"><td colspan="6" class="py-12 text-center text-red-500 font-semibold text-xs">Не удалось загрузить каталог. Проверьте подключение и обновите страницу.</td></tr>
                  <tr v-else-if="items.length === 0"><td colspan="6" class="py-12 text-center text-neutral-500 font-semibold text-xs">Каталог пуст.</td></tr>
                  <tr v-else-if="filtered.length === 0"><td colspan="6" class="py-12 text-center text-neutral-500 font-semibold text-xs">Позиций не найдено. Попробуйте сбросить фильтры.</td></tr>
                </tbody>
              </table>
            </div>

            <!-- Spec Modal -->
            <div v-if="selectedItem" class="fixed inset-0 z-50 flex items-center justify-center p-4" @click.self="selectedItem = null">
              <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" />
              <div class="relative bg-white rounded-3xl shadow-2xl border border-neutral-200 max-w-2xl w-full p-6 grid md:grid-cols-2 gap-6 overflow-hidden z-10">
                <button @click="selectedItem = null" class="absolute top-4 right-4 w-8 h-8 rounded-full bg-neutral-100 text-neutral-500 hover:text-black flex items-center justify-center font-bold">✕</button>
                <div class="space-y-4">
                  <div class="aspect-square bg-slate-100 rounded-2xl flex items-center justify-center border border-neutral-100 text-4xl">📦</div>
                  <div class="text-[10px] text-neutral-400 font-bold uppercase tracking-wider text-center">Оригинальное фото Hebei Hailan Bearing Co.</div>
                </div>
                <div class="space-y-4 flex flex-col justify-between">
                  <div>
                    <div class="text-[10px] font-bold text-brand-700 uppercase tracking-widest">СПЕЦИФИКАЦИЯ</div>
                    <h3 class="text-2xl font-extrabold text-neutral-900 tracking-wide font-bebas mt-1">{{ selectedItem.sku }}</h3>
                    <p class="text-xs text-neutral-500 font-medium">{{ selectedItem.type }}</p>
                    <div class="mt-4 border border-neutral-200 rounded-xl overflow-hidden text-xs">
                      <div class="grid grid-cols-2 bg-slate-50 border-b border-neutral-200 p-2.5"><span class="font-semibold text-neutral-500">Внутренний d</span><span class="font-extrabold text-neutral-800 text-right">{{ selectedItem.d }} мм</span></div>
                      <div class="grid grid-cols-2 border-b border-neutral-200 p-2.5"><span class="font-semibold text-neutral-500">Наружный D</span><span class="font-extrabold text-neutral-800 text-right">{{ selectedItem.D }} мм</span></div>
                      <div class="grid grid-cols-2 bg-slate-50 border-b border-neutral-200 p-2.5"><span class="font-semibold text-neutral-500">Ширина B</span><span class="font-extrabold text-neutral-800 text-right">{{ selectedItem.B }} мм</span></div>
                      <div class="grid grid-cols-2 border-b border-neutral-200 p-2.5"><span class="font-semibold text-neutral-500">ГОСТ</span><span class="font-extrabold text-neutral-800 text-right">{{ selectedItem.gost }}</span></div>
                      <div class="grid grid-cols-2 bg-slate-50 p-2.5"><span class="font-semibold text-neutral-500">Бренд</span><span class="font-extrabold text-brand-700 text-right uppercase">{{ selectedItem.brand }}</span></div>
                    </div>
                  </div>
                  <div class="space-y-3">
                    <div class="flex items-center justify-between border-t border-neutral-100 pt-4">
                      <div>
                        <div class="text-[10px] text-neutral-400 font-bold uppercase">Цена с НДС</div>
                        <div class="text-2xl font-extrabold text-neutral-900 font-bebas mt-0.5">{{ selectedItem.price }}</div>
                      </div>
                      <div class="text-right">
                        <div class="text-[10px] text-neutral-400 font-bold uppercase">Наличие</div>
                        <div class="text-sm font-bold text-emerald-600 mt-0.5">{{ selectedItem.stock }}</div>
                      </div>
                    </div>
                    <button class="w-full bg-brand-700 hover:bg-brand-800 text-white text-xs py-3 rounded-xl font-bold uppercase tracking-widest transition">Купить / Заказать КП</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>
