import { useEffect, useMemo, useRef, useCallback, forwardRef, useImperativeHandle } from 'react'
import { useTranslation } from 'react-i18next'
import type { RefObject } from 'react'
import { Film, Loader2, CalendarDays } from 'lucide-react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { VideoCard } from '../components/VideoCard'
import { SkeletonCard, groupByDate, VirtualRow } from './AssetGridUtils'
import type { Asset } from '../api/client'

export interface AssetGridVirtualHandle {
  scrollToYear: (year: number) => Promise<void>
  scrollToDate: (k: string) => void
}

interface AssetGridVirtualProps {
  display: Asset[]
  cols: number
  gridError: string | null
  initLoading: boolean
  gridPage: number
  gridHasMore: boolean
  gridTotal: number
  showMore: boolean
  filtering: boolean
  showSkeleton: boolean
  sortOrder: 'asc' | 'desc'
  navigatingYear: number | null
  setNavigatingYear: (v: number | null) => void
  allTimelineYears: Array<{year: number; count: number}>
  fetchPage: (page: number, append: boolean) => Promise<void>
  onYearChanged: (year: number | null, dayKey: string | null) => void
  moreLoading: boolean
  scrollRef: RefObject<HTMLDivElement | null>
  empty: boolean
  pageSize: number
  loadNext: () => void
}

