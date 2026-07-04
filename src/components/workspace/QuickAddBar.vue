<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useTasksStore } from '@/stores/tasks'
import { useNotesStore } from '@/stores/notes'
import { useAIStore } from '@/stores/ai'
import { useAuthStore } from '@/stores/auth'
import { useUsersStore } from '@/stores/users'
import BaseButton from '@/components/ui/BaseButton.vue'
import { toast } from '@/plugins/toast'
import { Sparkles } from 'lucide-vue-next'

const text = ref('')
const tasks = useTasksStore()
const notes = useNotesStore()
const ai = useAIStore()
const auth = useAuthStore()
const users = useUsersStore()

type EstimateKind = 'hours' | 'days'

// --- Task creation modal state ---
const showTaskModal = ref(false)
const pendingTaskTitle = ref('')
// assignee: '' = "без исполнителя", otherwise user id as string
const assigneeChoice = ref('')
const estimateKind = ref<EstimateKind>('hours')
const estimateValue = ref<number | null>(null)

const canPickAssignee = computed(() => (auth.role ?? 'employee') !== 'employee')
const assigneeOptions = computed(() => users.list)

async function openTaskModal(title: string) {
  pendingTaskTitle.value = title
  assigneeChoice.value = ''
  estimateKind.value = 'hours'
  estimateValue.value = null

  if (canPickAssignee.value && !users.list.length) {
    await users.load()
  }

  showTaskModal.value = true
  void nextTick(() => {
    if (canPickAssignee.value) {
      document.getElementById('qa-assignee')?.focus()
    } else {
      document.getElementById('qa-value')?.focus()
    }
  })
}

// Resolve assignee id from the modal selection, mirroring pickAssigneeFromPrompt():
// '' / null → no assignee; valid index → user id.
function resolveAssigneeId(): number | null {
  if (!canPickAssignee.value) return null
  if (assigneeChoice.value === '' ) return null
  const n = Number(assigneeChoice.value)
  if (!Number.isFinite(n) || n <= 0) return null
  const idx = n - 1
  if (idx < 0 || idx >= assigneeOptions.value.length) return null
  return assigneeOptions.value[idx].id
}

// Resolve minutes from the modal, mirroring pickEstimateMinutesFromPrompt().
// Empty/invalid value → null (→ undefined downstream), matching the original
// early-return semantics that resulted in no estimate.
function resolveEstimateMinutes(): number | null {
  if (estimateValue.value === null) return null
  const value = Number(estimateValue.value)
  if (!Number.isFinite(value) || value < 0) return null
  return estimateKind.value === 'hours'
    ? Math.floor(value * 60)
    : Math.floor(value * 24 * 60)
}

function closeTaskModal() {
  showTaskModal.value = false
}

async function confirmCreateTask() {
  const title = pendingTaskTitle.value
  const role = auth.role ?? 'employee'

  const assigneeId = resolveAssigneeId()
  const minutes = resolveEstimateMinutes()

  await tasks.create({
    title,
    status: 'todo',
    priority: 'medium',
    assignee_id: role === 'employee' ? undefined : assigneeId ?? undefined,
    estimated_minutes: minutes ?? undefined,
  })

  toast.success('Задача создана')
  closeTaskModal()
}

async function submit() {
  const v = text.value.trim()
  if (!v) return
  text.value = ''

  if (v.startsWith('/задача ')) {
    const title = v.slice(8).trim()
    if (!title) return
    await openTaskModal(title)
  } else if (v.startsWith('/заметка ')) {
    await notes.create({ title: v.slice(9).trim(), content: '', color: 'yellow' })
    toast.success('Заметка создана')
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

    <Teleport to="body">
      <div
        v-if="showTaskModal"
        class="fixed inset-0 z-[10000] flex items-center justify-center p-4"
        @click.self="closeTaskModal"
        @keydown.esc="closeTaskModal"
      >
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" />
        <div class="relative bg-white rounded-xl shadow-2xl border border-slate-200 max-w-md w-full p-6 z-10 space-y-4">
          <h3 class="font-bold text-base">Новая задача</h3>
          <div class="space-y-3">
            <div v-if="canPickAssignee" class="space-y-1">
              <label class="block text-xs font-semibold text-slate-600">Исполнитель</label>
              <select
                id="qa-assignee"
                v-model="assigneeChoice"
                class="input"
              >
                <option value="">Без исполнителя</option>
                <option
                  v-for="(u, idx) in assigneeOptions"
                  :key="u.id"
                  :value="String(idx + 1)"
                >
                  {{ u.name }} (@{{ u.username }})
                </option>
              </select>
            </div>

            <div class="space-y-1">
              <span class="block text-xs font-semibold text-slate-600">Срок</span>
              <div class="flex gap-4">
                <label class="flex items-center gap-1.5 text-sm cursor-pointer">
                  <input
                    v-model="estimateKind"
                    type="radio"
                    value="hours"
                    class="accent-brand-600"
                  />
                  Часы
                </label>
                <label class="flex items-center gap-1.5 text-sm cursor-pointer">
                  <input
                    v-model="estimateKind"
                    type="radio"
                    value="days"
                    class="accent-brand-600"
                  />
                  Дни
                </label>
              </div>
            </div>

            <div class="space-y-1">
              <label class="block text-xs font-semibold text-slate-600">
                {{ estimateKind === 'hours' ? 'Сколько часов?' : 'Сколько дней?' }}
              </label>
              <input
                id="qa-value"
                v-model.number="estimateValue"
                type="number"
                min="0"
                step="any"
                class="input"
                placeholder="Например, 2"
                @keydown.enter="confirmCreateTask"
              />
            </div>
          </div>

          <div class="flex gap-2 justify-end pt-1">
            <BaseButton variant="secondary" @click="closeTaskModal">Отмена</BaseButton>
            <BaseButton variant="primary" @click="confirmCreateTask">Создать</BaseButton>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
