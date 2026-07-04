<script setup lang="ts">
import { computed } from 'vue'
import { FileText, Image as ImageIcon, Archive, File as FileIcon } from 'lucide-vue-next'
import { filesApi } from '@/api/files'
import type { StoredFile } from '@/types/file'

const props = defineProps<{
  file: Pick<StoredFile, 'id' | 'original_name' | 'mime_type' | 'size_bytes' | 'is_image'>
}>()

const sizeLabel = computed(() => {
  const b = props.file.size_bytes
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
})

const Icon = computed(() => {
  const m = props.file.mime_type
  if (m.startsWith('image/')) return ImageIcon
  if (m === 'application/pdf' || m.startsWith('text/')) return FileText
  if (m === 'application/zip') return Archive
  return FileIcon
})
</script>

<template>
  <div class="flex items-center gap-3 rounded-md border border-gray-200 p-2">
    <img
      v-if="file.is_image"
      :src="filesApi.thumbnailUrl(file.id)"
      :alt="file.original_name"
      class="h-12 w-12 rounded object-cover"
    />
    <component :is="Icon" v-else class="h-10 w-10 text-gray-400" />
    <div class="min-w-0 flex-1">
      <p class="truncate text-sm font-medium text-gray-800">{{ file.original_name }}</p>
      <p class="text-xs text-gray-500">{{ sizeLabel }}</p>
    </div>
    <a
      :href="filesApi.url(file.id)"
      target="_blank"
      class="text-xs font-medium text-brand-600 hover:text-brand-700"
    >Открыть</a>
  </div>
</template>
