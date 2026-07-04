import { create } from 'zustand'
import type { UserInfo, AuthResponse } from '../api/client'
import { api, setToken, clearToken } from '../api/client'

interface AuthState {
  user: UserInfo | null
  isAuthenticated: boolean
  authLoading: boolean
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string) => Promise<void>
  logout: () => void
  checkAuth: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  authLoading: true,

  login: async (username: string, password: string) => {
    const res: AuthResponse = await api.login(username, password)
    setToken(res.token)
    set({ user: res.user, isAuthenticated: true })
  },

  register: async (username: string, password: string) => {
    const res: AuthResponse = await api.register(username, password)
    setToken(res.token)
    set({ user: res.user, isAuthenticated: true })
  },

  logout: () => {
    clearToken()
    set({ user: null, isAuthenticated: false })
  },

  checkAuth: async () => {
    const token = localStorage.getItem('reelmind_token')
    if (!token) {
      set({ authLoading: false, isAuthenticated: false })
      return
    }
    try {
      const user = await api.me()
      set({ user, isAuthenticated: true, authLoading: false })
    } catch {
      clearToken()
      set({ user: null, isAuthenticated: false, authLoading: false })
    }
  },
}))
