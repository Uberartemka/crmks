<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useNotesStore } from '@/stores/notes'
import NoteCard from './NoteCard.vue'
import { Plus } from 'lucide-vue-next'

const notes = useNotesStore()
onMounted(() => notes.list())

const sorted = computed(() =>
  [...notes.items].sort((a, b) => Number(b.pinned) - Number(a.pinned)),
)

async function addNote() {
  const title = prompt('Заголовок заметки?')
  if (title?.trim()) await notes.create({ title: title.trim(), content: '', color: 'yellow' })
}

async function removeNote(noteId: number) {
  if (!confirm('Удалить заметку?')) return
  await notes.remove(noteId)
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between">
      <h3 class="font-semibold">Заметки</h3>
      <button class="btn-ghost text-sm" @click="addNote">
        <Plus :size="14" /> Добавить
      </button>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
      <NoteCard
        v-for="n in sorted" :key="n.id" :note="n"
        @pin="(note) => notes.update(note.id, { pinned: !note.pinned })"
        @open="() => {}"
        @delete="(note) => removeNote(note.id)"
      />
    </div>
    <p v-if="!sorted.length" class="text-sm text-slate-500">Пока пусто. Создай первую заметку.</p>
  </div>
</template>
