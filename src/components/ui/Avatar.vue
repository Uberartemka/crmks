<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  name: string
  src?: string | null
  size?: number
}>(), { size: 40 })

const initials = computed(() => {
  const parts = props.name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[1][0]).toUpperCase()
})

const bgStyle = computed(() => {
  if (props.src) return {}
  let hash = 0
  for (const ch of props.name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  const hue = hash % 360
  return { backgroundColor: `hsl(${hue}, 55%, 50%)` }
})
</script>

<template>
  <img
    v-if="src"
    :src="src"
    :alt="name"
    class="rounded-full object-cover bg-slate-200"
    :style="{ width: `${size}px`, height: `${size}px` }"
  />
  <div
    v-else
    class="rounded-full flex items-center justify-center text-white font-semibold select-none"
    :style="{ ...bgStyle, width: `${size}px`, height: `${size}px`, fontSize: `${size * 0.4}px` }"
  >{{ initials }}</div>
</template>
