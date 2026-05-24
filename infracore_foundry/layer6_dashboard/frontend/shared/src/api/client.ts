import axios from 'axios'
import { useAuthStore } from '../store/authStore'

const API_URL = typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_API_URL || 'http://localhost:8006'

export const apiClient = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
})

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('satorix_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let _redirectingToLogin = false

apiClient.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401 && !_redirectingToLogin) {
      _redirectingToLogin = true
      useAuthStore.getState().clearAuth()
      if (typeof window !== 'undefined') {
        const returnTo = window.location.pathname + window.location.search
        window.location.href = returnTo === '/login' ? '/login' : `/login?from=${encodeURIComponent(returnTo)}`
      }
    }
    return Promise.reject(error)
  }
)
