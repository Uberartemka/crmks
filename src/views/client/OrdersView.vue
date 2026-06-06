<script setup lang="ts">
import { ref } from 'vue'
interface Order { id: string; date: string; name: string; qty: number; total: number; status: string }
const orders = ref<Order[]>([
  { id: '104-M', date: '26.05.2026', name: 'HHB UCP206 + UCF208 Сельхоз-пакет', qty: 90, total: 97100, status: 'В пути' },
  { id: '105-M', date: '30.05.2026', name: 'HHB 22315-E1-T41A Вибро', qty: 10, total: 79500, status: 'Ждет подтверждения' },
  { id: '103-M', date: '18.05.2026', name: 'HHB STAINLESS UC 204 нержав.', qty: 5, total: 14750, status: 'Получен' },
])
const trackerStep = ref(2)
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Мои заказы и статусы</h1>
      <span class="text-xs font-bold text-emerald-700 bg-green-50 px-3 py-1.5 rounded-full border border-green-200">Договор активен (Лимит 500k)</span>
    </div>

    <div class="card p-6 space-y-6">
      <h2 class="text-lg font-bold font-bebas tracking-wider">Активное отслеживание</h2>
      <div class="relative flex flex-col md:flex-row md:items-center justify-between gap-6 md:gap-4">
        <div class="hidden md:block absolute left-4 right-4 top-5 h-1 bg-slate-200 -z-0" />
        <div class="hidden md:block absolute left-4 top-5 h-1 bg-brand-700 transition-all duration-500 -z-0" :style="{ width: (trackerStep/3*100)+'%' }" />
        <div v-for="(step, i) in ['Заказ принят','Оплачен','В пути','Доставлен']" :key="i" class="flex items-center md:flex-col gap-3 md:gap-2 relative z-10 text-xs text-center md:w-32">
          <div class="w-10 h-10 rounded-full flex items-center justify-center font-bold shadow-md"
            :class="i<trackerStep?'bg-brand-700 text-white shadow-brand-700/20':i===trackerStep?'bg-brand-700 text-white animate-pulse shadow-brand-700/20':'bg-slate-200 text-slate-500'">
            {{ i<trackerStep?'✓':i===trackerStep?'🚚':i===3?'🏁':'○' }}
          </div>
          <div><div class="font-bold" :class="i<=trackerStep?'text-neutral-900':'text-neutral-400'">{{ step }}</div></div>
        </div>
      </div>
    </div>

    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50">
        <h2 class="text-base font-bold text-neutral-800">Архив заказов</h2>
        <span class="text-xs text-neutral-400 font-medium">Всего: {{ orders.length }}</span>
      </div>
      <table class="w-full text-sm text-left">
        <thead class="bg-slate-100 text-neutral-500 uppercase text-[10px] font-bold tracking-wider border-b border-slate-200">
          <tr><th class="px-6 py-3.5">Заказ №</th><th class="px-6 py-3.5">Дата</th><th class="px-6 py-3.5">Номенклатура</th><th class="px-6 py-3.5 text-center">Кол-во</th><th class="px-6 py-3.5 text-right">Сумма</th><th class="px-6 py-3.5 text-center">Статус</th></tr>
        </thead>
        <tbody class="divide-y divide-slate-200 text-xs font-semibold text-neutral-700">
          <tr v-for="o in orders" :key="o.id" class="hover:bg-slate-50 transition">
            <td class="px-6 py-4 font-bold text-neutral-900">{{ o.id }}</td>
            <td class="px-6 py-4 text-neutral-500">{{ o.date }}</td>
            <td class="px-6 py-4">{{ o.name }}</td>
            <td class="px-6 py-4 text-center font-bold">{{ o.qty }}</td>
            <td class="px-6 py-4 text-right font-extrabold text-neutral-900">{{ o.total.toLocaleString() }} ₽</td>
            <td class="px-6 py-4 text-center">
              <span class="px-2.5 py-1 rounded-full text-[9px] font-bold"
                :class="o.status==='Получен'?'bg-green-100 text-green-700':o.status==='В пути'?'bg-blue-100 text-blue-700':'bg-amber-100 text-amber-700'">
                {{ o.status }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
