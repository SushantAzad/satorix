import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User } from '../api/types'

interface AuthState {
  user: User | null; token: string | null
  _hasHydrated: boolean
  setAuth: (user: User, token: string) => void
  clearAuth: () => void
  isAuthenticated: () => boolean
  setHasHydrated: (v: boolean) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null, token: null,
      _hasHydrated: false,
      setAuth: (user, token) => { localStorage.setItem('satorix_token', token); set({ user, token }) },
      clearAuth: () => { localStorage.removeItem('satorix_token'); set({ user: null, token: null }) },
      isAuthenticated: () => get().token !== null,
      setHasHydrated: (v) => set({ _hasHydrated: v }),
    }),
    {
      name: 'satorix-auth',
      partialize: (s) => ({ user: s.user, token: s.token }),
      onRehydrateStorage: () => (state) => { state?.setHasHydrated(true) },
    }
  )
)
