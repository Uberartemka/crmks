<script setup lang="ts">
import type { Note } from '@/types/note'
import { marked } from 'marked'
import { computed } from 'vue'
import { Pin, Trash2 } from 'lucide-vue-next'

const props = defineProps<{ note: Note }>()
defineEmits<{
  (e: 'open', n: Note): void
  (e: 'pin', n: Note): void
  (e: 'delete', n: Note): void
}>()

const bg: Record<NonNullable<Note['color']>, string> = {
  yellow: 'bg-amber-50 border-amber-200',
  blue: 'bg-blue-50 border-blue-200',
  green: 'bg-emerald-50 border-emerald-200',
  pink: 'bg-pink-50 border-pink-200',
  gray: 'bg-slate-50 border-slate-200',
}

const html = computed(() => marked.parse(props.note.content || '', { async: false }) as string)
</script>

<template>
  <div
    class="rounded-lg border p-3 cursor-pointer hover:shadow-md transition"
    :class="bg[note.color ?? 'yellow']"
    @click="$emit('open', note)"
  >
    <div class="flex items-start justify-between gap-2">
      <h4 class="font-semibold text-sm">{{ note.title }}</h4>
      <div class="flex items-center gap-1">
        <button
          class="text-slate-400 hover:text-amber-600"
          :class="{ 'text-amber-600': note.pinned }"
          @click.stop="$emit('pin', note)"
          title="Закрепить"
        >
          <Pin :size="14" />
        </button>

        <button
          class="text-slate-400 hover:text-red-600"
          @click.stop="$emit('delete', note)"
          title="Удалить"
        >
          <Trash2 :size="14" />
        </button>
      </div>
    </div>

    <div class="prose prose-sm mt-1 max-w-none text-slate-700 line-clamp-4" v-html="html" />

    <div v-if="note.tags.length" class="mt-2 flex gap-1 flex-wrap text-[11px] text-slate-500">
      <span v-for="t in note.tags" :key="t" class="px-1.5 py-0.5 rounded bg-white/60">#{{ t }}</span>
    </div>
  </div>
</template>
