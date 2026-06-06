<script setup lang="ts">
import { onMounted } from 'vue'
import { useProposalsStore } from '@/stores/proposals'
const store = useProposalsStore()
onMounted(() => store.load())
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-3xl font-extrabold font-bebas tracking-wide">История КП</h1>
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-neutral-500 text-[10px] uppercase font-bold">
          <tr><th class="px-4 py-3 text-left">№ КП</th><th class="px-4 py-3 text-left">Клиент</th><th class="px-4 py-3 text-left">Дата</th><th class="px-4 py-3 text-right">Сумма</th><th class="px-4 py-3 text-center">Статус</th></tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="p in store.list" :key="p.id" class="hover:bg-slate-50 transition">
            <td class="px-4 py-3 font-bold text-neutral-900">KP-{{ p.seq_num || p.id }}</td>
            <td class="px-4 py-3">{{ p.client_name || '-' }}</td>
            <td class="px-4 py-3 text-xs text-neutral-500">{{ p.created_at?.slice(0,10) }}</td>
            <td class="px-4 py-3 text-right font-extrabold">{{ Math.round(p.total_amount).toLocaleString() }} ₽</td>
            <td class="px-4 py-3 text-center">
              <span class="px-2 py-1 rounded-full text-[9px] font-bold"
                :class="p.status==='sent'?'bg-green-100 text-green-700':p.status==='draft'?'bg-blue-100 text-blue-700':'bg-amber-100 text-amber-700'">
                {{ p.status==='sent'?'Отправлено':p.status==='draft'?'Черновик':p.status }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
