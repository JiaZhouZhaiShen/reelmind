import { useState, useEffect, useRef, useCallback } from 'react'
import { Calendar, ChevronDown, Loader2 } from 'lucide-react'
import { api, type Asset } from '../api/client'
import { VideoCard } from '../components/VideoCard'
import { YearTimeline } from '../components/YearTimeline'
import { BatchToolbar } from '../components/BatchToolbar'
import { useStore } from '../stores/app'
import { useLibraryStore } from '../stores/library'
import { useGridStore } from '../stores/grid'
import { useAssetStore } from '../stores/asset'
import { useTranslation } from 'react-i18next'
import { useMarqueeSelection } from '../hooks/useMarqueeSelection'

interface DayInfo {
  month: number
  day: number
  count: number
}

function formatCount(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M"
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K"
  return String(n)
}

export function TimelineView() {
  const { t } = useTranslation()
  const selectedLibraryId = useLibraryStore((s) => s.selectedLibraryId)
  const years = useGridStore(s => s.gridTimelineYears)

  const [expandedYears, setExpandedYears] = useState<Set<number>>(new Set())
  const [yearDays, setYearDays] = useState<Record<number, DayInfo[]>>({})
  const [dayAssets, setDayAssets] = useState<Record<string, Asset[]>>({})
  const [loadingFlags, setLoadingFlags] = useState<Record<string, boolean>>({})
  const [visibleYear, setVisibleYear] = useState<number | null>(null)
  const [visibleDayKey, setVisibleDayKey] = useState<string | null>(null)

  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const yearDaysRef = useRef(yearDays)
  yearDaysRef.current = yearDays
  const dayAssetsRef = useRef(dayAssets)
  dayAssetsRef.current = dayAssets

  const dayKey = (y: number, m: number, d: number) => `${y}-${m}-${d}`
  const isLoading = (key: string) => loadingFlags[key] === true

  // Load all years on mount
  useEffect(() => {
    (async () => {
      setLoadingFlags(f => ({ ...f, loadYears: true }))
      try {
        const data = await api.timelineYears(selectedLibraryId || undefined)
        useGridStore.setState({ gridTimelineYears: data })
     } catch (e) {
       console.error('Failed to load timeline years:', e)
        useStore.setState({ error: t('timelineView.yearLoadFailed') + ': ' + ((e as any).message || e) })
     } finally {
        setLoadingFlags(f => ({ ...f, loadYears: false }))
      }
    })()
  }, [selectedLibraryId])

  const handleYearToggle = async (year: number) => {
    const next = new Set(expandedYears)
    if (next.has(year)) {
      next.delete(year)
    } else {
      next.add(year)
      if (!yearDaysRef.current[year]) {
        const flagKey = `year-${year}`
        setLoadingFlags(f => ({ ...f, [flagKey]: true }))
        try {
          const data = await api.timelineDaysByYear(year, selectedLibraryId || undefined)
          setYearDays(prev => ({ ...prev, [year]: data }))
       } catch (e) {
         console.error('Failed to load days:', e)
          useStore.setState({ error: t('timelineView.dayLoadFailed') + ': ' + ((e as any).message || e) })
       } finally {
          setLoadingFlags(f => ({ ...f, [flagKey]: false }))
        }
      }
    }
    setExpandedYears(next)
  }

  const loadDayAssets = async (year: number, month: number, day: number) => {
    const key = dayKey(year, month, day)
    if (dayAssetsRef.current[key]) return
    const flagKey = `day-${key}`
    setLoadingFlags(f => ({ ...f, [flagKey]: true }))
    try {
     const data = await api.timelineAssets(year, month, day, selectedLibraryId || undefined)
      const byId: Record<string, Asset> = {}
      for (const item of data) byId[item.id] = item
      useStore.setState((s) => ({ assetsById: { ...s.assetsById, ...byId } }))
     setDayAssets(prev => ({ ...prev, [key]: data }))
   } catch (e) {
     console.error('Failed to load assets:', e)
      useStore.setState({ error: t('timelineView.assetLoadFailed') + ': ' + ((e as any).message || e) })
   } finally {
      setLoadingFlags(f => ({ ...f, [flagKey]: false }))
    }
  }

  // Single IntersectionObserver for both year/day tracking and lazy asset loading
  useEffect(() => {
    const yearSections = document.querySelectorAll('[id^="year-section-"]')
    const daySections = document.querySelectorAll('[id^="day-section-"]')

    const observer = new IntersectionObserver(
      (entries) => {
        let currentYear: number | null = null
        let currentDayKey: string | null = null

        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          const el = entry.target

          if (el.id.startsWith('year-section-')) {
            const yr = parseInt(el.getAttribute('data-year') || '0', 10)
            if (yr) currentYear = yr
          } else if (el.id.startsWith('day-section-')) {
            const dk = el.getAttribute('data-day-key')
            if (dk) {
              currentDayKey = dk
              // Trigger asset loading when day enters viewport
              const y = parseInt(el.getAttribute('data-year') || '0', 10)
              const m = parseInt(el.getAttribute('data-month') || '0', 10)
              const d = parseInt(el.getAttribute('data-day') || '0', 10)
              if (y && m && d) loadDayAssets(y, m, d)
            }
            const yr = parseInt(el.getAttribute('data-year') || '0', 10)
            if (yr) currentYear = yr
          }
        }

        if (currentYear !== null) setVisibleYear(currentYear)
        if (currentDayKey !== null) setVisibleDayKey(currentDayKey)
      },
      { rootMargin: '-60px 0px -60% 0px', threshold: 0 }
    )

    yearSections.forEach(el => observer.observe(el))
    daySections.forEach(el => observer.observe(el))
    return () => observer.disconnect()
  }, [years, expandedYears, yearDays])

  // ── Batch selection toolbar ──
  const allLoadedAssets = Object.values(dayAssets).flat()

  const refreshTimeline = useCallback(async () => {
    const yearsToRefresh = Array.from(expandedYears)
    for (const year of yearsToRefresh) {
      try {
        const data = await api.timelineDaysByYear(year, selectedLibraryId || undefined)
        setYearDays(prev => ({ ...prev, [year]: data }))
        setDayAssets(prev => {
          const next = { ...prev }
          for (const key of Object.keys(next)) {
            if (key.startsWith(`${year}-`)) delete next[key]
          }
          return next
        })
     } catch (e) {
       console.error('Failed to refresh days:', e)
        useStore.setState({ error: t('timelineView.refreshFailed') + ': ' + ((e as any).message || e) })
     }
    }
 }, [expandedYears, selectedLibraryId])
 

  useMarqueeSelection(scrollContainerRef)

 const mainLoading = loadingFlags['loadYears']
 const totalCount = years.reduce((s, y) => s + y.count, 0)

  return (
    <div className="h-full flex overflow-hidden">
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto scroll-smooth">
        <div className="p-6 pb-32 max-w-7xl mx-auto w-full">
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Calendar className="w-6 h-6 text-gray-500" />
              <span>{t('timeline.title')}</span>
            </h1>
            <p className="text-sm text-gray-500 mt-1">{years.length} years · {formatCount(totalCount)} assets</p>

          </div>

          <BatchToolbar currentAssets={allLoadedAssets} onRefresh={refreshTimeline} />

         {mainLoading && (
            <div className="space-y-6">
              {Array.from({ length: 6 }, (_, i) => (
                <div key={i} className="w-full flex items-center gap-3 px-4 py-3 rounded-lg bg-gray-900 border border-gray-800 animate-pulse">
                  <div className="w-10 h-10 rounded-lg bg-gray-800" />
                  <div className="flex-1">
                    <div className="h-5 bg-gray-800 rounded w-16 mb-1" />
                    <div className="h-3 bg-gray-800 rounded w-24" />
                  </div>
                  <div className="w-5 h-5 bg-gray-800 rounded" />
                </div>
              ))}
            </div>
          )}

          {!mainLoading && (
            <div className="space-y-6">
              {years.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-24 text-gray-500">
                  <Calendar className="w-12 h-12 mb-3 text-gray-500" />
                  <p className="text-gray-400 text-lg mb-1">{t('timeline.noMediaDate')}</p>
                  <p className="text-sm text-gray-500">{t('timeline.noMediaDateHint')}</p>
                </div>
              ) : years.map(({ year, count }) => {
                const isYearOpen = expandedYears.has(year)
                const days = yearDays[year]
                return (
                  <section key={year} id={`year-section-${year}`} data-year={year} className="scroll-mt-20">
                    <button
                      onClick={() => handleYearToggle(year)}
                      className="w-full flex items-center gap-3 px-4 py-3 rounded-lg bg-gray-900 border border-gray-800 hover:border-indigo-500/40 transition-all group cursor-pointer"
                    >
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center transition-colors ${isYearOpen ? 'bg-indigo-600/20' : 'bg-gray-800'}`}>
                        <Calendar className={`w-5 h-5 ${isYearOpen ? 'text-indigo-400' : 'text-gray-500 group-hover:text-gray-400'} transition-colors`} />
                      </div>
                      <div className="flex-1 text-left">
                        <h2 className="text-2xl font-bold text-white group-hover:text-indigo-300 transition-colors">{year}</h2>
                        <p className="text-sm text-gray-500">{count} {t('timeline.items')}</p>
                      </div>
                      {isLoading(`year-${year}`) ? (
                        <Loader2 className="w-5 h-5 animate-spin text-indigo-400" />
                      ) : (
                        <ChevronDown className={`w-5 h-5 text-gray-500 transition-transform duration-200 ${isYearOpen ? 'rotate-180' : ''}`} />
                      )}
                    </button>

                    {isYearOpen && days && (
                      <div className="ml-6 mt-3 space-y-6 border-l-2 border-gray-800 pl-6">
                        {days.map(({ month, day, count: dayCount }) => {
                          const dKey = dayKey(year, month, day)
                          const assets = dayAssets[dKey]
                          return (
                            <div
                              key={dKey}
                              id={`day-section-${dKey}`}
                              data-year={year}
                              data-month={month}
                              data-day={day}
                              data-day-key={dKey}
                              className="relative scroll-mt-20"
                            >
                              <div className="flex items-center gap-3 mb-2.5">
                                <div className="absolute -left-[26px] w-3 h-3 rounded-full border-2 border-gray-600 bg-gray-950" />
                                <span className="text-sm font-semibold text-gray-200">
                                  {year}/{String(month).padStart(2, '0')}/{String(day).padStart(2, '0')}
                                </span>
                                <span className="text-xs text-gray-500">({dayCount})</span>
                                {assets && assets.length > 0 && (
                                  <button
                                    onClick={(e) => { e.stopPropagation(); useAssetStore.getState().selectAllAssets(assets.map(a => a.id)); }}
                                    className="ml-2 text-xs text-indigo-500 hover:text-indigo-400 transition-colors"
                                  >
                                    {t("timelineView.selectAllDay")}
                                  </button>
                                )}
                              </div>

                             {isLoading(`day-${dKey}`) ? (
                                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2">
                                  {Array.from({ length: 4 }, (_, i) => (
                                    <div key={i} className="bg-gray-900 rounded-lg overflow-hidden border border-gray-800 animate-pulse">
                                      <div className="aspect-video bg-gray-800" style={{ minHeight: 112 }} />
                                      <div className="p-3 space-y-2">
                                        <div className="h-3 bg-gray-800 rounded w-3/4" />
                                        <div className="h-2 bg-gray-800 rounded w-1/2" />
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              ) : assets && assets.length > 0 ? (
                                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2">
                                  {assets.map(asset => (
                                    <VideoCard key={asset.id} assetId={asset.id} />
                                  ))}
                                </div>
                              ) : !assets ? (
                                    <div className="text-xs text-gray-500 pl-4 italic">{t("timelineView.scrollToLoad")}</div>
                              ) : null}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </section>
                )
              })}
            </div>
          )}
        </div>
      </div>

      <YearTimeline
        activeYear={visibleYear}
        activeDayKey={visibleDayKey}
        onYearClick={(year) => {
          const el = document.getElementById(`year-section-${year}`)
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }}
        onDayClick={(year, month, day) => {
          const el = document.getElementById(`day-section-${dayKey(year, month, day)}`)
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }}
      />
    </div>
  )
}


