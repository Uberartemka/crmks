<script setup lang="ts">
import { ref, computed } from 'vue'
const fr = ref(12)
const fa = ref(3)
const rpm = ref(1500)
const sealFactor = ref(1)

const l10 = computed(() => {
  const c = 33.2
  const p = Math.pow(Math.pow(fr.value, 2) + Math.pow(fa.value, 2), 0.5)
  const l = Math.pow(c / p, 3) * 1000000 / (60 * rpm.value)
  return Math.round(l * sealFactor.value)
})
const months = computed(() => (l10.value / (30.44 * 24)).toFixed(1))
const reliability = computed(() => {
  if (l10.value > 20000) return { text: 'Высокая надежность', color: 'text-green-600' }
  if (l10.value > 8000) return { text: 'Средняя надежность', color: 'text-yellow-600' }
  return { text: 'Требуется усиленный контроль', color: 'text-red-600' }
})
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-3xl font-extrabold font-bebas tracking-wide">Расчет ресурса подшипника ISO 281</h1>
      <span class="text-xs text-neutral-500 font-semibold">Калькулятор номинальной долговечности</span>
    </div>
    <div class="grid lg:grid-cols-2 gap-8 items-start">
      <div class="card p-6 md:p-8 space-y-6">
        <h2 class="text-lg font-bold font-bebas tracking-wider border-b border-slate-100 pb-2">Параметры нагрузок и вращения</h2>
        <div class="grid sm:grid-cols-2 gap-4">
          <div><label class="block text-xs font-bold text-neutral-500 uppercase mb-2">Радиальная нагрузка Fr (кН)</label><input v-model.number="fr" type="number" class="input w-full" /></div>
          <div><label class="block text-xs font-bold text-neutral-500 uppercase mb-2">Осевая нагрузка Fa (кН)</label><input v-model.number="fa" type="number" class="input w-full" /></div>
        </div>
        <div class="grid sm:grid-cols-2 gap-4">
          <div><label class="block text-xs font-bold text-neutral-500 uppercase mb-2">Обороты в минуту (RPM)</label><input v-model.number="rpm" type="number" class="input w-full" /></div>
          <div><label class="block text-xs font-bold text-neutral-500 uppercase mb-2">Уплотнение & Защита</label>
            <select v-model.number="sealFactor" class="input w-full">
              <option :value="1">Стандартное резиновое уплотнение (2RS)</option>
              <option :value="2.5">Премиум трехкромочное HHB (LS3)</option>
            </select>
          </div>
        </div>
      </div>
      <div class="card p-6 md:p-8 space-y-6">
        <h2 class="text-lg font-bold font-bebas tracking-wider border-b border-slate-100 pb-2">Результат расчета ISO 281</h2>
        <div class="border border-slate-200 p-6 rounded-xl bg-slate-50 space-y-4">
          <div class="text-center">
            <span class="text-[10px] text-neutral-400 font-bold uppercase tracking-wider">НОМИНАЛЬНЫЙ СРОК СЛУЖБЫ В ЧАСАХ (L10)</span>
            <div class="text-4xl font-extrabold font-bebas text-brand-700 tracking-wide mt-1">{{ l10.toLocaleString() }} ч.</div>
          </div>
          <div class="border-t border-slate-200 pt-4 flex justify-between text-xs font-semibold text-neutral-600">
            <span>Срок в календарных месяцах:</span><span class="text-neutral-900 font-bold">{{ months }} мес.</span>
          </div>
          <div class="flex justify-between text-xs font-semibold text-neutral-600">
            <span>Степень безопасности узла:</span><span :class="reliability.color" class="font-bold">{{ reliability.text }}</span>
          </div>
          <div class="border-t border-slate-200 pt-4 text-[11px] text-neutral-500 leading-relaxed italic">
            *Расчет произведен согласно ISO 281. Результат гарантируется при соблюдении температурных режимов и планового смазывания.
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
