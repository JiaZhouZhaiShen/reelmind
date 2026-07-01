import { useEffect, useRef, useCallback, useState } from "react"
import { useLogsStore } from "../../stores/logs"
import {
  FileText, RefreshCw, ChevronDown, Loader2, Terminal,
  Search, Copy, Check, Play, Pause, AlertTriangle,
  Server,
} from "lucide-react"
import type { LogEntry } from "../../api/logs"
import ErrorDashboard from "./ErrorDashboard"

// ── Helpers ────────────────────────────────────────────────────────────────

const LEVEL_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  ERROR:    { bg: "bg-red-900/40", text: "text-red-300",  dot: "bg-red-400" },
  CRITICAL: { bg: "bg-red-900/40", text: "text-red-300",  dot: "bg-red-400" },
  WARNING:  { bg: "bg-amber-900/40", text: "text-amber-300",  dot: "bg-amber-400" },
  WARN:     { bg: "bg-amber-900/40", text: "text-amber-300",  dot: "bg-amber-400" },
  INFO:     { bg: "bg-emerald-900/40", text: "text-emerald-300", dot: "bg-emerald-400" },
  DEBUG:    { bg: "bg-gray-800/40", text: "text-gray-400",  dot: "bg-gray-500" },
}

const DEFAULT_COLOR = { bg: "bg-gray-800/40", text: "text-gray-300", dot: "bg-gray-500" }

const LEVEL_PILLS = ["All", "ERROR", "WARN", "INFO", "DEBUG"] as const
const TAIL_OPTIONS = [50, 100, 200, 500, 1000] as const

function getLevelColor(level: string) {
  return LEVEL_COLORS[level.toUpperCase()] || DEFAULT_COLOR
}

function formatTimestamp(ts: string): string {
  if (!ts) return ""
  const cleaned = ts.replace(",", ".")
  try {
    const dt = new Date(cleaned)
    if (!isNaN(dt.getTime())) {
      return dt.toLocaleTimeString("zh-CN", { hour12: false })
    }
  } catch { /* fall through */ }
  const parts = ts.split(/[T ]/)
  return parts.length > 1 ? parts[1]?.slice(0, 12) || ts : ts
}

function isTraceback(msg: string): boolean {
  return msg.includes("Traceback (most recent call last)")
}

// ── LogLine component ──────────────────────────────────────────────────────

function LogLine({ entry }: { entry: LogEntry }) {
  const [copied, setCopied] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const isTrace = isTraceback(entry.message)

  const handleCopy = useCallback(() => {
    const text = entry.raw || entry.message
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }).catch(() => {})
  }, [entry])

  const color = getLevelColor(entry.level)

  return (
    <div
      onClick={handleCopy}
      className={`
        group flex items-start gap-2 px-3 py-0.5 text-xs font-mono
        cursor-pointer transition-colors select-none
        hover:bg-white/[0.03] active:bg-white/[0.06]
        ${color.text}
      `}
    >
      <span className="shrink-0 text-[10px] text-gray-600 leading-5 w-[70px] text-right tabular-nums">
        {formatTimestamp(entry.timestamp)}
      </span>
      <span className={`shrink-0 mt-[7px] w-1.5 h-1.5 rounded-full ${color.dot}`} />
      <span className={`shrink-0 text-[10px] font-semibold leading-5 w-12 text-center rounded ${color.bg}`}>
        {entry.level}
      </span>
      {entry.logger && (
        <span className="shrink-0 text-[10px] text-gray-600 leading-5 w-16 truncate">
          {entry.logger}
        </span>
      )}
      <span className="leading-5 whitespace-pre-wrap break-all min-w-0 flex-1">
        {isTrace ? (
          <>
            <button
              onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}
              className="inline-flex items-center gap-1 text-red-400 hover:text-red-300 underline decoration-dashed underline-offset-2"
            >
              <ChevronDown className={`w-3 h-3 transition-transform ${expanded ? "rotate-0" : "-rotate-90"}`} />
              Traceback
            </button>
            {expanded && (
              <span className="block mt-0.5 text-red-300/70 whitespace-pre-wrap">
                {entry.message}
              </span>
            )}
          </>
        ) : (
          entry.message
        )}
      </span>
      <span className="shrink-0 leading-5 opacity-0 group-hover:opacity-100 transition-opacity">
        {copied ? (
          <Check className="w-3 h-3 text-emerald-400" />
        ) : (
          <Copy className="w-3 h-3 text-gray-600 hover:text-gray-400" />
        )}
      </span>
    </div>
  )
}

