import { create } from 'zustand'
import type { Asset, Library, SearchResult, SystemStats, SystemStatus, UserInfo, AuthResponse, AdminDashboard } from '../api/client'
import type { TagInfo } from '../api/client'
import { api, setToken, clearToken } from '../api/client'
import * as assetsApi from '../api/assets'
import { toPseudoAsset } from '../utils/search'

interface AppState {
  // Auth
  user: UserInfo | null
  isAuthenticated: boolean
  authLoading: boolean
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string) => Promise<void>
  logout: () => void
  checkAuth: () => Promise<void>

  // Libraries
  libraries: Library[]
  selectedLibraryId: string | null
  loadLibraries: () => Promise<void>
  selectLibrary: (id: string | null) => void

  // Assets
  assets: Asset[]
  archivedAssets: Asset[]
  // AssetGrid business data (infinite scroll)
  gridAssets: Asset[]
  gridFiltered: Asset[]
  gridTotal: number
  gridHasMore: boolean
  gridPage: number
  gridInitLoading: boolean
  gridMoreLoading: boolean
  gridError: string | null
  gridFilterTags: string[]
  gridAvailTags: TagInfo[]
  gridSortOrder: 'asc' | 'desc'
  gridOrientationFilter: 'all' | 'landscape' | 'portrait' | 'square'
  gridAiFilter: 'all' | 'scene' | 'yolo' | 'ocr' | 'clip' | 'transcript' | 'diarization'
  gridFiltering: boolean
  gridPAGE_SIZE: number
  // Grid actions
  fetchGridAssets: (libraryId: string | null | undefined, sortOrder: string, showFavorites: boolean, aiFilter: string, orientationFilter: string, p: number, append: boolean) => Promise<void>
  toggleGridTag: (name: string) => void
  toggleGridSort: () => void
  setGridOrientationFilter: (o: 'all' | 'landscape' | 'portrait' | 'square') => void
  setGridAiFilter: (f: 'all' | 'scene' | 'yolo' | 'ocr' | 'clip' | 'transcript' | 'diarization') => void
  loadGridTags: () => Promise<void>
  resetGridState: () => void

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

  // Search
  searchResults: SearchResult[]
  searchTotal: number
  searchQuery: string
  searching: boolean
  searchPage: number
  searchHasMore: boolean
  searchInitLoading: boolean
  searchMoreLoading: boolean
 searchError: string | null
  setSearchQuery: (q: string) => void
  
  searchLoadResults: (page: number, append: boolean) => Promise<void>

  
  stats: SystemStats | null
  loadStats: () => Promise<void>

 // Batch selection
 selectedAssetIds: string[]
 toggleAssetSelection: (id: string) => void
 selectAllAssets: (ids: string[]) => void
 clearSelection: () => void

 // Error state
 error: string | null
 clearError: () => void

  // Asset by ID map (for VideoCard store reads — Iron Rule ⑥)
  assetsById: Record<string, Asset>

  // Admin dashboard
  adminDashboard: AdminDashboard | null
  systemStatus: SystemStatus | null
  sysStatusLoading: boolean
  dashboardError: string | null
  loadAdminDashboard: () => Promise<void>
  loadSystemStatus: () => Promise<void>
}

