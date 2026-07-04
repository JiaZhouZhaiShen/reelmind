import { create } from 'zustand'
import type { SearchResult } from '../api/client'
import { api } from '../api/client'
import { toPseudoAsset } from '../utils/search'
import { useStore as useAppStore } from './app'
import { useLibraryStore } from './library'
import i18n from '../i18n/config'

interface SearchState {
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
  searchTriggerKey: number
  triggerSearch: () => void

  searchDurationMin: number | undefined
  searchDurationMax: number | undefined
  searchFileSizeMin: number | undefined
  searchFileSizeMax: number | undefined
  setSearchDurationFilter: (min: number | undefined, max: number | undefined) => void
 setSearchFileSizeFilter: (min: number | undefined, max: number | undefined) => void
  resetSearch: () => void

 searchLoadResults: (page: number, append: boolean) => Promise<void>
  performSearch: (extraParams?: Record<string, unknown>) => Promise<void>
}

export const useSearchStore = create<SearchState>((set, get) => ({
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
  searchTriggerKey: 0,
  triggerSearch: () => set((state) => ({ searchTriggerKey: state.searchTriggerKey + 1 })),

  searchDurationMin: undefined,
  searchDurationMax: undefined,
  searchFileSizeMin: undefined,
  searchFileSizeMax: undefined,
  setSearchDurationFilter: (min, max) => set({ searchDurationMin: min, searchDurationMax: max }),
 setSearchFileSizeFilter: (min, max) => set({ searchFileSizeMin: min, searchFileSizeMax: max }),
  resetSearch: () => set({ searchResults: [], searchTotal: 0, searchQuery: '', searchDurationMin: undefined, searchDurationMax: undefined, searchFileSizeMin: undefined, searchFileSizeMax: undefined, searchPage: 1, searchHasMore: true, searchInitLoading: false, searchMoreLoading: false, searchError: null }),

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
    } catch (e) {
      console.error('Search failed:', e)
      useAppStore.setState({ error: i18n.t('store.searchFailed') + ': ' + ((e as any).message || e) })
    } finally {
      set({ searching: false })
    }
  },

  searchLoadResults: async (page, append) => {
    const { searchQuery, searchDurationMin, searchDurationMax, searchFileSizeMin, searchFileSizeMax } = get()
    if (!searchQuery && searchDurationMin === undefined && searchDurationMax === undefined && searchFileSizeMin === undefined && searchFileSizeMax === undefined) return
    set({ searchError: null })
    if (append) set({ searchMoreLoading: true })
    else set({ searchInitLoading: true })
    try {
      const result = await api.smartSearch({
        q: searchQuery,
        page,
        page_size: 200,
        ...(searchDurationMin !== undefined ? { min_duration: searchDurationMin } : {}),
        ...(searchDurationMax !== undefined ? { max_duration: searchDurationMax } : {}),
        ...(searchFileSizeMin !== undefined ? { min_file_size: searchFileSizeMin } : {}),
        ...(searchFileSizeMax !== undefined ? { max_file_size: searchFileSizeMax } : {}),
      })
      // Write search results to assetsById so VideoCard can read them (cross-store)
      const searchById: Record<string, any> = {}
      for (const r of result.results) {
        searchById[r.id] = toPseudoAsset(r)
      }
      const appState = useAppStore.getState()
      if (append) {
        set({ searchResults: [...get().searchResults, ...result.results], searchTotal: result.total })
        useAppStore.setState({ assetsById: { ...appState.assetsById, ...searchById } })
      } else {
        set({ searchResults: result.results, searchTotal: result.total })
        useAppStore.setState({ assetsById: { ...appState.assetsById, ...searchById } })
      }
      set({ searchPage: page, searchHasMore: page * 200 < result.total })
    } catch (e: any) {
      console.error('Search failed:', e)
      set({ searchError: e?.message || i18n.t('store.searchRetry') })
    } finally {
      set({ searchInitLoading: false, searchMoreLoading: false })
    }
  },
}))
