import { useState, useEffect } from "react"
import {
  Play, Save, Video, Search, Type, Camera, Mic, Users,
  Loader2, CheckCircle2, XCircle, Filter, AlertTriangle, RefreshCw,
} from "lucide-react"
import * as api from "../../api/ai"
import type { BatchCheckpointInfo } from "../../types/ai"

type Tab = "manual" | "auto" | "single"

const ALL_ENGINES = [
  { id: "scene", label: "场景检测", icon: Video },
  { id: "yolo", label: "YOLO", icon: Search },
  { id: "ocr", label: "OCR", icon: Type },
  { id: "clip", label: "CLIP", icon: Camera },
  { id: "transcript", label: "转录", icon: Mic },
  { id: "diarization", label: "说话人分离", icon: Users },
]

const TAB_LABELS: Record<Tab, string> = { manual: "手动批量", auto: "自动批量", single: "单视频" }

const DEFAULTS = {
  manual: {
    enabled: true, engines: ["scene", "yolo", "ocr", "clip", "transcript", "diarization"],
    batch_size: 100, timeout_minutes: 180,
    filters: { max_file_size_mb: 2000, max_duration_minutes: 30 },
  },
  auto: {
    enabled: false, engines: ["scene", "yolo", "ocr", "clip", "transcript", "diarization"],
    batch_size: 50, time_window_start: 0, time_window_end: 6,
    gpu_threshold_percent: 50, check_interval_seconds: 60,
    filters: { max_file_size_mb: 10000, max_duration_minutes: 60 },
  },
  single: {
    enabled: true, engines: ["scene", "yolo", "ocr", "clip", "transcript", "diarization"],
    timeout_minutes: 60,
    filters: { max_file_size_mb: 0, max_duration_minutes: 0 },
  },
} as const

type ConfigMap = { [K in Tab]: Record<string, any> }

const FETCH_MAP: Record<Tab, () => Promise<{ config: Record<string, any> }>> = {
  manual: api.getManualPipelineConfig,
  auto: api.getAutoPipelineConfig,
  single: api.getSinglePipelineConfig,
}

const SAVE_MAP: Record<Tab, (cfg: Record<string, any>) => Promise<{ status: string }>> = {
  manual: api.saveManualPipelineConfig,
  auto: api.saveAutoPipelineConfig,
  single: api.saveSinglePipelineConfig,
}

