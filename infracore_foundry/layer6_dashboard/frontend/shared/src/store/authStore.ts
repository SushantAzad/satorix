import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User } from '../api/types'

interface AuthState {
  user: User | null; token: string | null
  setAuth: (user: User, token: string) => void
  clearAuth: () => void
  isAuthenticated: () => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null, token: null,
      setAuth: (user, token) => { localStorage.setItem('satorix_token', token); set({ user, token }) },
      clearAuth: () => { localStorage.removeItem('satorix_token'); set({ user: null, token: null }) },
      isAuthenticated: () => get().token !== null,
    }),
    { name: 'satorix-auth', partialize: (s) => ({ user: s.user, token: s.token }) }
  )
)
