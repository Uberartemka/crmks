<template>
  <button :class="classes" :disabled="disabled" :type="type">
    <slot />
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'danger' | 'success' | 'ghost'
  disabled?: boolean
  type?: 'button' | 'submit'
}>(), { variant: 'primary', disabled: false, type: 'button' })

const classes = computed(() => [
  'base-btn',
  `base-btn--${props.variant}`,
])
</script>
