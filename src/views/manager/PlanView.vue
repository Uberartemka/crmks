<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { usePlansStore } from '@/stores/plans'
import { useCallsStore } from '@/stores/calls'
import { useLeadsStore } from '@/stores/leads'

const plansStore = usePlansStore()
const callsStore = useCallsStore()
const leadsStore = useLeadsStore()

const callsTarget = computed(() => plansStore.currentMonthPlan?.calls_target || 200)
const callsDone = computed(() => callsStore.list.length)
const regsTarget = computed(() => plansStore.currentMonthPlan?.registrations_target || 20)
const regsDone = computed(() => callsStore.list.filter(c => c.is_new_registration).length)

const newCall = ref({ client_name: '', to_number: '', call_date: '', status: 'scheduled' as 'completed'|'no_answer'|'scheduled', is_new_registration: false, notes: '' })

async function addCall() {
  if (!newCall.value.client_name) return
  await callsStore.create({
    client_name: newCall.value.client_name,
    to_number: newCall.value.to_number,
    call_date: newCall.value.call_date || new Date().toISOString().slice(0, 10),
    status: newCall.value.status,
    is_new_registration: newCall.value.is_new_registration,
    notes: newCall.value.notes,
  })
  newCall.value = { client_name: '', to_number: '', call_date: '', status: 'scheduled', is_new_registration: false, notes: '' }
}

onMounted(() => {
  plansStore.load()
  callsStore.load()
  leadsStore.load()
})
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Мой план на месяц</h1>

    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
      <div class="card p-6 flex items-center justify-between">
        <div><div class="text-xs font-semibold text-neutral-500 uppercase">Цель звонков</div><div class="text-3xl font-bold font-bebas mt-1 text-brand-700">{{ callsTarget }}</div></div>
        <div class="w-12 h-12 rounded-xl bg-brand-50 text-brand-700 flex items-center justify-center"><svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/></svg></div>
      </div>
      <div class="card p-6 flex items-center justify-between">
        <div><div class="text-xs font-semibold text-neutral-500 uppercase">Совершено</div><div class="text-3xl font-bold font-bebas mt-1 text-emerald-600">{{ callsDone }}</div></div>
        <div class="w-12 h-12 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center"><svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 4 12 14.01 9 11.01"/></svg></div>
      </div>
      <div class="card p-6 flex items-center justify-between">
        <div><div class="text-xs font-semibold text-neutral-500 uppercase">Дневная норма</div><div class="text-3xl font-bold font-bebas mt-1 text-blue-600">{{ Math.ceil(callsTarget/22) }}</div></div>
        <div class="w-12 h-12 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center"><svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/></svg></div>
      </div>
      <div class="card p-6 flex items-center justify-between">
        <div><div class="text-xs font-semibold text-neutral-500 uppercase">Осталось</div><div class="text-3xl font-bold font-bebas mt-1 text-amber-600">{{ callsTarget - callsDone }}</div></div>
        <div class="w-12 h-12 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center"><svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/></svg></div>
      </div>
    </div>

    <div class="card p-6 grid md:grid-cols-2 gap-6">
      <div>
        <div class="text-xs font-bold text-neutral-500 uppercase mb-3">Выполнение плана</div>
        <div class="w-full bg-slate-100 rounded-full h-4 overflow-hidden"><div class="bg-brand-700 h-full rounded-full transition-all" :style="{width: Math.min(100, (callsDone/callsTarget)*100)+'%'}" /></div>
        <div class="mt-2 text-xs text-neutral-500"><span class="font-bold text-brand-700">{{ callsDone }}</span> из {{ callsTarget }}</div>
      </div>
      <div>
        <div class="text-xs font-bold text-neutral-500 uppercase mb-3">Новые регистрации</div>
        <div class="w-full bg-slate-100 rounded-full h-4 overflow-hidden"><div class="bg-brand-700 h-full rounded-full transition-all" :style="{width: Math.min(100, (regsDone/regsTarget)*100)+'%'}" /></div>
        <div class="mt-2 text-xs text-neutral-500"><span class="font-bold text-brand-700">{{ regsDone }}</span> из {{ regsTarget }}</div>
      </div>
    </div>

    <div class="card p-5 space-y-4">
      <div class="text-xs font-bold text-neutral-500 uppercase">Быстро добавить звонок</div>
      <div class="grid md:grid-cols-5 gap-3">
        <input v-model="newCall.client_name" placeholder="Клиент" class="input text-xs" />
        <input v-model="newCall.to_number" placeholder="Телефон" class="input text-xs" />
        <input v-model="newCall.call_date" type="date" class="input text-xs" />
        <select v-model="newCall.status" class="input text-xs">
          <option value="scheduled">Запланирован</option>
          <option value="completed">Состоялся</option>
          <option value="no_answer">Нет ответа</option>
        </select>
        <button @click="addCall" class="btn-primary text-xs">Добавить</button>
      </div>
      <input v-model="newCall.notes" placeholder="Примечания..." class="input text-xs w-full" />
    </div>

    <div class="card p-5">
      <div class="text-xs font-bold text-neutral-500 uppercase mb-4">Мои назначенные лиды</div>
      <div class="space-y-2">
        <div v-for="l in leadsStore.list" :key="l.id" class="flex items-center justify-between p-3 rounded-xl border border-slate-100 hover:bg-slate-50 transition">
          <div>
            <div class="text-sm font-bold">{{ l.name }}</div>
            <div class="text-[10px] text-neutral-500 font-semibold">{{ l.category }}</div>
          </div>
          <span class="px-2 py-1 rounded-full text-[9px] font-bold bg-blue-100 text-blue-700">{{ l.status }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
