<script setup lang="ts">
import { onMounted } from 'vue'
import { useLeadsStore } from '@/stores/leads'
const store = useLeadsStore()
onMounted(() => store.load())
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Мои лиды</h1>
      <div class="text-xs text-neutral-500 font-semibold">Лиды назначены начальником отдела</div>
    </div>
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-neutral-500 text-[10px] uppercase font-bold">
          <tr><th class="px-4 py-3 text-left">Компания</th><th class="px-4 py-3 text-left">Отрасль</th><th class="px-4 py-3 text-left">Контакты</th><th class="px-4 py-3 text-center">Статус</th><th class="px-4 py-3 text-right">Действие</th></tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="l in store.list" :key="l.id" class="hover:bg-slate-50 transition">
            <td class="px-4 py-3 font-bold">{{ l.name }}</td>
            <td class="px-4 py-3 text-xs">{{ l.category }}</td>
            <td class="px-4 py-3 text-xs text-neutral-500">{{ l.contacts || '-' }}</td>
            <td class="px-4 py-3 text-center"><span class="px-2 py-1 rounded-full text-[9px] font-bold" :class="l.status==='new'?'bg-blue-100 text-blue-700':'bg-green-100 text-green-700'">{{ l.status }}</span></td>
            <td class="px-4 py-3 text-right"><button class="btn-primary text-[10px] px-2 py-1">Позвонить</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
