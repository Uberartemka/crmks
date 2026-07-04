<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import draggable from 'vuedraggable'
import { useTasksStore } from '@/stores/tasks'
import type { TaskStatus, UserTask } from '@/types/task'
import TaskCard from './TaskCard.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import { Plus, Trash2, CheckCircle, Play } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { useUsersStore } from '@/stores/users'

const tasks = useTasksStore()
const auth = useAuthStore()
const users = useUsersStore()

onMounted(async () => {
  await tasks.list()
  syncColumnListsFromStore()

  if (auth.role && auth.role !== 'employee') {
    await users.load()
  }
})

const COLUMNS: { id: TaskStatus; title: string; tint: string }[] = [
  { id: 'todo', title: 'К выполнению', tint: 'bg-slate-100' },
  { id: 'in_progress', title: 'В работе', tint: 'bg-blue-100' },
  { id: 'blocked', title: 'Срочное', tint: 'bg-red-100' },
  { id: 'done', title: 'Готово', tint: 'bg-emerald-100' },
]

// Стабильные массивы для vuedraggable (чтобы не было "возврата" при ререндере)
const columnLists = reactive<Record<TaskStatus, UserTask[]>>({
  todo: [],
  in_progress: [],
  blocked: [],
  done: [],
})

const isDragging = ref(false)

function syncColumnListsFromStore() {
  const map: Record<TaskStatus, UserTask[]> = { todo: [], in_progress: [], blocked: [], done: [] }
  for (const t of tasks.items) map[t.status].push(t)

  for (const status of Object.keys(columnLists) as TaskStatus[]) {
    columnLists[status].splice(0, columnLists[status].length, ...map[status])
  }
}

syncColumnListsFromStore()


function onChange(status: TaskStatus, evt: any) {
  const moved = (evt.added?.element ?? evt.moved?.element) as UserTask | undefined
  if (!moved) return

  // избегаем "возврата" из-за задержки API: сразу меняем статус локально
  if (moved.status !== status) {
    const local = tasks.items.find((x) => x.id === moved.id)
    if (local) local.status = status

    // запретим серверному ответу "перезатирать" визуальные списки во время drag
    if (!isDragging.value) syncColumnListsFromStore()

    // запрос на сервер без ожидания
    void tasks.update(moved.id, { status }).finally(() => {
      if (!isDragging.value) syncColumnListsFromStore()
    })
  }
}

async function quickAdd(status: TaskStatus) {
  openCreateModal(status)
}

// Modal state: existing task actions
const selectedTask = ref<UserTask | null>(null)
const showModal = ref(false)

function openTask(task: UserTask) {
  selectedTask.value = task
  showModal.value = true
}

function closeModal() {
  selectedTask.value = null
  showModal.value = false
}

async function completeTask() {
  if (!selectedTask.value) return
  await tasks.update(selectedTask.value.id, { status: 'done' })
  syncColumnListsFromStore()
  closeModal()
}

async function startWork() {
  if (!selectedTask.value) return
  await tasks.update(selectedTask.value.id, { status: 'in_progress' })
  syncColumnListsFromStore()
  closeModal()
}

async function deleteTask() {
  if (!selectedTask.value) return
  if (confirm('Удалить задачу?')) {
    await tasks.remove(selectedTask.value.id)
    syncColumnListsFromStore()
    closeModal()
  }
}

// Modal state: create task
const showCreateModal = ref(false)
const createStatus = ref<TaskStatus>('todo')
const createTitle = ref('')
const createAssigneeId = ref<number | null>(null)

type EstimateKind = 'hours' | 'days'
const createEstimateKind = ref<EstimateKind>('hours')
const createEstimateValue = ref<number | null>(1)

const createSubmitting = ref(false)

function openCreateModal(status: TaskStatus) {
  createStatus.value = status
  createTitle.value = ''

  createEstimateKind.value = 'hours'
  createEstimateValue.value = 1

  if (auth.role === 'employee' && auth.user) {
    createAssigneeId.value = auth.user.id
  } else {
    // можно создать без исполнителя
    createAssigneeId.value = null
  }

  showCreateModal.value = true
}

function closeCreateModal() {
  showCreateModal.value = false
  createSubmitting.value = false
}

function getEstimateMinutes(): number | undefined {
  const v = createEstimateValue.value
  if (v === null || !Number.isFinite(v) || v < 0) return undefined

  if (createEstimateKind.value === 'hours') return Math.floor(v * 60)
  return Math.floor(v * 24 * 60)
}

async function submitCreateTask() {
  const title = createTitle.value.trim()
  if (!title) return

  // для менеджера/админа можно создать задачу без исполнителя

  createSubmitting.value = true
  try {
    await tasks.create({
      title,
      status: createStatus.value,
      priority: 'medium',
      assignee_id: createAssigneeId.value ?? undefined,
      estimated_minutes: getEstimateMinutes(),
    })
    syncColumnListsFromStore()
    closeCreateModal()
  } finally {
    createSubmitting.value = false
  }
}
</script>