function SourceIcon({ type, status }: { type: string; status: string }) {
  if (type === "docker") {
    const running = status === "running"
    return (
      <span className={`shrink-0 ${running ? "text-emerald-400" : "text-gray-600"}`}>
        <Server className="w-3.5 h-3.5" />
      </span>
    )
  }
  return <FileText className="w-3.5 h-3.5 text-gray-500 shrink-0" />
}

export default function LogViewerPage() {
  const [activeTab, setActiveTab] = useState<"browse" | "dashboard">("browse")
  const sources = useLogsStore((s) => s.sources)
  const sourcesLoading = useLogsStore((s) => s.sourcesLoading)
  const sourcesError = useLogsStore((s) => s.sourcesError)
  const activeSourceId = useLogsStore((s) => s.activeSourceId)
  const activeSourceLabel = useLogsStore((s) => s.activeSourceLabel)
  const logs = useLogsStore((s) => s.logs)
  const totalLines = useLogsStore((s) => s.totalLines)
  const truncated = useLogsStore((s) => s.truncated)
  const logsLoading = useLogsStore((s) => s.logsLoading)
  const logsError = useLogsStore((s) => s.logsError)
  const levelFilter = useLogsStore((s) => s.levelFilter)
  const searchText = useLogsStore((s) => s.searchText)
  const tailCount = useLogsStore((s) => s.tailCount)
  const autoRefresh = useLogsStore((s) => s.autoRefresh)

  const fetchSources = useLogsStore((s) => s.fetchSources)
  const selectSource = useLogsStore((s) => s.selectSource)
  const fetchLogs = useLogsStore((s) => s.fetchLogs)
  const setLevelFilter = useLogsStore((s) => s.setLevelFilter)
  const setSearchText = useLogsStore((s) => s.setSearchText)
  const applySearch = useLogsStore((s) => s.applySearch)
  const setTailCount = useLogsStore((s) => s.setTailCount)
  const toggleAutoRefresh = useLogsStore((s) => s.toggleAutoRefresh)
  const refresh = useLogsStore((s) => s.refresh)

  const [searchFocused, setSearchFocused] = useState(false)
  const [showTailPicker, setShowTailPicker] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)
  const viewerRef = useRef<HTMLDivElement>(null)

  useEffect(() => { fetchSources() }, [])

  useEffect(() => {
    if (viewerRef.current && logs.length > 0) {
      viewerRef.current.scrollTop = viewerRef.current.scrollHeight
    }
  }, [logs])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault()
        searchRef.current?.focus()
      }
    }
    window.addEventListener("keydown", handler)

    return () => window.removeEventListener("keydown", handler)
  }, [])

  const dockerSources = sources.filter((s) => s.type === "docker")
  const fileSources = sources.filter((s) => s.type === "file")

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") applySearch()
  }

  const groupTitleStyle = "px-3 py-1.5 text-[10px] font-semibold text-gray-600 uppercase tracking-wider"
  const sourceItemBase = "w-full text-left px-3 py-1.5 text-xs rounded-md transition-colors flex items-center gap-2"

  return (
    <div className="h-full flex flex-col bg-gray-950 relative">
      {activeTab === "dashboard" && (
        <div className="absolute inset-0 z-10 bg-gray-950 overflow-y-auto">
          <div className="sticky top-0 z-20 flex items-center gap-3 px-4 h-9 border-b border-gray-800 bg-gray-900/90">
            <button
              onClick={() => setActiveTab("browse")}
              className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 hover:text-white transition-colors"
            >
              &larr; 返回日志浏览
            </button>
          </div>
          <ErrorDashboard />
        </div>
      )}
      {/* Toolbar */}
      <div className="shrink-0 flex items-center gap-3 px-4 py-2.5 border-b border-gray-800 bg-gray-900/80">
        <div className="flex items-center gap-2 mr-2">
          <Terminal className="w-4 h-4 text-indigo-400" />
          <h1 className="text-sm font-bold text-white">日志</h1>
        </div>

        <div className="flex items-center gap-0.5">
          {LEVEL_PILLS.map((l) => {
            const active = l === "All" ? levelFilter === null : levelFilter === l
            return (
              <button
                key={l}
                onClick={() => setLevelFilter(l === "All" ? null : l)}
                disabled={!activeSourceId}
                className={`
                  px-2 py-1 text-[11px] font-medium rounded transition-colors border
                  ${active
                    ? l === "All"
                      ? "bg-indigo-600/20 text-indigo-300 border-indigo-800/30"
                      : `${getLevelColor(l).bg} ${getLevelColor(l).text} border-transparent`
                    : "text-gray-500 hover:text-gray-300 border-transparent bg-transparent"
                  }
                  ${!activeSourceId ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}
                `}
              >
                {l}
              </button>
            )
          })}
        </div>

        <div className="w-px h-4 bg-gray-800" />

        <div className={`relative flex items-center flex-1 max-w-xs ${searchFocused ? "ring-1 ring-indigo-500/50" : ""}`}>
          <Search className="absolute left-2 w-3.5 h-3.5 text-gray-500 pointer-events-none" />
          <input
            ref={searchRef}
            type="text"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
            placeholder="搜索日志… (Ctrl+K)"
            disabled={!activeSourceId}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-7 pr-2 py-1 text-xs text-gray-200 placeholder-gray-600 focus:outline-none disabled:opacity-40 disabled:cursor-not-allowed"
          />
          {searchText && (
            <button onClick={applySearch} disabled={!activeSourceId}
              className="absolute right-1 px-1.5 py-0.5 text-[10px] font-medium text-indigo-400 hover:text-indigo-300 bg-gray-700/50 rounded disabled:opacity-40">
              搜索
            </button>
          )}
        </div>

        <div className="w-px h-4 bg-gray-800" />

        <div className="relative">
          <button onClick={() => setShowTailPicker(!showTailPicker)} disabled={!activeSourceId}
            className="flex items-center gap-1 px-2 py-1 bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 rounded-md text-xs transition-colors border border-gray-700/50 disabled:opacity-40 disabled:cursor-not-allowed">
            <span>{tailCount} 条</span>
            <ChevronDown className="w-3 h-3" />
          </button>
          {showTailPicker && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowTailPicker(false)} />
              <div className="absolute right-0 top-full mt-1 z-50 bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1 min-w-[100px]">
                {TAIL_OPTIONS.map((n) => (
                  <button key={n} onClick={() => { setTailCount(n); setShowTailPicker(false) }}
                    className={`flex items-center justify-between w-full text-left px-3 py-1.5 text-xs transition-colors ${tailCount === n ? "text-indigo-400 bg-indigo-900/20" : "text-gray-300 hover:bg-gray-700"}`}>
                    <span>{n} 条</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

          <div className="w-px h-4 bg-gray-800" />
          <button
            onClick={() => setActiveTab("browse")}
            className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded transition-colors ${activeTab === "browse" ? "text-white bg-gray-800" : "text-gray-600 hover:text-gray-300"}`}
          >
            日志浏览
          </button>
          <button
            onClick={() => setActiveTab("dashboard")}
            className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded transition-colors ${activeTab === "dashboard" ? "text-white bg-gray-800" : "text-gray-600 hover:text-gray-300"}`}
          >
            错误诊断
          </button>
        <button onClick={toggleAutoRefresh} disabled={!activeSourceId}
          className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-xs transition-colors border ${autoRefresh ? "bg-emerald-900/20 text-emerald-400 border-emerald-800/30 hover:bg-emerald-900/30" : "bg-gray-800 text-gray-400 border-gray-700/50 hover:bg-gray-700"} disabled:opacity-40 disabled:cursor-not-allowed`}>
          {autoRefresh ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
          <span>{autoRefresh ? "实时" : "手动"}</span>
        </button>

        <button onClick={refresh} disabled={!activeSourceId || logsLoading}
          className="flex items-center gap-1 px-2 py-1 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-600/50 text-white rounded-md text-xs transition-colors">
          <RefreshCw className={`w-3 h-3 ${logsLoading ? "animate-spin" : ""}`} />
          <span>刷新</span>
        </button>
      </div>

      <div className="flex-1 flex min-h-0">
        {/* Left panel */}
        <aside className="w-56 shrink-0 border-r border-gray-800 bg-gray-900/50 flex flex-col overflow-hidden">
          <div className="shrink-0 px-3 py-2 border-b border-gray-800">
            <span className="text-[11px] font-medium text-gray-500">日志源</span>
            <span className="text-[10px] text-gray-700 ml-1">({sources.length})</span>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-3">
            {sourcesLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
              </div>
            ) : sourcesError ? (
              <div className="px-3 py-4 text-xs text-red-400 bg-red-900/20 rounded-lg">{sourcesError}</div>
            ) : sources.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-gray-600">
                <FileText className="w-8 h-8 mb-2 text-gray-700" />
                <p className="text-xs">没有可用的日志源</p>
                <p className="text-[10px] text-gray-700 mt-1">启动容器后可查看日志</p>
              </div>
            ) : (
              <>
                {dockerSources.length > 0 && (
                  <div>
                    <div className={groupTitleStyle}>
                      <Server className="w-3 h-3 inline mr-1" />
                      容器
                    </div>
                    <div className="space-y-0.5 mt-0.5">
                      {dockerSources.map((src) => (
                        <button key={src.id} onClick={() => selectSource(src.id, src.label, src.type)}
                          className={`${sourceItemBase} ${activeSourceId === src.id ? "bg-indigo-600/15 text-indigo-300 border border-indigo-800/20" : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/50 border border-transparent"}`}>
                          <SourceIcon type={src.type} status={src.status} />
                          <div className="flex-1 min-w-0">
                            <div className="text-xs truncate">{src.label}</div>
                            <div className="text-[10px] text-gray-600">{src.status === "running" ? "运行中" : src.status || "未知"}</div>
                          </div>
                          {src.status === "running" && <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {fileSources.length > 0 && (
                  <div>
                    <div className={groupTitleStyle}>
                      <FileText className="w-3 h-3 inline mr-1" />文件
                    </div>
                    <div className="space-y-0.5 mt-0.5">
                      {fileSources.map((src) => (
                        <button key={src.id} onClick={() => selectSource(src.id, src.label, src.type)}
                          className={`${sourceItemBase} ${activeSourceId === src.id ? "bg-indigo-600/15 text-indigo-300 border border-indigo-800/20" : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/50 border border-transparent"}`}>
                          <SourceIcon type={src.type} status={src.status} />
                          <span className="truncate text-xs">{src.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </aside>

        {/* Right panel */}
        <div className="flex-1 flex flex-col min-w-0">
          {logsError && (
            <div className="shrink-0 mx-3 mt-2 px-3 py-2 bg-red-900/20 border border-red-800/30 rounded-lg flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
              <span className="text-xs text-red-300">{logsError}</span>
            </div>
          )}
          <div className="shrink-0 flex items-center justify-between px-3 py-1 border-b border-gray-800/50 bg-gray-900/30">
            <div className="flex items-center gap-2 text-[11px] text-gray-500">
              {activeSourceId ? (
                <>
                  <span className="font-medium text-gray-400">{activeSourceLabel}</span>
                  {logsLoading ? (
                    <span className="flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" />加载中…</span>
                  ) : (
                    <span>{logs.length} 行{truncated && ` (截断，共 ${totalLines} 行)`}</span>
                  )}
                </>
              ) : (
                <span>选择一个日志源开始查看</span>
              )}
              {autoRefresh && activeSourceId && (
                <span className="inline-flex items-center gap-1 text-emerald-500">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  实时
                </span>
              )}
            </div>
          </div>

          <div className="flex-1 min-h-0 relative">
            {!activeSourceId ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-600 select-none">
                <Terminal className="w-12 h-12 mb-3 text-gray-800" />
                <p className="text-sm text-gray-500">选择一个日志源</p>
                <p className="text-xs text-gray-700 mt-1">从左侧选择一个容器或文件</p>
              </div>
            ) : logsLoading && logs.length === 0 ? (
              <div className="absolute inset-0 flex items-center justify-center">
                <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
              </div>
            ) : logs.length === 0 ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-600 select-none">
                <FileText className="w-8 h-8 mb-2 text-gray-800" />
                <p className="text-xs">该源最近没有日志输出</p>
                <p className="text-[10px] text-gray-700 mt-1">尝试增加显示行数或切换过滤器</p>
              </div>
            ) : (
              <div ref={viewerRef} className="absolute inset-0 overflow-y-auto font-mono text-xs leading-relaxed">
                <div className="sticky top-0 z-10 flex items-center gap-2 px-3 py-1 bg-gray-900/90 backdrop-blur-sm border-b border-gray-800/50 text-[10px] text-gray-600 font-mono select-none">
                  <span className="w-[70px] text-right">时间</span>
                  <span className="w-12 text-center">等级</span>
                  <span className="w-16">来源</span>
                  <span className="flex-1">消息</span>
                </div>
                <div className="divide-y divide-transparent">
                  {logs.map((entry, idx) => (
                    <LogLine key={`${idx}-${entry.timestamp || idx}`} entry={entry} />
                  ))}
                </div>
                <div className="h-4" />
              </div>
            )}
          </div>
        </div>
      </div>

      {!activeSourceId && (
        <div className="shrink-0 px-4 py-2 border-t border-gray-800 bg-gray-900/50">
          <div className="flex items-center gap-3 text-[10px] text-gray-700">
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-gray-800 rounded text-[10px]">Ctrl</kbd>
              <span>+</span>
              <kbd className="px-1 py-0.5 bg-gray-800 rounded text-[10px]">K</kbd>
              <span>聚焦搜索</span>
            </span>
            <span>点击日志行复制</span>
            <span>Traceback 可展开</span>
          </div>
        </div>
      )}
    </div>
  )
}

interface LogFile {
  name: string
  size_bytes: number
  modified_at: number
}

interface LogContent {
  filename: string
  lines?: string[]
  content?: string
  truncated: boolean
  total_lines?: number
  total_bytes?: number
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + " B"
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB"
  return (bytes / (1024 * 1024)).toFixed(1) + " MB"
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000)
  return d.toLocaleString()
}


