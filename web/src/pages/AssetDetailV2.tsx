import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Heart, Archive, RotateCcw, Clock, Maximize2, Film,
  Hash, FileText, Tag, Volume2, Loader2, Info,
  Sparkles, RefreshCw,
  ImagePlay, ScanEye, Brain, AudioLines, Users,
  CheckCircle2, AlertCircle, MinusCircle
} from 'lucide-react'
import { useAssetStore } from '../stores/asset'
import { api } from '../api/client'
import * as aiApi from '../api/ai'
import { VideoPlayer } from '../components/VideoPlayer'
import { useTranslation } from 'react-i18next'
import { MetadataPanel } from '../components/MetadataPanel'

function getResolutionLabel(w?: number, h?: number, t?: (key: string) => string): string {
  if (!w || !h) return ''
  const max = Math.max(w, h)
  let level = ''
  if (max >= 7680) level = '8K'
  else if (max >= 3840) level = '4K'
  else if (max >= 2560) level = '2K'
  else if (max >= 1920) level = '1080p'
  else if (max >= 1280) level = '720p'
  else if (max >= 720) level = '480p'
  else level = 'SD'
  const orientation = w > h
    ? (t ? t('assetDetail.orientationLandscape') : 'Landscape')
    : w < h
      ? (t ? t('assetDetail.orientationPortrait') : 'Portrait')
      : (t ? t('assetDetail.orientationSquare') : 'Square')
  return `${w}\u00d7${h} (${level} ${orientation})`
}

function getExtension(path?: string): string {
  if (!path) return ''
  return path.split('.').pop()?.toUpperCase() || ''
}

function getEngineDefs(t: (key: string) => string) {
  return [
  { key: 'scene', label: t('assetDetail.engineScene'), icon: ImagePlay, color: 'text-cyan-400', bgColor: 'bg-cyan-500/10' },
  { key: 'yolo', label: t('assetDetail.engineYolo'), icon: Tag, color: 'text-amber-300', bgColor: 'bg-amber-500/10' },
  { key: 'ocr', label: t('assetDetail.engineOcr'), icon: ScanEye, color: 'text-violet-400', bgColor: 'bg-violet-500/10' },
  { key: 'clip', label: t('assetDetail.engineClip'), icon: Brain, color: 'text-indigo-400', bgColor: 'bg-indigo-500/10' },
  { key: 'transcript', label: t('assetDetail.engineTranscript'), icon: AudioLines, color: 'text-pink-400', bgColor: 'bg-pink-500/10' },
  { key: 'diarization', label: t('assetDetail.engineDiarization'), icon: Users, color: 'text-orange-400', bgColor: 'bg-orange-500/10' },
  ]
}

function EngineStatusIcon({ status }: { status: string }) {
  if (status === "completed") return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
  if (status === "running") return <Loader2 className="w-3.5 h-3.5 text-amber-400 animate-spin" />
  if (status === "error") return <AlertCircle className="w-3.5 h-3.5 text-red-400" />
  return <MinusCircle className="w-3.5 h-3.5 text-gray-600" />
}

function EngineStatusLabel({ status, t }: { status: string; t: (key: string) => string }) {
 if (status === "completed") return <span className="text-emerald-400 text-[10px]">{t("assetDetail.statusCompleted")}</span>
 if (status === "running") return <span className="text-amber-400 text-[10px]">{t("assetDetail.statusRunning")}</span>
 if (status === "error") return <span className="text-red-400 text-[10px]">{t("assetDetail.statusError")}</span>
 return <span className="text-gray-600 text-[10px]">{t("assetDetail.statusPending")}</span>
}

function InfoPill({ icon: Icon, label }: { icon: React.ComponentType<{ className?: string }>; label: string }) {
  return (
    <div className="inline-flex items-center gap-1 px-2.5 py-1 bg-gray-900 rounded-full border border-gray-800 text-xs text-gray-400 whitespace-nowrap">
      <Icon className="w-3 h-3 text-gray-500" />
      <span>{label}</span>
    </div>
  )
}

