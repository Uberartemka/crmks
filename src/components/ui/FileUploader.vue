<script setup lang="ts">
import { ref } from 'vue'
import { filesApi } from '@/api/files'
import type { StoredFile } from '@/types/file'

const props = defineProps<{
  accept?: string
  maxSizeBytes?: number
}>()

const emit = defineEmits<{
  uploaded: [file: StoredFile]
  error: [message: string]
}>()

const inputRef = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const isDragging = ref(false)

function openPicker() {
  inputRef.value?.click()
}

async function handleFile(file: File) {
  if (props.maxSizeBytes && file.size > props.maxSizeBytes) {
    emit('error', `Файл слишком большой (макс. ${Math.round(props.maxSizeBytes / 1024 / 1024)}MB)`)
    return
  }
  uploading.value = true
  try {
    const { data } = await filesApi.upload(file)
    emit('uploaded', data)
  } catch (e: any) {
    const detail = e?.response?.data?.detail || 'Не удалось загрузить файл'
    emit('error', detail)
  } finally {
    uploading.value = false
  }
}

function onChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) handleFile(file)
  target.value = ''
}

function onDrop(event: DragEvent) {
  isDragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) handleFile(file)
}
</script>

<template>
  <div
    class="file-uploader rounded-lg transition-colors"
    :class="{ 'bg-brand-50 ring-2 ring-brand-500 ring-inset': isDragging }"
    @dragover.prevent="isDragging = true"
    @dragleave.prevent="isDragging = false"
    @drop.prevent="onDrop"
  >
    <input
      ref="inputRef"
      type="file"
      class="hidden"
      :accept="accept"
      @change="onChange"
    />
    <slot :open="openPicker" :uploading="uploading" :is-dragging="isDragging">
      <button
        type="button"
        class="w-full rounded-md border border-dashed border-gray-300 px-4 py-3 text-sm text-gray-600 hover:border-brand-500 hover:text-brand-700"
        :disabled="uploading"
        @click="openPicker"
      >
        {{ uploading ? 'Загрузка…' : isDragging ? 'Отпустите, чтобы загрузить' : 'Выбрать или перетащить файл' }}
      </button>
    </slot>
  </div>
</template>
