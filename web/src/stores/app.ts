import { create } from 'zustand'
import type { Asset } from '../api/client'

interface AppState {
 error: string | null
 clearError: () => void
 setError: (msg: string) => void
  assetsById: Record<string, Asset>
}

export const useStore = create<AppState>((set) => ({
  error: null,
  clearError: () => set({ error: null }),
  setError: (msg) => set({ error: msg }),
  assetsById: {},
}))

