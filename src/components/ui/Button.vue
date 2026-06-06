<script setup lang="ts">
import { cn } from '@/lib/utils'

interface Props {
  variant?: 'default' | 'outline' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  size: 'md',
})
</script>

<template>
  <button :class="cn(
    'inline-flex items-center justify-center rounded-lg font-medium transition',
    props.variant === 'default' && 'bg-brand-600 text-white hover:bg-brand-700',
    props.variant === 'outline' && 'border border-white/20 hover:bg-white/5 text-white',
    props.variant === 'ghost' && 'hover:bg-white/5 text-white',
    props.size === 'sm' && 'px-3 py-1.5 text-xs',
    props.size === 'md' && 'px-4 py-2 text-sm',
    props.size === 'lg' && 'px-6 py-3 text-base',
  )">
    <slot />
  </button>
</template>
