import axios, { AxiosError, type InternalAxiosRequestConfig, type AxiosResponse } from 'axios'

const TOKEN_KEY = 'ksvrn_token'

// Use a SAME-ORIGIN (relative) base URL in production so the SPA talks to the
// FastAPI backend that serves it (via nginx /api/ proxy on the CRM server).
// In Vite dev, the `server.proxy['/api']` rule in vite.config forwards /api/*
// to localhost:8000, so a relative base works there too. This avoids hardcoding
// any host and works unchanged across localhost / IP / future domain.
const API_BASE_URL =
  window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? import.meta.env.VITE_API_BASE_URL || ''
    : ''

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
