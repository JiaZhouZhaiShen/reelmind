import { useEffect, useState, useMemo, useRef, useCallback } from 'react'
import { BatchToolbar } from '../components/BatchToolbar'
import { SearchBar } from '../components/SearchBar'
import { VideoCard } from '../components/VideoCard'
import { useStore } from '../stores/app'
import * as assetsApi from '../api/assets'
import { Film, Loader2, Archive, RotateCcw, Filter, X, ArrowUpDown, CalendarDays, Monitor, Smartphone, Square, Image, MessageSquareText, Tag, FileText } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { Asset, TagInfo } from '../api/client'
import { YearTimeline } from '../components/YearTimeline'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useMarqueeSelection } from '../hooks/useMarqueeSelection'
// ═══════════════════════════════════════════════════════════════════════
// Performance config — all tunable
 // ═══════════════════════════════════════════════════════════════════════
 const PAGE_SIZE = 200        // items per page — 只加载够填满视口，滚动时自动加载更多
 const OVERSCAN = 4            // extra rows above/below viewport (≈ 4×6×2 = 48 buffer cards)
const GRID_ROW_HEIGHT = 204   // px per grid row
const HEADER_ROW_HEIGHT = 40  // px per date header row
const LOAD_MORE_THRESHOLD = 800  // px from bottom to trigger next page
const BATCH_SIZE = 5              // pages to load in parallel when navigating to a year
// Max DOM nodes ≈ OVERSCAN × 2 × cols + viewport rows × cols
// With OVERSCAN=4, cols=6 → 4×2×6 + ~5×6 ≈ 78 cards < 100 ✅
const COL_BREAKPOINTS = [
  [1536, 6], [1280, 5], [1024, 4], [768, 3], [0, 2],
] as const
// ═══════════════════════════════════════════════════════════════════════
// ── Types ────────────────────────────────────────────────────────────
type VirtualRow =
  | { type: 'header'; key: string; dateKey: string; dayLabel: string; count: number }
  | { type: 'grid'; key: string; dateKey: string; assets: Asset[] }
  | { type: 'loading'; key: string }
interface DateGroup {
  dateKey: string
  year: number
  month: number
  day: number
  dayLabel: string
  assets: Asset[]
}
// ── Orientation helpers ──────────────────────────────────────────────
type Orientation = 'landscape' | 'portrait' | 'square'
type OrientationFilter = 'all' | 'landscape' | 'portrait' | 'square'
function getOrientation(w?: number, h?: number): Orientation | undefined {
  if (!w || !h) return undefined
  if (w === h) return 'square'
  return w > h ? 'landscape' : 'portrait'
}
function matchOrientation(asset: Asset, filter: OrientationFilter): boolean {
  if (filter === 'all') return true
  if (asset.tags?.includes('横屏')) return filter === 'landscape'
  if (asset.tags?.includes('竖屏')) return filter === 'portrait'
  const o = getOrientation(asset.width, asset.height)
  return o === filter
}
// ─────────────────────────────────────────────────────────────────────
// ── Helpers ──────────────────────────────────────────────────────────
function chunkArr<T>(arr: T[], size: number): T[][] {
  const r: T[][] = []
  for (let i = 0; i < arr.length; i += size) r.push(arr.slice(i, i + size))
  return r
}
function groupByDate(assets: Asset[], dir: 'asc' | 'desc') {
  const map = new Map<string, Asset[]>()
  const noDate: Asset[] = []
  for (const a of assets) {
    if (!a.media_date) { noDate.push(a); continue }
    const d = new Date(a.media_date)
    const k = [
      d.getFullYear(),
      String(d.getMonth() + 1).padStart(2, '0'),
      String(d.getDate()).padStart(2, '0'),
    ].join('-')
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(a)
  }
  const gs: DateGroup[] = []
  for (const [k, v] of map) {
    const [y, m, day] = k.split('-').map(Number)
    gs.push({
      dateKey: k,
      year: y,
      month: m,
      day,
      dayLabel: y + '年' + m + '月' + day + '日',
      assets: v,
    })
  }
  gs.sort((a, b) => (dir === 'desc' ? -1 : 1) * a.dateKey.localeCompare(b.dateKey))
  return { groups: gs, noDate }
}
function buildTimeline(gs: DateGroup[], dir: 'asc' | 'desc') {
  const ym = new Map<
    number,
    { year: number; months: Map<number, { month: number; days: Set<number> }> }
  >()
  for (const g of gs) {
    if (!ym.has(g.year)) ym.set(g.year, { year: g.year, months: new Map() })
    const y = ym.get(g.year)!
    if (!y.months.has(g.month)) y.months.set(g.month, { month: g.month, days: new Set() })
    y.months.get(g.month)!.days.add(g.day)
  }
  return Array.from(ym.values()).sort((a, b) =>
    dir === 'desc' ? b.year - a.year : a.year - b.year,
  )
}
// Skeleton card placeholder (no layout shift — fixed aspect-ratio)
function formatCount(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M"
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K"
  return String(n)
}

