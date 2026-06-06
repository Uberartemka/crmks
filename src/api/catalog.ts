import { api } from './client'
import type { Sku, SkuInput } from '@/types/catalog'

export const catalogApi = {
  list: (params?: { category?: string; search?: string; d_min?: number; d_max?: number }) =>
    api.get<Sku[]>('/api/catalog/skus', { params }),
  create: (data: SkuInput) =>
    api.post<{ status: string; sku_id: number }>('/api/catalog/skus', data),
}
