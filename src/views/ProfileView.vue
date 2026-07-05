<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { toast } from '@/plugins/toast'
import Avatar from '@/components/ui/Avatar.vue'
import FileUploader from '@/components/ui/FileUploader.vue'

const auth = useAuthStore()

async function onAvatarUploaded(file: { id: number }) {
  try {
    await auth.updateAvatar(file.id)
    toast.success('Аватар обновлён')
  } catch {
    toast.error('Не удалось обновить аватар')
  }
}
</script>

<template>
  <div class="max-w-md mx-auto py-8 px-4">
    <div class="card p-6 space-y-4">
      <div class="flex justify-center">
        <Avatar :name="auth.user?.name ?? '?'" :src="auth.avatarUrl" :size="120" />
      </div>
      <div class="text-center">
        <h1 class="text-xl font-semibold">{{ auth.user?.name }}</h1>
        <p class="text-sm text-slate-500">@{{ auth.user?.username }} · {{ auth.user?.role }}</p>
      </div>
      <FileUploader
        accept="image/*"
        :max-size-bytes="5 * 1024 * 1024"
        @uploaded="onAvatarUploaded"
        @error="(msg: string) => toast.error(msg)"
      >
        <template #default="{ open, uploading }">
          <button class="btn-primary w-full" :disabled="uploading" @click="open">
            {{ uploading ? 'Загрузка...' : 'Сменить фото' }}
          </button>
        </template>
      </FileUploader>
    </div>
  </div>
</template>
