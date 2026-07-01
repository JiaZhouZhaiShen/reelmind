 import { useEffect, useState, useMemo, useRef, useCallback } from "react"
 import { BatchToolbar } from "../components/BatchToolbar"
 import { Search, Film, Monitor, Smartphone, FileText, MessageSquareText, Tag, Image, Sparkles, Video } from "lucide-react"
 import { useStore } from "../stores/app"
 import { SearchBar } from "../components/SearchBar"
 import { SearchResultCard } from "../components/SearchResultCard"
 import { useNavigate } from "react-router-dom"
 import { useTranslation } from "react-i18next"
 import { useVirtualizer } from "@tanstack/react-virtual"
 import { useMarqueeSelection } from "../hooks/useMarqueeSelection"
 import { toPseudoAsset } from "../utils/search"
 import { formatCount } from "../utils/format"
 import type { Asset, SearchResult } from "../api/client"

const COL_BREAKPOINTS = [
  [1536, 6], [1280, 5], [1024, 4], [768, 3], [0, 2],
] as const

const GRID_ROW_HEIGHT = 204
const LOAD_MORE_THRESHOLD = 800

type VirtualRow = { type: "grid"; key: string; assets: Asset[]; searchResults: SearchResult[] } | { type: "loading"; key: string }

type SourceFilter = "all" | "metadata" | "transcript" | "object" | "ocr" | "visual"

interface FilterOption {
  key: SourceFilter
  icon: typeof Sparkles
  label: string
  color: string
}

const FILTER_OPTIONS: FilterOption[] = [
  { key: "all", icon: Sparkles, label: "\u5168\u90e8", color: "text-gray-400" },
  { key: "metadata", icon: FileText, label: "\u6587\u4ef6\u540d", color: "text-gray-400" },
  { key: "transcript", icon: MessageSquareText, label: "\u5b57\u5e55", color: "text-gray-400" },
  { key: "object", icon: Tag, label: "\u6807\u8bc6", color: "text-gray-400" },
  { key: "ocr", icon: FileText, label: "OCR", color: "text-gray-400" },
  { key: "visual", icon: Image, label: "\u573a\u666f", color: "text-gray-400" },
]


function getOrientation(w?: number, h?: number): "landscape" | "portrait" | "square" | undefined {
  if (!w || !h) return undefined
  if (w === h) return "square"
  return w > h ? "landscape" : "portrait"
}

type OrientationFilter = "all" | "landscape" | "portrait"

