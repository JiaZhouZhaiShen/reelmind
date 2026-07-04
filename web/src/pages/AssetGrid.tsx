import { useEffect, useState, useMemo, useRef, useCallback } from 'react'
import { useLibraryStore } from '../stores/library'
import { useAssetStore } from '../stores/asset'
import { useGridStore } from '../stores/grid'
import { api } from '../api/client'
import type { Asset } from '../api/client'
import { YearTimeline } from '../components/YearTimeline'
import { VideoCard } from '../components/VideoCard'
import { useMarqueeSelection } from '../hooks/useMarqueeSelection'
import { AssetGridFilters } from './AssetGridFilters'
import { AssetGridVirtual } from './AssetGridVirtual'
import type { AssetGridVirtualHandle } from './AssetGridVirtual'
import { COL_BREAKPOINTS, formatCount, groupByDate, assetMatchesAIFilter } from './AssetGridUtils'
import type { StatusFilter } from './AssetGridUtils'
import { Archive } from 'lucide-react'

const PAGE_SIZE = 200

export function AssetGrid() {
  // ── State ──
  const [visibleYear, setVisibleYear] = useState<number | null>(null)
  const [visibleDayKey, setVisibleDayKey] = useState<string | null>(null)
  const gridTimelineYears = useGridStore((s) => s.gridTimelineYears)
  const loadGridTimelineYears = useGridStore((s) => s.loadGridTimelineYears)
  const [navigatingYear, setNavigatingYear] = useState<number | null>(null)
  const [contW, setContW] = useState(0)

  // ── Store selectors ──
  const selectedLibraryId = useLibraryStore((s) => s.selectedLibraryId)
  const libraries = useLibraryStore((s) => s.libraries)
  const loadStoreLibraries = useLibraryStore((s) => s.loadLibraries)
  const showFavorites = useAssetStore((s) => s.showFavorites)
  const showArchived = useAssetStore((s) => s.showArchived)
  const archivedAssets = useAssetStore((s) => s.archivedAssets)
  const allAssets = useGridStore((s) => s.gridAssets)
  const gridTotal = useGridStore((s) => s.gridTotal)
  const gridHasMore = useGridStore((s) => s.gridHasMore)
  const gridPage = useGridStore((s) => s.gridPage)
  const initLoading = useGridStore((s) => s.gridInitLoading)
  const moreLoading = useGridStore((s) => s.gridMoreLoading)
  const gridError = useGridStore((s) => s.gridError)
  const filterTags = useGridStore((s) => s.gridFilterTags)
  const sortOrder = useGridStore((s) => s.gridSortOrder)
  const aiFilter = useGridStore((s) => s.gridAiFilter)
  const gridOrientationFilter = useGridStore((s) => s.gridOrientationFilter)
  const filtering = useGridStore((s) => s.gridFiltering)
  const filtered = useGridStore((s) => s.gridFiltered)
  const fetchGridAssets = useGridStore((s) => s.fetchGridAssets)
  const loadGridTags = useGridStore((s) => s.loadGridTags)

  // ── Refs ──
  const contRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const virtualRef = useRef<AssetGridVirtualHandle>(null)
  useMarqueeSelection(scrollRef)

  // ── Responsive columns ──
  const cols = useMemo(() => {
    for (const [minW, c] of COL_BREAKPOINTS) {
      if (contW >= minW) return c
    }
    return 2
  }, [contW])

  // ── Dynamic grid column class, matches `cols` ──
  const gridColsClass = useMemo(() => {
    const map: Record<number, string> = {
      2: 'grid-cols-2', 3: 'grid-cols-3', 4: 'grid-cols-4', 5: 'grid-cols-5', 6: 'grid-cols-6',
    }
    return map[cols] || 'grid-cols-5'
  }, [cols])

  const widthReady = contW > 0 && cols > 0

  useEffect(() => {
    if (!contRef.current) return
    const ro = new ResizeObserver((es) => {
      for (const e of es) setContW(e.contentRect.width)
    })
    ro.observe(contRef.current)
    return () => ro.disconnect()
  }, [])

  // ── Init effects ──
  useEffect(() => { loadStoreLibraries() }, [loadStoreLibraries])
  useEffect(() => { loadGridTags() }, [loadGridTags])
  useEffect(() => {
    loadGridTimelineYears()
  }, [loadGridTimelineYears, selectedLibraryId])

  // ── Data loading ──
  const fetchPage = useCallback(
    async (p: number, append: boolean) => {
      const s = useLibraryStore.getState()
      const g = useGridStore.getState()
      const a = useAssetStore.getState()
      await fetchGridAssets(
        s.selectedLibraryId, g.gridSortOrder, a.showFavorites,
        g.gridAiFilter, g.gridOrientationFilter, p, append,
      )
    },
    [fetchGridAssets],
  )

  useEffect(() => {
    useGridStore.getState().resetGridState()
    fetchPage(1, false)
  }, [fetchPage, showFavorites, selectedLibraryId, gridOrientationFilter, sortOrder, aiFilter])

  const loadNext = useCallback(() => {
      const g = useGridStore.getState()
    if (g.gridMoreLoading || !g.gridHasMore || g.gridInitLoading) return
    fetchPage(g.gridPage + 1, true).catch(() => {
      useGridStore.setState({ gridError: '\u52a0\u8f7d\u4e0b\u4e00\u9875\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u7f51\u7edc\u8fde\u63a5' })
    })
  }, [fetchPage])

  // ── Tag filter effect ──
  useEffect(() => {
    if (!filterTags.length) {
      useGridStore.setState({ gridFiltered: [] })
      return
    }
    useGridStore.setState({ gridFiltering: true })
    api
      .smartSearch({
        tags: filterTags.join(','),
        library_id: selectedLibraryId || undefined,
        page_size: 200,
      })
      .then((res) => {
        useGridStore.setState({
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
      .catch(() => useGridStore.setState({ gridFiltered: [], gridError: '\u6807\u7b7e\u7b5b\u9009\u5931\u8d25' }))
      .finally(() => useGridStore.setState({ gridFiltering: false }))
  }, [filterTags, selectedLibraryId])

  // ── Computed ──
  const display = useMemo(() => {
    let base = filterTags.length > 0 ? filtered : allAssets
    if (aiFilter !== 'all') {
      base = base.filter((a) => assetMatchesAIFilter(a, aiFilter as StatusFilter))
    }
    return base
  }, [filterTags, filtered, allAssets, aiFilter])

  const showMore = filterTags.length === 0 && gridHasMore
  const selectedLib = libraries.find((l) => l.id === selectedLibraryId)
  const empty = !initLoading && !gridError && display.length === 0 && gridTotal === 0
  const showSkeleton = initLoading && !gridError

  // ── Timeline data ──
  const yearsData = useMemo(() => {
    if (gridTimelineYears.length > 0) {
      return [...gridTimelineYears].sort((a, b) => b.year - a.year)
    }
    const { groups } = groupByDate(display, sortOrder)
    const yearMap = new Map<number, number>()
    for (const g of groups) {
      yearMap.set(g.year, (yearMap.get(g.year) || 0) + g.assets.length)
    }
    return Array.from(yearMap.entries())
      .map(([year, count]) => ({ year, count }))
      .sort((a, b) => b.year - a.year)
  }, [gridTimelineYears, display, sortOrder])

  // ── Year timeline callback ──
  const onYearChanged = useCallback((year: number | null, dayKey: string | null) => {
    setVisibleYear(year)
    setVisibleDayKey(dayKey)
  }, [])

  // ── Render ──
  return (
    <div className="flex h-full">
      <div
        ref={contRef}
        className="flex-1 flex flex-col min-w-0 overflow-hidden w-full"
        style={{ contain: 'layout size style' }}
      >

        {/* Filter toolbar */}
        <AssetGridFilters 
          display={display}
          heading={showFavorites ? '\u6211\u7684\u6536\u85cf' : (selectedLib ? selectedLib.name : '\u6240\u6709\u89c6\u9891')}
          countText={initLoading ? '\u52a0\u8f7d\u4e2d...' : '\u5171 ' + formatCount(gridTotal) + ' \u4e2a\u89c6\u9891 \u2014 \u663e\u793a ' + formatCount(display.length)}
        />

        {/* Archived view */}
        {showArchived && (
          <div className="flex-1 overflow-y-auto px-4 pb-4">
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              <Archive className="w-4 h-4" /> \u5df2\u5f52\u6863 ({archivedAssets.length})
            </h2>
            {archivedAssets.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-500">
                <Archive className="w-12 h-12 mb-3 text-gray-700" />
                <p className="text-sm text-gray-500">{'\u6ca1\u6709\u5df2\u5f52\u6863\u7684\u89c6\u9891'}</p>
                <p className="text-xs text-gray-600 mt-1">{'\u5728\u89c6\u9891\u8be6\u60c5\u4e2d\u70b9\u51fb\u5f52\u6863\u6309\u94ae\uff0c\u89c6\u9891\u4f1a\u81ea\u52a8\u79fb\u5230\u8fd9\u91cc'}</p>
              </div>
            ) : (
              <div className={"grid " + gridColsClass + " gap-4"}>
                {archivedAssets.map((a) => (
                  <VideoCard key={a.id} assetId={a.id} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Virtual scroll grid */}
        {!showArchived && widthReady && (
          <AssetGridVirtual
            ref={virtualRef}
            scrollRef={scrollRef}
            display={display}
            cols={cols}
            gridError={gridError}
            initLoading={initLoading}
            gridPage={gridPage}
            gridHasMore={gridHasMore}
            gridTotal={gridTotal}
            showMore={showMore}
            filtering={filtering}
            showSkeleton={showSkeleton}
            sortOrder={sortOrder}
            navigatingYear={navigatingYear}
            setNavigatingYear={setNavigatingYear}
            allTimelineYears={yearsData}
            fetchPage={fetchPage}
            onYearChanged={onYearChanged}
            moreLoading={moreLoading}
            empty={empty}
            pageSize={PAGE_SIZE}
            loadNext={loadNext}
          />
        )}
      </div>

      {/* Year timeline sidebar */}
      {!showArchived && (
        <YearTimeline
          activeYear={visibleYear}
          activeDayKey={visibleDayKey}
          onYearClick={(y) => virtualRef.current?.scrollToYear(y)}
          onDayClick={(year, month, day) => { const key = [year, String(month).padStart(2, '0'), String(day).padStart(2, '0')].join('-'); virtualRef.current?.scrollToDate(key) }}
        />
      )}
    </div>
  )
}
