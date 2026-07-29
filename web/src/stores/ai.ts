import { create } from 'zustand'
import * as aiApi from '../api/ai'
import type { QueueStatus, PendingCounts, PipelineProgress, GPUInfo } from '../types/ai'
import type { PipelineState } from '../types/ai'
import i18n from '../i18n/config'

import { logger } from '../utils/logger';


function defaultQueueStatus(): QueueStatus {
  return { status: "idle", total: 0, completed: 0, failed: 0, skipped: 0,
    overall_progress: 0, current_video: null, current_stage: '', current_progress: 0,
    message: '', videos: [] as { file_name: string; status: string }[], model_progress: {} as Record<string, { current: number; total: number }>
  }
}
interface AIStore {
  hfToken: string
  hfTokenSet: boolean
  modelStatus: Record<string, boolean> | null
  modelStatusLoading: boolean
  downloadingSet: Set<string>
  gpuInfo: GPUInfo
  gpuInfoLoading: boolean
  pipelineVideoId: string | null
  pipelineProgress: PipelineProgress | null
  pendingCounts: PendingCounts | null
  pendingLoading: boolean
  batchStarting: boolean
  sseActive: boolean
  queueStatus: QueueStatus
  error: string | null
  clearError: () => void

  moduleConfig: Record<string, any> | null
  moduleConfigLoading: boolean
  moduleConfigSaving: boolean
  fetchModuleConfig: () => Promise<void>
  saveModuleConfig: (config: Record<string, any>) => Promise<boolean>

  setHfToken: (t: string) => void
  saveHfToken: () => Promise<void>
  loadHfTokenStatus: () => Promise<void>
  fetchModelAndGpu: () => Promise<void>
  fetchPendingCount: () => Promise<void>
  fetchScanStatus: () => Promise<void>
  setPipelineVideoId: (id: string | null) => void
  setPipelineProgress: (p: PipelineProgress | null) => void
  setQueueStatus: (s: QueueStatus | ((prev: QueueStatus) => QueueStatus)) => void
  setBatchStarting: (v: boolean) => void
  setDownloading: (model: string, loading: boolean) => void
  handleModelAction: (model: string, action: 'load' | 'unload') => Promise<void>
  handleRunBatchPipeline: () => Promise<void>
  handleScanLibrary: () => Promise<void>
  startPolling: () => () => void
  startSSE: () => () => void
}

