import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import {
  Activity, RefreshCw, RotateCcw, XCircle,
 Loader2, Filter, CheckCircle, AlertCircle, Clock, Play,
 Trash2,
 PauseCircle, SkipForward, Search
} from "lucide-react"
import type { ReactNode } from "react"
import { formatRelativeTime } from "../../utils/format"
import { useAdminJobsStore } from "../../stores/adminJobs"
import type { AdminJob } from "../../api/client"

function SkeletonJobCard() {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 animate-pulse">
      <div className="flex items-start gap-3">
        <div className="w-4 h-4 bg-gray-800 rounded-full mt-0.5" />
        <div className="flex-1 space-y-2">
          <div className="flex items-center gap-2">
            <div className="h-4 w-24 bg-gray-800 rounded" />
            <div className="h-5 w-16 bg-gray-800 rounded" />
          </div>
          <div className="h-3 w-48 bg-gray-800 rounded" />
          <div className="h-3 w-36 bg-gray-800 rounded" />
        </div>
      </div>
    </div>
  )
}

const STATUS_CONFIG: Record<string, { icon: ReactNode; badge: string }> = {
  completed: {
    icon: <CheckCircle className="w-4 h-4 text-emerald-400" />,
    badge: "bg-emerald-900/30 text-emerald-400",
  },
  running: {
    icon: <Play className="w-4 h-4 text-blue-400" />,
    badge: "bg-blue-900/30 text-blue-400",
  },
  queued: {
    icon: <Clock className="w-4 h-4 text-amber-400" />,
    badge: "bg-amber-900/30 text-amber-400",
  },
  failed: {
    icon: <AlertCircle className="w-4 h-4 text-red-400" />,
    badge: "bg-red-900/30 text-red-400",
  },
  cancelled: {
    icon: <XCircle className="w-4 h-4 text-gray-500" />,
    badge: "bg-gray-800 text-gray-500",
  },
  paused: {
    icon: <PauseCircle className="w-4 h-4 text-orange-400" />,
    badge: "bg-orange-900/30 text-orange-400",
  },
  superseded: {
    icon: <SkipForward className="w-4 h-4 text-gray-500" />,
    badge: "bg-gray-800 text-gray-500 line-through",
  },
}

const FILTERS = ["", "queued", "running", "completed", "failed", "cancelled", "paused", "superseded"]

function statusIcon(status: string) {
  return STATUS_CONFIG[status]?.icon ?? <Activity className="w-4 h-4 text-gray-400" />
}

function statusBadgeClass(status: string) {
  return STATUS_CONFIG[status]?.badge ?? "bg-gray-800 text-gray-500"
}

function formatTime(t?: string) {
  return formatRelativeTime(t)
}