function SceneThumbnail({ seg, tags, ocrTexts, formatDuration, onClick, thumbnailUrl }: {
  seg: { id: string; start_time: number; end_time: number; thumbnail_path?: string; scene_label?: string }
  ocrTexts?: Array<{text: string; confidence: number; bbox?: {x: number; y: number; w: number; h: number}}>
  thumbnailUrl?: string
  tags?: Array<{label: string; confidence: number; count: number}>
  formatDuration: (s?: number) => string
  onClick: () => void
}) {
  const [imgError, setImgError] = useState<"primary" | "fallback" | null>(null)
  const { t } = useTranslation()
  const showPrimary = thumbnailUrl && imgError !== "primary"
  const showFallback = !showPrimary && seg.thumbnail_path && imgError !== "fallback"
  return (
    <div className="group relative w-full bg-gray-800 rounded-lg overflow-hidden cursor-pointer hover:ring-2 hover:ring-indigo-500/50 transition-all" onClick={onClick} title={t('assetDetail.clickJump')} style={{ aspectRatio: "16/9" }}>
      {showPrimary ? (
        <img src={thumbnailUrl} alt="" loading="lazy" className="w-full h-full object-cover" onError={() => setImgError("primary")} />
      ) : showFallback ? (
        <img src={api.segmentThumbnailUrl(seg.id)} alt="" loading="lazy" className="w-full h-full object-cover" onError={() => setImgError("fallback")} />
      ) : (
        <div className="flex items-center justify-center h-full"><Film className="w-4 h-4 text-gray-500" /></div>
      )}
      {tags && tags.length > 0 && (
        <div className="absolute top-1 left-1 flex flex-wrap gap-0.5 max-w-[70%]">
          {tags.slice(0, 3).map((t) => (
            <span key={t.label} className="text-[9px] bg-black/70 text-white px-1 py-0.5 rounded">{t.label}</span>
          ))}
        </div>
      )}
      {ocrTexts && ocrTexts.length > 0 && (
        <div className="absolute top-1 right-1 flex flex-col gap-0.5 max-w-[60%]">
          {ocrTexts.slice(0, 2).map((o, i) => (
            <span key={i} className="text-[9px] bg-black/70 text-gray-400 px-1 py-0.5 rounded truncate" title={o.text}>
              {o.text.length > 20 ? o.text.substring(0, 18) + "..." : o.text}
            </span>
          ))}
          {ocrTexts.length > 2 && (
            <span className="text-[8px] bg-black/50 text-gray-500 px-1 py-0.5 rounded text-center">+{ocrTexts.length - 2}</span>
          )}
        </div>
      )}
      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors" />
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 p-1.5">
        <p className="text-xs text-gray-200 font-medium">{seg.scene_label || formatDuration(seg.start_time)}</p>
        <p className="text-xs text-gray-500">{formatDuration(seg.start_time)} - {formatDuration(seg.end_time)}</p>
      </div>
    </div>
  )
}

