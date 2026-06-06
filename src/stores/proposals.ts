import { defineStore } from 'pinia'
import { ref } from 'vue'
import { proposalsApi } from '@/api/proposals'
import type { Proposal, ProposalInput, ProposalItemInput, DiscountInput, SendEmailInput } from '@/types/proposal'

export const useProposalsStore = defineStore('proposals', () => {
  const list = ref<Proposal[]>([])
  const current = ref<Proposal | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load() {
    loading.value = true
    try {
      const { data } = await proposalsApi.list()
      list.value = data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      loading.value = false
    }
  }

  async function get(id: number) {
    loading.value = true
    try {
      const { data } = await proposalsApi.get(id)
      current.value = data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      loading.value = false
    }
  }

  async function create(data: ProposalInput) {
    const res = await proposalsApi.create(data)
    await load()
    return res.data
  }

  async function setDiscount(id: number, data: DiscountInput) {
    await proposalsApi.setDiscount(id, data)
    await get(id)
  }

  async function send(id: number, data?: SendEmailInput) {
    await proposalsApi.send(id, data)
    await load()
  }

  async function addItem(proposalId: number, data: ProposalItemInput) {
    await proposalsApi.addItem(proposalId, data)
    await get(proposalId)
  }

  async function updateItem(proposalId: number, itemId: number, data: ProposalItemInput) {
    await proposalsApi.updateItem(proposalId, itemId, data)
    await get(proposalId)
  }

  async function removeItem(proposalId: number, itemId: number) {
    await proposalsApi.removeItem(proposalId, itemId)
    await get(proposalId)
  }

  async function remove(id: number) {
    await proposalsApi.delete(id)
    await load()
  }

  return { list, current, loading, error, load, get, create, setDiscount, send, addItem, updateItem, removeItem, remove }
})
