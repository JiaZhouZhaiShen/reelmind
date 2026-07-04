import { create } from 'zustand'
import type { AdminDashboard, SystemStatus } from '../api/client'
import { api } from '../api/client'
import i18n from '../i18n/config'

interface AdminState {
  adminDashboard: AdminDashboard | null
  systemStatus: SystemStatus | null
  sysStatusLoading: boolean
  dashboardError: string | null
  loadAdminDashboard: () => Promise<void>
  loadSystemStatus: () => Promise<void>
}

export const useAdminStore = create<AdminState>((set, get) => ({
  adminDashboard: null,
  systemStatus: null,
  sysStatusLoading: false,
  dashboardError: null,

  loadAdminDashboard: async () => {
    try {
      const adminDashboard = await api.getAdminDashboard()
      set({ adminDashboard, dashboardError: null })
    } catch (e) {
      console.error('Failed to load admin dashboard:', e)
      set({ dashboardError: i18n.t('store.loadFailed') + ': ' + ((e as any).message || e) })
    }
  },

  loadSystemStatus: async () => {
    const isFirstLoad = get().systemStatus === null
    if (isFirstLoad) {
      set({ sysStatusLoading: true, dashboardError: null })
    }
    try {
      const systemStatus = await api.getSystemStatus()
      set({ systemStatus, sysStatusLoading: false, dashboardError: null })
    } catch (e: any) {
      set({ dashboardError: e?.message || i18n.t('store.connFailed'), sysStatusLoading: false })
    }
  },
}))