export function AssetDetailV2() {
  const { t } = useTranslation()
  const engineDefs = getEngineDefs(t)
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const currentAsset = useAssetStore((s) => s.currentAsset)
  const loadAsset = useAssetStore((s) => s.loadAsset)

  const [loading, setLoading] = useState(true)
  const [, setError] = useState<string | null>(null)
  const [aiProcessing, setAiProcessing] = useState(false)
  const [resettingAI, setResettingAI] = useState(false)
  const [pipelineError, setPipelineError] = useState<string | null>(null)
  const [seekTime, setSeekTime] = useState<number | null>(null)
  const [aiScenes, setAiScenes] = useState<Array<{
    id: string; scene_index: number; start_time: number; end_time: number;
    thumbnail_path: string;
    tags: Array<{label: string; confidence: number; count: number}>;
    ocr_texts: Array<{text: string; confidence: number; bbox?: {x:number;y:number;w:number;h:number}}>;
  }>>([])
  const [aiTranscript, setAiTranscript] = useState<Array<{id: string; start: number; end: number; text: string; speaker: string | null}>>([])
  const [speakers, setSpeakers] = useState<string[]>([])
  const [engineJobs, setEngineJobs] = useState<Record<string, string>>({})
  const [sceneTags, setSceneTags] = useState<Array<{label: string; total_count: number}>>([])
  const [selectedSpeaker, setSelectedSpeaker] = useState<string | null>(null)
  const [loadedTabs, setLoadedTabs] = useState<Set<string>>(new Set())
  const [ocrTexts, setOcrTexts] = useState<Array<{scene_id: string; scene_time: number; text: string; confidence: number}>>([])
  const [activeTab, setActiveTab] = useState<string>("scenes")

  const TABS = [
    { id: "scenes", label: t('assetDetail.engineScene'), icon: ImagePlay },
    { id: "whisper", label: "Whisper", icon: AudioLines },

    { id: "ocr", label: "OCR", icon: ScanEye },
    { id: "detail", label: t('assetDetail.detail'), icon: Info },
  ]

  const speakerColors = ["#818cf8", "#34d399", "#f472b6", "#fbbf24", "#60a5fa", "#a78bfa", "#fb923c", "#2dd4bf"]
  const getSpeakerColor = (s: string) => speakerColors[speakers.indexOf(s) % speakerColors.length]

  useEffect(() => {
    if (!id) return
    setLoading(true)
    Promise.all([
      loadAsset(id),
      aiApi.getAIScenes(id).then((r: any) => { if (r.results?.length) setAiScenes(r.results) }).catch((e: any) => console.error("load AI scenes failed:", e)),
      aiApi.getAISubtitles(id).then((r: any) => { if (r.results?.length) setAiTranscript(r.results) }).catch((e: any) => console.error("load AI subs failed:", e)),
      aiApi.getAISpeakers(id).then((r: any) => { if (r.speakers?.length) setSpeakers(r.speakers) }).catch((e: any) => console.error("load AI speakers failed:", e)),
      aiApi.getAITags(id).then((r: any) => { if (r.tags?.length) setSceneTags(r.tags) }).catch((e: any) => console.error("load AI tags failed:", e)),
      aiApi.getEngineJobStatus(id).then((r: any) => { if (r.jobs) setEngineJobs(r.jobs) }).catch((e: any) => console.error("load engine jobs failed:", e)),
    ]).finally(() => setLoading(false))
  }, [id])

  useEffect(() => {
    if (!id || loadedTabs.has(activeTab)) return
    if (activeTab === "ocr") {
      const allOcr: Array<{scene_id: string; scene_time: number; text: string; confidence: number}> = []
      for (const sc of aiScenes) {
        if (sc.ocr_texts?.length) {
          for (const o of sc.ocr_texts) {
            allOcr.push({ scene_id: sc.id, scene_time: sc.start_time, text: o.text, confidence: o.confidence })
          }
        }
      }
      setOcrTexts(allOcr)
    }
    setLoadedTabs(prev => new Set(prev).add(activeTab))
  }, [id, activeTab, loadedTabs, aiScenes])

  const handleSeek = useCallback((time: number) => {
    setSeekTime(time)
    setTimeout(() => {
      document.getElementById("player-section")?.scrollIntoView({ behavior: "smooth", block: "start" })
    }, 100)
  }, [])

  const handleStartAIPipeline = async () => {
    if (!id || aiProcessing) return
    setAiProcessing(true)
    setPipelineError(null)
    try {
      const res = await aiApi.startSinglePipeline(id)
      if (res.status === "error") {
        setPipelineError(res.message || t("assetDetail.aiStartFailed"))
        setAiProcessing(false)
        return
      }
    } catch (e: any) {
      setPipelineError(e.message || t("assetDetail.aiStartFailed"))
      setAiProcessing(false)
      return
    }
    const poll = setInterval(async () => {
      try {
        const status = await aiApi.getResultsReady(id)
        setEngineJobs(status.jobs)
        const readyValues = Object.values(status.results_ready)
        if (readyValues.length > 0 && readyValues.every(v => v === true)) {
          const [scenesRes, subsRes, speakersRes, tagsRes] = await Promise.all([
            aiApi.getAIScenes(id), aiApi.getAISubtitles(id), aiApi.getAISpeakers(id), aiApi.getAITags(id),
          ])
          if ((scenesRes as any).results?.length) setAiScenes((scenesRes as any).results)
          if ((subsRes as any).results?.length) setAiTranscript((subsRes as any).results)
          if ((speakersRes as any).speakers?.length) setSpeakers((speakersRes as any).speakers)
          if ((tagsRes as any).tags?.length) setSceneTags((tagsRes as any).tags)
          loadAsset(id)
          clearInterval(poll)
          setAiProcessing(false)
        } else if (status.state === "error") {
          setPipelineError(t("assetDetail.aiEngineError"))
          setAiProcessing(false)
          clearInterval(poll)
        }
      } catch {
        setPipelineError(t("assetDetail.aiPollError"))
        clearInterval(poll)
        setAiProcessing(false)
      }
    }, 3000)
    setTimeout(() => { clearInterval(poll); setAiProcessing(false) }, 600000)
  }



  const handleResetAI = async () => {
    if (!id || !window.confirm(t("assetDetail.resetAIConfirm"))) return
    setResettingAI(true)
    try {
      await aiApi.resetSingleAssetAI(id)
      loadAsset(id)
      setEngineJobs({})
      setAiScenes([]); setAiTranscript([]); setSpeakers([])
      setSceneTags([]); setOcrTexts([]); setLoadedTabs(new Set())
    } catch { setError(t("assetDetail.resetAIFailed")) }
    finally { setResettingAI(false) }
  }
  const formatDuration = (s?: number) => {
    if (!s) return "--:--"
    const m = Math.floor(s / 60); const sec = Math.floor(s % 60)
    return `${m}:${sec.toString().padStart(2, "0")}`
  }
  const formatSize = (bytes: number) => {
    if (bytes < 1e6) return `${(bytes / 1e3).toFixed(0)} KB`
    if (bytes < 1e9) return `${(bytes / 1e6).toFixed(1)} MB`
    return `${(bytes / 1e9).toFixed(2)} GB`
  }



  if (loading) {
    return (
      <div className="h-full flex flex-col">
        <div className="h-14 px-6 border-b border-gray-800 flex items-center gap-3">
          <div className="w-5 h-5 bg-gray-800 rounded animate-pulse" />
          <div className="h-5 w-48 bg-gray-800 rounded animate-pulse" />
        </div>
        <div className="flex-1 overflow-y-auto p-6 max-w-7xl mx-auto w-full space-y-6">
          <div className="aspect-video bg-gray-900 rounded-lg animate-pulse" />
          <div className="flex gap-2">{[1,2,3,4,5,6].map(i => <div key={i} className="h-6 w-20 bg-gray-900 rounded-full animate-pulse" />)}</div>
        </div>
      </div>
    )
  }

  if (!currentAsset) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-500">
        <Film className="w-12 h-12 mb-3 text-gray-700" />
        <p>{t("assetDetail.notFound")}</p>
        <button onClick={() => navigate("/")} className="mt-4 text-indigo-400 hover:text-indigo-300">{t("assetDetail.goBack")}</button>
      </div>
    )
  }

  const a = currentAsset
  const displayedScenes = aiScenes
  const filteredTranscript = selectedSpeaker ? aiTranscript.filter(s => s.speaker === selectedSpeaker) : aiTranscript

  return (
    <div className="h-full flex flex-col">
      <header className="flex items-center gap-3 px-6 py-2 border-b border-gray-800 shrink-0">
        <button onClick={() => navigate(-1)} className="text-gray-400 hover:text-white transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <h1 className="text-lg font-medium text-white truncate">{a.file_name}</h1>
        <div className="flex-1" />
        <button onClick={async () => { await api.updateAsset(a.id, { is_archived: !a.is_archived }); loadAsset(a.id) }}
          className={`transition-colors ${a.is_archived ? "text-indigo-400" : "text-gray-500 hover:text-indigo-400"}`}
          title={a.is_archived ? t('assetDetail.unarchive') : t('assetDetail.archive')}>
          {a.is_archived ? <RotateCcw className="w-5 h-5" /> : <Archive className="w-5 h-5" />}
        </button>
        <button onClick={async () => { await api.updateAsset(a.id, { is_favorite: !a.is_favorite }); loadAsset(a.id) }}
          className={`transition-colors ${a.is_favorite ? "text-red-400" : "text-gray-500 hover:text-red-400"}`}>
          <Heart className={`w-5 h-5 ${a.is_favorite ? "fill-red-400" : ""}`} />
        </button>
        <button onClick={handleResetAI} disabled={resettingAI}
          className="text-gray-500 hover:text-red-400 transition-colors disabled:opacity-50" title={t('assetDetail.resetAI')}>
          <RefreshCw className={`w-5 h-5 ${resettingAI ? "animate-spin" : ""}`} />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-7xl mx-auto p-6 space-y-5">

          <div id="player-section" className="flex gap-3">
            <div className="flex-1 min-w-0">
              <VideoPlayer transcript={filteredTranscript} seekTime={seekTime} onSeek={handleSeek} />
            </div>
            {displayedScenes.length > 0 && (
              <div className="hidden md:flex flex-col gap-1 w-28 shrink-0 max-h-[400px] overflow-y-auto rounded-lg bg-gray-900/50 p-1 border border-gray-800/50">
                {displayedScenes.slice(0, 20).map((sc) => (
                  <div key={sc.id}
                    className="relative aspect-video bg-gray-800 rounded cursor-pointer hover:ring-2 hover:ring-indigo-500/50 overflow-hidden shrink-0 transition-all"
                    onClick={() => handleSeek(sc.start_time)} title={t('assetDetail.jumpTo', { time: formatDuration(sc.start_time) })}>
                    {sc.id ? <img src={api.sceneThumbnailUrl(sc.id)} alt="" className="w-full h-full object-cover" loading="lazy" />
                      : <div className="flex items-center justify-center h-full"><Film className="w-3 h-3 text-gray-500" /></div>}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {engineDefs.map((eng) => {
              const status = engineJobs[eng.key] || "pending"
              return (
                <div key={eng.key} className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border ${eng.bgColor} border-gray-800`}>
                  <eng.icon className={`w-4 h-4 ${eng.color}`} />
                  <span className={`text-xs font-medium ${eng.color}`}>{eng.label}</span>
                  <EngineStatusIcon status={status} />
                  <EngineStatusLabel status={status} t={t} />
                </div>
              )
            })}
          </div>

          <div className="flex items-center gap-1.5 flex-wrap">
            <InfoPill icon={Clock} label={formatDuration(a.duration)} />
            {a.width && a.height && <InfoPill icon={Maximize2} label={getResolutionLabel(a.width, a.height, t)} />}
            {(() => {
              const ext = getExtension(a.original_path)
              if (!ext) return null
              return <InfoPill icon={ext === "MOV" ? Film : FileText} label={ext} />
            })()}
            {a.codec && <InfoPill icon={Film} label={a.codec.toUpperCase()} />}
            <InfoPill icon={Hash} label={formatSize(a.file_size)} />
            {a.fps && <InfoPill icon={Clock} label={`${a.fps} fps`} />}
            {a.has_audio !== undefined && <InfoPill icon={Volume2} label={a.has_audio ? t('assetDetail.hasAudio') : t('assetDetail.noAudio')} />}
          </div>

          {a.tags.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <Tag className="w-3.5 h-3.5 text-gray-500" />
              {a.tags.map((tag) => (
                <span key={tag} className="px-2.5 py-0.5 text-xs rounded-full bg-gray-800 text-gray-400 border border-gray-700">{tag}</span>
              ))}
            </div>
          )}

          {a.notes && (
            <div className="text-sm text-gray-400 bg-gray-900/50 rounded-lg p-3 border border-gray-800/60 leading-relaxed">{a.notes}</div>
          )}

          {sceneTags.length === 0 && aiScenes.length === 0 && aiTranscript.length === 0 && (
            <div className="flex flex-col items-center justify-center py-8 text-gray-500 border border-dashed border-gray-800 rounded-lg">
              <Sparkles className="w-8 h-8 mb-2 text-gray-700" />
              <p className="text-sm mb-3">{t("assetDetail.noAIData")}</p>
              <button onClick={handleStartAIPipeline} disabled={aiProcessing}
                className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white transition-colors">
                {aiProcessing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                {aiProcessing ? t("assetDetail.aiProcessing") : t("assetDetail.runPipeline")}
              </button>
              {pipelineError && <p className="text-xs text-red-400 mt-2">{pipelineError}</p>}
            </div>
          )}

          {pipelineError && (sceneTags.length > 0 || aiScenes.length > 0) && (
            <div className="flex items-center gap-2 px-3 py-2 bg-red-900/20 border border-red-800/30 rounded-lg text-xs text-red-400">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />{pipelineError}
            </div>
          )}

          <div className="flex items-center gap-1 border-b border-gray-800 overflow-x-auto">
            {TABS.map(tab => {
              const Icon = tab.icon
              return (
                <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px shrink-0 ${
                    activeTab === tab.id ? "text-indigo-400 border-indigo-500" : "text-gray-500 border-transparent hover:text-gray-400 hover:border-gray-600"
                  }`}>
                  <Icon className="w-4 h-4" /><span>{tab.label}</span>
                </button>
              )
            })}
            <div className="flex-1" />
            {activeTab !== "detail" && (
              <button onClick={handleStartAIPipeline} disabled={aiProcessing}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white transition-colors">
                {aiProcessing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
                {aiProcessing ? t("assetDetail.processing") : t("assetDetail.aiProcess")}
              </button>
            )}
          </div>

          {activeTab === "scenes" && (
            displayedScenes.length > 0 ? (
              <div>
                {sceneTags.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-4">
                    {sceneTags.slice(0, 50).map(tag => (
                      <span key={tag.label} className="px-3 py-1.5 text-sm rounded-lg bg-gray-800/80 text-gray-300 border border-gray-700 hover:border-amber-500/50 transition-colors"
                        title={t('assetDetail.appearsCount', { count: tag.total_count })}>
                        {tag.label}<span className="ml-1.5 text-xs text-gray-500">x{tag.total_count}</span>
                      </span>
                    ))}
                  </div>
                )}
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
                  {displayedScenes.map((seg) => (
                    <SceneThumbnail key={seg.id} seg={seg} tags={seg.tags} ocrTexts={seg.ocr_texts}
                      formatDuration={formatDuration} onClick={() => handleSeek(seg.start_time)}
                      thumbnailUrl={api.sceneThumbnailUrl(seg.id)} />
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-gray-500">
                <ImagePlay className="w-10 h-10 mb-2 text-gray-700" /><p className="text-sm">{t("assetDetail.noScenes")}</p>
              </div>
            )
          )}

          {activeTab === "whisper" && (
            <div>
              {speakers.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 mb-3">
                  <span className="text-xs text-gray-500 font-medium">{t("assetDetail.speakersLabel")}</span>
                  <button onClick={() => setSelectedSpeaker(null)}
                    className={`px-2 py-0.5 text-xs rounded-full transition-colors ${selectedSpeaker === null ? "bg-indigo-600 text-white" : "bg-gray-800 text-gray-400 hover:text-white"}`}>{t('assetDetail.all')}</button>
                  {speakers.map(sp => (
                    <button key={sp} onClick={() => setSelectedSpeaker(sp === selectedSpeaker ? null : sp)}
                      className={`px-2 py-0.5 text-xs rounded-full border transition-colors flex items-center gap-1 ${selectedSpeaker === sp ? "bg-gray-700 border-indigo-500 text-white" : "bg-gray-800/50 border-gray-700 text-gray-400 hover:text-white"}`}>
                      <span className="w-2 h-2 rounded-full inline-block" style={{backgroundColor: getSpeakerColor(sp)}} />{sp}
                    </button>
                  ))}
                </div>
              )}
              {filteredTranscript.length > 0 ? (
                <div className="space-y-0.5 max-h-[60vh] overflow-y-auto bg-gray-900 rounded-lg p-2 border border-gray-800">
                  {filteredTranscript.map((seg, i) => (
                    <div key={seg.id || i} className="flex gap-3 text-sm hover:bg-gray-800 rounded px-2 py-1.5 cursor-pointer group transition-colors"
                      onClick={() => handleSeek(seg.start)} title={t('assetDetail.clickJump')}>
                      <span className="text-indigo-400 font-mono text-xs shrink-0 w-12 text-right pt-0.5 group-hover:text-indigo-300">{formatDuration(seg.start)}</span>
                      {seg.speaker && <span className="w-2 h-2 rounded-full inline-block mt-1.5 shrink-0" style={{backgroundColor: getSpeakerColor(seg.speaker)}} title={seg.speaker} />}
                      <span className="text-gray-200 group-hover:text-white transition-colors">{seg.text}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-gray-500">
                  <AudioLines className="w-10 h-10 mb-2 text-gray-700" /><p className="text-sm">{t("assetDetail.noTranscript")}</p>
                </div>
              )}
            </div>
          )}

          {activeTab === "ocr" && (
            ocrTexts.length > 0 ? (
              <div className="max-h-[60vh] overflow-y-auto bg-gray-900 rounded-lg border border-gray-800 p-3">
                <div className="text-xs text-gray-500 mb-2">{t("assetDetail.ocrCount", { count: ocrTexts.length })}</div>
                <div className="space-y-1">
                  {ocrTexts.map((o, i) => (
                    <div key={i} className="flex gap-3 text-sm hover:bg-gray-800 rounded px-2 py-1.5 cursor-pointer group transition-colors"
                      onClick={() => handleSeek(o.scene_time)} title={t("assetDetail.clickJump")}>
                      <span className="text-indigo-400 font-mono text-xs shrink-0 w-12 text-right pt-0.5">{formatDuration(o.scene_time)}</span>
                      <div className="flex-1 min-w-0"><span className="text-gray-200 group-hover:text-white transition-colors">{o.text}</span></div>
                      <span className={`text-xs shrink-0 ${o.confidence > 0.8 ? "text-emerald-500" : o.confidence > 0.5 ? "text-amber-500" : "text-red-400"}`}>
                        {(o.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-gray-500">
                <ScanEye className="w-10 h-10 mb-2 text-gray-700" /><p className="text-sm">{t("assetDetail.noOcr")}</p>
              </div>
            )
          )}

          {activeTab === "detail" && <MetadataPanel assetId={id!} />}

        </div>
      </div>
    </div>
  )
}





