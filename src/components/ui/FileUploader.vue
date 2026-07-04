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

function openPicker() {
  inputRef.value?.click()
}

async function onChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  if (props.maxSizeBytes && file.size > props.maxSizeBytes) {
    emit('error', `Файл слишком большой (макс. ${Math.round(props.maxSizeBytes / 1024 / 1024)}MB)`)
    target.value = ''
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
    target.value = ''
  }
}
</script>

<template>
  <div class="file-uploader">
    <input
      ref="inputRef"
      type="file"
      class="hidden"
      :accept="accept"
      @change="onChange"
    />
    <slot :open="openPicker" :uploading="uploading">
      <button
        type="button"
        class="rounded-md border border-dashed border-gray-300 px-4 py-3 text-sm text-gray-600 hover:border-brand-500 hover:text-brand-700"
        :disabled="uploading"
        @click="openPicker"
      >
        {{ uploading ? 'Загрузка…' : 'Выбрать файл' }}
      </button>
    </slot>
  </div>
</template>