function SkeletonCard() {
  return (
    <div className="bg-gray-900 rounded-lg overflow-hidden border border-gray-800 animate-pulse">
      <div className="aspect-video bg-gray-800 relative" style={{ minHeight: 112 }}>
        <div className="absolute inset-0 bg-gray-800/50" />
      </div>
      <div className="p-3 space-y-2">
        <div className="h-3 bg-gray-800 rounded w-3/4" />
        <div className="h-2 bg-gray-800 rounded w-1/2" />
      </div>
    </div>
  )
}
// Helper: page number range for pagination footer
// ── Main component ────────────────────────────────────────────────────
export function AssetGrid() {
  const { t } = useTranslation()
  const [visibleYear, setVisibleYear] = useState<number | null>(null)
  const [visibleDayKey, setVisibleDayKey] = useState<string | null>(null)
  // All years from DB for the right timeline (shows ALL years, not just loaded page)
  const [allTimelineYears, setAllTimelineYears] = useState<Array<{ year: number; count: number }>>([])
  // ── Store ──
  const selectedLibraryId = useStore((s) => s.selectedLibraryId)
  const libraries = useStore((s) => s.libraries)
  const loadStoreLibraries = useStore((s) => s.loadLibraries)
  const showFavorites = useStore((s) => s.showFavorites)
  const showArchived = useStore((s) => s.showArchived)
  const archivedAssets = useStore((s) => s.archivedAssets)
  const toggleShowArchived = useStore((s) => s.toggleShowArchived)
  // ── Grid business data (from store) ──
  const allAssets = useStore((s) => s.gridAssets)
  const gridTotal = useStore((s) => s.gridTotal)
  const gridHasMore = useStore((s) => s.gridHasMore)
  const gridPage = useStore((s) => s.gridPage)
  const initLoading = useStore((s) => s.gridInitLoading)
  const moreLoading = useStore((s) => s.gridMoreLoading)
  const gridError = useStore((s) => s.gridError)
  const filterTags = useStore((s) => s.gridFilterTags)
  const availTags = useStore((s) => s.gridAvailTags)
  const sortOrder = useStore((s) => s.gridSortOrder)
  const orientationFilter = useStore((s) => s.gridOrientationFilter)
  const aiFilter = useStore((s) => s.gridAiFilter)
  const filtering = useStore((s) => s.gridFiltering)
  const filtered = useStore((s) => s.gridFiltered)

  // Grid actions
  const fetchGridAssets = useStore((s) => s.fetchGridAssets)
  const toggleGridTag = useStore((s) => s.toggleGridTag)
  const toggleGridSort = useStore((s) => s.toggleGridSort)
  const setGridOrientationFilter = useStore((s) => s.setGridOrientationFilter)
  const setGridAiFilter = useStore((s) => s.setGridAiFilter)
  const loadGridTags = useStore((s) => s.loadGridTags)
 // ── AI task filter ──
type StatusFilter = 'all' | 'scene' | 'transcript' | 'yolo' | 'ocr'
const AI_FILTER_DEFS: { key: StatusFilter; label: string; icon: typeof Image }[] = [
  { key: 'all' as StatusFilter, label: '全部', icon: Film },
  { key: 'scene' as StatusFilter, label: '场景', icon: Image },
  { key: 'transcript' as StatusFilter, label: '字幕', icon: MessageSquareText },
  { key: 'yolo' as StatusFilter, label: '标识', icon: Tag },
  { key: 'ocr' as StatusFilter, label: 'OCR', icon: FileText },
]
function assetMatchesAIFilter(asset: Asset, f: StatusFilter): boolean {
  switch (f) {
    case 'all': return true
    case 'scene': return asset.scene_status === 'completed'
    case 'transcript': return asset.transcript_status === 'completed'
    case 'yolo': return asset.yolo_status === 'completed'
    case 'ocr': return asset.ocr_status === 'completed'
    default: return false
  }
}
// ── Tag filter ──
  const paginationMode: 'infinite' | 'page' = 'infinite'
  // ── Year navigation state ──
  const [navigatingYear, setNavigatingYear] = useState<number | null>(null)
  const [showFilter, setShowFilter] = useState(false)
 // ── Refs ──
 const scrollRef = useRef<HTMLDivElement>(null)
 const contRef = useRef<HTMLDivElement>(null)
 const scrollRAfRef = useRef<number | null>(null)
 const loadingYearRef = useRef<number | null>(null)
 const [contW, setContW] = useState(0)
  // ── Responsive columns ──

  useMarqueeSelection(scrollRef)
  const cols = useMemo(() => {
    for (const [minW, c] of COL_BREAKPOINTS) {
      if (contW >= minW) return c
    }
    return 2
  }, [contW])
  const widthReady = contW > 0 && cols > 0
  // ── ResizeObserver for container width ──
  useEffect(() => {
    if (!contRef.current) return
    const ro = new ResizeObserver((es) => {
      for (const e of es) setContW(e.contentRect.width)
    })
    ro.observe(contRef.current)
    return () => ro.disconnect()
  }, [])
  // ── Init libraries & tags ──
  useEffect(() => {
    loadStoreLibraries()
  }, [loadStoreLibraries])
  useEffect(() => {
    loadGridTags()
  }, [])
  // Fetch all timeline years from DB (for the right sidebar timeline display)
  useEffect(() => {
    api.timelineYears(selectedLibraryId || undefined)
      .then(setAllTimelineYears)
      .catch(() => useStore.setState({ gridError: '无法加载年份数据' }))
  }, [selectedLibraryId])
  // ── Total pages (page mode) ──
  // ── Core data loading ──
  // Fetches one page of PAGE_SIZE items, appends or replaces local state
    const fetchPage = useCallback(
      async (p: number, append: boolean) => {
        const sLibId = selectedLibraryId
        const sSort = sortOrder
        const sFav = showFavorites
        const sAi = aiFilter
        const sOrient = orientationFilter
        await fetchGridAssets(sLibId, sSort, sFav, sAi, sOrient, p, append)
      },
      [selectedLibraryId, sortOrder, showFavorites, aiFilter, orientationFilter, fetchGridAssets],
    )
  // Initial load + reload when sort/library changes

  // ── Parallel batch page loader ──
  // Loads a range of pages in parallel (e.g., pages 10–15) and merges into allAssets.
  // Used primarily by scrollToYear when the target year hasn't been loaded yet.
  const loadPageRange = useCallback(
    async (startPage: number, endPage: number): Promise<void> => {
      const s = useStore.getState()
      if (s.gridMoreLoading || s.gridInitLoading) return
      useStore.setState({ gridMoreLoading: true, gridError: null })

      const PAGE_SIZE = s.gridPAGE_SIZE
      const maxPage = Math.ceil(s.gridTotal / PAGE_SIZE)
      const pages: number[] = []
      for (let p = startPage; p <= endPage && p <= maxPage; p++) {
        if (p >= 1) pages.push(p)
      }
      if (pages.length === 0) {
        useStore.setState({ gridMoreLoading: false })
        return
      }

      try {
        const results = await Promise.all(
          pages.map((p) =>
            assetsApi.listAssets(
              s.selectedLibraryId || undefined,
              p,
              PAGE_SIZE,
              'media_date',
              s.gridSortOrder,
              s.showFavorites || undefined,
              s.gridAiFilter,
              s.gridOrientationFilter,
            ),
          ),
        )

        // Flatten all results, preserving page order
        const allNewItems: Asset[] = []
        let lastLoadedPage = 0
        for (let i = 0; i < results.length; i++) {
          allNewItems.push(...results[i].items)
          lastLoadedPage = pages[i]
        }

        const s2 = useStore.getState()
        useStore.setState((prev) => ({
          gridAssets: (() => {
            const existingIds = new Set(prev.gridAssets.map((a) => a.id))
            const uniqueNew = allNewItems.filter((a) => !existingIds.has(a.id))
            return [...prev.gridAssets, ...uniqueNew]
          })(),
        }))
        const s3 = useStore.getState()
        useStore.setState({ gridPage: Math.max(s3.gridPage, lastLoadedPage), gridHasMore: lastLoadedPage * PAGE_SIZE < s3.gridTotal })
      } catch (e: any) {
        useStore.setState({ gridError: e?.message || 'Load failed' })
      } finally {
        useStore.setState({ gridMoreLoading: false })
      }
    },
    [selectedLibraryId, PAGE_SIZE],
  )
  useEffect(() => {
    useStore.getState().resetGridState()
    fetchPage(1, false)
  }, [fetchPage])
 // Load next page (infinite mode)
 const loadNext = useCallback(() => {
   const s = useStore.getState()
   if (s.gridMoreLoading || !s.gridHasMore || s.gridInitLoading) return
   fetchPage(s.gridPage + 1, true).catch(() => {
     useStore.setState({ gridError: '加载下一页失败，请检查网络连接' })
   })
 }, [fetchPage])
  // Scroll detection for infinite loading
  const handleScroll = useCallback(() => {
    const s = useStore.getState()
    if (!scrollRef.current || !s.gridHasMore || s.gridMoreLoading || s.gridInitLoading) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    if (scrollHeight - scrollTop - clientHeight < LOAD_MORE_THRESHOLD) {
      loadNext()
    }
  }, [loadNext])
  // ── Tag filtering ──
  useEffect(() => {
    if (!filterTags.length) {
      useStore.setState({ gridFiltered: [] })
      return
    }
    useStore.setState({ gridFiltering: true })
    api
      .smartSearch({
        tags: filterTags.join(','),
        library_id: selectedLibraryId || undefined,
        page_size: 200,
      })
      .then((res) => {
        useStore.setState({
          gridFiltered: res.results.map(
            (r) =>
              ({
                id: r.id,
                file_name: r.file_name,
                file_size: 0,
                duration: r.duration,
                thumbnail_path: r.thumbnail_path,
                library_id: selectedLibraryId || '',
                original_path: '',
                tags: [],
                is_archived: false,
                is_favorite: false,
                created_at: '',
                updated_at: '',
              }) as unknown as Asset,
          ),
        })
      })
      .catch(() => useStore.setState({ gridFiltered: [], gridError: '标签筛选失败' }))
      .finally(() => useStore.setState({ gridFiltering: false }))
  }, [filterTags, selectedLibraryId])
  const toggleTag = (n: string) => toggleGridTag(n)
  // ── Sort toggle ──
  const toggleSort = useCallback(() => {
    toggleGridSort()
  }, [])
  // ── Page navigation (page mode) ──
  // ── Build date groups ──
 const display = useMemo(() => {
    let base = filterTags.length > 0 ? filtered : allAssets
    // Client-side safety filter for AI filter (guard against stale API responses)
    if (aiFilter !== 'all') {
      base = base.filter((a) => assetMatchesAIFilter(a, aiFilter as StatusFilter))
    }
    return base
  }, [filterTags, filtered, allAssets, aiFilter])
  const { groups, noDate } = useMemo(() => groupByDate(display, sortOrder), [display, sortOrder])
  const showMore = filterTags.length === 0 && gridHasMore
  // ── Build virtual rows ──
  // Each grid row = up to cols assets.
  // This is where we control total virtual row count.
  const virtualRows = useMemo((): VirtualRow[] => {
    const rs: VirtualRow[] = []
    // Assets without a media_date
    if (noDate.length) {
      rs.push({
        type: 'header',
        key: 'nd-header',
        dateKey: '',
        dayLabel: t('assetGrid.otherVideos') || '其他视频',
        count: noDate.length,
      })
      for (const [i, ch] of chunkArr(noDate, cols).entries()) {
        rs.push({ type: 'grid', key: 'nd-' + i, dateKey: '', assets: ch })
      }
    }
    // Date-grouped assets
    for (const g of groups) {
      rs.push({
        type: 'header',
        key: 'h-' + g.dateKey,
        dateKey: g.dateKey,
        dayLabel: g.dayLabel,
        count: g.assets.length,
      })
      for (const [i, ch] of chunkArr(g.assets, cols).entries()) {
        rs.push({ type: 'grid', key: 'g-' + g.dateKey + '-' + i, dateKey: g.dateKey, assets: ch })
      }
    }
    // Loading indicator (infinite mode only)
    if (paginationMode === 'infinite' && showMore && !filtering) {
      rs.push({ type: 'loading', key: 'lm' })
    }
    return rs
  }, [groups, noDate, cols, showMore, filtering, t, paginationMode])
  // ── Virtualizer row size estimation ──
  const estimateSize = useCallback(
    (i: number) => {
      const r = virtualRows[i]
      if (!r) return GRID_ROW_HEIGHT
      if (r.type === 'header') return HEADER_ROW_HEIGHT
      if (r.type === 'loading') return 60
      return GRID_ROW_HEIGHT
    },
    [virtualRows],
  )
  // ── @tanstack/react-virtual virtualizer ──
  // Core performance: only mounts (viewport_rows + 2×OVERSCAN) rows at any time
  const virtualizer = useVirtualizer({
    count: virtualRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize,
    overscan: OVERSCAN,
    getItemKey: (i: number) => virtualRows[i]?.key ?? String(i),
    measureElement: (el) => el.getBoundingClientRect().height,
  })
 
  // ── Timeline data ──
  const timeline = useMemo(() => buildTimeline(groups, sortOrder), [groups, sortOrder])
 // --- Years data for YearTimeline (from API — ALL years in DB) ---
 const yearsData = useMemo(() => {
   // Use API timeline data when available, fall back to loaded groups
   if (allTimelineYears.length > 0) {
     return [...allTimelineYears].sort((a, b) => b.year - a.year)
   }
   const yearMap = new Map<number, number>()
   for (const g of groups) {
     yearMap.set(g.year, (yearMap.get(g.year) || 0) + g.assets.length)
   }
   return Array.from(yearMap.entries())
     .map(([year, count]) => ({ year, count }))
     .sort((a, b) => b.year - a.year)
 }, [allTimelineYears, groups])
 // --- Track visible year/day from virtualizer scroll ---
const updateVisibleItems = useCallback(() => {
  if (!scrollRef.current || !widthReady) return
  const { scrollTop } = scrollRef.current



  // Use getVirtualItemForOffset to find item at scroll position, then scan backward for header
  const cur = virtualizer.getVirtualItemForOffset(scrollTop)
  if (!cur) return
  const startIndex = cur.index
  let foundYear: number | null = null
  let foundDayKey: string | null = null
  for (let i = startIndex; i >= 0; i--) {
    const row = virtualRows[i]
    if (!row || row.type !== 'header' || !row.dateKey) continue
    const parts = row.dateKey.split('-').map(Number)
    if (parts.length !== 3) continue
    foundYear = parts[0]
    // Check if header is near viewport top
    const headerInfo = virtualizer.getOffsetForIndex(i)
    const headerOffset = headerInfo ? headerInfo[0] : -1
    if (headerOffset >= scrollTop - 10 && headerOffset <= scrollTop + 150) {
      foundDayKey = row.dateKey
    }
    break
  }
  setVisibleYear(foundYear)
  setVisibleDayKey(foundDayKey)
}, [virtualizer, virtualRows, widthReady])
 // Initialize visible items on mount & data ready
 useEffect(() => {
   if (widthReady && !initLoading && virtualizer.getVirtualItems().length > 0) {
     updateVisibleItems()
   }
 }, [widthReady, initLoading, updateVisibleItems, virtualizer])
// ── Scroll to specific date ──
  const scrollToDate = useCallback(
    (k: string) => {
      const idx = virtualRows.findIndex((r) => r.type === 'header' && r.dateKey === k)
      if (idx >= 0) virtualizer.scrollToIndex(idx, { align: 'start', behavior: 'smooth' })
    },
    [virtualRows, virtualizer],
  )
  const scrollToYear = useCallback(
    async (year: number): Promise<void> => {
      // 1) Year already loaded → scroll directly
      const firstGroup = groups.find((g) => g.year === year)
      if (firstGroup) {
        scrollToDate(firstGroup.dateKey)
        return
      }

      // 2) Use allTimelineYears data to estimate the target year's page range
      if (allTimelineYears.length > 0) {
        // Sort newest-first (matching sortOrder=desc)
        const sorted = [...allTimelineYears].sort((a, b) => b.year - a.year)
        const target = sorted.find((y) => y.year === year)
        if (target) {
          // Count items in all years newer than the target
          const newerCount = sorted
            .filter((y) => y.year > year)
            .reduce((sum, y) => sum + y.count, 0)

          // In descending sort, the target year's items start at index `newerCount`
          const startIndex = newerCount
          const estimatedStartPage = Math.floor(startIndex / PAGE_SIZE) + 1
          const estimatedEndPage = Math.ceil((startIndex + target.count) / PAGE_SIZE)
          const maxPage = Math.ceil(gridTotal / PAGE_SIZE)

          // Buffer: load a few extra pages before and after for safety
          const loadStart = Math.max(1, estimatedStartPage - 1)
          const loadEnd = Math.min(maxPage, estimatedEndPage + 2)

          setNavigatingYear(year)
          loadingYearRef.current = year
          await loadPageRange(loadStart, loadEnd)

          // After loading, check if the year appeared
          const afterLoad = groups.find((g) => g.year === year)
          if (afterLoad) {
            scrollToDate(afterLoad.dateKey)
            loadingYearRef.current = null
            setNavigatingYear(null)
          } else {
            // Year wasn't in estimated range — ref will keep watcher loading
            loadingYearRef.current = year
          }
          return
        }
      }

      // 3) Fallback: load from next page onward
      loadingYearRef.current = year
      setNavigatingYear(year)
      if (gridHasMore && !moreLoading && !initLoading) {
        await loadPageRange(gridPage + 1, gridPage + BATCH_SIZE)
      }
    },
    [groups, scrollToDate, allTimelineYears, fetchPage, loadPageRange],
  )
  const scrollToDay = useCallback(
    (year: number, month: number, day: number) => {
      const key = [
        year,
        String(month).padStart(2, '0'),
        String(day).padStart(2, '0'),
      ].join('-')
      scrollToDate(key)
    },
   [scrollToDate],
 )
  // ── Loading effect for year navigation ──
  // ── Year navigation watcher ──
  // Watches for the target year to appear in groups after a batch load.
  // If the estimated range was wrong, loads additional batches.
  useEffect(() => {
    const target = loadingYearRef.current
    if (target === null) return

    // Year appeared in loaded data → scroll & clear
    const firstGroup = groups.find(g => g.year === target)
    if (firstGroup) {
      scrollToDate(firstGroup.dateKey)
      loadingYearRef.current = null
      setNavigatingYear(null)
      return
    }

    // Not found yet — load the next batch in parallel
    if (gridHasMore && !moreLoading && !initLoading && paginationMode === 'infinite') {
      loadPageRange(gridPage + 1, gridPage + BATCH_SIZE).catch(() => {
        useStore.setState({ gridError: '批量加载视频数据失败' })
      })
    } else if (!useStore.getState().gridHasMore && !useStore.getState().gridMoreLoading) {
      loadingYearRef.current = null
      setNavigatingYear(null)
    }
  }, [
    groups,
    gridHasMore,
    moreLoading,
    initLoading,
    gridPage,
    scrollToDate,
    loadPageRange,
    paginationMode,
  ])
 // ── Derived ──
 const selectedLib = libraries.find((l) => l.id === selectedLibraryId)
 const empty = !initLoading && !gridError && display.length === 0 && gridTotal === 0
 const showSkeleton = initLoading && !gridError
 return (
   <div className="flex h-full">
      {/* Main content area */}
      <div
        ref={contRef}
        className="flex-1 flex flex-col min-w-0 overflow-hidden max-w-7xl mx-auto w-full"
        style={{ contain: 'layout size style' }}
      >
        {/*
         * ── Header bar ──────────────────────────────────────────────
         * Title, sort toggle, pagination mode, search bar, tag filter, archive
         */}
        <div className="p-4 pb-2 shrink-0">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div>
                <h1 className="text-2xl font-bold text-white">
                  {showFavorites ? '我的收藏' : (selectedLib ? selectedLib.name : '所有视频')}
                </h1>
                <p className="text-sm text-gray-500 mt-1">
                  {initLoading
                    ? '加载中...'
                    : '共 ' + formatCount(gridTotal) + ' 个视频 — 显示 ' + formatCount(display.length)}
                </p>
              </div>
              {/* Sort toggle */}
              <button
                onClick={toggleSort}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border border-gray-700 text-gray-400 hover:text-gray-200 hover:border-gray-600 transition-colors mt-1"
              >
                <ArrowUpDown className="w-4 h-4" />
                <span className="text-xs">{sortOrder === 'asc' ? '最早' : '最新'}</span>
              </button>
              {/* Orientation filter toggle */}
              <div className="flex items-center border border-gray-700 rounded-lg overflow-hidden mt-1">
                <button
                  onClick={() => setGridOrientationFilter('all')}
                  className={
                    'px-2.5 py-1.5 text-xs transition-colors ' +
                    (orientationFilter === 'all'
                      ? 'bg-indigo-600 text-white'
                      : 'text-gray-400 hover:text-gray-200')
                  }
                  title="全部"
                >
                  全部
                </button>
                <button
                  onClick={() => setGridOrientationFilter('landscape')}
                  className={
                    'px-2.5 py-1.5 text-xs transition-colors flex items-center gap-1 ' +
                    (orientationFilter === 'landscape'
                      ? 'bg-indigo-600 text-white'
                      : 'text-gray-400 hover:text-gray-200')
                  }
                  title="横屏"
                >
                  <Monitor className="w-3.5 h-3.5" />
                  <span>横屏</span>
                </button>
                <button
                  onClick={() => setGridOrientationFilter('portrait')}
                  className={
                    'px-2.5 py-1.5 text-xs transition-colors flex items-center gap-1 ' +
                    (orientationFilter === 'portrait'
                      ? 'bg-indigo-600 text-white'
                      : 'text-gray-400 hover:text-gray-200')
                  }
                  title="竖屏"
                >
                  <Smartphone className="w-3.5 h-3.5" />
                  <span>竖屏</span>
                </button>
                <button
                  onClick={() => setGridOrientationFilter('square')}
                  className={
                    'px-2.5 py-1.5 text-xs transition-colors flex items-center gap-1 ' +
                    (orientationFilter === 'square'
                      ? 'bg-indigo-600 text-white'
                      : 'text-gray-400 hover:text-gray-200')
                  }
                  title="方形"
                >
                  <Square className="w-3.5 h-3.5" />
                  <span>方形</span>
                </button>
              </div>
         </div>
          <div className="flex items-center gap-2">
              <SearchBar compact />
              {/* Tag filter dropdown */}
              <div className="relative shrink-0">
                <button
                  onClick={() => setShowFilter(!showFilter)}
                  className={
                    'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm border transition-colors ' +
                    (filterTags.length
                      ? 'bg-indigo-600/20 text-indigo-400 border-indigo-700/50'
                      : 'text-gray-400 border-gray-700 hover:text-gray-200 hover:border-gray-600')
                  }
                >
                  <Filter className="w-4 h-4" />
                  <span>
                    {filterTags.length ? filterTags.length + ' ' : ''}标签
                  </span>
                </button>
                {showFilter && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setShowFilter(false)} />
                    <div className="absolute right-0 top-full mt-1 z-20 w-72 bg-gray-900 border border-gray-700 rounded-lg shadow-sm max-h-80 overflow-y-auto">
                      <div className="p-3 border-b border-gray-800">
                        <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">
                          筛选标签
                        </p>
                      </div>
                      <div className="p-2 space-y-0.5">
                        {!availTags.length && (
                          <p className="px-3 py-2 text-sm text-gray-500">暂无标签</p>
                        )}
                        {availTags.map((tag) => {
                          const sel = filterTags.includes(tag.name)
                          return (
                            <button
                              key={tag.id}
                              onClick={() => toggleTag(tag.name)}
                              className={
                                'w-full flex items-center gap-2 px-3 py-1.5 rounded text-sm transition-colors ' +
                                (sel
                                  ? 'bg-indigo-600/20 text-indigo-300'
                                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800')
                              }
                            >
                              <div
                                className={
                                  'w-1.5 h-1.5 rounded-full ' +
                                  (sel ? 'bg-indigo-400' : 'bg-gray-600')
                                }
                              />
                              <span className="flex-1 text-left">{tag.name}</span>
                              <span className="text-xs text-gray-600">{tag.category}</span>
                              {sel && <X className="w-3 h-3 text-indigo-400" />}
                            </button>
                          )
                        })}
                      </div>
                      {filterTags.length > 0 && (
                        <div className="p-2 border-t border-gray-800">
                          <button
                            onClick={() => {
                              useStore.getState().resetGridState()
                              setShowFilter(false)
                            }}
                            className="w-full px-3 py-1.5 text-xs text-gray-500 hover:text-gray-400 transition-colors rounded"
                          >
                            清除筛选
                          </button>
                        </div>
                      )}
                    </div>
                  </>
                )}
              </div>
              {/* Archive toggle */}
              <button
                onClick={toggleShowArchived}
                className={
                  'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm border transition-colors ' +
                  (showArchived
                    ? 'bg-indigo-600/20 text-indigo-400 border-indigo-700/50'
                    : 'text-gray-400 border-gray-700 hover:text-gray-200 hover:border-gray-600')
                }
              >
                {showArchived ? (
                  <RotateCcw className="w-4 h-4" />
                ) : (
                  <Archive className="w-4 h-4" />
                )}
                <span>{showArchived ? '活动视频' : '已归档'}</span>
              </button>
            </div>
          </div>
          {/* AI task filter buttons */}
          <div className="flex items-center gap-1.5 mb-3">
            {AI_FILTER_DEFS.map((f) => {
              const active = aiFilter === f.key
              return (
                <button
                  key={f.key}
                  onClick={() => setGridAiFilter(f.key)}
                  className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    active
                      ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-500/30'
                      : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200'
                  }`}
                >
                  <f.icon className="w-3.5 h-3.5" />
                  <span>{f.label}</span>
                </button>
              )
            })}
          </div>
          {/* Batch toolbar */}
          <BatchToolbar currentAssets={display} onRefresh={() => fetchPage(gridPage, false)} />
          {/* Active tag filter chips */}
          {filterTags.length > 0 && (
            <div className="flex items-center gap-2 mb-4 flex-wrap">
              {filterTags.map((n) => (
                <span
                  key={n}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-full bg-indigo-900/30 text-indigo-300 border border-indigo-800/30"
                >
                  {n}
                  <button onClick={() => toggleTag(n)} className="hover:text-white ml-0.5">
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>
        {/*
         * ── Archived view ──────────────────────────────────────────
         * Not virtualized (archived count is typically small).
         */}
        {showArchived && (
          <div className="flex-1 overflow-y-auto px-4 pb-4">
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              <Archive className="w-4 h-4" /> 已归档 ({archivedAssets.length})
            </h2>
            {archivedAssets.length === 0 ? (
             <div className="flex flex-col items-center justify-center py-16 text-gray-500">
               <Archive className="w-12 h-12 mb-3 text-gray-700" />
                <p className="text-sm text-gray-500">没有已归档的视频</p>
                <p className="text-xs text-gray-600 mt-1">在视频详情中点击归档按钮，视频会自动移到这里</p>
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-4">
              {archivedAssets.map((a) => (
                  <VideoCard key={a.id} assetId={a.id} />
                ))}
              </div>
            )}
          </div>
        )}
        {/*
        {/*
         * ── Year navigation loading indicator ──
         */}
        {navigatingYear !== null && moreLoading && (
          <div className="flex items-center justify-center gap-2 px-4 py-2 shrink-0 bg-indigo-900/20 border-b border-indigo-800/30">
            <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
            <span className="text-sm text-indigo-300">正在定位 {navigatingYear} 年的数据...</span>
          </div>
        )}
        {/*
         * Card-shaped gray placeholders matching final card size.
         */}
        {showSkeleton && widthReady && !showArchived && (
          <div className="flex-1 overflow-hidden px-4 pb-4">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-4">
              {Array.from({ length: cols * 6 }).map((_, i) => (
                <SkeletonCard key={i} />
              ))}
            </div>
          </div>
        )}
        {/*
         * ── Error state ────────────────────────────────────────────
         */}
        {gridError && !initLoading && !showArchived && (
          <div className="flex flex-col items-center justify-center flex-1 text-gray-400">
            <p className="text-sm mb-3 text-red-400">{gridError}</p>
            <button
              onClick={() => fetchPage(1, false)}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm"
            >
              重试
            </button>
          </div>
        )}
        {/*
         * ── Empty state ────────────────────────────────────────────
         */}
        {empty && !showArchived && (
          <div className="flex flex-col items-center justify-center flex-1 text-gray-500 px-4 pb-4">
            <Film className="w-16 h-16 mb-4 text-gray-700" />
            <h2 className="text-xl font-medium text-gray-400 mb-2">没有视频</h2>
            <p className="text-sm text-gray-600 mb-4">请先创建库并导入视频</p>
            <a
              href="/libraries"
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm"
            >
              管理库
            </a>
          </div>
        )}
        {/*
         * ── Virtual scroll list (core performance area) ────────────
         *
         * Performance guarantees:
         * • Virtualizer always mounts ≤100 DOM nodes (viewport + overscan buffer)
         * • `contain: 'strict'` isolates layout/paint to this container
         * • Fixed row heights — no layout reflow during scroll
         * • <img loading="lazy" decoding="async"> prevents off-screen downloads
         * • No filter:drop-shadow() or large box-shadow on scrollable cards
         */}
        {widthReady && !showSkeleton && !showArchived && display.length > 0 && (
          <>
           <div
             ref={scrollRef}
             onScroll={() => {
               handleScroll()
               if (scrollRAfRef.current !== null) cancelAnimationFrame(scrollRAfRef.current)
               scrollRAfRef.current = requestAnimationFrame(() => {
                 updateVisibleItems()
                 scrollRAfRef.current = null
               })
             }}
             className="flex-1 overflow-y-auto px-4"
              style={{ contain: 'strict' }}
            >
              <div
                style={{
                  height: virtualizer.getTotalSize() + 'px',
                  width: '100%',
                  position: 'relative',
                }}
              >
                {virtualizer.getVirtualItems().map((virtualItem) => {
                  const row = virtualRows[virtualItem.index]
                  if (!row) return null
                  return (
                    <div
                      key={virtualItem.key}
                      data-index={virtualItem.index}
                      ref={virtualizer.measureElement}
                      style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        transform: 'translateY(' + virtualItem.start + 'px)',
                        willChange: 'transform',
                      }}
                    >
                      {/* ═══ Date header ═══ */}
                      {row.type === 'header' && (
                        <div
                          className="flex items-center gap-2"
                          style={{ height: HEADER_ROW_HEIGHT + 'px' }}
                        >
                          <CalendarDays className="w-4 h-4 text-gray-500 shrink-0" />
                          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
                            {row.dayLabel}
                          </h3>
                          <span className="text-xs text-gray-600 font-normal">
                            ({row.count} 个视频)
                          </span>
                        </div>
                      )}
                      {/* ═══ Card grid row ═══ */}
                      {row.type === 'grid' && (
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(' + cols + ', 1fr)',
                            gap: '1rem',
                          }}
                        >
                          {row.assets!.map((a) => (
                            <VideoCard key={a.id} assetId={a.id} />
                          ))}
                        </div>
                      )}
                      {/* ═══ Loading more (infinite) ═══ */}
                      {row.type === 'loading' && (
                        <div
                          className="flex items-center justify-center"
                          style={{ height: '60px' }}
                        >
                          {moreLoading ? (
                            <>
                              <Loader2 className="w-5 h-5 animate-spin text-indigo-400 mr-2" />
                              <span className="text-sm text-gray-400">加载中...</span>
                            </>
                          ) : (
                            <span className="text-sm text-gray-400">滚动加载更多...</span>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
            {/* Infinite-mode bottom loading indicator */}
            {moreLoading && (
              <div className="flex items-center justify-center py-4 shrink-0">
                <Loader2 className="w-5 h-5 animate-spin text-indigo-400 mr-2" />
                <span className="text-sm text-gray-400">加载更多视频...</span>
              </div>
            )}
          </>
        )}
      </div>
      {!showArchived && (
        <YearTimeline
          years={yearsData}
          activeYear={visibleYear}
          activeDayKey={visibleDayKey}
          onYearClick={scrollToYear}
          onDayClick={scrollToDay}
        />
      )}
    </div>
  )
}


