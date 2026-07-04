import { create } from 'zustand'
import type { Library, SystemStats } from '../api/client'
import { api } from '../api/client'
import { useStore as useAppStore } from './app'
import i18n from '../i18n/config'

interface LibraryState {
  libraries: Library[]
  selectedLibraryId: string | null
  stats: SystemStats | null
  loadLibraries: () => Promise<void>
  selectLibrary: (id: string | null) => void
  loadStats: () => Promise<void>
}

export const useLibraryStore = create<LibraryState>((set) => ({
  libraries: [],
  selectedLibraryId: null,
  stats: null,

  loadLibraries: async () => {
    try {
      const libraries = await api.listLibraries()
      set({ libraries })
    } catch (e) {
      console.error('Failed to load libraries:', e)
      useAppStore.setState({ error: i18n.t('store.loadFailed') + ': ' + ((e as any).message || e) })
    }
  },
  selectLibrary: (id) => set({ selectedLibraryId: id }),

  loadStats: async () => {
    try {
      const stats = await api.stats()
      set({ stats })
    } catch (e) {
      console.error('Failed to load stats:', e)
      useAppStore.setState({ error: i18n.t('store.loadFailed') + ': ' + ((e as any).message || e) })
    }
  },
}))