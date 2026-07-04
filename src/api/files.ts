import { api } from './client'
import type { StoredFile } from '@/types/file'

export const filesApi = {
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    // axios auto-sets multipart/form-data with the correct boundary when the
    // body is FormData. Do NOT set Content-Type manually — it would omit the
    // boundary and the server couldn't parse the form.
    return api.post<StoredFile>('/api/files', form)
  },
  url: (id: number) => `/api/files/${id}`,
  thumbnailUrl: (id: number) => `/api/files/${id}/thumbnail`,
}
