import { create } from 'zustand'
import type { Asset, ScanJobInfo } from '../api/client'
import { api } from '../api/client'
import { useStore as useAppStore } from './app'
import { useLibraryStore } from './library'
import i18n from '../i18n/config'

interface AssetState {
  assets: Asset[]
  archivedAssets: Asset[]
  processedAssets: Asset[]
  processedAssetsTotal: number
  processedAssetsLoading: boolean
  showArchived: boolean
  showFavorites: boolean
  currentAsset: Asset | null
  loadingAssets: boolean
  currentPage: number
  totalCount: number
  pageSize: number
  loadAssets: (libraryId?: string, sortBy?: string, sortOrder?: string, page?: number, pageSize?: number, isFavorite?: boolean) => Promise<void>
  loadArchivedAssets: (libraryId?: string) => Promise<void>
  toggleShowArchived: () => void
  toggleShowFavorites: () => void
  loadAsset: (id: string) => Promise<void>
  setCurrentAsset: (asset: Asset | null) => void
  loadProcessedAssets: () => Promise<void>
  selectedAssetIds: string[]
  toggleAssetSelection: (id: string) => void
  selectAllAssets: (ids: string[]) => void
  clearSelection: () => void
  libraryScanStatus: Record<string, { pending_import: number; recent_jobs: ScanJobInfo[] }>
  setLibraryScanStatus: (libId: string, status: { pending_import: number; recent_jobs: ScanJobInfo[] }) => void
  clearLibraryScanStatus: (libId: string) => void
  clearAllLibraryScanStatus: () => void
}

export const useAssetStore = create<AssetState>((set, get) => ({
  assets: [],
  archivedAssets: [],
  processedAssets: [],
  processedAssetsTotal: 0,
  processedAssetsLoading: false,
  showArchived: false,
  showFavorites: false,
  currentAsset: null,
  loadingAssets: false,
  currentPage: 1,
  totalCount: 0,
  pageSize: 5000,

  loadProcessedAssets: async () => {
    set({ processedAssetsLoading: true })
    try {
      const res = await api.getProcessedAssets()
      set({ processedAssets: res.items, processedAssetsTotal: res.total })
    } catch (e) {
      console.error('Failed to load processed assets:', e)
      useAppStore.setState({ error: i18n.t('store.loadFailed') + ': ' + ((e as any).message || e) })
    } finally {
      set({ processedAssetsLoading: false })
    }
  },

  loadAssets: async (libraryId?: string, sortBy = 'media_date', sortOrder = 'asc', page?: number, pageSize?: number, isFavorite?: boolean) => {
    set({ loadingAssets: true })
    const p = page ?? get().currentPage
    const ps = pageSize ?? get().pageSize
    try {
      const libId = libraryId || useLibraryStore.getState().selectedLibraryId || undefined
      const result = await api.listAssets(libId, p, ps, sortBy, sortOrder, isFavorite)
      const byId: Record<string, Asset> = {}
      for (const item of result.items) byId[item.id] = item
      useAppStore.setState({ assetsById: byId })
      set({ assets: result.items, totalCount: result.total, currentPage: p })
    } catch (e) {
      console.error('Failed to load assets:', e)
      useAppStore.setState({ error: i18n.t('store.loadFailed') + ': ' + ((e as any).message || e) })
    } finally {
      set({ loadingAssets: false })
    }
  },

  loadArchivedAssets: async (libraryId?: string) => {
    set({ loadingAssets: true })
    try {
      const libId = libraryId || useLibraryStore.getState().selectedLibraryId || undefined
      const result = await api.listArchivedAssets(libId)
      const byId: Record<string, Asset> = {}
      for (const item of result.items) byId[item.id] = item
      const appState = useAppStore.getState()
      useAppStore.setState({ assetsById: { ...appState.assetsById, ...byId } })
      set({ archivedAssets: result.items })
    } catch (e) {
      console.error('Failed to load archived assets:', e)
      useAppStore.setState({ error: i18n.t('store.loadFailed') + ': ' + ((e as any).message || e) })
    } finally {
      set({ loadingAssets: false })
    }
  },

  toggleShowArchived: () => {
    const { showArchived } = get()
    set({ showArchived: !showArchived })
    if (!showArchived) {
      get().loadArchivedAssets()
    } else {
      set({ archivedAssets: [] })
    }
  },

  toggleShowFavorites: () => {
    const { showFavorites } = get()
    const selectedLibraryId = useLibraryStore.getState().selectedLibraryId
    const next = !showFavorites
    set({ showFavorites: next })
    get().loadAssets(selectedLibraryId || undefined, undefined, undefined, 1, undefined, next || undefined)
  },

  loadAsset: async (id: string) => {
    try {
      const asset = await api.getAsset(id)
      set({ currentAsset: asset })
    } catch (e) {
      console.error('Failed to load asset:', e)
      useAppStore.setState({ error: i18n.t('store.loadFailed') + ': ' + ((e as any).message || e) })
    }
  },

  setCurrentAsset: (asset) => set({ currentAsset: asset }),

  selectedAssetIds: [],
  toggleAssetSelection: (id: string) => {
    const { selectedAssetIds } = get()
    if (selectedAssetIds.includes(id)) {
      set({ selectedAssetIds: selectedAssetIds.filter((i) => i !== id) })
    } else {
      set({ selectedAssetIds: [...selectedAssetIds, id] })
    }
  },
  selectAllAssets: (ids: string[]) => set({ selectedAssetIds: ids }),
  clearSelection: () => set({ selectedAssetIds: [] }),

  libraryScanStatus: {},
  setLibraryScanStatus: (libId, status) => {
    set((s) => ({ libraryScanStatus: { ...s.libraryScanStatus, [libId]: status } }))
  },
  clearLibraryScanStatus: (libId) => {
    set((s) => {
      const next = { ...s.libraryScanStatus }
      delete next[libId]
      return { libraryScanStatus: next }
    })
  },
  clearAllLibraryScanStatus: () => {
    set({ libraryScanStatus: {} })
  },
}))