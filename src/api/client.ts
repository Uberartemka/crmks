import axios, { AxiosError, type InternalAxiosRequestConfig, type AxiosResponse } from 'axios'

const TOKEN_KEY = 'ksvrn_token'

const API_BASE_URL =
  window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
    : window.location.origin

export const api = axios.create({
  baseURL: API_BASE_URL,
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
