import { useEffect, useRef, useState, memo } from "react"
import { useTranslation } from "react-i18next"
import { Cpu, Gauge, Thermometer, Zap } from "lucide-react"
import { useAdminStore } from "../../stores/admin"

export const GPUStatusCard = memo(function GPUStatusCard() {
  const { t } = useTranslation()
  const sysStatus = useAdminStore((s) => s.systemStatus)
  const loading = useAdminStore((s) => s.sysStatusLoading)
  const data = sysStatus?.gpu ?? null
  const canvasRef = useRef<HTMLCanvasElement>(null)
 const [animatedPct, setAnimatedPct] = useState(0)
 const prevPctRef = useRef(0)
  const stablePctRef = useRef(0)

  const totalPct = data ? data.total_percent : 0
  const aiPct = data ? data.ai_percent : 0
  const totalUsed = data ? data.total_used : 0
  const aiUsed = data ? data.ai_used : 0
  const totalGb = data ? data.total : 0

  // Animate the percentage change smoothly
  useEffect(() => {
    if (loading || !data) return
    // Dead band: ignore changes < 2% to prevent micro-jitter
    if (Math.abs(totalPct - stablePctRef.current) < 2) {
      // Still draw the stable value so the gauge doesn't freeze
      setAnimatedPct(stablePctRef.current)
      return
    }
    stablePctRef.current = totalPct

    let start = prevPctRef.current
    const end = totalPct
    const duration = 600
    const startTime = performance.now()
    const tick = (now: number) => {
      const elapsed = now - startTime
      const t = Math.min(elapsed / duration, 1)
      const ease = 1 - (1 - t) * (1 - t)
      setAnimatedPct(start + (end - start) * ease)
      if (t < 1) requestAnimationFrame(tick)
    }
    prevPctRef.current = end
    requestAnimationFrame(tick)
  }, [totalPct, loading, data])

  // Draw radial gauge on canvas
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const w = canvas.width
    const h = canvas.height
    const cx = w / 2
    const cy = h / 2
    const r = Math.min(cx, cy) - 18
    const lineWidth = 10

    ctx.clearRect(0, 0, w, h)

    if (loading) {
      // Pulsing ring animation
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.strokeStyle = "rgba(99, 102, 241, 0.15)"
      ctx.lineWidth = lineWidth
      ctx.stroke()
      return
    }

    const pct = animatedPct / 100
    const startAngle = -Math.PI / 2
    const endAngle = startAngle + Math.PI * 2 * pct

    // Background ring
    ctx.beginPath()
    ctx.arc(cx, cy, r, 0, Math.PI * 2)
    ctx.strokeStyle = "rgba(75, 85, 99, 0.4)"
    ctx.lineWidth = lineWidth
    ctx.stroke()

    // Gradient ring
    const grad = ctx.createLinearGradient(0, 0, w, h)
    if (pct < 0.5) {
      grad.addColorStop(0, "#34d399")
      grad.addColorStop(1, "#06b6d4")
    } else if (pct < 0.8) {
      grad.addColorStop(0, "#fbbf24")
      grad.addColorStop(1, "#f59e0b")
    } else {
      grad.addColorStop(0, "#f87171")
      grad.addColorStop(1, "#ef4444")
    }

    ctx.beginPath()
    ctx.arc(cx, cy, r, startAngle, endAngle)
    ctx.strokeStyle = grad
    ctx.lineWidth = lineWidth
    ctx.lineCap = "round"
    ctx.stroke()

    // Glow dot at the tip
    if (pct > 0.01) {
      const tipAngle = endAngle
      const tx = cx + r * Math.cos(tipAngle)
      const ty = cy + r * Math.sin(tipAngle)
      ctx.beginPath()
      ctx.arc(tx, ty, 4, 0, Math.PI * 2)
      ctx.fillStyle = pct < 0.5 ? "#34d399" : pct < 0.8 ? "#fbbf24" : "#f87171"
      ctx.fill()
      ctx.shadowBlur = 12
      ctx.shadowColor = pct < 0.5 ? "#34d399" : pct < 0.8 ? "#fbbf24" : "#f87171"
      ctx.beginPath()
      ctx.arc(tx, ty, 3, 0, Math.PI * 2)
      ctx.fill()
      ctx.shadowBlur = 0
    }
  }, [animatedPct, loading])

  const colorClass = loading ? "text-gray-500" : totalPct < 50 ? "text-emerald-400" : totalPct < 80 ? "text-amber-400" : "text-red-400"
  const glowClass = loading ? "" : totalPct < 50 ? "shadow-emerald-500/30" : totalPct < 80 ? "shadow-amber-500/30" : "shadow-red-500/30"
  const barColor = loading ? "bg-gray-700" : totalPct < 50 ? "bg-gradient-to-r from-emerald-400 to-cyan-400" : totalPct < 80 ? "bg-gradient-to-r from-amber-400 to-orange-400" : "bg-gradient-to-r from-red-400 to-rose-500"

  return (
    <div className="bg-gray-900/80 border border-gray-800 rounded-lg p-5 relative overflow-hidden group">
      {/* Decorative background glow */}
      <div className={`absolute -top-20 -right-20 w-40 h-40 rounded-full blur-3xl opacity-10 transition-colors duration-700 ${glowClass}`} />

      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-indigo-900/30 flex items-center justify-center">
            <Cpu className="w-5 h-5 text-indigo-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-300">{t("gpuStatus.title")}</h3>
            <p className="text-xs text-gray-500">GPU Status</p>
          </div>
        </div>
        {loading ? (
          <div className="w-16 h-6 bg-gray-800 rounded animate-pulse" />
        ) : (
          <div className="text-right">
            <span className={`text-2xl font-bold ${colorClass} transition-colors duration-500`}>
              {totalPct.toFixed(0)}<span className="text-lg">%</span>
            </span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-6">
        {/* Canvas radial gauge */}
        <canvas ref={canvasRef} width={110} height={110} className="shrink-0" />

        {/* Stats */}
        <div className="flex-1 min-w-0 space-y-3">
          {/* Total GPU usage bar */}
          <div>
            <div className="flex items-center justify-between text-xs mb-1.5">
              <span className="text-gray-400 flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                {t("gpuStatus.totalMemory")}
              </span>
              <span className="text-gray-300 font-mono text-xs">
                {loading ? "..." : `${totalUsed.toFixed(1)} / ${totalGb.toFixed(1)} GB`}
              </span>
            </div>
            <div className="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
              <div className={`h-full rounded-full transition-all duration-700 ease-out ${barColor}`}
                style={{ width: loading ? 100 : totalPct + "%" }} />
            </div>
          </div>

          {/* AI module GPU usage bar */}
          <div>
            <div className="flex items-center justify-between text-xs mb-1.5">
              <span className="text-gray-400 flex items-center gap-1.5">
                <Gauge className="w-3.5 h-3.5 text-purple-400" />
                {t("gpuStatus.aiMemory")}
              </span>
              <span className="text-gray-300 font-mono text-xs">
                {loading ? "..." : `${aiUsed.toFixed(1)} / ${totalGb.toFixed(1)} GB`}
              </span>
            </div>
            <div className="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
              <div className="h-full rounded-full transition-all duration-700 ease-out bg-gradient-to-r from-purple-500 to-violet-500"
                style={{ width: loading ? 100 : aiPct + "%" }} />
            </div>
          </div>

          {/* Temperature indicator */}
          <div className="flex items-center gap-2 pt-1">
            <Thermometer className="w-3.5 h-3.5 text-gray-600" />
            <span className={`text-xs ${loading ? "text-gray-600" : totalPct < 50 ? "text-emerald-500" : totalPct < 80 ? "text-amber-500" : "text-red-500"}`}>
              {loading ? t("gpuStatus.checking") : totalPct < 50 ? t("gpuStatus.normal") : totalPct < 80 ? t("gpuStatus.highLoad") : t("gpuStatus.critical")}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
});

