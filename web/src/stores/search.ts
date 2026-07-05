import { create } from 'zustand'
import type { SearchResult } from '../api/client'
import { api } from '../api/client'
import { toPseudoAsset } from '../utils/search'
import { useStore as useAppStore } from './app'
import { useLibraryStore } from './library'
import i18n from '../i18n/config'

const SEARCH_SAVE_KEY = 'reelmind_search_state'

function getInitialSearchState() {
  try {
    const saved = sessionStorage.getItem(SEARCH_SAVE_KEY)
    if (!saved) return {}
    const p = JSON.parse(saved)
    return {
      searchQuery: p.q || '',
      searchDurationMin: p.minDur != null ? p.minDur : undefined,
      searchDurationMax: p.maxDur != null ? p.maxDur : undefined,
      searchFileSizeMin: p.minSize != null ? p.minSize : undefined,
      searchFileSizeMax: p.maxSize != null ? p.maxSize : undefined,
    }
  } catch {}
  return {}
}

const _init = getInitialSearchState()

interface SearchState {
  searchResults: SearchResult[]
  searchTotal: number
  sourceTotals: Record<string, number>
  searchQuery: string
  searching: boolean
  searchPage: number
  searchHasMore: boolean
  searchInitLoading: boolean
  searchMoreLoading: boolean
  searchError: string | null
  setSearchQuery: (q: string) => void
  searchTriggerKey: number
  triggerSearch: () => void

  searchDurationMin: number | undefined
  searchDurationMax: number | undefined
  searchFileSizeMin: number | undefined
  searchFileSizeMax: number | undefined
  searchSourceFilter: string
  searchOrientationFilter: string
  setSearchDurationFilter: (min: number | undefined, max: number | undefined) => void
 setSearchFileSizeFilter: (min: number | undefined, max: number | undefined) => void
  resetSearch: () => void
  setSearchSourceFilter: (source: string) => void
  setSearchOrientationFilter: (o: string) => void

 searchLoadResults: (page: number, append: boolean) => Promise<void>
  performSearch: (extraParams?: Record<string, unknown>) => Promise<void>
  removeResults: (ids: string[]) => void
}

export const useSearchStore = create<SearchState>((set, get) => ({
  searchResults: [],
  searchTotal: 0,
  sourceTotals: {},
  searchQuery: _init.searchQuery ?? '',
  searching: false,
  searchPage: 1,
  searchHasMore: true,
  searchInitLoading: false,
  searchMoreLoading: false,
  searchError: null,
  setSearchQuery: (q) => set({ searchQuery: q }),
  searchTriggerKey: 0,
  triggerSearch: () => set((state) => ({ searchTriggerKey: state.searchTriggerKey + 1 })),

  searchDurationMin: _init.searchDurationMin,
  searchDurationMax: _init.searchDurationMax,
  searchFileSizeMin: _init.searchFileSizeMin,
  searchFileSizeMax: _init.searchFileSizeMax,
  searchSourceFilter: "all",
  searchOrientationFilter: "all",
  setSearchDurationFilter: (min, max) => set({ searchDurationMin: min, searchDurationMax: max }),
 setSearchFileSizeFilter: (min, max) => set({ searchFileSizeMin: min, searchFileSizeMax: max }),
 resetSearch: () => set({ searchResults: [], searchTotal: 0, sourceTotals: {}, searchSourceFilter: "all", searchOrientationFilter: "all", searchQuery: '', searchDurationMin: undefined, searchDurationMax: undefined, searchFileSizeMin: undefined, searchFileSizeMax: undefined, searchPage: 1, searchHasMore: true, searchInitLoading: false, searchMoreLoading: false, searchError: null }),
  setSearchSourceFilter: (source) => set({ searchSourceFilter: source }),
  setSearchOrientationFilter: (o) => set({ searchOrientationFilter: o }),
  removeResults: (ids: string[]) => {
    set((state) => {
      const remaining = state.searchResults.filter((r) => !ids.includes(r.id))
      return {
        searchResults: remaining,
        searchTotal: state.searchTotal - (state.searchResults.length - remaining.length),
      }
    })
  },

 performSearch: async (extraParams?: Record<string, unknown>) => {
    const { searchQuery } = get()
    const { selectedLibraryId } = useLibraryStore.getState()
    if (!searchQuery && !extraParams?.tags) return
    set({ searching: true })
    try {
      const result = await api.smartSearch({
        q: searchQuery,
        library_id: selectedLibraryId || undefined,
        ...extraParams,
      })
      set({ searchResults: result.results, searchTotal: result.total })
      set({ sourceTotals: (result as any).source_totals || {} })
    } catch (e) {
      console.error('Search failed:', e)
      useAppStore.setState({ error: i18n.t('store.searchFailed') + ': ' + ((e as any).message || e) })
    } finally {
      set({ searching: false })
    }
  },

  searchLoadResults: async (page, append) => {
    const { searchQuery, searchDurationMin, searchDurationMax, searchFileSizeMin, searchFileSizeMax, searchSourceFilter, searchOrientationFilter } = get()
    const { selectedLibraryId } = useLibraryStore.getState()
    if (!searchQuery && searchDurationMin === undefined && searchDurationMax === undefined && searchFileSizeMin === undefined && searchFileSizeMax === undefined && !selectedLibraryId) return
    set({ searchError: null })
    if (append) set({ searchMoreLoading: true })
    else set({ searchInitLoading: true })
    try {
      const result = await api.smartSearch({
        q: searchQuery,
        library_id: selectedLibraryId || undefined,
        page,
        page_size: 200,
        ...(searchDurationMin !== undefined ? { min_duration: searchDurationMin } : {}),
        ...(searchDurationMax !== undefined ? { max_duration: searchDurationMax } : {}),
        ...(searchFileSizeMin !== undefined ? { min_file_size: searchFileSizeMin } : {}),
                ...(searchFileSizeMax !== undefined ? { max_file_size: searchFileSizeMax } : {}),
        ...(searchSourceFilter !== "all" ? { source_engine: ({ "tag": "yolo" })[searchSourceFilter] || searchSourceFilter } : {}),
        ...(searchOrientationFilter !== "all" ? { orientation: searchOrientationFilter } : {}),
      })
      // Write search results to assetsById so VideoCard can read them (cross-store)
      const searchById: Record<string, any> = {}
      for (const r of result.results) {
        searchById[r.id] = toPseudoAsset(r)
      }
       const appState = useAppStore.getState()
     if (append) {
       const existing = get().searchResults
       const existingIds = new Set(existing.map(r => r.id))
       const dedupedNew = result.results.filter(r => !existingIds.has(r.id))
       const currentTotal = get().searchTotal
       set({ searchResults: [...existing, ...dedupedNew], searchTotal: Math.max(currentTotal, result.total) })
       if (get().searchSourceFilter === "all") set({ sourceTotals: (result as any).source_totals || {} })
       useAppStore.setState({ assetsById: { ...appState.assetsById, ...searchById } })
     } else {
       set({ searchResults: result.results, searchTotal: result.total })
       if (get().searchSourceFilter === "all") set({ sourceTotals: (result as any).source_totals || {} })
       useAppStore.setState({ assetsById: { ...appState.assetsById, ...searchById } })
     }
      const newTotal = get().searchTotal
      set({ searchPage: page, searchHasMore: get().searchResults.length < newTotal })
    } catch (e: any) {
      console.error('Search failed:', e)
      set({ searchError: e?.message || i18n.t('store.searchRetry') })
    } finally {
      set({ searchInitLoading: false, searchMoreLoading: false })
    }
  },
}))
