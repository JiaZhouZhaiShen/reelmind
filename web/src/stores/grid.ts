import { create } from 'zustand'
import type { Asset, TagInfo } from '../api/client'
import { api } from '../api/client'
import * as assetsApi from '../api/assets'
import { useStore as useAppStore } from './app'
import { useLibraryStore } from './library'
import i18n from '../i18n/config'

interface GridState {
  gridAssets: Asset[]
  gridFiltered: Asset[]
  gridTotal: number
  gridHasMore: boolean
  gridPage: number
  gridInitLoading: boolean
  gridMoreLoading: boolean
  gridError: string | null
  gridTimelineYears: Array<{year: number; count: number}>
  gridFilterTags: string[]
  gridAvailTags: TagInfo[]
  gridSortOrder: 'asc' | 'desc'
  gridOrientationFilter: 'all' | 'landscape' | 'portrait' | 'square'
  gridAiFilter: 'all' | 'scene' | 'yolo' | 'ocr' | 'clip' | 'transcript' | 'diarization'
  gridFiltering: boolean
  gridPAGE_SIZE: number
  fetchGridAssets: (libraryId: string | null | undefined, sortOrder: string, showFavorites: boolean, aiFilter: string, orientationFilter: string, p: number, append: boolean) => Promise<void>
  toggleGridTag: (name: string) => void
  toggleGridSort: () => void
  setGridOrientationFilter: (o: 'all' | 'landscape' | 'portrait' | 'square') => void
  setGridAiFilter: (f: 'all' | 'scene' | 'yolo' | 'ocr' | 'clip' | 'transcript' | 'diarization') => void
  loadGridTags: () => Promise<void>
 loadGridTimelineYears: () => Promise<void>
 resetGridState: () => void
}

export const useGridStore = create<GridState>((set, get) => ({
  gridAssets: [],
  gridFiltered: [],
  gridTotal: 0,
  gridHasMore: true,
  gridPage: 1,
  gridInitLoading: true,
  gridMoreLoading: false,
  gridError: null,
  gridTimelineYears: [],
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
      const appState = useAppStore.getState()
      if (append) {
        set((s) => ({ gridAssets: [...s.gridAssets, ...items] }))
        useAppStore.setState({ assetsById: { ...appState.assetsById, ...byId } })
      } else {
        set({ gridAssets: items })
        useAppStore.setState({ assetsById: byId })
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

  loadGridTimelineYears: async () => {
    try {
      const id = useLibraryStore.getState().selectedLibraryId
      const years = await api.timelineYears(id || undefined)
      set({ gridTimelineYears: years })
    } catch {
      set({ gridError: i18n.t('store.yearLoadFailed') })
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
      gridTimelineYears: [],
      gridFilterTags: [],
     gridFiltering: false,
   })
   useAppStore.setState({ assetsById: {} })
},
}))