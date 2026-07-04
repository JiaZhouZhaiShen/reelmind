 import { useEffect, useState, useMemo, useRef, useCallback } from "react"
import { BatchToolbar } from "../components/BatchToolbar"
import { useTranslation } from 'react-i18next'
 import { Film, Monitor, Smartphone, FileText, MessageSquareText, Tag, Image, Sparkles, Video, ChevronDown, Search, Users } from "lucide-react"
 import { useSearchStore } from '../stores/search'
import { useStore } from '../stores/app'
 import { SearchBar } from "../components/SearchBar"
 import { SearchVideoCard } from "../components/SearchVideoCard"
 import { useNavigate } from "react-router-dom"
 import { useVirtualizer } from "@tanstack/react-virtual"
 import { useMarqueeSelection } from "../hooks/useMarqueeSelection"
 import { toPseudoAsset } from "../utils/search"
 import { formatCount } from "../utils/format"
 import type { Asset, SearchResult } from "../api/client"
const COL_BREAKPOINTS = [
  [1536, 6], [1024, 5], [768, 3], [0, 2],
] as const
const GRID_ROW_HEIGHT = 204
const LOAD_MORE_THRESHOLD = 800
type VirtualRow = { type: "grid"; key: string; assets: Asset[]; searchResults: SearchResult[] } | { type: "loading"; key: string }
 type SourceFilter = "all" | "scene" | "tag" | "ocr" | "clip" | "transcript" | "diarization"