export function PipelineConfigPanel() {
  const [activeTab, setActiveTab] = useState<Tab>("manual")
  const [configs, setConfigs] = useState<ConfigMap>({ ...DEFAULTS } as any)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState<"idle" | "success" | "error">("idle")
  const [starting, setStarting] = useState(false)
  const [startResult, setStartResult] = useState<{ status: string; batch_id?: string; message?: string } | null>(null)
  const [pendingCount, setPendingCount] = useState<number | null>(null)
  const [checkpoints, setCheckpoints] = useState<BatchCheckpointInfo[]>([])
  const [engineProgress, setEngineProgress] = useState<Record<string, Record<string, number>>>({})
  const [chunkSize, setChunkSize] = useState(0)
  const [resetting, setResetting] = useState(false)
  const [resetMsg, setResetMsg] = useState<string | null>(null)

  const ENGINE_NAMES: Record<string, string> = {
    scene: "场景切割",
    yolo: "YOLO",
    ocr: "OCR",
    clip: "CLIP",
    transcript: "语音转文字",
    diarization: "说话人分离",
  }
  const ENGINE_ORDER = ["scene", "yolo", "ocr", "clip", "transcript", "diarization"]


  const loadPendingCount = async (engines?: string[], max_file_size_mb?: number, max_duration_minutes?: number) => {
    try {
      const resp = await api.getPendingAssetCount(engines, max_file_size_mb, max_duration_minutes)
      setPendingCount(resp?.selected_pending ?? resp?.total_pending ?? null)
    } catch { }
  }

  const loadCheckpoints = async () => {
    try {
      const resp = await api.listBatchCheckpoints(5)
      setCheckpoints(resp.checkpoints || [])
    } catch { }
  }

  useEffect(() => {
    let cancelled = false
    async function load() {
      const results: Partial<ConfigMap> = {}
      for (const tab of ["manual", "auto", "single"] as Tab[]) {
        try {
          const resp = await FETCH_MAP[tab]()
          results[tab] = { ...DEFAULTS[tab], ...resp.config }
        } catch { results[tab] = { ...DEFAULTS[tab] } }
      }
      if (!cancelled) setConfigs(results as ConfigMap)
      if (!cancelled) setLoading(false)
      if (!cancelled) {
        const manualCfg = results.manual || DEFAULTS.manual
        loadPendingCount(manualCfg.engines, manualCfg.filters?.max_file_size_mb, manualCfg.filters?.max_duration_minutes)
      }
    }
    load()
    loadCheckpoints()
    return () => { cancelled = true }
  }, [])

  const cfg = configs[activeTab] || DEFAULTS[activeTab]
  const isAuto = activeTab === "auto"
  const isSingle = activeTab === "single"
  const engines = (cfg.engines || []) as string[]
  const hasRunningBatch = checkpoints.some(cp => cp.status === "running")

  // Re-fetch pending count when engines change (engine toggle or tab switch)
  useEffect(() => {
    if (!loading && activeTab !== "single") {
      loadPendingCount(engines, cfg.filters?.max_file_size_mb, cfg.filters?.max_duration_minutes)
    }
  }, [engines, loading, activeTab])

  // Poll engine progress for running batches
  useEffect(() => {
    const runningCp = checkpoints.find((cp) => cp.status === "running")
    if (!runningCp) { setEngineProgress({}); setChunkSize(0); return }
    const interval = setInterval(async () => {
      try {
        const resp = await api.getBatchEngineProgress(runningCp.id)
        if (resp.engine_progress) setEngineProgress(resp.engine_progress)
        if (resp.chunk_size) setChunkSize(resp.chunk_size)
      } catch {}
    }, 3000)
    return () => clearInterval(interval)
  }, [checkpoints])

  // Auto-refresh checkpoints when there is a running batch
  useEffect(() => {
    const runningCp = checkpoints.find((cp) => cp.status === "running")
    if (!runningCp) return
    const interval = setInterval(() => {
      loadCheckpoints()
      loadPendingCount(engines, cfg.filters?.max_file_size_mb, cfg.filters?.max_duration_minutes)
    }, 5000)
    return () => clearInterval(interval)
  }, [checkpoints])
  const setCfg = (patch: Record<string, any>) => {
    setConfigs((prev) => ({ ...prev, [activeTab]: { ...prev[activeTab], ...patch } }))
  }

  const toggleEngine = (engineId: string) => {
    const engines: string[] = cfg.engines || []
    if (engines.includes(engineId)) {
      setCfg({ engines: engines.filter((e) => e !== engineId) })
    } else {
      setCfg({ engines: [...engines, engineId] })
    }
  }

  const handleResetErrors = async () => {
    if (!window.confirm('确定要重置所有错误任务吗？此操作不可撤销。')) return;
    setResetting(true)
    setResetMsg(null)
    try {
      const result = await api.resetErrorJobs()
      if (result.count > 0) {
        setResetMsg(result.count.toString())
        loadPendingCount(engines, cfg.filters?.max_file_size_mb, cfg.filters?.max_duration_minutes)
      } else {
        setResetMsg('0')
      }
      setTimeout(() => setResetMsg(null), 3000)
    } catch {
      setResetMsg('error')
      setTimeout(() => setResetMsg(null), 3000)
    } finally {
      setResetting(false)
    }
  }

  const setFilters = (patch: Record<string, any>) => {
    setCfg({ filters: { ...(cfg.filters || {}), ...patch } })
  }

  const handleSave = async () => {
    setSaving(true)
    setSaveMsg("idle")
    try {
      await SAVE_MAP[activeTab](cfg)
      setSaveMsg("success")
      setTimeout(() => setSaveMsg("idle"), 2000)
      if (activeTab !== "single") loadPendingCount(engines, cfg.filters?.max_file_size_mb, cfg.filters?.max_duration_minutes)
    } catch {
      setSaveMsg("error")
      setTimeout(() => setSaveMsg("idle"), 3000)
    } finally { setSaving(false) }
  }

  const handleStart = async () => {
    setStarting(true)
    setStartResult(null)
    try {
      const result = await api.startManualPipeline()
      setStartResult({ status: result.status, batch_id: result.batch_id, message: result.message })
      if (result.status === "started") {
        setTimeout(() => loadPendingCount(engines, cfg.filters?.max_file_size_mb, cfg.filters?.max_duration_minutes), 1000)
        setTimeout(loadCheckpoints, 1000)
      }
    } catch {
      setStartResult({ status: "error" })
    } finally {
      setStarting(false)
      // Always reload checkpoints after a start attempt (success or error),
      // to pick up any status changes (e.g. stale running -> cancelled)
      setTimeout(loadCheckpoints, 500)
    }
  }



  return (
    <div className="bg-gray-900/30 rounded-lg border border-gray-800">
      {/* Tab bar */}
      <div className="flex border-b border-gray-800">
        {(["manual", "auto", "single"] as Tab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={
              "px-4 py-2.5 text-sm font-medium transition-colors relative " +
              (activeTab === tab
                ? "text-indigo-400 bg-gray-800/50"
                : "text-gray-500 hover:text-gray-300 hover:bg-gray-800/20")
            }
          >
            {TAB_LABELS[tab]}
            {activeTab === tab && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-500" />}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {loading ? (
          <div className="flex items-center justify-center py-8 text-gray-500">
            <Loader2 className="w-5 h-5 animate-spin mr-2" />
            加载配置中...
          </div>
        ) : (
          <>
            {/* Whisper Warning — when both transcript + diarization are enabled */}
            {engines.includes("transcript") && engines.includes("diarization") && (
              <div className="flex items-start gap-2 p-2.5 rounded-md bg-amber-900/30 border border-amber-700/40">
                <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
                <div className="text-xs text-amber-300/90 leading-relaxed">
                  <span className="font-semibold text-amber-200">Whisper 模式已启用</span>
                  — 转录 + 说话人分离需要加载 Whisper 大模型。<br />
                  <span className="text-amber-400/80">
                    5000 个视频约 <span className="font-bold text-amber-200">19 天</span>
                    {" → "}关闭后降至约 <span className="font-bold text-amber-200">2 天</span>
                  </span>
                  <br />考虑关闭转录和说话人分离来大幅提速。
                </div>
              </div>
            )}

            {/* Enable Toggle */}
            <label className="flex items-center gap-3 cursor-pointer">
              <div
                className={
                  "w-9 h-5 rounded-full transition-colors relative " +
                  (cfg.enabled ? "bg-indigo-600" : "bg-gray-700")
                }
              >
                <div
                  className={
                    "w-4 h-4 rounded-full bg-white absolute top-0.5 transition-transform " +
                    (cfg.enabled ? "translate-x-4" : "translate-x-0.5")
                  }
                />
                <input
                  type="checkbox"
                  checked={!!cfg.enabled}
                  onChange={() => setCfg({ enabled: !cfg.enabled })}
                  className="sr-only"
                />
              </div>
              <span className="text-sm text-gray-300 font-medium">
                {isAuto ? "自动调度" : isSingle ? "单视频处理" : "手动批量处理"}{" "}
                {cfg.enabled ? "已启用" : "已禁用"}
              </span>
              {pendingCount !== null && !isSingle && (
                <span className="text-xs text-gray-500 ml-auto">
                  待处理: <span className="text-gray-400 font-mono">{pendingCount}</span> 个视频
                </span>
              )}
            </label>

            {/* Engines */}
            <div>
              <label className="text-xs text-gray-500 uppercase tracking-wider font-semibold mb-2 block">
                引擎选择
              </label>
              <div className="flex flex-wrap gap-2">
                {ALL_ENGINES.map((eng) => {
                  const selected = engines.includes(eng.id)
                  const EngineIcon = eng.icon
                  return (
                    <button
                      key={eng.id}
                      onClick={() => toggleEngine(eng.id)}
                      title={eng.label}
                      className={
                        "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all " +
                        (selected
                          ? "bg-indigo-600/30 text-indigo-300 border border-indigo-600/50"
                          : "bg-gray-800 text-gray-500 border border-gray-700 hover:border-gray-600")
                      }
                    >
                      <EngineIcon className="w-3.5 h-3.5" />
                      {eng.label}
                      {eng.id === "transcript" && selected && (
                        <span className="text-[10px] text-amber-400/70 ml-0.5">(Whisper)</span>
                      )}
                      {eng.id === "diarization" && selected && (
                        <span className="text-[10px] text-amber-400/70 ml-0.5">(Whisper)</span>
                      )}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Config Params */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-gray-400 block mb-1">每批数量</label>
                <input
                  type="number" min={1} max={500}
                  value={cfg.batch_size ?? 100}
                  onChange={(e) => setCfg({ batch_size: parseInt(e.target.value) || 1 })}
                  disabled={isSingle}
                  className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200 disabled:opacity-40"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">超时 (分钟)</label>
                <input
                  type="number" min={1} max={1440}
                  value={cfg.timeout_minutes ?? 180}
                  onChange={(e) => setCfg({ timeout_minutes: parseInt(e.target.value) || 180 })}
                  disabled={isAuto}
                  className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200 disabled:opacity-40"
                />
              </div>
              {isAuto && (
                <>
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">时间窗口起始 (UTC)</label>
                    <input
                      type="number" min={0} max={23}
                      value={cfg.time_window_start ?? 0}
                      onChange={(e) => setCfg({ time_window_start: parseInt(e.target.value) || 0 })}
                      className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">时间窗口结束 (UTC)</label>
                    <input
                      type="number" min={0} max={23}
                      value={cfg.time_window_end ?? 6}
                      onChange={(e) => setCfg({ time_window_end: parseInt(e.target.value) || 6 })}
                      className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">GPU 阈值 (%)</label>
                    <input
                      type="number" min={0} max={100}
                      value={cfg.gpu_threshold_percent ?? 50}
                      onChange={(e) => setCfg({ gpu_threshold_percent: parseInt(e.target.value) || 50 })}
                      className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">检查间隔 (秒)</label>
                    <input
                      type="number" min={5} max={600}
                      value={cfg.check_interval_seconds ?? 60}
                      onChange={(e) => setCfg({ check_interval_seconds: parseInt(e.target.value) || 60 })}
                      className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200"
                    />
                  </div>
                </>
              )}
            </div>

            {/* File Filters */}
            <div className="border-t border-gray-800 pt-3">
              <label className="text-xs text-gray-500 uppercase tracking-wider font-semibold mb-2 flex items-center gap-1">
                <Filter className="w-3.5 h-3.5" />
                文件过滤（在 AI 容器侧执行）
              </label>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-400 block mb-1">最大文件大小 (MB, 0=不限)</label>
                  <input
                    type="number" min={0}
                    value={cfg.filters?.max_file_size_mb ?? 0}
                    onChange={(e) => setFilters({ max_file_size_mb: parseInt(e.target.value) || 0 })}
                    className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-400 block mb-1">最长视频时长 (分钟, 0=不限)</label>
                  <input
                    type="number" min={0}
                    value={cfg.filters?.max_duration_minutes ?? 0}
                    onChange={(e) => setFilters({ max_duration_minutes: parseInt(e.target.value) || 0 })}
                    className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200"
                  />
                </div>
              </div>

            </div>
            {/* Action Buttons */}
            <div className="flex items-center gap-3 pt-2 border-t border-gray-800">
              <div className="flex-1 min-w-0">
                {saveMsg === "success" && (
                  <span className="text-xs text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" /> 配置已保存
                  </span>
                )}
                {saveMsg === "error" && (
                  <span className="text-xs text-red-400 flex items-center gap-1">
                    <XCircle className="w-3.5 h-3.5" /> 保存失败
                  </span>
                )}
                {startResult && startResult.status === "started" && (
                    <span className="text-xs text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" /> 已启动
                    {startResult.batch_id && (
                        <span className="font-mono text-emerald-500/70 ml-1">
                        batch: {startResult.batch_id.slice(0, 8)}...
                        </span>
                      )}
                    </span>
                  )}
                {startResult && startResult.status !== "started" && (
                    <span className="text-xs text-red-400 flex items-center gap-1">
                      <XCircle className="w-3.5 h-3.5" /> {startResult.message || "启动失败"}
                    </span>
                  )}
              </div>
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-40 transition-all"
              >
                {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                {saving ? "保存中..." : "保存配置"}
              </button>
              {!isAuto && !isSingle && (
                <button
                  onClick={handleStart}
                  disabled={starting || hasRunningBatch}
                  title={hasRunningBatch ? "已有批处理任务正在运行" : "启动手动批量处理"}
                  className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-40 transition-all"
                >
                  {starting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                  {starting ? "启动中..." : hasRunningBatch ? "已有任务运行中" : "立即开始"}
                </button>
              )}
            </div>

            {/* 重置错误 - 危险操作 */}
            <div className="mt-2 pt-2 border-t border-gray-800/40 flex justify-end">
              <button
                onClick={handleResetErrors}
                disabled={resetting}
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors flex items-center gap-1"
              >
                {resetting ? <Loader2 className="w-3 h-3 animate-spin" /> : <AlertTriangle className="w-3 h-3" />}
                {resetting ? "重置中..." : "重置错误"}
              </button>
            </div>

          </>
        )}

                {checkpoints.length > 0 && (
          <div className="border-t border-gray-800 pt-3">
            <BatchProgressSection
              checkpoints={checkpoints}
              engineProgress={engineProgress}
              chunkSize={chunkSize}
              ENGINE_NAMES={ENGINE_NAMES}
              ENGINE_ORDER={ENGINE_ORDER}
            />
          </div>
        )}
        

      </div>
    </div>
  )
}

// ── Batch Progress Components ──

function BlockBar({ completed, total, running }: { completed: number; total: number; running: number }) {
  const BLOCKS = 20
  const pct = total > 0 ? completed / total : 0
  const filledBlocks = Math.round(pct * BLOCKS)
  const inProgressBlock = running > 0 && filledBlocks < BLOCKS ? filledBlocks : -1

  return (
    <div className="flex gap-[2px] items-stretch h-full">
      {Array.from({ length: BLOCKS }).map((_, i) => {
        let cls = "w-2 h-3.5 rounded-[1px] "
        if (i < filledBlocks) {
          cls += "bg-emerald-500"
        } else if (i === inProgressBlock) {
          cls += "bg-emerald-400/70 animate-pulse"
        } else {
          cls += "bg-gray-700/50"
        }
        return <div key={i} className={cls} />
      })}
    </div>
  )
}

function BatchProgressSection({
  checkpoints,
  engineProgress,
  chunkSize,
  ENGINE_NAMES,
  ENGINE_ORDER,
}: {
  checkpoints: BatchCheckpointInfo[]
  engineProgress: Record<string, Record<string, number>>
  chunkSize: number
  ENGINE_NAMES: Record<string, string>
  ENGINE_ORDER: string[]
}) {
  const runningCp = checkpoints.find((cp) => cp.status === "running")
  const displayCp = runningCp || checkpoints[0]
  const isRunning = !!runningCp

 if (!displayCp) return null

 const pct = displayCp.total_videos > 0
   ? Math.round((displayCp.processed / displayCp.total_videos) * 100)
   : 0
 const totalChunks = Math.ceil(displayCp.total_videos / (displayCp.batch_size || 1))
 const currentChunk = Math.floor(displayCp.processed / (displayCp.batch_size || 1)) + 1
  // Use engine progress to show smoother overall progress within a chunk
  const completedInChunk = engineProgress?.scene?.completed || 0
  const virtualProcessed = displayCp.processed + completedInChunk
   const hasEngineProgress = engineProgress && Object.keys(engineProgress).length > 0 && 
      Object.values(engineProgress).some((e: any) => (e.completed || 0) > 0 || (e.running || 0) > 0)

  return (
    <div className="rounded-lg border border-gray-700/40 bg-gray-800/40 p-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={
            "w-2 h-2 rounded-full " +
            (isRunning ? "bg-emerald-500 animate-pulse" :
             displayCp.status === "completed" ? "bg-emerald-500" :
             displayCp.status === "error" ? "bg-red-500" : "bg-gray-500")
          } />
          <span className="text-sm font-semibold text-gray-200">
            {displayCp.task_label} {displayCp.id.slice(0, 8)}
          </span>
          <span className={
            "text-xs font-medium " +
            (displayCp.status === "completed" ? "text-emerald-400" :
             isRunning ? "text-emerald-300" :
             displayCp.status === "error" ? "text-red-400" :
             displayCp.status === "cancelled" ? "text-gray-400" : "text-gray-400")
          }>
            · {displayCp.status === "completed" ? "✓ \u5b8c\u6210" :
               isRunning ? "\u8fd0\u884c\u4e2d" :
               displayCp.status === "error" ? "\u5931\u8d25" :
               displayCp.status === "cancelled" ? "\u5df2\u53d6\u6d88" : displayCp.status}
          </span>
        </div>
        <button
          onClick={() => window.location.reload()}
          className="text-gray-500 hover:text-gray-300 transition-colors p-1"
          title="刷新"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Per-engine progress */}
      {isRunning && hasEngineProgress && (
        <div className="space-y-1.5 mb-3">
          {ENGINE_ORDER.filter(e => engineProgress[e]).map((eng) => {
            const e = engineProgress[eng]
            const completed = e.completed || 0
            const running = e.running || 0
            const total = chunkSize || completed + running + (e.pending || 0) || 1
            const statusLabel =
              completed >= total ? "✓" :
              running > 0 ? "处理中" :
              completed > 0 ? "等待中" : "等待中"
            const statusColor =
              completed >= total ? "text-emerald-400" :
              running > 0 ? "text-emerald-300" : "text-gray-500"
            return (
              <div key={eng} className="flex items-center gap-2">
                <span className="w-14 text-xs text-gray-400 text-right shrink-0">{ENGINE_NAMES[eng] || eng}</span>
                <div className="flex-1 h-full min-h-[18px]">
                  <BlockBar completed={completed} total={total} running={running} />
                </div>
                <span className={"text-xs font-mono shrink-0 w-14 text-right " + statusColor}>
                  {completed}/{total}
                </span>
                <span className={"text-xs shrink-0 w-12 text-right " + statusColor}>
                  {statusLabel}
                </span>
              </div>
            )
          })}
        </div>
      )}

      {/* Between chunks */}
      {isRunning && (!hasEngineProgress) && (
        <div className="text-xs text-gray-500 mb-2.5 flex items-center gap-1.5">
          <Loader2 className="w-3 h-3 animate-spin" />
          {displayCp.processed > 0 ? "\u51c6\u5907\u4e0b\u4e00批次..." : "等待 AI 处理..."}
        </div>
      )}

    {/* Overall progress bar */}
    <div className="w-full h-3 bg-gray-700/40 rounded-sm overflow-hidden mb-1.5">
       <div
         className={
           "h-full transition-all duration-1000 ease-out " +
           (displayCp.status === "completed" ? "bg-emerald-500" :
            isRunning ? "bg-gradient-to-r from-emerald-600 to-emerald-400" :
            displayCp.status === "cancelled" ? "bg-gray-500" :
            "bg-emerald-500/60")
         }
          style={{
            width: isRunning && chunkSize > 0
              ? Math.min(100, Math.round((completedInChunk / chunkSize) * 100)) + "%"
              : Math.min(100, Math.round((virtualProcessed / displayCp.total_videos) * 100)) + "%"
          }}
        />
      </div>

    {/* Summary line */}
    <div className="text-xs text-gray-500">
      {isRunning || displayCp.status === "cancelled" ? (
        <>
          <span>总 {virtualProcessed}/{displayCp.total_videos}</span>
          {isRunning && chunkSize > 0 && (
            <span className="text-gray-500"> · 本批 {completedInChunk}/{chunkSize} 完成 ({Math.round(completedInChunk / chunkSize * 100)}%)</span>
          )}
         </>
        ) : displayCp.status === "completed" ? (
          <>全部完成 · 共 {displayCp.total_videos} 个视频</>
        ) : (
          <>{displayCp.processed}/{displayCp.total_videos}</>
        )}
        

      </div>
    </div>

  )
}

