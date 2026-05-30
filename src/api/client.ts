import axios, { AxiosError, type InternalAxiosRequestConfig, type AxiosResponse } from 'axios'

const TOKEN_KEY = 'ksvrn_token'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000,
})

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r: AxiosResponse) => r,
  (err: AxiosError) => {
    // Do NOT force logout/redirect here.
    // The auth store and router guard handle 401 gracefully.
    // This prevents infinite logout loops when the backend is down or returns 401 on /api/auth/me.
    return Promise.reject(err)
  },
)
