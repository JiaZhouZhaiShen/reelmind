import { useEffect, useRef, memo } from "react"
import { useTranslation } from "react-i18next"
import { Box, Cpu, MemoryStick, Activity } from "lucide-react"
import { useAdminStore } from "../../stores/admin"

interface Props {
  name: string
  label: string
  icon?: "server" | "ai"
}

export const ContainerStatusCard = memo(function ContainerStatusCard({ name, label, icon = "server" }: Props) {
  const { t } = useTranslation()
  const sysStatus = useAdminStore((s) => s.systemStatus)
  const loading = useAdminStore((s) => s.sysStatusLoading)
  const data = name === "server" ? (sysStatus?.containers?.server ?? null) : (sysStatus?.containers?.ai ?? null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const prevCpuRef = useRef(0)
  const animatedCpuRef = useRef(0)
  const stableCpuRef = useRef(0)
  const stableMemRef = useRef(0)

  const cpuPct = data ? data.cpu_percent : 0
  const memPct = data ? data.memory_percent : 0
  const memMb = data ? data.memory_mb : 0
  const memLimit = data ? data.memory_limit_mb : 0
  const status = data ? data.status : "unknown"
  const err = data ? data.error : undefined

  // Dead band — only update when change exceeds threshold to prevent micro-jitter
  if (!loading && data) {
    if (Math.abs(cpuPct - stableCpuRef.current) > 3) {
      stableCpuRef.current = cpuPct
    }
    if (Math.abs(memPct - stableMemRef.current) > 1) {
      stableMemRef.current = memPct
    }
  }
  const displayCpuPct = loading || (stableCpuRef.current === 0 && cpuPct > 0) ? cpuPct : stableCpuRef.current
  const displayMemPct = loading || (stableMemRef.current === 0 && memPct > 0) ? memPct : stableMemRef.current

  // Animate CPU gauge
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const w = canvas.width
    const h = canvas.height
    const cx = 48
    const cy = 48
    const r = 38
    const lineWidth = 6

    ctx.clearRect(0, 0, w, h)

    if (loading) {
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.strokeStyle = "rgba(99, 102, 241, 0.12)"
      ctx.lineWidth = lineWidth
      ctx.stroke()
      return
    }

    // Smooth animation toward target
    const target = displayCpuPct / 100
    animatedCpuRef.current += (target - animatedCpuRef.current) * 0.08
    const pct = Math.min(animatedCpuRef.current, 1)

    const startAngle = -Math.PI / 2
    const endAngle = startAngle + Math.PI * 2 * pct

    // Background ring
    ctx.beginPath()
    ctx.arc(cx, cy, r, 0, Math.PI * 2)
    ctx.strokeStyle = "rgba(75, 85, 99, 0.35)"
    ctx.lineWidth = lineWidth
    ctx.stroke()

    // Active arc with gradient
    const cpuColor = pct < 0.5 ? "#34d399" : pct < 0.8 ? "#fbbf24" : "#f87171"
    ctx.beginPath()
    ctx.arc(cx, cy, r, startAngle, endAngle)
    ctx.strokeStyle = cpuColor
    ctx.lineWidth = lineWidth
    ctx.lineCap = "round"
    ctx.stroke()

    // Glow dot
    if (pct > 0.02) {
      const tipAngle = endAngle
      const tx = cx + r * Math.cos(tipAngle)
      const ty = cy + r * Math.sin(tipAngle)
      ctx.shadowBlur = 8
      ctx.shadowColor = cpuColor
      ctx.beginPath()
      ctx.arc(tx, ty, 2.5, 0, Math.PI * 2)
      ctx.fillStyle = cpuColor
      ctx.fill()
      ctx.shadowBlur = 0
    }

    prevCpuRef.current = displayCpuPct
  }, [displayCpuPct, loading])

  const isRunning = status === "running"
  const memColor = displayMemPct < 50 ? "from-emerald-400 to-cyan-400" : displayMemPct < 80 ? "from-amber-400 to-orange-400" : "from-red-400 to-rose-500"
  const memDisplay = loading ? "..." : memMb.toFixed(0) + " / " + memLimit.toFixed(0) + " MB"
  const statusDot = loading ? "bg-yellow-500 animate-pulse" : isRunning ? "bg-emerald-500 shadow-sm shadow-emerald-500/40" : "bg-red-500"

  return (
    <div className="bg-gray-900/80 border border-gray-800 rounded-lg p-5 relative overflow-hidden group">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${icon === "ai" ? "bg-violet-900/30" : "bg-blue-900/30"}`}>
            {icon === "ai" ? (
              <Cpu className="w-5 h-5 text-violet-400" />
            ) : (
              <Box className="w-5 h-5 text-blue-400" />
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-300">{label}</h3>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className={`w-1.5 h-1.5 rounded-full transition-colors duration-300 ${statusDot}`} />
              <span className="text-xs text-gray-500 capitalize">{loading ? t("containerStatus.checking") : status}</span>
            </div>
          </div>
        </div>
        {err && (
          <span className="text-xs text-red-400/60 max-w-[100px] truncate" title={err}>
            {err}
          </span>
        )}
      </div>

      <div className="flex items-center gap-5">
        {/* CPU ring */}
        <div className="relative shrink-0">
          <canvas ref={canvasRef} width={96} height={96} />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <span className="text-sm font-bold text-gray-200">{loading ? "--" : displayCpuPct.toFixed(0)}</span>
              <span className="text-[10px] text-gray-500 block -mt-0.5">% CPU</span>
            </div>
          </div>
        </div>

        {/* Memory bar */}
        <div className="flex-1 min-w-0 space-y-3">
          <div>
            <div className="flex items-center justify-between text-xs mb-1.5">
              <span className="text-gray-400 flex items-center gap-1.5">
                <MemoryStick className="w-3.5 h-3.5 text-cyan-400" />
                {t("containerStatus.memory")}
              </span>
              <span className="text-gray-300 font-mono text-xs">{memDisplay}</span>
            </div>
            <div className="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
              <div className={`h-full rounded-full transition-all duration-700 ease-out bg-gradient-to-r ${memColor}`}
                style={{ width: loading ? 100 : displayMemPct + "%" }} />
            </div>
          </div>

          {/* Status indicator */}
          <div className="flex items-center gap-2 pt-1">
            <Activity className="w-3.5 h-3.5 text-gray-600" />
            <span className={`text-xs ${loading ? "text-gray-600" : (isRunning ? "text-emerald-500" : "text-red-500")}`}>
              {loading ? t("containerStatus.checkingDot") : isRunning ? t("containerStatus.running") : t("containerStatus.stopped")}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
});