export const AssetGridVirtual = forwardRef<AssetGridVirtualHandle, AssetGridVirtualProps>(function AssetGridVirtual(props, ref) {
  const {
    display, cols, gridError, initLoading, gridPage, gridTotal,
    showMore, filtering, showSkeleton, sortOrder,
    navigatingYear, setNavigatingYear, allTimelineYears,
    fetchPage, onYearChanged, moreLoading, empty, pageSize, loadNext, scrollRef
  } = props

  // scrollRef comes from props
  // ── Dynamic grid column class, matches the `cols` prop ──
  const gridColsClass = useMemo(() => {
    const map: Record<number, string> = {
      2: 'grid-cols-2',
      3: 'grid-cols-3',
      4: 'grid-cols-4',
      5: 'grid-cols-5',
      6: 'grid-cols-6',
    }
    return map[cols] || 'grid-cols-5'
  }, [cols])

  const loadingYearRef = useRef<number | null>(null)
  const { t } = useTranslation()

  const { groups, noDate } = useMemo(() => groupByDate(display, sortOrder), [display, sortOrder])

  const virtualRows = useMemo((): VirtualRow[] => {
    const rs: VirtualRow[] = []
    for (const g of groups) {
      rs.push({ type: 'header', key: 'h-' + g.dateKey, dateKey: g.dateKey, dayLabel: g.dayLabel, count: g.assets.length, year: g.year })
      const chunks: Asset[][] = []
      for (let i = 0; i < g.assets.length; i += cols) chunks.push(g.assets.slice(i, i + cols))
      for (let i = 0; i < chunks.length; i++) rs.push({ type: 'grid', key: 'g-' + g.dateKey + '-' + i, dateKey: g.dateKey, assets: chunks[i] })
    }
    if (noDate && noDate.length > 0) {
      rs.push({ type: 'header', key: 'nd-header', dateKey: 'no-date', dayLabel: t('assetGridVirtual.uncategorized'), count: noDate.length, year: 0 })
      const chunks2: Asset[][] = []
      for (let i = 0; i < noDate.length; i += cols) chunks2.push(noDate.slice(i, i + cols))
      for (let i = 0; i < chunks2.length; i++) rs.push({ type: 'grid', key: 'nd-' + i, dateKey: 'no-date', assets: chunks2[i] })
    }
    if (showMore && !filtering) rs.push({ type: 'loading', key: 'lm' })
    return rs
  }, [groups, noDate, cols, showMore, filtering])

  const estimateSize = useCallback((i: number) => virtualRows[i]?.type === 'header' ? 40 : 204, [virtualRows])

  const virtualizer = useVirtualizer({
    count: virtualRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize,
    overscan: 15,
  })

  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    if (scrollHeight - scrollTop - clientHeight < 800 && showMore && !moreLoading) {
      loadNext()
    }
  }, [showMore, moreLoading, loadNext])

  const updateVisibleItems = useCallback(() => {
    if (!scrollRef.current) return
    const { scrollTop } = scrollRef.current
    const cur = virtualizer.getVirtualItemForOffset(scrollTop)
    if (!cur) return
    let foundYear: number | null = null
    let foundDayKey: string | null = null
    for (let i = cur.index; i >= 0; i--) {
      const row = virtualRows[i]
      if (!row || row.type !== 'header' || !row.dateKey) continue
      foundYear = row.year ?? null
      foundDayKey = row.dateKey
      break
    }
    onYearChanged(foundYear, foundDayKey)
  }, [virtualizer, virtualRows, onYearChanged])

  useEffect(() => {
    if (scrollRef.current && !initLoading && virtualizer.getVirtualItems().length > 0) updateVisibleItems()
  }, [initLoading, updateVisibleItems, virtualizer])

  const scrollToDate = useCallback((k: string) => {
    const idx = virtualRows.findIndex((r) => r.type === 'header' && r.dateKey === k)
    if (idx >= 0) virtualizer.scrollToIndex(idx, { align: 'start', behavior: 'smooth' })
  }, [virtualRows, virtualizer])

  const scrollToYear = useCallback(async (year: number): Promise<void> => {
    const firstGroup = groups.find((g) => g.year === year)
    if (firstGroup) { scrollToDate(firstGroup.dateKey); return }
    if (allTimelineYears.length > 0) {
      const sorted = [...allTimelineYears].sort((a, b) => b.year - a.year)
      const target = sorted.find((y) => y.year === year)
      if (target) {
        const newerCount = sorted.filter((y) => y.year > year).reduce((sum, y) => sum + y.count, 0)
        const estimatedStartPage = Math.floor(newerCount / pageSize) + 1
        const estimatedEndPage = Math.ceil((newerCount + target.count) / pageSize)
        const maxPage = Math.ceil(gridTotal / pageSize)
        setNavigatingYear(year)
        loadingYearRef.current = year
        const pages: number[] = []
        for (let p = estimatedStartPage; p <= Math.min(estimatedEndPage, maxPage); p++) pages.push(p)
        if (pages.length === 0) { setNavigatingYear(null); return }
        try {
          await Promise.all(pages.map((p) => fetchPage(p, true).catch(() => null)))
          if (loadingYearRef.current === year) {
            for (let attempt = 0; attempt < 3; attempt++) {
              await new Promise((r) => setTimeout(r, 100))
              const idx = virtualRows.findIndex((v) => v.type === 'header' && v.year === year)
              if (idx >= 0) { virtualizer.scrollToIndex(idx, { align: 'start', behavior: 'smooth' }); break }
            }
          }
        } catch { /* ignore */ }
        setNavigatingYear(null)
      }
    }
  }, [groups, allTimelineYears, gridTotal, pageSize, fetchPage, virtualRows, virtualizer, setNavigatingYear, scrollToDate])

  useImperativeHandle(ref, () => ({ scrollToYear, scrollToDate }), [scrollToYear, scrollToDate])

  /* ── Render ── */
  const loadingBar = navigatingYear !== null && moreLoading && (
    <div className="flex items-center justify-center gap-2 px-4 py-2 shrink-0 bg-indigo-900/20 border-b border-indigo-800/30">
      <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
      <span className="text-sm text-indigo-300">{'正在定位'} {navigatingYear} {'年的数据...'}</span>
    </div>
  )

  const skeleton = showSkeleton && (
    <div className="flex-1 overflow-hidden px-4 pb-4">
      <div className={"grid " + gridColsClass + " gap-4"}>
        {Array.from({ length: cols * 6 }).map((_, i) => <SkeletonCard key={i} />)}
      </div>
    </div>
  )

  const error = gridError && !initLoading && (
    <div className="flex flex-col items-center justify-center flex-1 text-gray-400">
      <p className="text-sm mb-3 text-red-400">{gridError}</p>
      <button onClick={() => fetchPage(gridPage, false)}
        className="px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-500 transition-colors">{'重试'}</button>
    </div>
  )

  const emptyState = empty && !showSkeleton && !initLoading && (
    <div className="flex flex-col items-center justify-center flex-1 text-gray-500 px-4 pb-4">
      <Film className="w-16 h-16 mb-4 text-gray-700" />
      <h2 className="text-xl font-medium text-gray-400 mb-2">{'没有视频'}</h2>
      <p className="text-sm text-gray-600 mb-4">{'请先创建库并导入视频'}</p>
      <a href="/libraries" className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-500 transition-colors">{'前往库管理'}</a>
    </div>
  )

  const grid = !showSkeleton && !initLoading && display.length > 0 && (
    <>
      <div ref={scrollRef as React.LegacyRef<HTMLDivElement>} onScroll={handleScroll} className="flex-1 overflow-y-auto" style={{ contain: 'strict' }}>
        <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
          {virtualizer.getVirtualItems().map((virtualItem) => {
            const row = virtualRows[virtualItem.index]
            if (!row) return null
            return (
              <div key={virtualItem.key} data-index={virtualItem.index} ref={virtualizer.measureElement}
                style={{ position: 'absolute', top: 0, left: 0, width: '100%', transform: 'translateY(' + virtualItem.start + 'px)' }}>
                {row.type === 'header' && (
                  <div className="flex items-center gap-2 px-4 py-2 bg-gray-900/95 border-b border-gray-800 sticky top-0 z-10" style={{ height: 40 }}>
                    <CalendarDays className="w-4 h-4 text-gray-500 shrink-0" />
                    <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">{row.dayLabel}</h3>
                    <span className="text-xs text-gray-600 font-normal">{row.dateKey}</span>
                  </div>
                )}
                {row.type === 'grid' && (
                  <div className={"grid " + gridColsClass + " gap-4 px-4 pb-4 pt-2"}>
                    {row.assets!.map((a: Asset) => <VideoCard key={a.id} assetId={a.id} />)}
                  </div>
                )}
                {row.type === 'loading' && (
                  <div className="flex items-center justify-center py-4">
                    {moreLoading ? (
                      <><Loader2 className="w-5 h-5 animate-spin text-indigo-400 mr-2" /><span className="text-sm text-gray-400">{'加载中...'}</span></>
                    ) : (
                      <span className="text-sm text-gray-400">{'滚动加载更多...'}</span>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
      {moreLoading && (
        <div className="flex items-center justify-center py-4 shrink-0">
          <Loader2 className="w-5 h-5 animate-spin text-indigo-400 mr-2" />
          <span className="text-sm text-gray-400">{'加载更多视频...'}</span>
        </div>
      )}
    </>
  )

  return <>{loadingBar}{skeleton}{error}{emptyState}{grid}</>
})