<template>
  <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
    <div
      v-for="col in COLUMNS"
      :key="col.id"
      class="flex flex-col rounded-lg bg-white border border-slate-200"
    >
      <div class="flex items-center justify-between px-3 py-2 border-b" :class="col.tint">
        <div class="flex items-center gap-2">
          <span class="font-semibold text-sm">{{ col.title }}</span>
          <span class="text-xs text-slate-500">{{ columnLists[col.id].length }}</span>
        </div>
        <button class="btn-ghost !p-1" @click="quickAdd(col.id)" title="Добавить">
          <Plus :size="14" />
        </button>
      </div>

      <draggable
        :list="columnLists[col.id]"
        group="tasks"
        item-key="id"
        class="flex-1 p-2 space-y-2 min-h-[100px]"
        :animation="180"
        easing="cubic-bezier(0.4, 0, 0.2, 1)"
        :fallback-on-body="true"
        @start="() => { isDragging = true }"
        @end="() => { isDragging = false }"
        @change="(e: any) => onChange(col.id, e)"
      >
        <template #item="{ element }">
          <TaskCard :task="element" @open="openTask" />
        </template>
      </draggable>
    </div>

    <!-- Create Task Modal -->
    <div
      v-if="showCreateModal"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      @click.self="closeCreateModal"
    >
      <div class="bg-white rounded-lg p-6 max-w-xl w-full mx-4">
        <h3 class="text-lg font-semibold mb-2">Новая задача</h3>

        <div class="space-y-3">
          <div>
            <div class="text-xs font-semibold text-slate-600 mb-1">Название</div>
            <input
              v-model="createTitle"
              class="input w-full"
              placeholder="Например: Позвонить клиенту"
              @keydown.enter="submitCreateTask"
            />
          </div>

          <div v-if="auth.role !== 'employee'">
            <div class="text-xs font-semibold text-slate-600 mb-1">Исполнитель</div>
            <select v-model="createAssigneeId" class="input w-full">
              <option :value="null">Без исполнителя</option>
              <option v-for="u in users.list" :key="u.id" :value="u.id">
                {{ u.name }} ({{ u.username }})
              </option>
            </select>
          </div>

          <div>
            <div class="text-xs font-semibold text-slate-600 mb-1">Срок</div>

            <div class="grid grid-cols-2 gap-2">
              <select v-model="createEstimateKind" class="input w-full">
                <option value="hours">Часы</option>
                <option value="days">Дни</option>
              </select>

              <input
                v-model.number="createEstimateValue"
                type="number"
                min="0"
                step="1"
                class="input w-full"
                :placeholder="createEstimateKind === 'hours' ? 'Напр. 5' : 'Напр. 2'"
              />
            </div>
            <p class="text-[11px] text-slate-500 mt-1">
              Вы выбрали: {{ createEstimateKind === 'hours' ? 'часы' : 'дни' }}
            </p>
          </div>
        </div>

        <div class="flex gap-2 mt-4">
          <BaseButton
            variant="primary"
            class="whitespace-nowrap"
            :disabled="createSubmitting"
            @click="submitCreateTask"
          >
            {{ createSubmitting ? 'Создаю...' : 'Создать' }}
          </BaseButton>
          <BaseButton variant="secondary" class="whitespace-nowrap" @click="closeCreateModal">
            Отмена
          </BaseButton>
        </div>

        <p class="text-xs text-slate-500 mt-3">
          Если вы сотрудник — назначение будет на вас (как и должно быть).
        </p>
      </div>
    </div>

    <!-- Task Modal -->
    <div
      v-if="showModal && selectedTask"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      @click.self="closeModal"
    >
      <div class="bg-white rounded-lg p-6 max-w-xl w-full mx-4">
        <h3 class="text-lg font-semibold mb-2">{{ selectedTask.title }}</h3>
        <p v-if="selectedTask.description" class="text-sm text-slate-600 mb-4">
          {{ selectedTask.description }}
        </p>

        <div class="flex gap-3 mb-4 text-xs text-slate-500 flex-wrap">
          <span>Статус: {{ selectedTask.status }}</span>
          <span>Приоритет: {{ selectedTask.priority }}</span>
          <span v-if="selectedTask.assignee_name">Ответственный: {{ selectedTask.assignee_name }}</span>
          <span v-if="selectedTask.estimated_minutes !== undefined">
            ⏱ {{ selectedTask.estimated_minutes }} мин
          </span>
        </div>

        <div class="flex gap-2">
          <BaseButton
            v-if="selectedTask.status !== 'in_progress' && selectedTask.status !== 'done'"
            variant="primary"
            class="whitespace-nowrap"
            @click="startWork"
          >
            <Play :size="16" class="mr-1" />
            Взять в работу
          </BaseButton>

          <BaseButton
            v-if="selectedTask.status !== 'done'"
            variant="success"
            class="whitespace-nowrap"
            @click="completeTask"
          >
            <CheckCircle :size="16" class="mr-1" />
            Выполнено
          </BaseButton>

          <BaseButton variant="danger" class="whitespace-nowrap" @click="deleteTask">
            <Trash2 :size="16" class="mr-1" />
            Удалить
          </BaseButton>

          <BaseButton variant="secondary" @click="closeModal">Закрыть</BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>