export function SearchPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const searchQuery = useStore((s) => s.searchQuery)
  const setSearchQuery = useStore((s) => s.setSearchQuery)
  const searchResults = useStore((s) => s.searchResults)
  const searchTotal = useStore((s) => s.searchTotal)
  const searchPage = useStore((s) => s.searchPage)
  const searchHasMore = useStore((s) => s.searchHasMore)
  const searchInitLoading = useStore((s) => s.searchInitLoading)
  const searchMoreLoading = useStore((s) => s.searchMoreLoading)
  const searchError = useStore((s) => s.searchError)
  const searchLoadResults = useStore((s) => s.searchLoadResults)
  const clearError = useStore((s) => s.clearError)

  // ── UI-only local state ──
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all")
  const [orientationFilter, setOrientationFilter] = useState<OrientationFilter>("all")

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

  // ── Trigger search when query changes ──
  useEffect(() => {
    if (searchQuery) {
      searchLoadResults(1, false)
    }
  }, [searchQuery])

  // ── Infinite scroll detection ──
  const handleScroll = useCallback(() => {
    if (!scrollRef.current || !searchHasMore || searchMoreLoading || searchInitLoading) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    if (scrollHeight - scrollTop - clientHeight < LOAD_MORE_THRESHOLD) {
      searchLoadResults(searchPage + 1, true)
    }
  }, [searchHasMore, searchMoreLoading, searchInitLoading, searchPage, searchLoadResults])

  // ── Source filter ──
  const sourceFiltered = useMemo(() => {
    if (sourceFilter === "all") return searchResults
    return searchResults.filter((r) => (r.match_sources ?? []).includes(sourceFilter))
  }, [searchResults, sourceFilter])

  // ── Orientation filter ──
  const filteredResults = useMemo(() => {
    if (orientationFilter === "all") return sourceFiltered
    return sourceFiltered.filter((r) => {
      const o = getOrientation(r.width, r.height)
      return o === orientationFilter
    })
  }, [sourceFiltered, orientationFilter])

  // ── Source stats ──
  const sourceStats = useMemo(() => {
    const stats: Record<string, number> = { all: searchResults.length }
    for (const r of searchResults) {
      for (const src of r.match_sources ?? []) {
        stats[src] = (stats[src] || 0) + 1
      }
    }
    return stats
  }, [searchResults])

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
  const skeletonCols = cols || 4
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
      {!searchQuery && !searchInitLoading && (
        <div className="flex flex-col items-center justify-center min-h-screen -mt-16 px-4">
          <div className="mb-8 flex flex-col items-center gap-1">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-sm mb-4">
              <Video className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-4xl font-semibold tracking-tight text-white">ReelMind</h1>
            <p className="text-sm text-gray-500 mt-1.5">搜索你的视频库</p>
          </div>
          <div className="w-full max-w-lg">
            <SearchBar />
          </div>
          <div className="mt-8 flex items-center gap-2 text-sm text-gray-500">
            <span>试试搜索:</span>
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
      {(searchQuery || searchInitLoading) && (
        <div ref={contRef} className="flex h-full flex-1 min-w-0 overflow-hidden">
          <div className="flex-1 flex flex-col min-w-0 overflow-hidden max-w-7xl mx-auto w-full">
            {/* ── Header ── */}
            <div className="p-4 pb-2 shrink-0">
              <div className="flex items-center gap-4 mb-6">
                <div className="flex-1"><SearchBar /></div>
                {!searchInitLoading && (
                  <div className="flex items-center border border-gray-700 rounded-lg overflow-hidden shrink-0">
                    <button onClick={() => setOrientationFilter("all")}
                      className={"py-1.5 px-3 text-xs transition-colors " + (orientationFilter === "all" ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-gray-200")}>全部</button>
                    <button onClick={() => setOrientationFilter("landscape")}
                      className={"py-1.5 px-3 text-xs transition-colors flex items-center gap-1 " + (orientationFilter === "landscape" ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-gray-200")}>
                      <Monitor className="w-3.5 h-3.5" /><span>横屏</span></button>
                    <button onClick={() => setOrientationFilter("portrait")}
                      className={"py-1.5 px-3 text-xs transition-colors flex items-center gap-1 " + (orientationFilter === "portrait" ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-gray-200")}>
                      <Smartphone className="w-3.5 h-3.5" /><span>竖屏</span></button>
                  </div>
                )}
              </div>
              {searchQuery && (
                <div className="flex flex-col gap-2">
                  <p className="text-sm text-gray-400">
                    搜索 "<span className="text-gray-200">{searchQuery}</span>" — {formatCount(searchTotal)} 个结果
                  </p>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {FILTER_OPTIONS.map((opt) => {
                      const count = sourceStats[opt.key]
                      const isActive = sourceFilter === opt.key
                      return (
                        <button key={opt.key} onClick={() => setSourceFilter(opt.key)}
                          className={"inline-flex items-center gap-1 py-1.5 px-3 text-xs rounded-lg transition-colors " + (isActive ? "bg-gray-700 text-white border border-gray-600" : "bg-gray-800/60 text-gray-400 hover:text-gray-200 border border-gray-800 hover:border-gray-600")}>
                          <opt.icon className={"w-3 h-3 " + opt.color} />
                          <span>{opt.label}</span>
                          {count > 0 && <span className={"ml-0.5 text-[10px] " + (isActive ? "text-gray-400" : "text-gray-500")}>{count}</span>}
                        </button>
                      )
                    })}
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
                <p className="text-gray-400">没有找到匹配的结果</p>
                <p className="text-sm text-gray-500 mt-1">尝试其他关键词或调整筛选条件</p>
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
                                  <SearchResultCard key={sr.id} result={sr} />
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

