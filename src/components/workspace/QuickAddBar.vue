<script setup lang="ts">
import { ref } from 'vue'
import { useTasksStore } from '@/stores/tasks'
import { useNotesStore } from '@/stores/notes'
import { useAIStore } from '@/stores/ai'
import { Sparkles } from 'lucide-vue-next'

const text = ref('')
const tasks = useTasksStore()
const notes = useNotesStore()
const ai = useAIStore()

async function submit() {
  const v = text.value.trim()
  if (!v) return
  text.value = ''

  if (v.startsWith('/задача ')) {
    await tasks.create({ title: v.slice(8).trim(), status: 'todo', priority: 'medium' })
  } else if (v.startsWith('/заметка ')) {
    await notes.create({ title: v.slice(9).trim(), content: '', color: 'yellow' })
  } else if (v.startsWith('/ai ')) {
    await ai.send(v.slice(4).trim())
  } else {
    await ai.send(v)
  }
}
</script>

<template>
  <div class="card flex items-center gap-2 p-2">
    <Sparkles :size="16" class="text-brand-600 ml-1" />
    <input
      v-model="text"
      class="flex-1 bg-transparent outline-none text-sm placeholder:text-slate-400"
      placeholder="Спроси AI или начни с /задача, /заметка"
      @keydown.enter="submit"
    />
    <button class="btn-primary text-xs" @click="submit">↵</button>
  </div>
</template>
