<script setup lang="ts">
import { ref } from 'vue'
interface Machine { name: string; node: string; bearing: string; date: string; wear: number; status: string; brand: string }
const machines = ref<Machine[]>([
  { name: 'Нория №1 головной барабан', node: 'Приводной вал головки', bearing: 'HHB UCP 208 LS3', date: '10.05.2025', wear: 35, status: 'Норма', brand: 'HHB' },
  { name: 'Виброгрохот ГИЛ-42', node: 'Центральный эксцентрик', bearing: 'HHB 22315-E1-T41A', date: '12.01.2026', wear: 80, status: 'Предельный', brand: 'HHB' },
  { name: 'Свеклорезка №3', node: 'Отрезной барабан', bearing: 'FKD UC210', date: '05.10.2024', wear: 95, status: 'Заменить!', brand: 'FKD' },
])
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Карта оборудования</h1>
      <button class="btn-primary text-xs">+ Добавить узел</button>
    </div>
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-sm text-left">
        <thead class="bg-slate-50 text-neutral-500 uppercase text-[10px] font-bold tracking-wider border-b border-slate-200">
          <tr><th class="px-6 py-4">Оборудование</th><th class="px-6 py-4">Узел</th><th class="px-6 py-4">Установленная модель</th><th class="px-6 py-4 text-center">Дата установки</th><th class="px-6 py-4 text-center">Износ</th><th class="px-6 py-4 text-center">Статус</th><th class="px-6 py-4 text-center">Замена</th></tr>
        </thead>
        <tbody class="divide-y divide-slate-200 text-xs font-semibold text-neutral-700">
          <tr v-for="m in machines" :key="m.name" class="hover:bg-slate-50 transition">
            <td class="px-6 py-4 font-bold text-neutral-900">{{ m.name }}</td>
            <td class="px-6 py-4 text-neutral-500">{{ m.node }}</td>
            <td class="px-6 py-4 font-bold" :class="m.brand==='HHB'?'text-brand-700':'text-neutral-500'">{{ m.bearing }}</td>
            <td class="px-6 py-4 text-center">{{ m.date }}</td>
            <td class="px-6 py-4 text-center">
              <div class="w-24 bg-slate-100 rounded-full h-2.5 mx-auto overflow-hidden">
                <div class="h-2.5" :class="m.wear>90?'bg-red-500':m.wear>70?'bg-yellow-500':'bg-green-500'" :style="{width: m.wear+'%'}" />
              </div>
              <span class="text-[10px] mt-1 block" :class="m.wear>90?'text-red-600':m.wear>70?'text-yellow-600':'text-green-600'">{{ m.wear }}%</span>
            </td>
            <td class="px-6 py-4 text-center">
              <span class="px-2 py-0.5 rounded text-[9px] font-bold"
                :class="m.status==='Норма'?'bg-green-100 text-green-700':m.status==='Предельный'?'bg-yellow-100 text-yellow-700':'bg-red-100 text-red-700'">
                {{ m.status }}
              </span>
            </td>
            <td class="px-6 py-4 text-center">
              <button v-if="m.wear>70" class="btn-primary text-[9px] px-2 py-1">Заказать замену</button>
              <span v-else class="text-neutral-400 text-[10px] font-bold">Не требуется</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
