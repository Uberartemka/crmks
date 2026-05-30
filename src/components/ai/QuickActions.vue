<script setup lang="ts">
import { useAIStore } from '@/stores/ai'
const ai = useAIStore()

const ACTIONS = [
  { label: '📋 Что важного сегодня', prompt: 'Покажи мне самые важные задачи на сегодня и предложи план действий.' },
  { label: '📝 Подготовь ТЭО', prompt: 'Подготовь шаблон ТЭО для нового клиента. Спроси у меня недостающие параметры.' },
  { label: '🧹 Резюмируй задачи', prompt: 'Сгруппируй мои задачи по приоритету и дай короткое резюме.' },
  { label: '⚡ Создай задачу', prompt: 'Создай задачу: ' },
]
</script>

<template>
  <div class="flex flex-wrap gap-1.5 px-3 pb-2">
    <button
      v-for="a in ACTIONS" :key="a.label"
      class="text-xs px-2 py-1 rounded-full border border-slate-200 hover:bg-slate-100"
      @click="ai.send(a.prompt)"
    >
      {{ a.label }}
    </button>
  </div>
</template>
