<script setup lang="ts">
import { ref } from 'vue'
const query = ref('')
const results = ref<string[]>([])
const loading = ref(false)

function search() {
  loading.value = true
  setTimeout(() => {
    results.value = query.value
      ? [`ООО "${query.value.toUpperCase()}" — Воронеж, ИНН 3600xxxxxx`, `АО "${query.value.toUpperCase()} ХОЛДИНГ" — Москва, ИНН 7700xxxxxx`]
      : []
    loading.value = false
  }, 600)
}
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Парсер лидов B2B</h1>
    <div class="card p-5 flex gap-3">
      <input v-model="query" @keyup.enter="search" placeholder="Название компании, ИНН, отрасль..." class="input flex-1" />
      <button @click="search" :disabled="loading" class="btn-primary disabled:opacity-50">{{ loading ? 'Поиск...' : 'Найти' }}</button>
    </div>
    <div v-if="results.length" class="space-y-2">
      <div v-for="(r, i) in results" :key="i" class="card p-4 flex items-center justify-between">
        <span class="text-sm font-bold">{{ r }}</span>
        <button class="btn-primary text-xs">Добавить в CRM</button>
      </div>
    </div>
    <div v-else-if="!loading && query" class="text-center text-neutral-400 text-sm py-8">Ничего не найдено</div>
  </div>
</template>
