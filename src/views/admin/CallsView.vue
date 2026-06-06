<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useCallsStore } from '@/stores/calls'

const store = useCallsStore()
const filter = ref<'all' | 'today' | 'week' | 'month'>('all')
const newCall = ref({ client_name: '', to_number: '', call_date: '', status: 'scheduled' as 'completed'|'no_answer'|'scheduled', is_new_registration: false, notes: '' })

async function addCall() {
  if (!newCall.value.client_name) return
  await store.create({
    client_name: newCall.value.client_name,
    to_number: newCall.value.to_number,
    call_date: newCall.value.call_date || new Date().toISOString().slice(0, 10),
    status: newCall.value.status,
    is_new_registration: newCall.value.is_new_registration,
    notes: newCall.value.notes,
  })
  newCall.value = { client_name: '', to_number: '', call_date: '', status: 'scheduled', is_new_registration: false, notes: '' }
}

onMounted(() => store.load())
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-3xl font-extrabold font-bebas tracking-wide">История звонков</h1>

    <div class="flex gap-2 bg-white rounded-xl border border-slate-200 p-1.5 shadow-sm w-fit">
      <button v-for="f in ['all','today','week','month']" :key="f" @click="filter=f as any"
        class="px-4 py-1.5 rounded-lg text-xs font-bold transition"
        :class="filter===f ? 'bg-brand-700 text-white' : 'text-neutral-500 hover:bg-slate-50'">
        {{ f==='all'?'Все':f==='today'?'Сегодня':f==='week'?'Неделя':'Месяц' }}
      </button>
    </div>

    <div class="card p-5 space-y-4">
      <div class="text-xs font-bold text-neutral-500 uppercase">Быстро добавить звонок</div>
      <div class="grid md:grid-cols-6 gap-3">
        <input v-model="newCall.client_name" placeholder="Клиент" class="input text-xs" />
        <input v-model="newCall.to_number" placeholder="Телефон" class="input text-xs" />
        <input v-model="newCall.call_date" type="date" class="input text-xs" />
        <select v-model="newCall.status" class="input text-xs">
          <option value="scheduled">Запланирован</option>
          <option value="completed">Состоялся</option>
          <option value="no_answer">Нет ответа</option>
        </select>
        <label class="flex items-center gap-2 text-xs font-bold text-neutral-500"><input v-model="newCall.is_new_registration" type="checkbox" class="w-4 h-4 rounded" /> Новый клиент</label>
        <button @click="addCall" class="btn-primary text-xs">Добавить</button>
      </div>
      <input v-model="newCall.notes" placeholder="Примечания..." class="input text-xs w-full" />
    </div>

    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-neutral-500 text-[10px] uppercase font-bold">
          <tr><th class="px-4 py-3 text-left">Клиент</th><th class="px-4 py-3 text-left">Email</th><th class="px-4 py-3 text-left">Дата</th><th class="px-4 py-3 text-center">Статус</th><th class="px-4 py-3 text-left">Примечания</th></tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="c in store.list" :key="c.id" class="hover:bg-slate-50 transition">
            <td class="px-4 py-3 font-bold">{{ c.client_name }} <span v-if="c.is_new_registration" class="ml-1 text-[9px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-bold">NEW</span></td>
            <td class="px-4 py-3 text-xs text-neutral-500">{{ c.to_number || '-' }}</td>
            <td class="px-4 py-3 text-xs">{{ c.call_date }}</td>
            <td class="px-4 py-3 text-center">
              <span class="px-2 py-1 rounded-full text-[9px] font-bold"
                :class="c.status==='completed'?'bg-green-100 text-green-700':c.status==='no_answer'?'bg-red-100 text-red-700':'bg-blue-100 text-blue-700'">
                {{ c.status==='completed'?'Состоялся':c.status==='no_answer'?'Нет ответа':'Запланирован' }}
              </span>
            </td>
            <td class="px-4 py-3 text-xs text-neutral-600">{{ c.notes }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
