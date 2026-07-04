<template>
  <span :class="classes"><slot /></span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  type?: 'success' | 'warning' | 'danger' | 'info' | 'purple' | 'gray'
}>(), { type: 'gray' })

const classes = computed(() => [
  'base-badge',
  `base-badge--${props.type}`,
])
</script>
