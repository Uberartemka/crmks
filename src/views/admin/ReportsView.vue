<script setup lang="ts">
import { ref } from 'vue'
const period = ref('month')
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
    <div class="grid md:grid-cols-3 gap-6">
      <div class="card p-6 space-y-3">
        <div class="text-xs font-bold text-neutral-500 uppercase">Оборот HHB/FKD</div>
        <div class="text-4xl font-bold font-bebas text-brand-700">4.2 млн ₽</div>
        <div class="text-xs text-green-600 font-bold">+12% к прошлому периоду</div>
      </div>
      <div class="card p-6 space-y-3">
        <div class="text-xs font-bold text-neutral-500 uppercase">Средний чек B2B</div>
        <div class="text-4xl font-bold font-bebas text-brand-700">84 500 ₽</div>
        <div class="text-xs text-green-600 font-bold">+5% к прошлому периоду</div>
      </div>
      <div class="card p-6 space-y-3">
        <div class="text-xs font-bold text-neutral-500 uppercase">Конверсия КП</div>
        <div class="text-4xl font-bold font-bebas text-brand-700">34%</div>
        <div class="text-xs text-red-600 font-bold">-2% к прошлому периоду</div>
      </div>
    </div>
    <div class="card p-5">
      <div class="text-lg font-bold font-bebas tracking-wider mb-4">Динамика по категориям</div>
      <div class="h-48 flex items-end gap-4">
        <div v-for="(h, i) in [40,55,70,85,95,100]" :key="i" class="flex-1 flex flex-col items-center gap-2">
          <div class="w-full bg-slate-100 rounded-t-xl h-32 relative flex items-end justify-center overflow-hidden">
            <div class="bg-brand-700 w-full transition-all" :style="{ height: h+'%' }" />
          </div>
          <span class="text-[10px] text-neutral-500 font-bold">{{ ['Янв','Фев','Мар','Апр','Май','Июн'][i] }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
