import { useEffect, useState, useCallback } from "react"
import { useTranslation } from "react-i18next"
import {
  RefreshCw, AlertTriangle, Activity, Server,
  Loader2, Terminal,
} from "lucide-react"
import { request } from "../../api/base"

// ── Types ──────────────────────────────────────────────────────────────────

interface DiagnosticsResponse {
  error_counts?: Record<string, number>
  top_errors?: { message: string; count: number }[]
  recent_errors?: { source: string; timestamp: string; level: string; message: string }[]
  container_health?: Record<string, string>
  container_details?: Record<string, { state: string; status: string; id: string }>
  total_docker_sources?: number
  error?: string
}

// ── Helpers ────────────────────────────────────────────────────────────────

const HEALTH_COLOR: Record<string, string> = {
  running: "text-emerald-400",
  stopped: "text-red-400",
  restarting: "text-amber-400",
}

function SmallCard({ title, count, color }: { title: string; count: string | number; color: string }) {
  const bgMap: Record<string, string> = {
    red: "bg-red-900/20 border-red-800/40",
    amber: "bg-amber-900/20 border-amber-800/40",
    green: "bg-emerald-900/20 border-emerald-800/40",
    gray: "bg-gray-800/40 border-gray-700/40",
  }
  return (
    <div className={`rounded-lg border p-3 ${bgMap[color] || bgMap.gray}`}>
      <div className="text-[10px] text-gray-500 uppercase tracking-wide">{title}</div>
      <div className="text-2xl font-bold text-white mt-0.5">{count}</div>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

export default function ErrorDashboard() {
  const [data, setData] = useState<DiagnosticsResponse>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  const { t } = useTranslation()

  const fetchDiag = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await request("/admin/logs/diagnostics")
      setData(res as DiagnosticsResponse)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to fetch diagnostics")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchDiag() }, [fetchDiag])

  const ec = data.error_counts || {}
  const te = data.top_errors || []
  const re = data.recent_errors || []
  const ch = data.container_health || {}

  const totalErrors = Object.values(ec).reduce((a, b) => a + (b > 0 ? b : 0), 0)
  const sourcesWithErrors = Object.entries(ec).filter(([_, v]) => v > 0).length

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-gray-500 animate-spin" />
        <span className="ml-2 text-sm text-gray-500">{t("errorDashboard.diagnosing")}</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="w-8 h-8 text-red-400 mx-auto" />
          <p className="text-sm text-red-400 mt-2">{error}</p>
          <button onClick={fetchDiag} className="mt-3 text-xs text-gray-400 hover:text-white underline">
            {t("errorDashboard.retry")}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-white flex items-center gap-2">
          <Activity className="w-4 h-4 text-red-400" />
          {t("errorDashboard.title")}
        </h2>
        <button
          onClick={fetchDiag}
          className="flex items-center gap-1 px-2.5 py-1 text-xs rounded bg-gray-800 hover:bg-gray-700 text-gray-300 transition-colors"
        >
          <RefreshCw className="w-3 h-3" />
          {t("errorDashboard.refresh")}
        </button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <SmallCard title={t("errorDashboard.totalErrors")} count={totalErrors} color={totalErrors > 0 ? "red" : "green"} />
        <SmallCard title={t("errorDashboard.abnormalContainers")} count={sourcesWithErrors} color={sourcesWithErrors > 0 ? "amber" : "green"} />
        <SmallCard title={t("errorDashboard.duplicatePatterns")} count={te.length} color="gray" />
        <SmallCard title={t("errorDashboard.totalContainers")} count={Object.keys(ch).length} color="gray" />
      </div>

      <div>
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">{t("errorDashboard.errorsByContainer")}</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
          {Object.entries(ch).map(([id, status]) => (
            <div key={id} className="rounded-lg border border-gray-800 bg-gray-900/50 p-2.5">
              <div className="flex items-center gap-1.5">
                <Server className="w-3 h-3 text-gray-500 shrink-0" />
                <span className="text-xs text-gray-300 truncate">{id}</span>
              </div>
              <div className="flex items-center justify-between mt-1.5">
                <span className={`text-[10px] ${HEALTH_COLOR[status] || "text-gray-500"}`}>{status}</span>
                <span className={`text-sm font-bold ${(ec[id] || 0) > 0 ? "text-red-400" : "text-emerald-400"}`}>
                  {ec[id] ?? "?"}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {te.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
            {t('errorDashboard.topErrors', { count: te.length })}
          </h3>
          <div className="space-y-1">
            {te.map((item, i) => (
              <div
                key={i}
                className="flex items-start gap-2 px-3 py-2 rounded bg-red-900/10 border border-red-900/20 cursor-pointer hover:bg-red-900/20 transition-colors"
                onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
              >
                <span className="text-[10px] text-red-400 font-mono w-6 shrink-0">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-gray-300 truncate">{item.message}</div>
                  {expandedIdx === i && (
                    <div className="text-xs text-gray-500 mt-1 break-all whitespace-pre-wrap">{item.message}</div>
                  )}
                </div>
                <span className="shrink-0 text-xs font-mono text-red-400 bg-red-900/30 px-1.5 py-0.5 rounded">
                  x{item.count}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {re.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
            {t('errorDashboard.recentErrors', { count: re.length })}
          </h3>
          <div className="space-y-0.5 font-mono text-xs">
            {re.map((err, i) => (
              <div key={i} className="flex items-start gap-2 px-2 py-1 rounded hover:bg-white/[0.03]">
                <span className="shrink-0 text-gray-600 w-[70px] text-right">
                  {err.timestamp ? err.timestamp.slice(11, 23) : "--"}
                </span>
                <span className="shrink-0 text-red-400 w-10">ERROR</span>
                <span className="shrink-0 text-gray-500 w-16">{err.source}</span>
                <span className="text-gray-300 truncate">{err.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {totalErrors === 0 && te.length === 0 && re.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12">
          <Terminal className="w-10 h-10 text-emerald-500/50" />
          <p className="text-sm text-gray-500 mt-3">{t("errorDashboard.noErrors")}</p>
          <p className="text-[10px] text-gray-700 mt-1">{t("errorDashboard.allNormal")}</p>
        </div>
      )}
    </div>
  )
}
