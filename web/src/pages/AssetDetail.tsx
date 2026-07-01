import { useEffect, useState, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
ArrowLeft, Heart, Archive, RotateCcw, Clock, Maximize2, Film, Scissors,
Hash, FileText, Tag, Volume2, Loader2, MessageSquareText, Info, Monitor, Smartphone, Sparkles, XCircle, RefreshCw
} from 'lucide-react'
import { useStore } from '../stores/app'
import { api } from '../api/client'
import * as aiApi from '../api/ai'
import { VideoPlayer } from '../components/VideoPlayer'
import { useTranslation } from 'react-i18next'
import { MetadataPanel } from '../components/MetadataPanel'

export function AssetDetail() {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const currentAsset = useStore((s) => s.currentAsset)
  const loadAsset = useStore((s) => s.loadAsset)
  const [transcript, setTranscript] = useState<Array<{ start: number; end: number; text: string }>>([])
  const [segments, setSegments] = useState<Array<{ id: string; start_time: number; end_time: number; thumbnail_path?: string; scene_label?: string; source: string }>>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'scenes' | 'transcript' | 'metadata'>('scenes')
  const [seekTime, setSeekTime] = useState<number | null>(null)
  const [aiScenes, setAiScenes] = useState<Array<{id: string; scene_index: number; start_time: number; end_time: number; thumbnail_path: string; tags: Array<{label: string; confidence: number; count: number}>; ocr_texts: Array<{text: string; confidence: number; bbox: {x:number;y:number;w:number;h:number}}>}>>([])
  const [aiTranscript, setAiTranscript] = useState<Array<{id: string; start: number; end: number; text: string; speaker: string | null}>>([])
  const [speakers, setSpeakers] = useState<string[]>([])
  const [sceneTags, setSceneTags] = useState<Array<{label: string; total_count: number}>>([])
  const [selectedSpeaker, setSelectedSpeaker] = useState<string | null>(null)
  const [aiProcessing, setAiProcessing] = useState(false)
  const pollRef = useRef<Set<ReturnType<typeof setInterval>>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [processing, setProcessing] = useState<Record<string, { running: boolean; taskId?: string }>>({})
  const [resettingAI, setResettingAI] = useState(false)

  const handleResetAI = async () => {
    if (!id || !window.confirm("确定重置该视频的所有AI处理数据？场景、字幕、标签、OCR数据将被清除。")) return
    setResettingAI(true)
    try {
      const result = await aiApi.resetAssetAI(id)
      console.log("Reset AI result:", result)
      loadAsset(id)
    } catch (e) {
      setError('重置AI数据失败'); console.error("Reset AI failed:", e)
    } finally {
      setResettingAI(false)
    }
  }

  useEffect(() => {
    if (!id) return
    setLoading(true)
    Promise.all([
      loadAsset(id),
      api.getTranscript(id).then(setTranscript).catch(() => setError('加载字幕失败')),
      aiApi.getAIScenes(id).then((r: any) => { if (r.results?.length) setAiScenes(r.results) }).catch(() => setError('加载场景数据失败')),
      aiApi.getAISubtitles(id).then((r: any) => { if (r.results?.length) setAiTranscript(r.results) }).catch(() => setError('加载字幕数据失败')),
      aiApi.getAISpeakers(id).then((r: any) => { if (r.speakers?.length) setSpeakers(r.speakers) }).catch(() => setError('加载说话人数据失败')),
      aiApi.getAITags(id).then((r: any) => { if (r.tags?.length) setSceneTags(r.tags) }).catch(() => setError('加载场景标签失败')),
      api.getSegments(id).then(setSegments).catch(() => setError('加载分段数据失败')),
    ]).finally(() => setLoading(false))
  }, [id])

  const handleSeek = useCallback((time: number) => {
    setSeekTime(time)
    setTimeout(() => {
      document.getElementById('player-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 100)
  }, [])

  const handleTranscribe = useCallback(async () => {
    if (!id || processing['transcribe']?.running) return
    setProcessing(p => ({ ...p, transcribe: { running: true } }))
    try {
      await api.transcribeAsset(id)
    } catch (e) {
      setError('转写失败'); console.error('Transcribe failed:', e)
      setProcessing(p => ({ ...p, transcribe: { running: false } }))
      return
    }
    // Poll for completion
    const poll = setInterval(async () => {
      try {
        const t = await api.getTranscript(id)
        if (t.length > 0) {
          setTranscript(t)
          setProcessing(p => ({ ...p, transcribe: { running: false } }))
          clearInterval(poll)
        }
      } catch { /* still processing */ }
    }, 3000)
    setTimeout(() => { clearInterval(poll); setProcessing(p => ({ ...p, transcribe: { running: false } })) }, 300000)
  }, [id])

  const handleGenerateScenes = useCallback(async () => {
    if (!id || processing['scenes']?.running) return
    setProcessing(p => ({ ...p, scenes: { running: true } }))
    try {
      await api.generateSceneThumbnails(id)
    } catch (e) {
      setError('生成场景失败'); console.error('Generate scenes failed:', e)
      setProcessing(p => ({ ...p, scenes: { running: false } }))
      return
    }
    const poll = setInterval(async () => {
      try {
        const s = await api.getSegments(id)
        if (s.length > 0) {
          setSegments(s)
          setProcessing(p => ({ ...p, scenes: { running: false } }))
          clearInterval(poll)
        }
      } catch { /* still processing */ }
    }, 3000)
    setTimeout(() => { clearInterval(poll); setProcessing(p => ({ ...p, scenes: { running: false } })) }, 300000)
  }, [id])

 const handleCancelTranscribe = useCallback(async () => {
    if (!id) return
    try {
      await aiApi.cancelAIPipeline(id)
    } catch (e) {
      setError('取消转写失败'); console.error('Cancel transcribe failed:', e)
    }
    setProcessing(p => ({ ...p, transcribe: { running: false } }))
}, [id])

  const handleCancelScenes = useCallback(async () => {
    if (!id) return
    try {
      await aiApi.cancelAIPipeline(id)
    } catch (e) {
      setError('取消场景生成失败'); console.error('Cancel scenes failed:', e)
    }
    setProcessing(p => ({ ...p, scenes: { running: false } }))
 }, [id])

      const filteredTranscript = selectedSpeaker
    ? aiTranscript.filter(s => s.speaker === selectedSpeaker)
    : (aiTranscript.length > 0 ? aiTranscript : transcript)

  const displayedScenes = aiScenes.length > 0 ? aiScenes : segments

  const handleStartAIPipeline = async () => {
    if (!id || aiProcessing) return
    setAiProcessing(true)
    try {
      await aiApi.processAI(id, currentAsset?.original_path || '')
    } catch (e) {
      setError('AI 管道启动失败'); console.error('AI pipeline failed:', e)
      setAiProcessing(false)
      return
    }
    const poll = setInterval(async () => {
      try {
        const status: any = await aiApi.getAIStatus(id)
        if (status.status === 'done') {
          const [scenesRes, subsRes, speakersRes, tagsRes] = await Promise.all([
            aiApi.getAIScenes(id),
            aiApi.getAISubtitles(id),
            aiApi.getAISpeakers(id),
            aiApi.getAITags(id),
          ])
          if ((scenesRes as any).results?.length) setAiScenes((scenesRes as any).results)
          if ((subsRes as any).results?.length) setAiTranscript((subsRes as any).results)
          if ((speakersRes as any).speakers?.length) setSpeakers((speakersRes as any).speakers)
          if ((tagsRes as any).tags?.length) setSceneTags((tagsRes as any).tags)
          setAiProcessing(false)
          clearInterval(poll)
        } else if (status.status === 'error') {
          setAiProcessing(false)
          clearInterval(poll)
        }
      } catch { }
    }, 3000)
    setTimeout(() => { clearInterval(poll); setAiProcessing(false) }, 600000)
  }

  // Speaker color palette
  const speakerColors = ['#818cf8', '#34d399', '#f472b6', '#fbbf24', '#60a5fa', '#a78bfa', '#fb923c', '#2dd4bf']
  const getSpeakerColor = (speaker: string) => {
    const idx = speakers.indexOf(speaker)
    return speakerColors[idx % speakerColors.length]
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
          <div className="flex gap-2">
            {[1,2,3,4,5].map(i => <div key={i} className="h-6 w-20 bg-gray-900 rounded-full animate-pulse" />)}
          </div>
        </div>
      </div>
    )
  }

  if (!currentAsset) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-500">
        <Film className="w-12 h-12 mb-3 text-gray-700" />
        <p>{t('assetDetail.notFound')}</p>
        <button onClick={() => navigate('/')} className="mt-4 text-indigo-400 hover:text-indigo-300">{t('assetDetail.goBack')}</button>
      </div>
    )
  }

  const a = currentAsset
  const formatDuration = (s?: number) => {
    if (!s) return '--:--'
    const m = Math.floor(s / 60); const sec = Math.floor(s % 60)
    return `${m}:${sec.toString().padStart(2, '0')}`
  }
  const formatSize = (bytes: number) => {
    if (bytes < 1e6) return `${(bytes / 1e3).toFixed(0)} KB`
    if (bytes < 1e9) return `${(bytes / 1e6).toFixed(1)} MB`
    return `${(bytes / 1e9).toFixed(2)} GB`
  }
  const formatCount = (n: number) => {
    if (n >= 1000000) return `{(n / 1000000).toFixed(1)}M`
    if (n >= 1000) return `{(n / 1000).toFixed(1)}K`
    return String(n)
  }


  const TABS = [
    { id: 'scenes' as const, label: t('assetDetail.scenes'), icon: Film, count: segments.length },
    { id: 'transcript' as const, label: t('assetDetail.transcript'), icon: MessageSquareText, count: transcript.length },
    { id: 'metadata' as const, label: t('metadata.title'), icon: Info },
  ]

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-2 border-b border-gray-800 shrink-0">
        <button onClick={() => navigate(-1)} className="text-gray-400 hover:text-white transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <h1 className="text-lg font-medium text-white truncate">{a.file_name}</h1>
        <div className="flex-1" />
        <button
          onClick={async () => {
            await api.updateAsset(a.id, { is_archived: !a.is_archived });
            loadAsset(a.id);
          }}
          className={`transition-colors ${a.is_archived ? 'text-indigo-400' : 'text-gray-500 hover:text-indigo-400'}`}
          title={a.is_archived ? t('assetDetail.unarchive') : t('assetDetail.archive')}
        >
          {a.is_archived ? <RotateCcw className="w-5 h-5" /> : <Archive className="w-5 h-5" />}
        </button>
        <button
          onClick={async () => { await api.updateAsset(a.id, { is_favorite: !a.is_favorite }); loadAsset(a.id); }}
          className={`transition-colors ${a.is_favorite ? 'text-red-400' : 'text-gray-500 hover:text-red-400'}`}
        >
         <Heart className={`w-5 h-5 ${a.is_favorite ? 'fill-red-400' : ''}`} />
       </button>
        <button
          onClick={handleResetAI}
          disabled={resettingAI}
          className="text-gray-500 hover:text-red-400 transition-colors disabled:opacity-50"
          title="重置AI处理数据"
        >
          <RefreshCw className={`w-5 h-5 ${resettingAI ? 'animate-spin' : ''}`} />
        </button>
     </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-7xl mx-auto p-6 space-y-6">
          {/* Player */}
          <div id="player-section" className="flex gap-3">
            <div className="flex-1 min-w-0">
    <VideoPlayer transcript={transcript} seekTime={seekTime} onSeek={handleSeek} />
  </div>
  {/* Scene sidebar strip */}
  {displayedScenes.length > 0 && (
    <div className="hidden md:flex flex-col gap-1 w-20 shrink-0 max-h-[400px] overflow-y-auto rounded-lg bg-gray-900/50 p-1 border border-gray-800/50">
      {displayedScenes.map((sc: any) => (
        <div
          key={sc.id || sc.start_time}
          className="relative aspect-video bg-gray-800 rounded cursor-pointer hover:ring-2 hover:ring-indigo-500/50 overflow-hidden shrink-0 transition-all"
          onClick={() => handleSeek(sc.start_time || (sc as any).start)}
          title={`Seek to ${formatDuration(sc.start_time || (sc as any).start)}`}
        >
         {sc.id ? (
            <img src={aiScenes.length > 0 ? api.sceneThumbnailUrl(sc.id) : api.segmentThumbnailUrl(sc.id)} alt="" className="w-full h-full object-cover" loading="lazy" />
          ) : (
            <div className="flex items-center justify-center h-full"><Film className="w-3 h-3 text-gray-500" /></div>
          )}
        </div>
      ))}
    </div>
  )}
          </div>

          {/* ── Always-visible Info Strip ── */}
          {/* AI Tag Cloud */}
  {sceneTags.length > 0 && (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-xs text-gray-500 font-medium mr-0.5">{t('assetDetail.scenes')}:</span>
      {sceneTags.slice(0, 20).map(tag => (
        <span key={tag.label}
          className="px-2 py-0.5 text-xs rounded-full bg-gray-800 text-gray-400 border border-gray-700"
          title={`${tag.label} (${tag.total_count})`}
        >
          {tag.label}
        </span>
      ))}
    </div>
  )}

  {/* Speaker filter */}
  {speakers.length > 0 && (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-xs text-gray-500 font-medium mr-0.5">Speaker:</span>
      <button
        onClick={() => setSelectedSpeaker(null)}
        className={`px-2 py-0.5 text-xs rounded-full transition-colors ${
          selectedSpeaker === null
            ? 'bg-indigo-600 text-white'
            : 'bg-gray-800 text-gray-400 hover:text-white'
        }`}
      >
        All
      </button>
      {speakers.map(sp => (
        <button
          key={sp}
          onClick={() => setSelectedSpeaker(sp === selectedSpeaker ? null : sp)}
          className={`px-2 py-0.5 text-xs rounded-full border transition-colors flex items-center gap-1.5 ${
            selectedSpeaker === sp
              ? 'bg-gray-700 border-indigo-500 text-white'
              : 'bg-gray-800/50 border-gray-700 text-gray-400 hover:text-white'
          }`}
        >
          <span className="w-2 h-2 rounded-full inline-block" style={{backgroundColor: getSpeakerColor(sp)}} />
          {sp}
        </button>
      ))}
    </div>
  )}

  <div className="flex items-center gap-1.5 flex-wrap">
            <InfoPill icon={Clock} label={formatDuration(a.duration)} />
            {a.width && a.height && <InfoPill icon={Maximize2} label={`${a.width}x${a.height}`} />}
            {(() => {
              const isLandscape = a.tags?.includes('横屏')
              const isPortrait = a.tags?.includes('竖屏')
              const hasDbTag = isLandscape || isPortrait
              const w = a.width
              const h = a.height
              const showLandscape = hasDbTag ? isLandscape : (w != null && h != null && w > h)
              const showPortrait = hasDbTag ? isPortrait : (w != null && h != null && w < h)
              let icon = Maximize2
              let label = 'Square'
              if (showLandscape) { icon = Monitor; label = '横屏' }
              if (showPortrait) { icon = Smartphone; label = '竖屏' }
              if (!showLandscape && !showPortrait && (w == null || h == null)) return null
              return <InfoPill icon={icon} label={label} />
            })()}
            {a.codec && <InfoPill icon={Film} label={a.codec.toUpperCase()} />}
            <InfoPill icon={Hash} label={formatSize(a.file_size)} />
            {a.fps && <InfoPill icon={Clock} label={`${a.fps} fps`} />}
            {a.has_audio !== undefined && (
              <InfoPill icon={Volume2} label={a.has_audio ? 'Audio' : 'No Audio'} />
            )}
            {a.audio_codec && <InfoPill icon={Volume2} label={a.audio_codec.toUpperCase()} />}
            {a.mime_type && (
              <InfoPill icon={FileText} label={a.mime_type} />
            )}
            {a.file_hash && (
              <span className="text-xs text-gray-500 font-mono ml-1" title="SHA-256">{a.file_hash.slice(0, 10)}…</span>
            )}
          </div>

          {/* ── Always-visible Tags ── */}
          {a.tags.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <Tag className="w-3.5 h-3.5 text-gray-500" />
              {a.tags.map((tag) => (
                <span key={tag} className="px-2.5 py-0.5 text-xs rounded-full bg-gray-800 text-gray-400 border border-gray-700">
                  {tag}
                </span>
              ))}
            </div>
          )}

          {/* ── Always-visible Notes ── */}
          {a.notes && (
            <div className="text-sm text-gray-400 bg-gray-900/50 rounded-lg p-3 border border-gray-800/60 leading-relaxed">
              {a.notes}
            </div>
          )}

          {/* Tabs */}
          <div className="flex items-center gap-1 border-b border-gray-800 overflow-x-auto">
            {TABS.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px shrink-0 ${
                  activeTab === tab.id
                    ? 'text-indigo-400 border-indigo-500'
                    : 'text-gray-500 border-transparent hover:text-gray-400 hover:border-gray-600'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                <span>{tab.label}</span>
                {tab.count != null && tab.count > 0 && (
                  <span className="text-xs bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded-full ml-0.5">{formatCount(tab.count)}</span>
                )}
              </button>
            ))}
          </div>

          {/* ── Tab: Scenes ── */}
          {activeTab === 'scenes' && (
            (displayedScenes.length > 0 ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
                {displayedScenes.map((seg: any, i) => (
                  <SceneThumbnail key={seg.id} seg={seg} tags={seg.tags} ocrTexts={seg.ocr_texts} formatDuration={formatDuration} onClick={() => handleSeek(seg.start_time)} thumbnailUrl={aiScenes.length > 0 ? api.sceneThumbnailUrl(seg.id) : api.segmentThumbnailUrl(seg.id)} />
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-gray-500">
                <Film className="w-10 h-10 mb-2 text-gray-700" />
                <p className="text-sm">No scene data. Click AI Process to analyze this video automatically.</p>
                <div className="mt-3 flex items-center gap-2">
    {/* AI Process button */}
    <button
      onClick={handleStartAIPipeline}
      disabled={aiProcessing}
      className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white transition-colors"
    >
      {aiProcessing ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
      ) : (
        <Sparkles className="w-3.5 h-3.5" />
      )}
      {aiProcessing ? 'AI Processing...' : 'Run AI Pipeline'}
    </button>
    {/* Legacy buttons */}
    <button
      onClick={handleGenerateScenes}
      disabled={processing['scenes']?.running}
      className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg bg-indigo-600/50 hover:bg-indigo-700 disabled:opacity-50 text-white transition-colors"
    >
      {processing['scenes']?.running ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
      ) : (
        <Film className="w-3.5 h-3.5" />
      )}
      {processing['scenes']?.running ? 'Generating...' : 'Scenes'}
    </button>
    <button
      onClick={handleTranscribe}
      disabled={processing['transcribe']?.running}
      className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg bg-indigo-600/50 hover:bg-indigo-700 disabled:opacity-50 text-white transition-colors"
    >
      {processing['transcribe']?.running ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
      ) : (
        <Volume2 className="w-3.5 h-3.5" />
      )}
      {processing['transcribe']?.running ? 'Transcribing...' : 'Transcript'}
    </button>
    {processing['scenes']?.running && (
      <button onClick={handleCancelScenes}
        className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg bg-red-600/20 hover:bg-red-600/40 text-red-400 transition-colors"
      >
        <XCircle className="w-3.5 h-3.5" />
      </button>
    )}
    {aiProcessing && (
      <span className="text-xs text-gray-500 animate-pulse">Processing may take several minutes...</span>
    )}
  </div>
              </div>
            )
          ))}

          {/* ── Tab: Transcript ── */}
          {activeTab === 'transcript' && (
            <>
    {speakers.length > 0 && (
      <div className="flex flex-wrap items-center gap-1.5 mb-2">
        <span className="text-xs text-gray-500 font-medium">Filter by speaker:</span>
        <button
          onClick={() => setSelectedSpeaker(null)}
          className={`px-2 py-0.5 text-xs rounded-full transition-colors ${
            selectedSpeaker === null
              ? 'bg-indigo-600 text-white'
              : 'bg-gray-800 text-gray-400 hover:text-white'
          }`}
        >
          All
        </button>
        {speakers.map(sp => (
          <button
            key={sp}
            onClick={() => setSelectedSpeaker(sp === selectedSpeaker ? null : sp)}
            className={`px-2 py-0.5 text-xs rounded-full border transition-colors flex items-center gap-1 ${
              selectedSpeaker === sp
                ? 'bg-gray-700 border-indigo-500 text-white'
                : 'bg-gray-800/50 border-gray-700 text-gray-400 hover:text-white'
            }`}
          >
            <span className="w-2 h-2 rounded-full inline-block" style={{backgroundColor: getSpeakerColor(sp)}} />
            {sp}
          </button>
        ))}
      </div>
    )}
            {(filteredTranscript.length > 0 ? (
              <div className="space-y-0.5 max-h-[60vh] overflow-y-auto bg-gray-900 rounded-lg p-2 border border-gray-800">
                {filteredTranscript.map((seg: any, i) => (
                  <div
    key={i}
    className="flex gap-3 text-sm hover:bg-gray-800 rounded px-2 py-1.5 cursor-pointer group transition-colors"
    onClick={() => handleSeek(seg.start)}
    title="Click to seek"
  >
    <span className="text-indigo-400 font-mono text-xs shrink-0 w-12 text-right pt-0.5 group-hover:text-indigo-300 transition-colors">
      {formatDuration(seg.start)}
    </span>
    {seg.speaker && (
      <span
        className="w-2 h-2 rounded-full inline-block mt-1.5 shrink-0"
        style={{backgroundColor: getSpeakerColor(seg.speaker)}}
        title={seg.speaker}
      />
    )}
    <span className="text-gray-200 group-hover:text-white transition-colors">{seg.text}</span>
  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-gray-500">
                <MessageSquareText className="w-10 h-10 mb-2 text-gray-700" />
                <p className="text-sm">No transcript data available. Try AI processing to generate subtitles.</p>
                {(a.transcript_status !== 'done') && (
                  <div className="mt-3 flex items-center gap-2">
                    <button
                      onClick={handleTranscribe}
                      disabled={processing['transcribe']?.running}
                      className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white transition-colors"
                    >
                      {processing['transcribe']?.running ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Sparkles className="w-3.5 h-3.5" />
                      )}
                      {processing['transcribe']?.running ? 'Transcribing...' : 'Generate Transcript'}
                    </button>
                    {processing['transcribe']?.running && (
                      <button
                        onClick={handleCancelTranscribe}
                        className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg bg-red-600/20 hover:bg-red-600/40 text-red-400 transition-colors"
                      >
                        <XCircle className="w-3.5 h-3.5" />
                        Cancel
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
            </>
          )}
          {/* ── Tab: Metadata ── */}
          {activeTab === 'metadata' && (
            <MetadataPanel assetId={id!} />
          )}
        </div>
      </div>
    </div>
  )
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
  ocrTexts?: Array<{text: string; confidence: number; bbox: {x: number; y: number; w: number; h: number}}>
  thumbnailUrl?: string
  tags?: Array<{label: string; confidence: number; count: number}>
  formatDuration: (s?: number) => string
  onClick: () => void
}) {
  const [imgError, setImgError] = useState<"primary" | "fallback" | null>(null)
  const showPrimaryThumb = thumbnailUrl && imgError !== "primary"
  const showSegThumb = !showPrimaryThumb && seg.thumbnail_path && imgError !== "fallback"
  const showEmpty = !showPrimaryThumb && !showSegThumb
  return (
    <div
      className="group relative aspect-video bg-gray-800 rounded-lg overflow-hidden cursor-pointer hover:ring-2 hover:ring-indigo-500/50 transition-all"
      onClick={onClick}
      title="Click to seek"
    >
      {showPrimaryThumb ? (
        <img src={thumbnailUrl} alt="" loading="lazy" className="w-full h-full object-cover" onError={() => setImgError("primary")} />
      ) : showSegThumb ? (
        <img src={api.segmentThumbnailUrl(seg.id)} alt="" loading="lazy" className="w-full h-full object-cover" onError={() => setImgError("fallback")} />
      ) : (
        <div className="flex items-center justify-center h-full">
          <Film className="w-4 h-4 text-gray-500" />
        </div>
      )}
      {tags && tags.length > 0 && (
        <div className="absolute top-1 left-1 flex flex-wrap gap-0.5 max-w-[70%]">
          {tags.slice(0, 3).map((t) => (
            <span key={t.label} className="text-[9px] bg-black/70 text-white px-1 py-0.5 rounded">
              {t.label}
            </span>
          ))}
        </div>
      )}
      {ocrTexts && ocrTexts.length > 0 && (
        <div className="absolute top-1 right-1 flex flex-col gap-0.5 max-w-[60%]">
          {ocrTexts.slice(0, 2).map((o, i) => (
            <span key={i} className="text-[9px] bg-black/70 text-gray-400 px-1 py-0.5 rounded truncate" title={o.text}>
              {o.text.length > 20 ? o.text.substring(0, 18) + '…' : o.text}
            </span>
          ))}
          {ocrTexts.length > 2 && (
            <span className="text-[8px] bg-black/50 text-gray-500 px-1 py-0.5 rounded text-center">
              +{ocrTexts.length - 2}
            </span>
          )}
        </div>
      )}
      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors" />
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 p-1.5">
        <p className="text-xs text-gray-200 font-medium">{seg.scene_label || formatDuration(seg.start_time)}</p>
        <p className="text-xs text-gray-500">
          {formatDuration(seg.start_time)} &ndash; {formatDuration(seg.end_time)}
        </p>
      </div>
    </div>
  )
}

function TranscriptLine({ seg, formatDuration, onClick }: {
  seg: { start: number; end: number; text: string }
  formatDuration: (s?: number) => string
  onClick: () => void
}) {
  return (
    <div
      className="flex gap-3 text-sm hover:bg-gray-800 rounded px-2 py-1.5 cursor-pointer group transition-colors"
      onClick={onClick}
      title="Click to seek"
    >
      <span className="text-indigo-400 font-mono text-xs shrink-0 w-12 text-right pt-0.5 group-hover:text-indigo-300 transition-colors">
        {formatDuration(seg.start)}
      </span>
      <span className="text-gray-200 group-hover:text-white transition-colors">{seg.text}</span>
    </div>
  )
}

