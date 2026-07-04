<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="fixed inset-0 z-[10000] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-modal-title"
      @click.self="cancel"
      @keydown.esc="cancel"
    >
      <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" />
      <div
        ref="cardRef"
        tabindex="-1"
        class="relative bg-white rounded-xl shadow-2xl border border-slate-200 max-w-md w-full p-6 z-10"
      >
        <h3 id="confirm-modal-title" class="font-bold text-base text-slate-900">
          {{ options.title }}
        </h3>
        <p v-if="options.message" class="text-sm text-slate-500 mt-2">
          {{ options.message }}
        </p>
        <div class="flex gap-2 justify-end mt-5">
          <BaseButton variant="secondary" @click="cancel">
            {{ options.cancelText || 'Отмена' }}
          </BaseButton>
          <BaseButton
            ref="confirmBtnRef"
            :variant="options.danger ? 'danger' : 'primary'"
            @click="ok"
          >
            {{ options.confirmText || 'Подтвердить' }}
          </BaseButton>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { onClickOutside } from '@vueuse/core'
import BaseButton from './BaseButton.vue'
import { useConfirm } from '@/composables/useConfirm'

const { visible, options, resolve } = useConfirm()
const cardRef = ref<HTMLElement | null>(null)
const confirmBtnRef = ref<{ $el: HTMLElement } | null>(null)

// Click outside card = cancel
onClickOutside(cardRef, () => cancel())

// On open, focus the confirm button (a11y)
watch(visible, async (v) => {
  if (v) {
    await nextTick()
    const el = confirmBtnRef.value?.$el as HTMLElement | undefined
    el?.focus()
  }
})

function ok() { resolve(true) }
function cancel() { resolve(false) }
</script>
