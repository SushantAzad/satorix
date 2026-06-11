import { apiClient } from '../api/client'
import { useAuthStore } from '../store/authStore'

export function useAuth() {
  const { user, token, setAuth, clearAuth, isAuthenticated } = useAuthStore()

  const login = async (email: string, password: string) => {
    const res = await apiClient.post('/api/v1/auth/login', { email, password })
    const { access_token, user: u } = res.data
    setAuth(u, access_token)
    return u
  }

  const logout = () => { clearAuth(); window.location.href = '/login' }
  return { user, token, login, logout, isAuthenticated: isAuthenticated() }
}
