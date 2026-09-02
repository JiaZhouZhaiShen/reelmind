import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { formatCount } from "../../utils/format"
import { useAdminStore } from "../../stores/admin"
import {
  Film, HardDrive, Clock, Users,
  Play, AlertTriangle, RefreshCw, Activity, Monitor
} from "lucide-react"
import { GPUStatusCard } from "../../components/dashboard/GPUStatusCard"
import { AIModelStatusCard } from "../../components/dashboard/AIModelStatusCard"

export default function AdminDashboardPage() {
  const { t } = useTranslation()
  const dashboard = useAdminStore((s) => s.adminDashboard)
  const dashboardError = useAdminStore((s) => s.dashboardError)
  const loadAdminDashboard = useAdminStore((s) => s.loadAdminDashboard)
  const sysStatusLoading = useAdminStore((s) => s.sysStatusLoading)
  const loadSystemStatus = useAdminStore((s) => s.loadSystemStatus)

  useEffect(() => {
    loadAdminDashboard()
    loadSystemStatus()
  }, [])

  // Poll system status every 5 seconds for real-time updates
  useEffect(() => {
    const interval = setInterval(loadSystemStatus, 15000)
    return () => clearInterval(interval)
  }, [])

  if (!dashboard) {
    return (
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        {dashboardError ? (
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-8 flex flex-col items-center gap-3">
            <AlertTriangle className="w-8 h-8 text-red-400" />
            <p className="text-sm text-red-400">{dashboardError}</p>
            <button
              onClick={() => { loadAdminDashboard(); loadSystemStatus(); }}
              className="text-xs text-gray-400 hover:text-gray-200 px-3 py-1.5 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors"
            >
              {t("dashboard.retry")}
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="bg-gray-900 border border-gray-800 rounded-lg p-4 animate-pulse">
                <div className="w-10 h-10 rounded-lg bg-gray-800" />
                <div className="h-7 bg-gray-800 rounded w-20 mt-4" />
                <div className="h-4 bg-gray-800 rounded w-16 mt-2" />
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }



  const formatBytes = (bytes: number) => {
    if (bytes >= 1e12) return (bytes / 1e12).toFixed(2) + " TB"
    if (bytes >= 1e9) return (bytes / 1e9).toFixed(2) + " GB"
    if (bytes >= 1e6) return (bytes / 1e6).toFixed(2) + " MB"
    return (bytes / 1e3).toFixed(1) + " KB"
  }

  const formatDuration = (sec: number) => {
    const h = Math.floor(sec / 3600)
    const m = Math.floor((sec % 3600) / 60)
    if (h > 0) return `${h}h ${m}m`
    return `${m}m`
  }

  const stats = [
    { label: t("admin.totalAssets"), value: formatCount(dashboard.total_assets), icon: Film, color: "text-blue-400", bg: "bg-blue-900/20" },
    { label: t("admin.totalStorage"), value: formatBytes(dashboard.total_size_bytes), icon: HardDrive, color: "text-emerald-400", bg: "bg-emerald-900/20" },
    { label: t("admin.totalDuration"), value: formatDuration(dashboard.total_duration_seconds), icon: Clock, color: "text-violet-400", bg: "bg-violet-900/20" },
    { label: t("admin.totalUsers"), value: dashboard.total_users.toString(), icon: Users, color: "text-cyan-400", bg: "bg-cyan-900/20" },
  ]


  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>

          <h1 className="text-2xl font-bold text-white">{t("admin.dashboard")}</h1>
          <p className="text-sm text-gray-500 mt-1">{t("admin.dashboardDesc")}</p>
        </div>
        <button
          onClick={() => { loadAdminDashboard(); loadSystemStatus(); }}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm text-gray-400 border border-gray-700 hover:text-gray-200 hover:border-gray-600 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          {t("admin.refresh")}
        </button>
      </div>

      {/* ── Asset Stats Grid ─────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s) => (
          <div key={s.label} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div className={`w-10 h-10 rounded-lg ${s.bg} flex items-center justify-center`}>
                <s.icon className={`w-5 h-5 ${s.color}`} />
              </div>
            </div>
            <p className="text-2xl font-bold text-white mt-3">{s.value}</p>
            <p className="text-sm text-gray-500 mt-1">{s.label}</p>
          </div>
        ))}
      </div>

      {/* ── Job Status Cards ─────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-amber-900/20 flex items-center justify-center">
              <Activity className="w-5 h-5 text-amber-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500">{t("admin.pendingImport")}</p>
              <p className="text-xl font-bold text-white">{dashboard.pending_import}</p>
            </div>
          </div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-indigo-900/20 flex items-center justify-center">
              <Play className="w-5 h-5 text-indigo-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500">{t("admin.runningJobs")}</p>
              <p className="text-xl font-bold text-white">{dashboard.running_jobs}</p>
            </div>
          </div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-red-900/20 flex items-center justify-center">
              <AlertTriangle className="w-5 h-5 text-red-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500">{t("admin.failedJobs")}</p>
              <p className="text-xl font-bold text-white">{dashboard.failed_jobs}</p>
            </div>
          </div>
        </div>
      </div>

      {/* ── System Monitor Section ───────────────────────────── */}
      <div>
        <div className="flex items-center gap-3 mb-4">
          <div className="w-8 h-8 rounded-lg bg-indigo-900/20 flex items-center justify-center">
            <Monitor className="w-4 h-4 text-indigo-400" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-gray-200">{t("dashboard.systemMonitor")}</h2>
            <p className="text-xs text-gray-500">{t("dashboard.systemMonitorDesc")}</p>
          </div>
          {sysStatusLoading && (
            <div className="ml-auto flex items-center gap-2 text-xs text-gray-500">
              <RefreshCw className="w-3 h-3 animate-spin" />
              {t("dashboard.checking")}
            </div>
          )}
        </div>

        {/* GPU Status — full width */}
        <div className="mb-4">
          <GPUStatusCard />
        </div>

        {/* AI Model Status */}
        <div className="mb-4">
          <AIModelStatusCard />
        </div>
      </div>

      {/* Inline dot indicator — live */}
      <div className="flex items-center gap-2 pt-2 border-t border-gray-800/50">
        <span className="relative flex h-2 w-2">
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${sysStatusLoading ? "bg-yellow-400" : "bg-emerald-400"}`} />
          <span className={`relative inline-flex rounded-full h-2 w-2 ${sysStatusLoading ? "bg-yellow-500" : "bg-emerald-500"}`} />
        </span>
        <span className="text-[11px] text-gray-600">
          {sysStatusLoading ? t("dashboard.connecting") : t("dashboard.monitoring")}
        </span>
      </div>
    </div>
  )
}
