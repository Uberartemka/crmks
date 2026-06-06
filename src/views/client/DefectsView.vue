<script setup lang="ts">
import { ref } from 'vue'
interface Defect { id: number; equipment: string; bearing: string; defect: string; date: string; status: string; action: string }
const defects = ref<Defect[]>([
  { id: 1, equipment: 'Виброгрохот ГИЛ-42', bearing: 'HHB 22315-E1-T41A', defect: 'Повышенная вибрация, износ дорожек качения', date: '28.05.2026', status: 'Требует замены', action: 'Заказана замена' },
  { id: 2, equipment: 'Нория №2', bearing: 'FKD UC210', defect: 'Трещина наружного кольца', date: '25.05.2026', status: 'Критично', action: 'Срочный заказ отправлен' },
])
const newDefect = ref({ equipment: '', bearing: '', defect: '', action: '' })
function addDefect() {
  if (!newDefect.value.equipment) return
  defects.value.unshift({
    id: Date.now(),
    equipment: newDefect.value.equipment,
    bearing: newDefect.value.bearing,
    defect: newDefect.value.defect,
    date: new Date().toLocaleDateString('ru-RU'),
    status: 'Требует замены',
    action: newDefect.value.action,
  })
  newDefect.value = { equipment: '', bearing: '', defect: '', action: '' }
}
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Журнал дефектовки</h1>
    <div class="card p-5 space-y-4">
      <div class="text-xs font-bold text-neutral-500 uppercase">Новая запись</div>
      <div class="grid md:grid-cols-4 gap-3">
        <input v-model="newDefect.equipment" placeholder="Оборудование" class="input text-xs" />
        <input v-model="newDefect.bearing" placeholder="Подшипник" class="input text-xs" />
        <input v-model="newDefect.defect" placeholder="Описание дефекта" class="input text-xs" />
        <button @click="addDefect" class="btn-primary text-xs">Добавить</button>
      </div>
    </div>
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-sm text-left">
        <thead class="bg-slate-50 text-neutral-500 uppercase text-[10px] font-bold tracking-wider border-b border-slate-200">
          <tr><th class="px-6 py-4">Оборудование</th><th class="px-6 py-4">Подшипник</th><th class="px-6 py-4">Дефект</th><th class="px-6 py-4 text-center">Дата</th><th class="px-6 py-4 text-center">Статус</th><th class="px-6 py-4">Действие</th></tr>
        </thead>
        <tbody class="divide-y divide-slate-200 text-xs font-semibold text-neutral-700">
          <tr v-for="d in defects" :key="d.id" class="hover:bg-slate-50 transition">
            <td class="px-6 py-4 font-bold text-neutral-900">{{ d.equipment }}</td>
            <td class="px-6 py-4">{{ d.bearing }}</td>
            <td class="px-6 py-4 text-neutral-600">{{ d.defect }}</td>
            <td class="px-6 py-4 text-center">{{ d.date }}</td>
            <td class="px-6 py-4 text-center">
              <span class="px-2 py-0.5 rounded text-[9px] font-bold"
                :class="d.status==='Критично'?'bg-red-100 text-red-700':'bg-amber-100 text-amber-700'">{{ d.status }}</span>
            </td>
            <td class="px-6 py-4 text-xs">{{ d.action }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
