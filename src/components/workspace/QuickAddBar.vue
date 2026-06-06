<script setup lang="ts">
import { ref } from 'vue'
import { useTasksStore } from '@/stores/tasks'
import { useNotesStore } from '@/stores/notes'
import { useAIStore } from '@/stores/ai'
import { useAuthStore } from '@/stores/auth'
import { useUsersStore } from '@/stores/users'
import { Sparkles } from 'lucide-vue-next'

const text = ref('')
const tasks = useTasksStore()
const notes = useNotesStore()
const ai = useAIStore()
const auth = useAuthStore()
const users = useUsersStore()

function pickAssigneeFromPrompt() {
  const list = users.list
  if (!list.length) return null

  const lines = list.map((u, idx) => `${idx + 1}) ${u.name} (@${u.username})`).join('\n')
  const raw = prompt(`Выберите исполнителя:\n0) Без исполнителя\n1..${list.length}) По номеру\n\n${lines}`)

  if (!raw) return null

  const n = Number(raw)
  if (!Number.isFinite(n) || n < 0) return null
  if (n === 0) return null

  const idx = n - 1
  if (idx < 0 || idx >= list.length) return null
  return list[idx].id
}

type EstimateKind = 'hours' | 'days'

function pickEstimateMinutesFromPrompt(): number | null {
  const kindRaw = prompt('Срок:\n1) Часы\n2) Дни\n\nВыберите: (1/2)')
  if (!kindRaw) return null

  const kindNum = Number(kindRaw)
  if (!Number.isFinite(kindNum) || (kindNum !== 1 && kindNum !== 2)) return null

  const kind: EstimateKind = kindNum === 1 ? 'hours' : 'days'
  const valueRaw = prompt(kind === 'hours' ? 'Сколько часов?' : 'Сколько дней?')
  if (!valueRaw) return null

  const value = Number(valueRaw)
  if (!Number.isFinite(value) || value < 0) return null

  if (kind === 'hours') return Math.floor(value * 60)
  return Math.floor(value * 24 * 60)
}

async function submit() {
  const v = text.value.trim()
  if (!v) return
  text.value = ''

  if (v.startsWith('/задача ')) {
    const title = v.slice(8).trim()
    if (!title) return

    const role = auth.role ?? 'employee'
    if (role !== 'employee') {
      if (!users.list.length) await users.load()
    }

    const assigneeId = role === 'employee' ? null : pickAssigneeFromPrompt()
    const minutes = pickEstimateMinutesFromPrompt()

    await tasks.create({
      title,
      status: 'todo',
      priority: 'medium',
      assignee_id: role === 'employee' ? undefined : assigneeId ?? undefined,
      estimated_minutes: minutes ?? undefined,
    })
  } else if (v.startsWith('/заметка ')) {
    await notes.create({ title: v.slice(9).trim(), content: '', color: 'yellow' })
  } else if (v.startsWith('/ai ')) {
    await ai.send(v.slice(4).trim())
  } else {
    await ai.send(v)
  }
}
</script>

<template>
  <div class="card flex items-center gap-2 p-2">
    <Sparkles :size="16" class="text-brand-600 ml-1" />
    <input
      v-model="text"
      class="flex-1 bg-transparent outline-none text-sm placeholder:text-slate-400"
      placeholder="Спроси AI или начни с /задача, /заметка"
      @keydown.enter="submit"
    />
    <button class="btn-primary text-xs" @click="submit">↵</button>
  </div>
</template>
