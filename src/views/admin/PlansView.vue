<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { usePlansStore } from '@/stores/plans'

const store = usePlansStore()
const newPlan = ref({ user_id: 1, month: 6, year: 2026, calls_target: 200, registrations_target: 20 })

async function savePlan() {
  await store.create({
    user_id: newPlan.value.user_id,
    month: newPlan.value.month,
    year: newPlan.value.year,
    calls_target: newPlan.value.calls_target,
    registrations_target: newPlan.value.registrations_target,
  })
}

onMounted(() => store.load())
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-3xl font-extrabold font-bebas tracking-wide">План и звонки менеджеров</h1>

    <div class="card p-5 grid md:grid-cols-2 gap-6">
      <div v-for="p in store.list" :key="p.id" class="space-y-3">
        <div class="text-xs font-bold text-neutral-500 uppercase">{{ p.user_name }}</div>
        <div>
          <div class="flex items-end gap-3">
            <div class="text-4xl font-bold font-bebas text-brand-700">0</div>
            <div class="text-sm text-neutral-500 mb-1">из {{ p.calls_target }}</div>
          </div>
          <div class="w-full bg-slate-100 rounded-full h-3 overflow-hidden">
            <div class="bg-brand-700 h-full rounded-full transition-all" :style="{ width: '0%' }" />
          </div>
        </div>
        <div>
          <div class="flex items-end gap-3">
            <div class="text-4xl font-bold font-bebas text-brand-700">0</div>
            <div class="text-sm text-neutral-500 mb-1">из {{ p.registrations_target }}</div>
          </div>
          <div class="w-full bg-slate-100 rounded-full h-3 overflow-hidden">
            <div class="bg-brand-700 h-full rounded-full transition-all" :style="{ width: '0%' }" />
          </div>
        </div>
      </div>
    </div>

    <div class="card p-5 space-y-4">
      <div class="text-xs font-bold text-neutral-500 uppercase mb-2">Новый план</div>
      <div class="grid md:grid-cols-5 gap-3">
        <input v-model.number="newPlan.user_id" type="number" placeholder="User ID" class="input text-xs" />
        <input v-model.number="newPlan.month" type="number" min="1" max="12" placeholder="Месяц" class="input text-xs" />
        <input v-model.number="newPlan.year" type="number" placeholder="Год" class="input text-xs" />
        <input v-model.number="newPlan.calls_target" type="number" placeholder="Звонков" class="input text-xs" />
        <input v-model.number="newPlan.registrations_target" type="number" placeholder="Регистраций" class="input text-xs" />
      </div>
      <div class="flex gap-2">
        <button @click="savePlan" class="btn-primary text-xs">Сохранить план</button>
        <button class="btn-ghost text-xs">⚡ Распределить лиды</button>
      </div>
    </div>
  </div>
</template>
