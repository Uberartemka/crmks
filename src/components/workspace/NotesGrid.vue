<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useNotesStore } from '@/stores/notes'
import NoteCard from './NoteCard.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import { toast } from '@/plugins/toast'
import { Plus } from 'lucide-vue-next'

const notes = useNotesStore()
onMounted(() => notes.list())

const sorted = computed(() =>
  [...notes.items].sort((a, b) => Number(b.pinned) - Number(a.pinned)),
)

const showNoteModal = ref(false)
const newNoteTitle = ref('')
const titleInput = ref<HTMLInputElement | null>(null)

function openNoteModal() {
  newNoteTitle.value = ''
  showNoteModal.value = true
  void nextTick(() => titleInput.value?.focus())
}

async function confirmCreateNote() {
  const title = newNoteTitle.value.trim()
  if (!title) {
    toast.warning('Введите заголовок заметки')
    return
  }
  await notes.create({ title, content: '', color: 'yellow' })
  toast.success('Заметка создана')
  showNoteModal.value = false
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
      <button class="btn-ghost text-sm" @click="openNoteModal">
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

    <Teleport to="body">
      <div
        v-if="showNoteModal"
        class="fixed inset-0 z-[10000] flex items-center justify-center p-4"
        @click.self="showNoteModal = false"
        @keydown.esc="showNoteModal = false"
      >
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" />
        <div class="relative bg-white rounded-xl shadow-2xl border border-slate-200 max-w-md w-full p-6 z-10">
          <h3 class="font-bold text-base mb-3">Новая заметка</h3>
          <input
            ref="titleInput"
            v-model="newNoteTitle"
            class="input mb-4"
            placeholder="Заголовок заметки"
            @keydown.enter="confirmCreateNote"
          />
          <div class="flex gap-2 justify-end">
            <BaseButton variant="secondary" @click="showNoteModal = false">Отмена</BaseButton>
            <BaseButton variant="primary" @click="confirmCreateNote">Создать</BaseButton>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
