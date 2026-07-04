import { useStore } from "../../stores/app"
import { useState, useEffect } from "react"
import {
  Play, Save, Video, Search, Type, Camera, Mic, Users,
  Loader2, CheckCircle2, XCircle, Filter, AlertTriangle,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { BatchProgressSection } from "./BatchProgressSection"
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
  const { t } = useTranslation()




  const loadPendingCount = async (engines?: string[], max_file_size_mb?: number, max_duration_minutes?: number) => {
    try {
      const resp = await api.getPendingAssetCount(engines, max_file_size_mb, max_duration_minutes)
      setPendingCount(resp?.selected_pending ?? resp?.total_pending ?? null)
    } catch (e) {
      console.warn("Failed to load pending count", e)
      useStore.getState().setError("Failed to load pending count")
    }
  }

  const loadCheckpoints = async () => {
    try {
      const resp = await api.listBatchCheckpoints(5)
      setCheckpoints(resp.checkpoints || [])
    } catch (e) {
      console.warn("Failed to load checkpoints", e)
      useStore.getState().setError("Failed to load checkpoints")
    }
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
      } catch (e) {
        console.warn("Engine progress poll failed", e)
      }
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
    if (!window.confirm(t('pipelineConfig.confirmReset'))) return;
   setResetting(true)
   try {
     const result = await api.resetErrorJobs()
     if (result.count > 0) {
       loadPendingCount(engines, cfg.filters?.max_file_size_mb, cfg.filters?.max_duration_minutes)
     }
   } catch (e) {
     console.error("Failed to reset error jobs", e)
     useStore.getState().setError("Failed to reset error jobs")
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
            {t('pipelineConfig.tabs.' + tab)}
            {activeTab === tab && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-500" />}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {loading ? (
          <div className="flex items-center justify-center py-8 text-gray-500">
            <Loader2 className="w-5 h-5 animate-spin mr-2" />
            {t('pipelineConfig.loading')}
          </div>
        ) : (
          <>
            {/* Whisper Warning — when both transcript + diarization are enabled */}
            {engines.includes("transcript") && engines.includes("diarization") && (
              <div className="flex items-start gap-2 p-2.5 rounded-md bg-amber-900/30 border border-amber-700/40">
                <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
                <div className="text-xs text-amber-300/90 leading-relaxed">
                  <span className="font-semibold text-amber-200">{t('pipelineConfig.whisperModeEnabled')}</span>
                  {t('pipelineConfig.whisperDesc')}<br />
                  <span className="text-amber-400/80">
                    {t('pipelineConfig.estimatePrefix')} <span className="font-bold text-amber-200">19 {t('pipelineConfig.estimateDays')}</span>
                    {" → "}{t('pipelineConfig.estimateSuffix')} <span className="font-bold text-amber-200">2 {t('pipelineConfig.estimateDays')}</span>
                  </span>
                  <br />{t('pipelineConfig.whisperTip')}
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
                {isAuto ? t('pipelineConfig.modeAuto') : isSingle ? t('pipelineConfig.modeSingle') : t('pipelineConfig.modeManual')}{" "}
                {cfg.enabled ? t('pipelineConfig.enabled') : t('pipelineConfig.disabled')}
              </span>
              {pendingCount !== null && !isSingle && (
                <span className="text-xs text-gray-500 ml-auto">
                  {t('pipelineConfig.pendingLabel')}: <span className="text-gray-400 font-mono">{pendingCount}</span> {t('pipelineConfig.pendingVideos')}
                </span>
              )}
            </label>

            {/* Engines */}
            <div>
              <label className="text-xs text-gray-500 uppercase tracking-wider font-semibold mb-2 block">
                {t('pipelineConfig.engineSelect')}
              </label>
              <div className="flex flex-wrap gap-2">
                {ALL_ENGINES.map((eng) => {
                  const selected = engines.includes(eng.id)
                  const EngineIcon = eng.icon
                  return (
                    <button
                      key={eng.id}
                      onClick={() => toggleEngine(eng.id)}
                      title={t('pipelineConfig.engines.' + eng.id + '.label')}
                      className={
                        "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all " +
                        (selected
                          ? "bg-indigo-600/30 text-indigo-300 border border-indigo-600/50"
                          : "bg-gray-800 text-gray-500 border border-gray-700 hover:border-gray-600")
                      }
                    >
                      <EngineIcon className="w-3.5 h-3.5" />
                      {t('pipelineConfig.engines.' + eng.id + '.label')}
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
                <label className="text-xs text-gray-400 block mb-1">{t('pipelineConfig.batchSize')}</label>
                <input
                  type="number" min={1} max={500}
                  value={cfg.batch_size ?? 100}
                  onChange={(e) => setCfg({ batch_size: parseInt(e.target.value) || 1 })}
                  disabled={isSingle}
                  className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200 disabled:opacity-40"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">{t('pipelineConfig.timeout')}</label>
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
                    <label className="text-xs text-gray-400 block mb-1">{t('pipelineConfig.timeWindowStart')}</label>
                    <input
                      type="number" min={0} max={23}
                      value={cfg.time_window_start ?? 0}
                      onChange={(e) => setCfg({ time_window_start: parseInt(e.target.value) || 0 })}
                      className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">{t('pipelineConfig.timeWindowEnd')}</label>
                    <input
                      type="number" min={0} max={23}
                      value={cfg.time_window_end ?? 6}
                      onChange={(e) => setCfg({ time_window_end: parseInt(e.target.value) || 6 })}
                      className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">{t('pipelineConfig.gpuThreshold')}</label>
                    <input
                      type="number" min={0} max={100}
                      value={cfg.gpu_threshold_percent ?? 50}
                      onChange={(e) => setCfg({ gpu_threshold_percent: parseInt(e.target.value) || 50 })}
                      className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">{t('pipelineConfig.checkInterval')}</label>
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
                {t('pipelineConfig.fileFilter')}
              </label>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-400 block mb-1">{t('pipelineConfig.maxFileSize')}</label>
                  <input
                    type="number" min={0}
                    value={cfg.filters?.max_file_size_mb ?? 0}
                    onChange={(e) => setFilters({ max_file_size_mb: parseInt(e.target.value) || 0 })}
                    className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-400 block mb-1">{t('pipelineConfig.maxDuration')}</label>
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
                    <CheckCircle2 className="w-3.5 h-3.5" /> {t('pipelineConfig.saved')}
                  </span>
                )}
                {saveMsg === "error" && (
                  <span className="text-xs text-red-400 flex items-center gap-1">
                    <XCircle className="w-3.5 h-3.5" /> {t('pipelineConfig.saveFailed')}
                  </span>
                )}
                {startResult && startResult.status === "started" && (
                    <span className="text-xs text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" /> {t('pipelineConfig.started')}
                    {startResult.batch_id && (
                        <span className="font-mono text-emerald-500/70 ml-1">
                        batch: {startResult.batch_id.slice(0, 8)}...
                        </span>
                      )}
                    </span>
                  )}
                {startResult && startResult.status !== "started" && (
                    <span className="text-xs text-red-400 flex items-center gap-1">
                      <XCircle className="w-3.5 h-3.5" /> {startResult.message || t('pipelineConfig.startFailed')}
                    </span>
                  )}
              </div>
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-40 transition-all"
              >
                {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                {saving ? t('pipelineConfig.saving') : t('pipelineConfig.save')}
              </button>
              {!isAuto && !isSingle && (
                <button
                  onClick={handleStart}
                  disabled={starting || hasRunningBatch}
                  title={hasRunningBatch ? t('pipelineConfig.batchRunning') : t('pipelineConfig.startManual')}
                  className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-40 transition-all"
                >
                  {starting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                  {starting ? t('pipelineConfig.starting') : hasRunningBatch ? t('pipelineConfig.taskRunning') : t('pipelineConfig.startNow')}
                </button>
              )}
            </div>

            {/* {t('pipelineConfig.resetErrors')} - 危险操作 */}
            <div className="mt-2 pt-2 border-t border-gray-800/40 flex justify-end">
              <button
                onClick={handleResetErrors}
                disabled={resetting}
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors flex items-center gap-1"
              >
                {resetting ? <Loader2 className="w-3 h-3 animate-spin" /> : <AlertTriangle className="w-3 h-3" />}
                {resetting ? t('pipelineConfig.resetting') : t('pipelineConfig.resetErrors')}
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

            />
          </div>
        )}
        

      </div>
    </div>
  )
}