export default function JobManagementPage() {
  const { t } = useTranslation()
  const jobs = useAdminJobsStore((s) => s.jobs)
  const loading = useAdminJobsStore((s) => s.loading)
  const actionLoading = useAdminJobsStore((s) => s.actionLoading)
  const statusFilter = useAdminJobsStore((s) => s.statusFilter)
  const searchText = useAdminJobsStore((s) => s.searchText)
  const error = useAdminJobsStore((s) => s.error)
  const loadJobs = useAdminJobsStore((s) => s.loadJobs)
  const retryJob = useAdminJobsStore((s) => s.retryJob)
  const cancelJob = useAdminJobsStore((s) => s.cancelJob)
  const setStatusFilter = useAdminJobsStore((s) => s.setStatusFilter)
  const setSearchText = useAdminJobsStore((s) => s.setSearchText)
  const clearError = useAdminJobsStore((s) => s.clearError)
  const cleaningUp = useAdminJobsStore((s) => s.cleaningUp)
  const cleanupResult = useAdminJobsStore((s) => s.cleanupResult)
  const cleanupJobs = useAdminJobsStore((s) => s.cleanupJobs)
  const setCleanupResult = useAdminJobsStore((s) => s.setCleanupResult)

  useEffect(() => { loadJobs() }, [loadJobs, statusFilter])

  const hasActive = jobs.some((j) => j.status === "running" || j.status === "queued")
  useEffect(() => {
    if (!hasActive) return
    const interval = setInterval(() => {
      useAdminJobsStore.getState().loadJobs()
    }, 5000)
    return () => clearInterval(interval)
  }, [hasActive])

  useEffect(() => {
    if (!error) return
    const timer = setTimeout(clearError, 5000)
    return () => clearTimeout(timer)
  }, [error, clearError])

  useEffect(() => {
    if (!cleanupResult) return
    const timer = setTimeout(() => setCleanupResult(null), 5000)
    return () => clearTimeout(timer)
  }, [cleanupResult, setCleanupResult])

  const filteredJobs = searchText
    ? jobs.filter((j) =>
        j.job_type?.toLowerCase().includes(searchText.toLowerCase()) ||
        j.message?.toLowerCase().includes(searchText.toLowerCase()) ||
        j.error?.toLowerCase().includes(searchText.toLowerCase()) ||
        j.id?.toLowerCase().includes(searchText.toLowerCase())
      )
    : jobs

  if (loading && jobs.length === 0) {
    return (
      <div className="bg-gray-950 min-h-screen p-6">
        <div className="max-w-4xl mx-auto space-y-6">
          {Array.from({ length: 5 }, (_, i) => (
            <SkeletonJobCard key={i} />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="bg-gray-950 min-h-screen p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-white">{t("admin.jobManagement")}</h1>
            <p className="text-sm text-gray-400 mt-1">{t("admin.jobManagementDesc")}</p>
         </div>
         <button
           onClick={() => {
             if (window.confirm('确定要清理旧任务和僵尸任务吗？')) {
               cleanupJobs()
             }
           }}
           disabled={cleaningUp}
           className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm text-gray-400 border border-gray-700 hover:text-red-400 hover:border-red-800/50 transition-colors"
         >
           {cleaningUp ? (
             <Loader2 className="w-4 h-4 animate-spin" />
           ) : (
             <Trash2 className="w-4 h-4" />
           )}
           清理
         </button>
         <button
            onClick={loadJobs}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm text-gray-400 border border-gray-700 hover:text-gray-200 hover:border-gray-600 transition-colors"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            {t("admin.refresh")}
          </button>
        </div>

        {error && (
          <div className="mb-6 flex items-center gap-2 px-4 py-2.5 rounded-lg bg-red-900/20 border border-red-800/50 text-sm text-red-400">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
            <button onClick={clearError} className="ml-auto hover:text-red-300 transition-colors">
              <XCircle className="w-4 h-4" />
            </button>
         </div>
       )}

        {cleanupResult && (
          <div className="mb-6 flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-900/20 border border-emerald-800/50 text-sm text-emerald-400">
            <CheckCircle className="w-4 h-4 flex-shrink-0" />
            <span>清理完成：删除了 {cleanupResult.deleted_old} 条旧记录，标记了 {cleanupResult.marked_stale} 条僵尸任务为失败</span>
            <button onClick={() => setCleanupResult(null)} className="ml-auto hover:text-emerald-300 transition-colors">
              <XCircle className="w-4 h-4" />
            </button>
          </div>
        )}

       <div className="space-y-6">
          <div className="relative">
            <Search className="w-4 h-4 text-gray-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="搜索任务类型、消息、错误..."
              className="w-full bg-gray-800 text-gray-200 rounded-xl pl-10 pr-4 py-2 text-sm border border-gray-700 placeholder-gray-500 focus:outline-none focus:border-indigo-500/60 transition-colors"
            />
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <Filter className="w-4 h-4 text-gray-500 flex-shrink-0" />
            {FILTERS.map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s || undefined)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  (statusFilter || "") === s
                    ? "bg-indigo-600/20 text-indigo-400 border border-indigo-700/50"
                    : "text-gray-400 border border-gray-700 hover:text-gray-200 hover:border-gray-600"
                }`}
              >
                {s || t("admin.all")}
              </button>
            ))}
          </div>

          <div className="space-y-6">
            {filteredJobs.map((job) => (
              <div key={job.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <div className="mt-0.5">{statusIcon(job.status)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-white">{job.job_type}</span>
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${statusBadgeClass(job.status)}`}>
                          {job.status}
                        </span>
                        {job.progress > 0 && (
                          <span className="text-xs text-gray-500">{Math.round(job.progress * 100)}%</span>
                        )}
                      </div>
                      {job.message && (
                        <p className="text-xs text-gray-400 mt-1 truncate">{job.message}</p>
                      )}
                      {job.error && (
                        <p className="text-xs text-red-400 mt-1 truncate">{job.error}</p>
                      )}
                      <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-500">
                        <span>{t("admin.created")}: {formatTime(job.created_at)}</span>
                        {job.started_at && <span>{t("admin.started")}: {formatTime(job.started_at)}</span>}
                        {job.finished_at && <span>{t("admin.finished")}: {formatTime(job.finished_at)}</span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0 ml-2">
                    {["failed", "cancelled"].includes(job.status) && (
                      <button
                        onClick={() => retryJob(job.id)}
                        disabled={actionLoading === job.id}
                        className="p-1.5 rounded text-gray-500 hover:text-indigo-400 hover:bg-indigo-900/20 transition-colors"
                        title={t("admin.retry")}
                      >
                        {actionLoading === job.id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <RotateCcw className="w-4 h-4" />
                        )}
                      </button>
                    )}
                    {["queued", "running", "paused"].includes(job.status) && (
                      <button
                        onClick={() => cancelJob(job.id)}
                        disabled={actionLoading === job.id}
                        className="p-1.5 rounded text-gray-500 hover:text-red-400 hover:bg-red-900/20 transition-colors"
                        title={t("admin.cancel")}
                      >
                        {actionLoading === job.id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <XCircle className="w-4 h-4" />
                        )}
                      </button>
                    )}
                  </div>
                </div>
                {job.status === "running" && job.progress > 0 && (
                  <div className="mt-3 h-1 bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-indigo-600 rounded-full transition-all duration-500"
                      style={{ width: `${Math.round(job.progress * 100)}%` }}
                    />
                  </div>
                )}
              </div>
            ))}
            {filteredJobs.length === 0 && (
              <div className="flex flex-col items-center justify-center py-16 text-gray-500">
                <Activity className="w-12 h-12 mb-3 text-gray-700" />
                <p className="text-sm">{searchText ? "没有匹配的任务" : t("admin.noJobs")}</p>
                {searchText && (
                  <p className="text-xs text-gray-500 mt-1">试试其他搜索词，或清除筛选条件</p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
