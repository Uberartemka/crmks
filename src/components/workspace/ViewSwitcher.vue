<script setup lang="ts">
import { ref } from 'vue'

const views = ['kanban', 'list', 'calendar'] as const
type View = typeof views[number]

const active = ref<View>('kanban')

const emit = defineEmits<{
  (e: 'change', view: View): void
}>()
</script>

<template>
  <div class="flex gap-1 p-1 rounded-lg bg-white/5 border border-white/10">
    <button
      v-for="view in views"
      :key="view"
      @click="emit('change', view); active = view"
      :class="['px-3 py-1.5 rounded-md text-xs font-medium transition capitalize', active === view ? 'bg-hhb text-white' : 'text-neutral-400 hover:text-white']"
    >
      {{ view }}
    </button>
  </div>
</template>
