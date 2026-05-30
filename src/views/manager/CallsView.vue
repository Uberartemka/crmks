<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useCallsStore } from '@/stores/calls'

const store = useCallsStore()
const filter = ref<'all'|'today'|'week'|'month'>('all')
const filtered = computed(() => {
  if (filter.value === 'all') return store.list
  const now = new Date()
  return store.list.filter(c => {
    const d = new Date(c.call_date)
    if (filter.value === 'today') return d.toDateString() === now.toDateString()
    if (filter.value === 'week') return (now.getTime() - d.getTime()) < 7 * 86400000
    return (now.getTime() - d.getTime()) < 30 * 86400000
  })
})
onMounted(() => store.load())
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-3xl font-extrabold font-bebas tracking-wide">История звонков</h1>
    <div class="flex gap-2 bg-white rounded-xl border border-slate-200 p-1.5 shadow-sm w-fit">
      <button v-for="f in ['all','today','week','month']" :key="f" @click="filter=f as any"
        class="px-4 py-1.5 rounded-lg text-xs font-bold transition"
        :class="filter===f ? 'bg-brand-700 text-white' : 'text-neutral-500 hover:bg-slate-50'">
        {{ f==='all'?'Все':f==='today'?'Сегодня':f==='week'?'Неделя':'Месяц' }}
      </button>
    </div>
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden p-5">
      <div class="space-y-4">
        <div v-for="c in filtered" :key="c.id" class="flex items-start gap-4 p-4 rounded-xl border border-slate-100 hover:bg-slate-50 transition">
          <div class="w-10 h-10 rounded-full flex items-center justify-center font-bold text-xs shrink-0"
            :class="c.status==='completed'?'bg-green-100 text-green-700':c.status==='no_answer'?'bg-red-100 text-red-700':'bg-blue-100 text-blue-700'">
            {{ c.status==='completed'?'✓':c.status==='no_answer'?'✕':'⏱' }}
          </div>
          <div class="flex-1">
            <div class="flex items-center justify-between">
              <div class="font-bold text-sm">{{ c.client_name }}</div>
              <div class="text-[10px] text-neutral-400 font-bold">{{ c.call_date }}</div>
            </div>
            <div class="text-xs text-neutral-500 mt-1">{{ c.notes }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
