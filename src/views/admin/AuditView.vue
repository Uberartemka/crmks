<script setup lang="ts">
import { ref } from 'vue'
const checklist = ref([
  { item: 'Чемоданчик с образцами HHB', done: true },
  { item: 'Технические паспорта подшипников', done: true },
  { item: 'Конкурентные образцы (SKF, CRAFT)', done: false },
  { item: 'Планшет с презентацией', done: true },
  { item: 'Визитки и каталоги', done: false },
])
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Цифровой Чемоданчик</h1>
    <div class="grid md:grid-cols-2 gap-6">
      <div class="card p-5 space-y-3">
        <div class="text-xs font-bold text-neutral-500 uppercase mb-2">Чек-лист аудита</div>
        <label v-for="(c, i) in checklist" :key="i" class="flex items-center gap-3 p-3 rounded-xl border border-slate-100 hover:bg-slate-50 cursor-pointer transition">
          <input v-model="c.done" type="checkbox" class="w-5 h-5 rounded text-brand-700" />
          <span class="text-sm font-semibold" :class="c.done ? 'line-through text-neutral-400' : 'text-neutral-800'">{{ c.item }}</span>
        </label>
      </div>
      <div class="card p-5 space-y-4">
        <div class="text-xs font-bold text-neutral-500 uppercase mb-2">Результат визита</div>
        <textarea placeholder="Описание встречи, потребности клиента..." rows="6" class="input w-full text-sm resize-none" />
        <button class="btn-primary w-full text-xs">Сохранить отчет</button>
      </div>
    </div>
  </div>
</template>