interface FilterOption {
  key: SourceFilter
  icon: typeof Sparkles
  color: string
}
const FILTER_OPTIONS: FilterOption[] = [
  { key: "all", icon: Sparkles, color: "text-gray-400" },
  { key: "scene", icon: Image, color: "text-gray-400" },
  { key: "tag", icon: Tag, color: "text-gray-400" },
  { key: "ocr", icon: FileText, color: "text-gray-400" },
  { key: "clip", icon: Search, color: "text-gray-400" },
  { key: "transcript", icon: MessageSquareText, color: "text-gray-400" },
  { key: "diarization", icon: Users, color: "text-gray-400" },
]
function getOrientation(w?: number, h?: number): "landscape" | "portrait" | "square" | undefined {
  if (!w || !h) return undefined
  if (w === h) return "square"
  return w > h ? "landscape" : "portrait"
}
type OrientationFilter = "all" | "landscape" | "portrait"
// ── Compact custom dropdown ──
function CompactSelect({ value, options, onChange }: {
  value: string
  options: { value: string; label: string }[]
  onChange: (v: string) => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])
  const selected = options.find(o => o.value === value)
  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="border-0 bg-gray-800/40 text-gray-300 rounded-lg px-2 py-1 text-xs focus:outline-none cursor-pointer flex items-center gap-1"
      >
        <span>{selected?.label || value}</span>
        <ChevronDown className="w-3 h-3 text-gray-500" />
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 bg-gray-800 border border-gray-700 rounded-lg shadow-lg min-w-[90px] overflow-hidden">
          {options.map((opt) => (
            <button
              key={opt.value}
              onClick={() => { onChange(opt.value); setOpen(false) }}
              className={`w-full text-left px-3 py-1.5 text-xs transition-colors ${opt.value === value ? 'bg-indigo-600/20 text-indigo-400' : 'text-gray-300 hover:bg-gray-700'}`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
export function SearchPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const sourceLabel = (key: SourceFilter) => {
    switch (key) {
     case 'all': return t('common.all')
     case 'scene': return t('common.scene')
     case 'tag': return t('common.tagLabel')
     case 'ocr': return 'OCR'
     case 'clip': return t('searchPage.sourceClip')
     case 'transcript': return t('common.subtitle')
     case 'diarization': return t('searchPage.sourceDiarization')
      default: return key
    }
  }


  const searchQuery = useSearchStore((s) => s.searchQuery)
  const setSearchQuery = useSearchStore((s) => s.setSearchQuery)
  const searchResults = useSearchStore((s) => s.searchResults)
 const searchTotal = useSearchStore((s) => s.searchTotal)
  const sourceTotals = useSearchStore((s) => s.sourceTotals)
 const searchPage = useSearchStore((s) => s.searchPage)
  const searchHasMore = useSearchStore((s) => s.searchHasMore)
  const searchInitLoading = useSearchStore((s) => s.searchInitLoading)
  const searchMoreLoading = useSearchStore((s) => s.searchMoreLoading)
  const searchSourceFilter = useSearchStore((s) => s.searchSourceFilter)
  const searchOrientationFilter = useSearchStore((s) => s.searchOrientationFilter)
  const searchError = useSearchStore((s) => s.searchError)
  const searchLoadResults = useSearchStore((s) => s.searchLoadResults)
  const clearError = useStore((s) => s.clearError)
  const searchDurationMin = useSearchStore((s) => s.searchDurationMin)
  const searchDurationMax = useSearchStore((s) => s.searchDurationMax)
  const searchFileSizeMin = useSearchStore((s) => s.searchFileSizeMin)
  const searchFileSizeMax = useSearchStore((s) => s.searchFileSizeMax)
  const setSearchDurationFilter = useSearchStore((s) => s.setSearchDurationFilter)
  const setSearchFileSizeFilter = useSearchStore((s) => s.setSearchFileSizeFilter)
 const searchTriggerKey = useSearchStore((s) => s.searchTriggerKey)
  const resetSearch = useSearchStore((s) => s.resetSearch)
 // ── UI-only local state ──
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all")
  const [orientationFilter, setOrientationFilter] = useState<OrientationFilter>("all")
  const [durFilter, setDurFilter] = useState("all")
  const [customMinStr, setCustomMinStr] = useState("")
 const [customMaxStr, setCustomMaxStr] = useState("")
 const [sizeFilter, setSizeFilter] = useState("all")
  const savedRef = useRef(false)
 const SEARCH_SAVE_KEY = 'reelmind_search_state'
  // ── Sync restore: pre-set loading when saved filters exist without keyword ──
  useState(() => {
    try {
      const saved = sessionStorage.getItem(SEARCH_SAVE_KEY)
      if (saved) {
        const p = JSON.parse(saved)
        if (!p.q && (p.minDur !== undefined || p.maxDur !== undefined || p.minSize !== undefined || p.maxSize !== undefined)) {
          useSearchStore.setState({ searchInitLoading: true })
        }
      }
    } catch {}
    return true
  })
 // ── Responsive cols ──
  const contRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [contW, setContW] = useState(1200)
  useMarqueeSelection(scrollRef)
  const cols = useMemo(() => {
    for (const [minW, c] of COL_BREAKPOINTS) {
      if (contW >= minW) return c
    }
    return 2
  }, [contW])
  useEffect(() => {
    if (!contRef.current) return
    const ro = new ResizeObserver((es) => {
      for (const e of es) setContW(e.contentRect.width)
    })
    ro.observe(contRef.current)
   return () => ro.disconnect()
 }, [])
  // ── Restore search state from sessionStorage on mount ──
  useEffect(() => {
    if (savedRef.current) return
    savedRef.current = true
    try {
      const saved = sessionStorage.getItem(SEARCH_SAVE_KEY)
      if (saved) {
        const p = JSON.parse(saved)
        if (p.q || p.maxDur !== undefined || p.minDur !== undefined) {
          if (p.q) setSearchQuery(p.q)
          if (p.minDur !== undefined || p.maxDur !== undefined) {
            setSearchDurationFilter(p.minDur, p.maxDur)
          }
          if (p.minSize !== undefined || p.maxSize !== undefined) {
            setSearchFileSizeFilter(p.minSize, p.maxSize)
          }
          if (p.durFilter) setDurFilter(p.durFilter)
          if (p.sizeFilter) setSizeFilter(p.sizeFilter)
          if (p.customMinStr) setCustomMinStr(p.customMinStr)
         if (p.customMaxStr) setCustomMaxStr(p.customMaxStr)
          // Trigger search when filters exist without keyword
          if (!p.q && (p.minDur !== undefined || p.maxDur !== undefined || p.minSize !== undefined || p.maxSize !== undefined)) {
            searchLoadResults(1, false)
          }
       }
     }
   } catch {}
  }, [])
  // ── Save search state to sessionStorage on every change ──
  useEffect(() => {
    if (!savedRef.current) return
    sessionStorage.setItem(SEARCH_SAVE_KEY, JSON.stringify({
      q: searchQuery,
      minDur: searchDurationMin,
      maxDur: searchDurationMax,
      minSize: searchFileSizeMin,
      maxSize: searchFileSizeMax,
      durFilter,
      sizeFilter,
      customMinStr,
      customMaxStr,
    }))
  }, [searchQuery, searchDurationMin, searchDurationMax, searchFileSizeMin, searchFileSizeMax, durFilter, sizeFilter, customMinStr, customMaxStr])
 // ── Trigger search when query/duration/size/source filter changes ──
  useEffect(() => {
    if (durFilter === "custom") {
      const min = customMinStr === "" ? undefined : Number(customMinStr)
      const max = customMaxStr === "" ? undefined : Number(customMaxStr)
      setSearchDurationFilter(min, max)
      if (searchQuery || searchResults.length > 0) searchLoadResults(1, false)
      return
    }

    if (searchQuery || searchResults.length > 0) {
      searchLoadResults(1, false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchTriggerKey, searchQuery, searchDurationMin, searchDurationMax, searchFileSizeMin, searchFileSizeMax, durFilter, searchSourceFilter, searchOrientationFilter, customMinStr, customMaxStr])
  // ── Infinite scroll detection ──
  const handleScroll = useCallback(() => {
    if (!scrollRef.current || !searchHasMore || searchMoreLoading || searchInitLoading) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    if (scrollHeight - scrollTop - clientHeight < LOAD_MORE_THRESHOLD) {
      searchLoadResults(searchPage + 1, true)
    }
  }, [searchHasMore, searchMoreLoading, searchInitLoading, searchPage, searchLoadResults])

  // ── Orientation filter ──
  const filteredResults = useMemo(() => {
    let results = searchResults
    // Client-side fallback: filter by AI engine status (Phase 2/3 may skip source_engine)
    if (sourceFilter !== "all") {
      const statusMap: Record<string, (r: SearchResult) => boolean> = {
        "scene": (r) => r.scene_status === "completed",
        "tag": (r) => r.has_yolo_tags === true,
        "ocr": (r) => r.has_ocr_text === true,
        "clip": (r) => r.clip_status === "completed",
        "transcript": (r) => r.transcript_status === "completed",
        "diarization": (r) => r.diarization_status === "completed",
      }
      const checker = statusMap[sourceFilter]
      if (checker) results = results.filter(checker)
    }
    return results
  }, [searchResults, sourceFilter])
  // ── Source stats ──
  const sourceStats = useMemo(() => {
    const stats: Record<string, number> = { all: searchTotal }
    stats["scene"] = sourceTotals?.scene || 0
    stats["tag"] = sourceTotals?.yolo || 0
    stats["ocr"] = sourceTotals?.ocr || 0
    stats["clip"] = sourceTotals?.clip || 0
    stats["transcript"] = sourceTotals?.transcript || 0
    stats["diarization"] = sourceTotals?.diarization || 0
    return stats
  }, [searchTotal, sourceTotals])
  // ── Convert filtered search results → pseudo Asset[], then chunk for virtual grid ──
  const allChunks = useMemo(() => {
    const assets = filteredResults.map(toPseudoAsset)
    const chunks: { assets: Asset[]; searchResults: SearchResult[] }[] = []
    for (let i = 0; i < assets.length; i += cols) {
      chunks.push({
        assets: assets.slice(i, i + cols),
        searchResults: filteredResults.slice(i, i + cols),
      })
    }
    return chunks
  }, [filteredResults, cols])
  // ── Virtual rows ──
  const virtualRows: VirtualRow[] = useMemo(() => {
    const rows: VirtualRow[] = []
    for (const [i, ch] of allChunks.entries()) {
      rows.push({ type: "grid", key: "g-" + i, assets: ch.assets, searchResults: ch.searchResults })
    }
    if (searchHasMore && !searchInitLoading) {
      rows.push({ type: "loading", key: "lm" })
    }
    return rows
  }, [allChunks, searchHasMore, searchInitLoading])
  const estimateSize = useCallback(
    (i: number) => {
      const r = virtualRows[i]
      if (!r) return GRID_ROW_HEIGHT
      if (r.type === "loading") return GRID_ROW_HEIGHT
      return GRID_ROW_HEIGHT
    },
    [virtualRows],
  )
  const virtualizer = useVirtualizer({
    count: virtualRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize,
    overscan: 4,
    getItemKey: (i) => virtualRows[i]?.key ?? String(i),
    measureElement: (el) => el.getBoundingClientRect().height,
  })
  // ── Skeleton grid for initial loading ──
  const skeletonCols = cols
  const skeletonRows = 3
  // ══════════════ Render ══════════════
  return (
    <>
      {/* Error banner */}
      {searchError && (
        <div className="fixed top-4 right-4 z-50 bg-red-900/80 border border-red-800/50 rounded-lg px-4 py-3 shadow-sm">
          <div className="flex items-center gap-2">
            <span className="text-sm text-red-400">{searchError}</span>
            <button onClick={() => clearError()} className="ml-2 text-gray-400 hover:text-gray-200 transition-colors">
              ✕
            </button>
          </div>
        </div>
      )}
      {/* Empty state — Google-style */}
      {!searchQuery && !searchInitLoading && searchResults.length === 0 && (
        <div className="flex flex-col items-center justify-center min-h-screen -mt-16 px-4">
          <div className="mb-8 flex flex-col items-center gap-1">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-sm mb-4">
              <Video className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-4xl font-semibold tracking-tight text-white">ReelMind</h1>
            <p className="text-sm text-gray-500 mt-1.5">{t('searchPage.searchLibrary')}</p>
          </div>
          <div className="w-full max-w-lg">
            <SearchBar />
          </div>
          <div className="w-full max-w-lg mt-4 flex items-center justify-center gap-2 text-sm">
            <span className="text-gray-400 shrink-0">{t('common.duration')}</span>
            <CompactSelect
              value={durFilter}
              options={[
                { value: 'all', label: t('common.all') },
                { value: 'le15', label: t('searchPage.durationLe15') },
                { value: 'le30', label: t('searchPage.durationLe30') },
                { value: 'le1m', label: t('searchPage.durationLe1m') },
                { value: 'le5m', label: t('searchPage.durationLe5m') },
                { value: 'le10m', label: t('searchPage.durationLe10m') },
                { value: 'ge10m', label: t('searchPage.durationGe10m') },
                { value: 'ge30m', label: t('searchPage.durationGe30m') },
                { value: 'custom', label: t('searchPage.durationCustom') },
              ]}
             onChange={(v) => {
               setDurFilter(v);
               if (v === "custom") return;
               const m = { all: [undefined, undefined], le15: [undefined, 15], le30: [undefined, 30], le1m: [undefined, 60], le5m: [undefined, 300], le10m: [undefined, 600], ge10m: [600, undefined], ge30m: [1800, undefined], custom: [undefined, undefined] };
               const p = m[v];
               setSearchDurationFilter(p[0], p[1]);
             }}
            />
            {durFilter === 'custom' && (
              <div className="flex items-center gap-1">
                <input type="number" min={0} value={customMinStr} placeholder="0"
                  onChange={(e) => setCustomMinStr(e.target.value)}
                  className="w-16 bg-gray-800/40 border border-gray-700 rounded-lg px-2 py-1 text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-indigo-500/60" />
                <span className="text-gray-500 text-xs">~</span>
                <input type="number" min={0} value={customMaxStr} placeholder="inf"
                  onChange={(e) => setCustomMaxStr(e.target.value)}
                  className="w-16 bg-gray-800/40 border border-gray-700 rounded-lg px-2 py-1 text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-indigo-500/60" />
                <span className="text-gray-500 text-xs">{t("searchPage.seconds")}</span>
              </div>
            )}
            <span className="text-gray-400 shrink-0 ml-2">{t('common.size')}</span>
            <CompactSelect
              value={sizeFilter}
              options={[
                { value: 'all', label: t('common.all') },
                { value: 'le100m', label: '≤100M' },
                { value: 'le500m', label: '≤500M' },
                { value: 'ge500m', label: '≥500M' },
                { value: 'ge1g', label: '≥1G' },
              ]}
              onChange={(v) => {
                setSizeFilter(v);
                const m: Record<string, (number | undefined)[]> = { all: [undefined, undefined], le100m: [undefined, 104857600], le500m: [undefined, 524288000], ge500m: [524288000, undefined], ge1g: [1073741824, undefined] };
                const p = m[v];
                setSearchFileSizeFilter(p[0], p[1]);
              }}
            />
          </div>
          <div className="mt-8 flex items-center gap-2 text-sm text-gray-500">
            <span>{t('searchPage.trySearch')}</span>
            <button onClick={() => { setSearchQuery("Car"); navigate("/search"); }}
              className="py-1.5 px-3 rounded-lg border border-gray-700/50 text-gray-400 hover:border-gray-500 hover:text-gray-300 cursor-pointer transition-colors">Car</button>
            <button onClick={() => { setSearchQuery("House"); navigate("/search"); }}
              className="py-1.5 px-3 rounded-lg border border-gray-700/50 text-gray-400 hover:border-gray-500 hover:text-gray-300 cursor-pointer transition-colors">House</button>
            <button onClick={() => { setSearchQuery("Sun"); navigate("/search"); }}
              className="py-1.5 px-3 rounded-lg border border-gray-700/50 text-gray-400 hover:border-gray-500 hover:text-gray-300 cursor-pointer transition-colors">Sun</button>
          </div>
        </div>
      )}
      {/* Results / searching state */}
      {(searchQuery || searchInitLoading || searchResults.length > 0) && (
        <div ref={contRef} className="flex h-full flex-1 min-w-0 overflow-hidden">
          <div className="flex-1 flex flex-col min-w-0 overflow-hidden max-w-7xl mx-auto w-full">
            {/* ── Header ── */}
            <div className="p-4 pb-10 shrink-0">
             <div className="flex justify-center mb-6">
              <div className="w-80 sm:w-96 flex items-center gap-4">
               <div className="flex-1 min-w-0"><SearchBar compact /></div>
              <button
                  onClick={() => {
                    resetSearch(); useSearchStore.setState({ searchSourceFilter: "all", searchOrientationFilter: "all" });
                    setDurFilter("all");
                    setSizeFilter("all");
                    setCustomMinStr("");
                    setCustomMaxStr("");
                    setOrientationFilter("all");
                    setSourceFilter("all");
                  }}
                 className={"text-gray-500 hover:text-gray-300 transition-colors shrink-0 " + (searchInitLoading ? 'invisible' : '')}
                 title={t('searchPage.backToHome')}
               >
                 ✕
               </button>
              </div>
             </div>
            {searchQuery && (
               <div className="flex flex-col gap-2">
                 <p className="text-sm text-gray-400 tabular-nums">
                  {t('searchPage.searchLabel')} "<span className="text-gray-200">{searchQuery}</span>" — {formatCount(searchTotal)} {t('searchPage.resultUnit')}
                 </p>
                 <div className="flex items-center gap-2 flex-wrap">
                   {FILTER_OPTIONS.map((opt) => {
                     const count = sourceStats[opt.key]
                     const isActive = sourceFilter === opt.key
                     return (
                       <button key={opt.key} onClick={() => { setSourceFilter(opt.key); useSearchStore.setState({ searchSourceFilter: opt.key }) }}
                         className={"inline-flex items-center gap-1 py-1.5 px-3 text-xs rounded-lg transition-colors " + (isActive ? "bg-gray-700 text-white border border-gray-600" : "bg-gray-800/60 text-gray-400 hover:text-gray-200 border border-gray-800 hover:border-gray-600")}>
                         <opt.icon className={"w-3 h-3 " + opt.color} />
                         <span>{sourceLabel(opt.key)}</span>
                         {count > 0 && <span className={"ml-0.5 text-[10px] " + (isActive ? "text-gray-400" : "text-gray-500")}>{count}</span>}
                       </button>
                    )
                   })}
                  {/* ── Orientation ── */}
                  <div className="w-px h-5 bg-gray-700 mx-1" />
                  <button onClick={() => { const next = orientationFilter === "landscape" ? "all" : "landscape"; setOrientationFilter(next); useSearchStore.setState({ searchOrientationFilter: next }) }}
                    className={"inline-flex items-center gap-1 py-1.5 px-3 text-xs rounded-lg transition-colors " + (orientationFilter === "landscape" ? "bg-indigo-600 text-white border border-indigo-500" : "bg-gray-800/60 text-gray-400 hover:text-gray-200 border border-gray-800 hover:border-gray-600")}>
                    <Monitor className="w-3.5 h-3.5" />
                    <span>{t('common.landscape')}</span>
                  </button>
                  <button onClick={() => { const next = orientationFilter === "portrait" ? "all" : "portrait"; setOrientationFilter(next); useSearchStore.setState({ searchOrientationFilter: next }) }}
                    className={"inline-flex items-center gap-1 py-1.5 px-3 text-xs rounded-lg transition-colors " + (orientationFilter === "portrait" ? "bg-indigo-600 text-white border border-indigo-500" : "bg-gray-800/60 text-gray-400 hover:text-gray-200 border border-gray-800 hover:border-gray-600")}>
                    <Smartphone className="w-3.5 h-3.5" />
                    <span>{t('common.portrait')}</span>
                  </button>
                 </div>
               </div>
             )}
              {!searchQuery && searchResults.length > 0 && (
                <div className="flex flex-col gap-2">
                  <p className="text-sm text-gray-400 tabular-nums">
                   {formatCount(searchTotal)} {t('searchPage.resultUnit')}
                  </p>
                  <div className="flex items-center gap-2 flex-wrap">
                    {FILTER_OPTIONS.map((opt) => {
                      const count = sourceStats[opt.key]
                      const isActive = sourceFilter === opt.key
                      return (
                        <button key={opt.key} onClick={() => { setSourceFilter(opt.key); useSearchStore.setState({ searchSourceFilter: opt.key }) }}
                          className={"inline-flex items-center gap-1 py-1.5 px-3 text-xs rounded-lg transition-colors " + (isActive ? "bg-gray-700 text-white border border-gray-600" : "bg-gray-800/60 text-gray-400 hover:text-gray-200 border border-gray-800 hover:border-gray-600")}>
                          <opt.icon className={"w-3 h-3 " + opt.color} />
                          <span>{sourceLabel(opt.key)}</span>
                          {count > 0 && <span className={"ml-0.5 text-[10px] " + (isActive ? "text-gray-400" : "text-gray-500")}>{count}</span>}
                        </button>
                     )
                    })}
                   {/* ── Orientation ── */}
                   <div className="w-px h-5 bg-gray-700 mx-1" />
                   <button onClick={() => { const next = orientationFilter === "landscape" ? "all" : "landscape"; setOrientationFilter(next); useSearchStore.setState({ searchOrientationFilter: next }) }}
                     className={"inline-flex items-center gap-1 py-1.5 px-3 text-xs rounded-lg transition-colors " + (orientationFilter === "landscape" ? "bg-indigo-600 text-white border border-indigo-500" : "bg-gray-800/60 text-gray-400 hover:text-gray-200 border border-gray-800 hover:border-gray-600")}>
                     <Monitor className="w-3.5 h-3.5" />
                     <span>{t('common.landscape')}</span>
                   </button>
                   <button onClick={() => { const next = orientationFilter === "portrait" ? "all" : "portrait"; setOrientationFilter(next); useSearchStore.setState({ searchOrientationFilter: next }) }}
                     className={"inline-flex items-center gap-1 py-1.5 px-3 text-xs rounded-lg transition-colors " + (orientationFilter === "portrait" ? "bg-indigo-600 text-white border border-indigo-500" : "bg-gray-800/60 text-gray-400 hover:text-gray-200 border border-gray-800 hover:border-gray-600")}>
                     <Smartphone className="w-3.5 h-3.5" />
                     <span>{t('common.portrait')}</span>
                   </button>
                  </div>
                </div>
              )}
            </div>
            {/* ── Initial loading — Skeleton ── */}
            {searchInitLoading && (
              <div className="flex-1 overflow-y-auto px-4">
                <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(" + skeletonCols + ", minmax(0, 1fr))" }}>
                  {Array.from({ length: skeletonCols * skeletonRows }).map((_, i) => (
                    <div key={i} className="animate-pulse rounded-lg bg-gray-900" style={{ aspectRatio: "16/9" }} />
                  ))}
                </div>
              </div>
            )}
            {/* ── No results ── */}
            {!searchInitLoading && searchQuery && filteredResults.length === 0 && !searchError && (
              <div className="flex flex-col items-center justify-center flex-1 text-gray-500">
                <Film className="w-16 h-16 mb-4 text-gray-500" />
                <p className="text-gray-400">{t('searchPage.noResults')}</p>
                <p className="text-sm text-gray-500 mt-1">{t('searchPage.tryAdjustFilters')}</p>
              </div>
            )}
            {/* ── Virtualized results grid ── */}
            {!searchInitLoading && filteredResults.length > 0 && (
              <>
                <BatchToolbar currentAssets={filteredResults.map((r) => ({ id: r.id }))} onRefresh={() => searchLoadResults(1, false)} />
                <div
                  ref={scrollRef}
                  onScroll={handleScroll}
                  className="flex-1 overflow-y-auto px-4"
                  style={{ contain: "size layout" }}
                >
                  <div style={{ height: virtualizer.getTotalSize() + "px", width: "100%", position: "relative" }}>
                    {virtualizer.getVirtualItems().map((virtualItem) => {
                      const row = virtualRows[virtualItem.index]
                      if (!row) return null
                      return (
                        <div
                          key={virtualItem.key}
                          data-index={virtualItem.index}
                          ref={virtualizer.measureElement}
                          style={{
                            position: "absolute",
                            top: 0,
                            left: 0,
                            width: "100%",
                            transform: "translateY(" + virtualItem.start + "px)",
                            willChange: "transform",
                          }}
                        >
                          {row.type === "grid" && (
                            <div
                              className="grid gap-4"
                              style={{ gridTemplateColumns: "repeat(" + cols + ", minmax(0, 1fr))" }}
                            >
                              {row.searchResults.map((sr: SearchResult) => {
                                return (
                                  <SearchVideoCard key={sr.id} resultId={sr.id} />
                                )
                              })}
                            </div>
                          )}
                          {row.type === "loading" && (
                            <div className="pb-4">
                              <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(" + cols + ", minmax(0, 1fr))" }}>
                                {Array.from({ length: cols }).map((_, si) => (
                                  <div key={si} className="animate-pulse rounded-lg bg-gray-900 overflow-hidden">
                                    <div className="aspect-video bg-gray-800" />
                                    <div className="p-3 space-y-2">
                                      <div className="h-3 bg-gray-800 rounded w-3/4" />
                                      <div className="h-2 bg-gray-800 rounded w-1/2" />
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}
