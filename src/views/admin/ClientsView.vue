<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useClientsStore } from '@/stores/clients'

const store = useClientsStore()
const search = ref('')

onMounted(() => store.load())
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-3xl font-extrabold font-bebas tracking-wide">База B2B клиентов</h1>
      <span class="text-xs font-bold text-emerald-700 bg-green-50 px-3 py-1.5 rounded-full border border-green-200">Всего: {{ store.list.length }}</span>
    </div>

    <div class="card p-4 flex items-center gap-3">
      <svg class="w-5 h-5 text-neutral-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.3-4.3"/></svg>
      <input v-model="search" type="text" placeholder="Поиск по названию, ИНН, городу..." class="w-full text-sm outline-none font-semibold" />
    </div>

    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-neutral-500 text-[10px] uppercase font-bold">
          <tr>
            <th class="px-4 py-3 text-left">Компания</th>
            <th class="px-4 py-3 text-left">ИНН</th>
            <th class="px-4 py-3 text-left">Город</th>
            <th class="px-4 py-3 text-left">Отрасль</th>
            <th class="px-4 py-3 text-left">Менеджер</th>
            <th class="px-4 py-3 text-center">Статус</th>
            <th class="px-4 py-3 text-center">Скидка</th>
            <th class="px-4 py-3 text-center"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="c in store.list.filter(x => !search || x.name.toLowerCase().includes(search.toLowerCase()) || (x.email||'').includes(search))" :key="c.id" class="hover:bg-slate-50 transition">
            <td class="px-4 py-3 font-bold text-neutral-900">{{ c.name }}</td>
            <td class="px-4 py-3 text-neutral-500 text-xs">{{ c.email || '-' }}</td>
            <td class="px-4 py-3 text-xs">{{ c.city || '-' }}</td>
            <td class="px-4 py-3 text-xs">{{ c.bitrix_id || '-' }}</td>
            <td class="px-4 py-3 text-xs font-semibold">-</td>
            <td class="px-4 py-3 text-center"><span class="px-2 py-1 rounded-full text-[9px] font-bold bg-green-100 text-green-700">{{ c.status }}</span></td>
            <td class="px-4 py-3 text-center font-bold text-brand-700">{{ c.discount }}%</td>
            <td class="px-4 py-3 text-center">
              <button @click="store.remove(c.id)" class="text-red-500 hover:text-red-700 transition" title="Удалить">
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
