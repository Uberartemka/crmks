<script setup lang="ts">
import { ref } from 'vue'
import QuickAddBar from '@/components/workspace/QuickAddBar.vue'
import TaskBoard from '@/components/workspace/TaskBoard.vue'
import NotesGrid from '@/components/workspace/NotesGrid.vue'

const view = ref<'board' | 'notes' | 'split'>('split')
</script>

<template>
  <div class="p-4 space-y-4">
    <header class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold">Воркспейс</h1>
        <p class="text-sm text-slate-500">Задачи, заметки и AI-ассистент в одном месте</p>
      </div>
      <div class="flex gap-1 bg-white border border-slate-200 rounded-md p-0.5">
        <button class="btn-ghost text-xs" :class="{ '!bg-brand-50 !text-brand-700': view==='split' }" @click="view='split'">Всё</button>
        <button class="btn-ghost text-xs" :class="{ '!bg-brand-50 !text-brand-700': view==='board' }" @click="view='board'">Доска</button>
        <button class="btn-ghost text-xs" :class="{ '!bg-brand-50 !text-brand-700': view==='notes' }" @click="view='notes'">Заметки</button>
      </div>
    </header>

    <QuickAddBar />

    <section v-if="view !== 'notes'">
      <h2 class="text-sm font-semibold mb-2 text-slate-700">Задачи</h2>
      <TaskBoard />
    </section>

    <section v-if="view !== 'board'">
      <NotesGrid />
    </section>
  </div>
</template>
