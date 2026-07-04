import { create } from 'zustand'
import { api } from '../api/client'
import type { AdminJob } from '../api/client'
import i18n from '../i18n/config'

interface AdminJobsState {
  jobs: AdminJob[]
  statusFilter: string | undefined
  loading: boolean
  actionLoading: string | null
  searchText: string
  error: string | null
  cleaningUp: boolean
  cleanupResult: { deleted_old: number; marked_stale: number } | null
  loadJobs: () => Promise<void>
  retryJob: (jobId: string) => Promise<void>
  cancelJob: (jobId: string) => Promise<void>
  cleanupJobs: () => Promise<void>
  setStatusFilter: (filter: string | undefined) => void
  setSearchText: (text: string) => void
  clearError: () => void
  setCleanupResult: (result: { deleted_old: number; marked_stale: number } | null) => void
}

export const useAdminJobsStore = create<AdminJobsState>((set, get) => ({
  jobs: [],
  statusFilter: undefined,
  loading: false,
  actionLoading: null,
  searchText: '',
  error: null,
  cleaningUp: false,
  cleanupResult: null,

  loadJobs: async () => {
    set({ loading: true, error: null })
    try {
      const { statusFilter } = get()
      const data = await api.listAdminJobs(statusFilter, 100)
      set({ jobs: data, loading: false })
    } catch (e) {
      set({
        loading: false,
        error: e instanceof Error ? e.message : i18n.t('store.loadFailed'),
      })
    }
  },

  retryJob: async (jobId: string) => {
    set({ actionLoading: jobId, error: null })
    try {
      await api.retryAdminJob(jobId)
      await get().loadJobs()
    } catch (e) {
      set({ error: e instanceof Error ? e.message : i18n.t('store.retryFailed') })
    } finally {
      set({ actionLoading: null })
    }
  },

  cancelJob: async (jobId: string) => {
    set({ actionLoading: jobId, error: null })
    try {
      await api.cancelAdminJob(jobId)
      await get().loadJobs()
    } catch (e) {
      set({ error: e instanceof Error ? e.message : i18n.t('store.cancelFailed') })
    } finally {
      set({ actionLoading: null })
    }
  },

  cleanupJobs: async () => {
    set({ cleaningUp: true, error: null, cleanupResult: null })
    try {
      const result = await api.cleanupAdminJobs()
      set({ cleaningUp: false, cleanupResult: result })
      await get().loadJobs()
    } catch (e) {
      set({
        cleaningUp: false,
        error: e instanceof Error ? e.message : i18n.t('store.cleanupFailed'),
      })
    }
  },

  setStatusFilter: (filter) => {
    set({ statusFilter: filter })
  },

  setSearchText: (text) => {
    set({ searchText: text })
  },

  clearError: () => {
    set({ error: null })
  },

  setCleanupResult: (result) => {
    set({ cleanupResult: result })
  },
}))