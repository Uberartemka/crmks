import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { plansApi } from '@/api/plans'
import type { EmployeePlan, PlanCreate } from '@/types/plan'

export const usePlansStore = defineStore('plans', () => {
  const list = ref<EmployeePlan[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load() {
    loading.value = true
    error.value = null
    try {
      const { data } = await plansApi.list()
      list.value = data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      loading.value = false
    }
  }

  async function create(data: PlanCreate) {
    const res = await plansApi.create(data)
    await load()
    return res.data
  }

  const currentMonthPlan = computed(() => {
    const now = new Date()
    return list.value.find(p => p.month === now.getMonth() + 1 && p.year === now.getFullYear())
  })

  return { list, loading, error, load, create, currentMonthPlan }
})