export const useStore = create<AppState>((set, get) => ({
  // ── Auth ──
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

  // Libraries
  libraries: [],
  selectedLibraryId: null,
  loadLibraries: async () => {
    try {
      const libraries = await api.listLibraries()
      set({ libraries })
    } catch (e) {
      console.error('Failed to load libraries:', e)
      set({ error: '无法加载库列表: ' + ((e as any).message || e) })
    }
  },
  selectLibrary: (id) => set({ selectedLibraryId: id }),

  // Assets
  assets: [],
  archivedAssets: [],
  // Grid state
  gridAssets: [],
  gridFiltered: [],
  gridTotal: 0,
  gridHasMore: true,
  gridPage: 1,
  gridInitLoading: true,
  gridMoreLoading: false,
  gridError: null,
  gridFilterTags: [],
  gridAvailTags: [],
  gridSortOrder: 'desc',
  gridOrientationFilter: 'all' as const,
  gridAiFilter: 'all' as const,
  gridFiltering: false,
  gridPAGE_SIZE: 200,

  fetchGridAssets: async (libraryId, sortOrder, showFavorites, aiFilter, orientationFilter, p, append) => {
    const PAGE_SIZE = get().gridPAGE_SIZE
    if (append) set({ gridMoreLoading: true })
    else set({ gridInitLoading: true })
    set({ gridError: null })
    try {
      const r = await assetsApi.listAssets(
        libraryId || undefined,
        p,
        PAGE_SIZE,
        'media_date',
        sortOrder,
        showFavorites || undefined,
        aiFilter,
        orientationFilter,
      )
     const items = r.items || []
      const byId: Record<string, Asset> = {}
      for (const item of items) byId[item.id] = item
      if (append) {
        set((s) => ({ gridAssets: [...s.gridAssets, ...items], assetsById: { ...s.assetsById, ...byId } }))
      } else {
        set({ gridAssets: items, assetsById: byId })
      }
      set({
        gridTotal: r.total,
        gridHasMore: items.length >= PAGE_SIZE && p * PAGE_SIZE < r.total,
        gridPage: p,
      })
    } catch (e: any) {
      set({ gridError: e?.message || 'Load failed' })
    } finally {
      set({ gridInitLoading: false, gridMoreLoading: false })
    }
  },

  toggleGridTag: (name) => {
    set((s) => ({
      gridFilterTags: s.gridFilterTags.includes(name)
        ? s.gridFilterTags.filter((x) => x !== name)
        : [...s.gridFilterTags, name],
    }))
  },

  toggleGridSort: () => {
    set((s) => ({
      gridSortOrder: s.gridSortOrder === 'asc' ? 'desc' : 'asc',
    }))
  },

  setGridOrientationFilter: (o) => set({ gridOrientationFilter: o }),
  setGridAiFilter: (f) => set({ gridAiFilter: f }),

  loadGridTags: async () => {
    try {
      const tags = await api.listTags()
      set({ gridAvailTags: tags })
   } catch {
      set({ gridAvailTags: [] })
   }
  },

  resetGridState: () => {
    set({
      gridAssets: [],
      gridFiltered: [],
      gridTotal: 0,
      gridHasMore: true,
      gridPage: 1,
      gridInitLoading: true,
      gridMoreLoading: false,
      gridError: null,
      gridFilterTags: [],
      // gridSortOrder, gridOrientationFilter, gridAiFilter kept — user prefs, not transient state
     gridFiltering: false,
   })
    set({ assetsById: {} })
 },

 showArchived: false,
 showFavorites: false,
 currentAsset: null,
 loadingAssets: false,
 currentPage: 1,
 totalCount: 0,
 pageSize: 5000,
  assetsById: {},
  loadAssets: async (libraryId?: string, sortBy = 'media_date', sortOrder = 'asc', page?: number, pageSize?: number, isFavorite?: boolean) => {
    set({ loadingAssets: true })
    const p = page ?? get().currentPage
    const ps = pageSize ?? get().pageSize
    try {
     const result = await api.listAssets(libraryId || get().selectedLibraryId || undefined, p, ps, sortBy, sortOrder, isFavorite)
      const byId: Record<string, Asset> = {}
      for (const item of result.items) byId[item.id] = item
      set({ assets: result.items, totalCount: result.total, currentPage: p, assetsById: byId })
    } catch (e) {
      console.error('Failed to load assets:', e)
      set({ error: '无法加载资产列表: ' + ((e as any).message || e) })
    } finally {
      set({ loadingAssets: false })
    }
  },
  loadArchivedAssets: async (libraryId?: string) => {
    set({ loadingAssets: true })
    try {
     const result = await api.listArchivedAssets(libraryId || get().selectedLibraryId || undefined)
      const byId: Record<string, Asset> = {}
      for (const item of result.items) byId[item.id] = item
      set((s) => ({
        archivedAssets: result.items,
        assetsById: { ...s.assetsById, ...byId },
      }))
    } catch (e) {
      console.error('Failed to load archived assets:', e)
      set({ error: '无法加载归档资产: ' + ((e as any).message || e) })
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
    const { showFavorites, selectedLibraryId } = get()
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
      set({ error: '无法加载资产详情: ' + ((e as any).message || e) })
    }
  },
  setCurrentAsset: (asset) => set({ currentAsset: asset }),

  // Search
  searchResults: [],
  searchTotal: 0,
  searchQuery: '',
  searching: false,
  searchPage: 1,
  searchHasMore: true,
  searchInitLoading: false,
  searchMoreLoading: false,
 searchError: null,
  setSearchQuery: (q) => set({ searchQuery: q }),
  performSearch: async (extraParams?: Record<string, unknown>) => {
    const { searchQuery, selectedLibraryId } = get()
    if (!searchQuery && !extraParams?.tags) return
    set({ searching: true })
    try {
      const result = await api.smartSearch({
        q: searchQuery,
        library_id: selectedLibraryId || undefined,
        ...extraParams,
      })
      set({ searchResults: result.results, searchTotal: result.total })
    } catch (e) {
      console.error('Search failed:', e)
     set({ error: '搜索失败: ' + ((e as any).message || e) })
    } finally {
     set({ searching: false })
   }
  },
  searchLoadResults: async (page, append) => {
    const { searchQuery } = get()
    if (!searchQuery) return
    set({ searchError: null })
    if (append) set({ searchMoreLoading: true })
    else set({ searchInitLoading: true })
    try {
      const result = await api.smartSearch({
        q: searchQuery,
        page,
        page_size: 200,
      })
      // Write search results to assetsById so VideoCard can read them
      const searchById: Record<string, Asset> = {}
      for (const r of result.results) {
        searchById[r.id] = toPseudoAsset(r) as unknown as Asset
      }
      if (append) {
        set({ searchResults: [...get().searchResults, ...result.results], searchTotal: result.total, assetsById: { ...get().assetsById, ...searchById } })
      } else {
        set({ searchResults: result.results, searchTotal: result.total, assetsById: { ...get().assetsById, ...searchById } })
      }
      set({ searchPage: page, searchHasMore: page * 200 < result.total })
    } catch (e: any) {
      console.error('Search failed:', e)
      set({ searchError: e?.message || '搜索失败，请重试' })
    } finally {
      set({ searchInitLoading: false, searchMoreLoading: false })
    }
  },

  // Stats
  stats: null,
  loadStats: async () => {
    try {
      const stats = await api.stats()
      set({ stats })
    } catch (e) {
      console.error('Failed to load stats:', e)
      set({ error: '无法加载统计数据: ' + ((e as any).message || e) })
    }
  },

 // Batch selection
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

  // Error state
  error: null,
  clearError: () => set({ error: null }),

  // Admin dashboard
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
      set({ dashboardError: '无法加载管理员面板: ' + ((e as any).message || e) })
    }
  },
  loadSystemStatus: async () => {
    // only show loading on first load, not on subsequent polls (to prevent flickering)
    const isFirstLoad = get().systemStatus === null
    if (isFirstLoad) {
      set({ sysStatusLoading: true, dashboardError: null })
    }
    try {
      const systemStatus = await api.getSystemStatus()
      set({ systemStatus, sysStatusLoading: false, dashboardError: null })
    } catch (e: any) {
      set({ dashboardError: e?.message || "连接服务器失败，请检查容器状态", sysStatusLoading: false })
    }
  },
}))