export const useAIStore = create<AIStore>((set, get) => ({
  hfToken: '',
  hfTokenSet: false,
  modelStatus: null,
 modelStatusLoading: true,
 downloadingSet: new Set(),
  gpuInfo: { used: 0, total: 0, percent: 0 },
 gpuInfoLoading: true,
  pipelineVideoId: null,
  pipelineProgress: null,
  pendingCounts: null,
  pendingLoading: true,
  batchStarting: false,
  sseActive: false,
  queueStatus: defaultQueueStatus(),
  error: null,
  moduleConfig: null,
  moduleConfigLoading: true,
  moduleConfigSaving: false,

  clearError: () => set({ error: null }),

  fetchModuleConfig: async () => {
    try {
      const resp = await aiApi.getModulesConfig()
      if (resp?.config) {
        const modIds = ["scene","yolo","ocr","clip","whisper","diarization"]
        const filtered: Record<string, any> = {}
        for (const id of modIds) { if (resp.config[id]) filtered[id] = { ...resp.config[id] } }
        set({ moduleConfig: filtered, moduleConfigLoading: false })
      } else {
        set({ moduleConfigLoading: false })
      }
    } catch (err) {
      logger.error("fetchModuleConfig failed:", err)
      set({ error: "\u83b7\u53d6\u6a21\u5757\u914d\u7f6e\u5931\u8d25: " + (err as Error).message, moduleConfigLoading: false })
    }
  },

  saveModuleConfig: async (config: Record<string, any>) => {
    set({ moduleConfigSaving: true })
    try {
      await aiApi.saveModulesConfig(config)
      set({ moduleConfig: config, moduleConfigSaving: false })
      return true
    } catch (err) {
      logger.error("saveModuleConfig failed:", err)
      set({ error: "\u4fdd\u5b58\u6a21\u5757\u914d\u7f6e\u5931\u8d25: " + (err as Error).message, moduleConfigSaving: false })
      return false
    }
  },

  setHfToken: (t) => set({ hfToken: t }),

  saveHfToken: async () => {
    try {
      await aiApi.setHFToken(get().hfToken)
      set({ hfTokenSet: true })
    } catch (err) { logger.error('saveHfToken failed:', err); set({ error: 'Failed to save HF token: ' + (err as Error).message }) }
  },

  loadHfTokenStatus: async () => {
    try {
      const data = await aiApi.getHFTokenStatus()
      set({ hfTokenSet: data.set })
    } catch (err) { logger.error('loadHfTokenStatus failed:', err); set({ error: 'Failed to load HF token status: ' + (err as Error).message }) }
  },

  fetchModelAndGpu: async () => {
    try {
      const data = await aiApi.getAIModelStatus()
      const gpu = data.gpu as any; const mappedGpu: GPUInfo = { used: gpu.used ?? 0, total: gpu.total ?? 0, percent: gpu.percent ?? 0 }; set({ modelStatus: data.models, gpuInfo: mappedGpu, gpuInfoLoading: false, modelStatusLoading: false })
    } catch (err) { logger.error('fetchModelAndGpu failed:', err); set({ error: i18n.t('store.loadFailed') + ': ' + (err as Error).message, gpuInfoLoading: false, modelStatusLoading: false }) }
  },

  fetchPendingCount: async () => {
    try {
      const data: any = await aiApi.getPendingAssetCount()
      set({ pendingCounts: data, pendingLoading: false })
    } catch (err) { logger.error('fetchPendingCount failed:', err); set({ error: 'Failed to fetch pending counts: ' + (err as Error).message, pendingLoading: false }) }
  },


  fetchScanStatus: async () => {
    try {
      const data = await aiApi.getScanStatusAI()
      if (!data) return
      set((s) => {
        if (data.status === 'idle' && s.queueStatus.status === 'idle' && s.queueStatus.total > 0) return {}
        if (s.queueStatus.status === 'completed' && data.status === 'completed') return {}
        // When SSE is active, polling data may be stale; preserve real-time fields
        const update: Partial<QueueStatus> = {
          status: (data.paused ? "paused" : data.status) as PipelineState,
          total: data.total || 0,
          completed: data.completed || s.queueStatus.completed,
          failed: data.failed || s.queueStatus.failed,
          skipped: data.skipped || s.queueStatus.skipped,
          model_progress: (data.model_progress as any) || s.queueStatus.model_progress,
          videos: (data.videos as any) || s.queueStatus.videos,
        }
        if (!s.sseActive) {
          // Polling is the only data source; overwrite all fields
          update.overall_progress = data.overall_progress || 0
          update.current_progress = data.current_progress || 0
          update.current_stage = data.current_stage || s.queueStatus.current_stage
          update.current_video = data.current_video || s.queueStatus.current_video
          update.message = data.message || ''
        }
        return { queueStatus: { ...s.queueStatus, ...update } }
      })
    } catch (err) { logger.error('fetchScanStatus failed:', err); set({ error: 'Failed to fetch scan status: ' + (err as Error).message }) }
  },




  setPipelineVideoId: (id) => set({ pipelineVideoId: id }),
  setPipelineProgress: (p) => set({ pipelineProgress: p }),
  setQueueStatus: (s) => set((state) => ({ queueStatus: typeof s === 'function' ? s(state.queueStatus) : s })),
  setBatchStarting: (v) => set({ batchStarting: v }),
  setDownloading: (model, loading) => {
    set((s) => {
      const next = new Set(s.downloadingSet)
      if (loading) next.add(model); else next.delete(model)
      return { downloadingSet: next }
    })
  },

  handleModelAction: async (model, action) => {
    get().setDownloading(model, true)
    try {
      if (action === 'load') await aiApi.loadAIModel(model); else await aiApi.unloadAIModel(model)
      await get().fetchModelAndGpu()
    } catch (err) { logger.error('handleModelAction failed:', err); set({ error: 'Model action failed: ' + (err as Error).message }) }
    finally { get().setDownloading(model, false) }
  },

 handleRunBatchPipeline: async () => {
   set({ batchStarting: true, queueStatus: { ...defaultQueueStatus(), status: 'running', message: 'Batch processing started...' } })
   try {
      const res: any = await aiApi.startManualPipeline()
     if (res.status === 'already_running') { /* already running, polling will pick up */ }
      else if (res.status === 'started') {
       /* Keep "running" UI immediately; polling will pick up real state within 3s.
          Don't call getScanStatusAI() here — it's a race: the background thread
          may not have updated _scan_state yet, causing a flash back to "idle". */
     }
     get().fetchPendingCount()
   } catch (err) { logger.error('handleRunBatchPipeline failed:', err); set({ error: 'Batch pipeline failed: ' + (err as Error).message }) }
   finally { set({ batchStarting: false }) }
 },

  handleScanLibrary: async () => {
    try {
      const res: any = await aiApi.scanLibraryAI()
      set({ queueStatus: { ...defaultQueueStatus(), status: 'running', message: res.message || 'Scanning...' } })
    } catch (err) { logger.error('handleScanLibrary failed:', err); set({ error: 'Scan library failed: ' + (err as Error).message }) }
  },




  startPolling: () => {
    const store = get()
    store.loadHfTokenStatus()
    store.fetchModelAndGpu()
    store.fetchPendingCount()
    store.fetchModuleConfig()
    store.fetchScanStatus()

    const intervals = [
      setInterval(() => get().fetchModelAndGpu(), 10000),
      setInterval(() => get().fetchPendingCount(), 10000),
      setInterval(() => get().fetchScanStatus(), 2000),
      setInterval(() => get().fetchModuleConfig(), 30000),
    ]
    return () => intervals.forEach(clearInterval)
  },

  startSSE: () => {
    const url = aiApi.scanEventsUrl()
    const MAX_VIDEOS = 100
    const es = new EventSource(url)

    es.onmessage = (e) => {
      if (e.data.startsWith(':')) return
      try {
        const evt = JSON.parse(e.data)
        const store = get()
        set({ sseActive: true })

        if (evt.type === 'batch_progress') {
          store.setPipelineProgress({ status: 'running', progress: evt.progress || 0, message: evt.stage || '' })
        } else if (evt.type === 'complete' || evt.type === 'error') {
          store.setPipelineProgress(null)
        } else if (evt.type === 'loop_progress') {
          store.setPipelineProgress({ status: 'running', progress: evt.overall_progress || 0, message: 'Loop ' + (evt.overall_progress || 0) + '%' })
        }

        store.setQueueStatus((prev) => {
          const base = { ...prev }
          switch (evt.type) {
            case 'start': {
              const vidList = evt.videos ? evt.videos.map((fn: string) => ({ file_name: fn, status: 'pending' as const })) : []
              return { ...base, status: 'running', total: Number(evt.total), skipped: Number(evt.skipped || 0), message: 'Batch processing ' + vidList.length + ' videos', videos: vidList }
            }
            case 'video_start': {
              const videos = [...base.videos]
              if (!videos.some((v) => v.file_name === evt.file_name)) {
                videos.push({ file_name: evt.file_name, status: 'processing' })
                if (videos.length > MAX_VIDEOS) videos.splice(0, videos.length - MAX_VIDEOS)
              }
              return { ...base, videos, current_video: { file_name: evt.file_name }, current_stage: 'Queued', current_progress: 0, message: 'Processing ' + evt.file_name + ' (' + evt.index + '/' + evt.total + ')' }
            }
            case 'video_progress': {
              if (evt.file_name) {
                const videos = [...base.videos]
                if (!videos.some((v) => v.file_name === evt.file_name)) {
                  videos.push({ file_name: evt.file_name, status: 'processing' })
                  if (videos.length > MAX_VIDEOS) videos.splice(0, videos.length - MAX_VIDEOS)
                }
                return { ...base, videos }
              }
              return base
            }
            case 'batch_progress': {
              const bpVideos = [...base.videos]
              if (evt.video_name && evt.video_name !== '' && evt.video_name !== 'BATCH PROCESS') {
                const bpIdx = bpVideos.findIndex((v) => v.file_name === evt.video_name)
                if (bpIdx >= 0 && bpVideos[bpIdx].status !== 'processing') {
                  bpVideos[bpIdx] = { ...bpVideos[bpIdx], status: 'processing' }
                }
              }
              const total = base.total || 1
              const done = (base.completed || 0) + (base.failed || 0)
              const videoFraction = (evt.progress || 0) / 100 / total
              const estimated = Math.min(99, Math.round((done / total * 100) + videoFraction * 100))
              return { ...base, status: 'running', current_stage: evt.stage, current_progress: evt.stage_progress !== undefined ? evt.stage_progress : evt.progress, overall_progress: evt.overall_progress !== undefined ? evt.overall_progress : estimated, current_video: evt.video_name ? { file_name: evt.video_name } : base.current_video, videos: bpVideos, completed: evt.completed !== undefined ? evt.completed : base.completed, failed: evt.failed !== undefined ? evt.failed : base.failed, model_progress: evt.model_progress || {} }
            }
            case 'video_end': {
              store.fetchPendingCount()
              const videos = [...base.videos]
              const idx = videos.findIndex((v) => v.file_name === evt.file_name)
              if (idx >= 0) videos[idx] = { ...videos[idx], status: 'completed' }
              return { ...base, videos, completed: evt.completed, failed: evt.failed, overall_progress: evt.overall_progress, current_video: null, current_stage: '', current_progress: 0, message: evt.file_name + ' done' }
            }
            case 'video_error': {
              store.fetchPendingCount()
              const videos = [...base.videos]
              const idx = videos.findIndex((v) => v.file_name === evt.file_name)
              if (idx >= 0) videos[idx] = { ...videos[idx], status: 'failed' }
              return { ...base, videos, failed: base.failed + 1, current_video: null, message: 'Error: ' + (evt.error || evt.file_name) }
            }
            case 'paused': store.fetchPendingCount(); return { ...base, status: 'paused', message: 'Paused' }
            case 'complete': {
              store.fetchPendingCount()
              const videos = base.videos.map((v) => v.status === 'processing' ? { ...v, status: 'completed' as const } : v)
              return { ...base, videos, status: 'completed', completed: evt.completed, failed: evt.failed, skipped: evt.skipped || 0, overall_progress: 100, message: 'Complete: ' + evt.completed + ' done, ' + evt.failed + ' failed' + (evt.skipped ? ', ' + evt.skipped + ' skipped' : '') }
            }
            case 'error': return { ...base, status: 'error', message: evt.message }
            case 'video_skipped': store.fetchPendingCount(); return { ...base, message: 'Skipped: ' + (evt.file_name || 'unknown') + ' - ' + (evt.reason || '') }
            case 'loop_progress': {
              const total = base.total || 1
              const done = (evt.completed || 0) + (evt.failed || 0)
              return { ...base, status: 'running', overall_progress: Math.min(99, Math.round((done / total * 100))), completed: evt.completed !== undefined ? evt.completed : base.completed, failed: evt.failed !== undefined ? evt.failed : base.failed, model_progress: evt.model_progress || base.model_progress || {} }
            }
            default: return base
          }
        })
      } catch { /* SSE JSON parse errors — non-critical */ }
    }

    es.onerror = () => { set({ sseActive: false, error: i18n.t('store.sseDisconnected') }) }
    return () => es.close()
  }
}))
