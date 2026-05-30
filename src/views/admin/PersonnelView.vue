<script setup lang="ts">
import { onMounted } from 'vue'
import { useUsersStore } from '@/stores/users'

const store = useUsersStore()
onMounted(() => store.load())
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Персонал</h1>
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-neutral-500 text-[10px] uppercase font-bold">
          <tr><th class="px-4 py-3 text-left">ФИО</th><th class="px-4 py-3 text-left">Должность</th><th class="px-4 py-3 text-left">Телефон</th><th class="px-4 py-3 text-left">Email</th><th class="px-4 py-3 text-center">Статус</th></tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="e in store.list" :key="e.id" class="hover:bg-slate-50 transition">
            <td class="px-4 py-3 font-bold text-neutral-900">{{ e.name }}</td>
            <td class="px-4 py-3 text-xs">{{ e.role }}</td>
            <td class="px-4 py-3 text-xs text-neutral-500">-</td>
            <td class="px-4 py-3 text-xs text-neutral-500">{{ e.username }}</td>
            <td class="px-4 py-3 text-center">
              <span class="px-2 py-1 rounded-full text-[9px] font-bold bg-green-100 text-green-700">Активен</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
