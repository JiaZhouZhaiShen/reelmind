import { useRef, useEffect, useState, useCallback, useMemo } from 'react'
import { Play, Pause, Volume2, VolumeX, Maximize, PictureInPicture2, Camera, Keyboard, Scissors, SkipBack, SkipForward, AlertCircle, RefreshCw, Monitor } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useAssetStore } from '../stores/asset'
import { api } from '../api/client'

interface SourceDef {
  src: string
  type: string
}

interface VideoPlayerProps {
  src?: string
  sources?: SourceDef[]
  poster?: string
  transcript?: Array<{ start: number; end: number; text: string }>
  seekTime?: number | null
  onTimeUpdate?: (time: number) => void
  onSeek?: (time: number) => void
  className?: string
}

// ── Constants ────────────────────────────────────────────────
const IDLE_TIMEOUT_MS = 30000

// ── Format support detection ─────────────────────────────────
function pickSupportedSource(sources: SourceDef[]): SourceDef | null {
  if (!sources.length) return null
  const probe = document.createElement('video')
  for (const s of sources) {
    const r = probe.canPlayType(s.type)
    if (r === 'probably' || r === 'maybe') return s
  }
  return null
}

// ── Reusable draw-plane (no allocations in draw loop) ────────
interface DrawPlane {
  ox: number; oy: number
  dw: number; dh: number
}
function computePlane(cw: number, ch: number, vw: number, vh: number, p: DrawPlane): void {
  const s = Math.min(cw / vw, ch / vh)
  p.dw = vw * s
  p.dh = vh * s
  p.ox = (cw - p.dw) / 2
  p.oy = (ch - p.dh) / 2
}

const planePool: DrawPlane = { ox: 0, oy: 0, dw: 0, dh: 0 }

// ── Main component ───────────────────────────────────────────
export function VideoPlayer({ src, sources, poster, transcript, seekTime, onTimeUpdate, onSeek, className = '' }: VideoPlayerProps) {
  // 从 store 读取当前 asset，自行构建视频源和封面
  const currentAsset = useAssetStore(s => s.currentAsset)
  const derivedSources = useMemo(() => {
    if (sources && sources.length > 0) return sources
    if (src) return [{ src, type: 'video/mp4' as const }]
    if (currentAsset) {
      const list: Array<{ src: string; type: string }> = []
      if (currentAsset.proxy_path) list.push({ src: api.proxyUrl(currentAsset.id), type: 'video/mp4' })
      list.push({ src: api.sourceUrl(currentAsset.id), type: currentAsset.mime_type || 'video/mp4' })
      return list
    }
    return []
  }, [sources, src, currentAsset])
  const derivedPoster = useMemo(() => {
    if (poster) return poster
    if (currentAsset?.thumbnail_path) return api.thumbnailUrl(currentAsset.id)
    return undefined
  }, [poster, currentAsset])
  const { t } = useTranslation()

  // Refs (mutable, no re-render)
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const ctxRef = useRef<CanvasRenderingContext2D | null>(null)
  const idleTimerRef = useRef<ReturnType<typeof setTimeout>>()
  const savedTimeRef = useRef(0)
  const isIdleRef = useRef(false)
  const rvfcPendingRef = useRef(false)
  const prevSeekRef = useRef<number | null>(null)
  const hideTimerRef = useRef<ReturnType<typeof setTimeout>>()
  const progressRef = useRef<HTMLDivElement>(null)
  const sourceRef = useRef('')
  const posterImgRef = useRef<HTMLImageElement | null>(null)
  const posterCanvasRef = useRef(false)

  // Reactive state
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [muted, setMuted] = useState(true)
  const [volume, setVolume] = useState(1)
  const [playbackRate, setPlaybackRate] = useState(1)
  const [showTranscript, setShowTranscript] = useState(false)
  const [hoverTime, setHoverTime] = useState<number | null>(null)
  const [hoverPos, setHoverPos] = useState(0)
  const [controlsVisible, setControlsVisible] = useState(true)
  const [showSpeedMenu, setShowSpeedMenu] = useState(false)
  const [videoError, setVideoError] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [resWarn, setResWarn] = useState(false)
  const [canvasReady, setCanvasReady] = useState(false)
  const [loading, setLoading] = useState(true)
  const canvasAspect = 16 / 9
  const [showShortcuts, setShowShortcuts] = useState(false)

  const SPEEDS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2]

  // Source list — from props or derived from store
  const sourceList: SourceDef[] = derivedSources
  const activeSource = sourceList.length > 0 ? pickSupportedSource(sourceList) : null

  // ═══════════════════════════════════════════════════════════
  // 1. ResizeObserver — sync canvas pixel dims to container CSS size
  useEffect(() => {
    const container = containerRef.current
    const canvas = canvasRef.current
    if (!container || !canvas) return
    const ctx = canvas.getContext('2d', { alpha: false, desynchronized: true })
    if (ctx) ctxRef.current = ctx
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        const w = Math.floor(Math.max(width, 320))
        const h = Math.floor(Math.max(height, 1))
        if (canvas.width !== w || canvas.height !== h) {
          canvas.width = w
          canvas.height = h
          if (ctx) { ctx.fillStyle = '#000'; ctx.fillRect(0, 0, w, h) }
          if (posterCanvasRef.current && posterImgRef.current && ctx) {
            computePlane(w, h, posterImgRef.current.naturalWidth, posterImgRef.current.naturalHeight, planePool)
            ctx.fillStyle = '#000'
            ctx.fillRect(0, 0, w, h)
            ctx.drawImage(posterImgRef.current, planePool.ox, planePool.oy, planePool.dw, planePool.dh)
          }
        }
      }
    })
    ro.observe(container)
    setCanvasReady(true)
    return () => ro.disconnect()
    }, [])

  // ==============================================================================
  // 1b. Load poster image onto canvas before video loads
  // ==============================================================================
  useEffect(() => {
    const actualPoster = derivedPoster
    if (!actualPoster) {
      posterImgRef.current = null
      posterCanvasRef.current = false
      return
    }
    const canvas = canvasRef.current
    const ctx = ctxRef.current
    if (!canvas || !ctx) return
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      posterImgRef.current = img
      posterCanvasRef.current = true
      const cw = canvas.width
      const ch = canvas.height
      computePlane(cw, ch, img.naturalWidth, img.naturalHeight, planePool)
      ctx.fillStyle = '#000'
      ctx.fillRect(0, 0, cw, ch)
      ctx.drawImage(img, planePool.ox, planePool.oy, planePool.dw, planePool.dh)
    }
    img.onerror = () => { posterCanvasRef.current = false }
    img.src = actualPoster
  }, [derivedPoster, canvasReady])

  // ═══════════════════════════════════════════════════════════
  // 2. Draw frame — zero allocations inside
  // ═══════════════════════════════════════════════════════════
  const drawFrame = useCallback(() => {
    const video = videoRef.current
    const canvas = canvasRef.current
    const ctx = ctxRef.current
    if (!video || !canvas || !ctx) return

    const vw = video.videoWidth
    const vh = video.videoHeight
    if (!vw || !vh) return

    // First video frame ready -- poster no longer needed

    posterCanvasRef.current = false
    const cw = canvas.width
    const ch = canvas.height

    computePlane(cw, ch, vw, vh, planePool)
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, cw, ch)
    ctx.drawImage(video, planePool.ox, planePool.oy, planePool.dw, planePool.dh)
  }, [])

  // ═══════════════════════════════════════════════════════════
  // 3. rVFC frame loop
  // ═══════════════════════════════════════════════════════════
  const onVideoFrame = useCallback((_now: DOMHighResTimeStamp, _meta: VideoFrameCallbackMetadata) => {
    rvfcPendingRef.current = false
    drawFrame()
    const video = videoRef.current
    if (video && !video.paused && !video.ended && !isIdleRef.current) {
      rvfcPendingRef.current = true
      video.requestVideoFrameCallback(onVideoFrame)
    }
  }, [drawFrame])

  const startRVFC = useCallback(() => {
    const video = videoRef.current
    if (!video || rvfcPendingRef.current || isIdleRef.current) return
    rvfcPendingRef.current = true
    video.requestVideoFrameCallback(onVideoFrame)
  }, [onVideoFrame])

  const stopRVFC = useCallback(() => { rvfcPendingRef.current = false }, [])

  // ═══════════════════════════════════════════════════════════
  // 4. Source loading — single video element, swap via src="" → load()
  // ═══════════════════════════════════════════════════════════
  const loadSource = useCallback((s: SourceDef) => {
    const video = videoRef.current
    if (!video) return
    setVideoError(false)
    setErrorMessage('')
    setLoading(true)
    setResWarn(false)
    sourceRef.current = s.src
    video.src = ''
    video.load()
    video.src = s.src
    video.load()
  }, [])

  useEffect(() => {
    if (activeSource) loadSource(activeSource)
  }, [activeSource, loadSource])

  // ═══════════════════════════════════════════════════════════
  // 5. Idle timeout — pause > 30s releases decoder
  // ═══════════════════════════════════════════════════════════
  const clearIdleTimer = useCallback(() => {
    if (idleTimerRef.current) {
      clearTimeout(idleTimerRef.current)
      idleTimerRef.current = undefined
    }
  }, [])

  const releaseDecoder = useCallback(() => {
    const video = videoRef.current
    if (!video || isIdleRef.current) return
    savedTimeRef.current = video.currentTime
    stopRVFC()
    video.src = ''
    video.load()
    isIdleRef.current = true
  }, [stopRVFC])

  const restoreDecoder = useCallback(() => {
    const video = videoRef.current
    if (!video || !activeSource || !isIdleRef.current) return
    isIdleRef.current = false
    video.src = activeSource.src
    video.load()
  }, [activeSource])

  const startIdleTimer = useCallback(() => {
    clearIdleTimer()
    idleTimerRef.current = setTimeout(releaseDecoder, IDLE_TIMEOUT_MS)
  }, [clearIdleTimer, releaseDecoder])

  // ═══════════════════════════════════════════════════════════
  // 6. Playback controls
  // ═══════════════════════════════════════════════════════════
  const togglePlay = useCallback(() => {
    const video = videoRef.current
    if (!video || videoError) return

    if (isIdleRef.current) {
      restoreDecoder()
      const onMeta = () => {
        video.removeEventListener('loadedmetadata', onMeta)
        video.currentTime = savedTimeRef.current
        video.play().then(startRVFC).catch(() => {})
      }
      video.addEventListener('loadedmetadata', onMeta)
      return
    }

    if (video.paused) {
      video.play().then(startRVFC).catch(() => {})
    } else {
      video.pause()
      startIdleTimer()
    }
  }, [videoError, restoreDecoder, startRVFC, startIdleTimer])

  const seek = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!videoRef.current || videoError) return
    const rect = e.currentTarget.getBoundingClientRect()
    const pos = (e.clientX - rect.left) / rect.width
    videoRef.current.currentTime = pos * duration
    onSeek?.(pos * duration)
  }, [duration, videoError, onSeek])

  const seekSeconds = useCallback((delta: number) => {
    const video = videoRef.current
    if (!video || videoError) return
    video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + delta))
  }, [videoError])

  const retryPlayback = useCallback(() => {
    setVideoError(false)
    setErrorMessage('')
    if (activeSource) loadSource(activeSource)
  }, [activeSource, loadSource])

  // ═══════════════════════════════════════════════════════════
  // 7. Video events on hidden element
  // ═══════════════════════════════════════════════════════════
  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const onPlay = () => {
      setPlaying(true)
      clearIdleTimer()
      startRVFC()
    }
    const onPause = () => {
      setPlaying(false)
      stopRVFC()
      startIdleTimer()
    }
    const onTime = () => {
      const t = video.currentTime
      setCurrentTime(t)
      onTimeUpdate?.(t)
    }
    const onMeta = () => {
      setDuration(video.duration)
      setLoading(false)
      setVideoError(false)
      const vw = video.videoWidth
      const vh = video.videoHeight
      if (vw > 0 && vh > 0) {
        const canvas = canvasRef.current
        if (canvas) { setResWarn(vw > canvas.width * 2 || vh > canvas.height * 2) }
      }
      drawFrame()
    }
    const onEnded = () => setPlaying(false)
    const onErrorFn = () => {
      const me = video.error
      if (!me) return
      setVideoError(true)
      const msgs: Record<number, string> = {
        [MediaError.MEDIA_ERR_ABORTED]: 'Playback was aborted',
        [MediaError.MEDIA_ERR_NETWORK]: 'Network error occurred while loading video',
        [MediaError.MEDIA_ERR_DECODE]: 'Video format is not supported by your browser',
        [MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED]: 'Video format is not supported or the file is missing',
      }
      setErrorMessage(msgs[me.code] || 'An unknown error occurred')
    }

    video.addEventListener('play', onPlay)
    video.addEventListener('pause', onPause)
    video.addEventListener('timeupdate', onTime)
    video.addEventListener('loadedmetadata', onMeta)
    video.addEventListener('ended', onEnded)
    video.addEventListener('error', onErrorFn)

    video.muted = muted

    if (video.readyState >= 1) {
      setDuration(video.duration)
      setLoading(false)
    }

    return () => {
      video.removeEventListener('play', onPlay)
      video.removeEventListener('pause', onPause)
      video.removeEventListener('timeupdate', onTime)
      video.removeEventListener('loadedmetadata', onMeta)
      video.removeEventListener('ended', onEnded)
      video.removeEventListener('error', onErrorFn)
    }
  }, [onTimeUpdate, startRVFC, stopRVFC, startIdleTimer, clearIdleTimer, drawFrame])

  // ── Volume sync ──
  useEffect(() => {
    const v = videoRef.current
    if (v) v.muted = muted
  }, [muted])

  // ── Controls auto-hide ──
  const showCtrl = useCallback(() => {
    setControlsVisible(true)
    clearTimeout(hideTimerRef.current)
    if (playing) hideTimerRef.current = setTimeout(() => setControlsVisible(false), 3000)
  }, [playing])
  const keepCtrl = useCallback(() => {
    setControlsVisible(true)
    clearTimeout(hideTimerRef.current)
  }, [])
  useEffect(() => () => clearTimeout(hideTimerRef.current), [])

  // ── External seek ──
  useEffect(() => {
    if (seekTime != null && seekTime !== prevSeekRef.current) {
      prevSeekRef.current = seekTime
      const video = videoRef.current
      if (video && !videoError) {
        video.currentTime = seekTime
        if (video.paused) video.play().catch(() => {})
      }
    }
  }, [seekTime, videoError])

  // ═══════════════════════════════════════════════════════════
  // 8. Keyboard shortcuts
  // ═══════════════════════════════════════════════════════════
  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName || '')) return
      if (videoError) return
      switch (e.key) {
        case ' ':
          e.preventDefault()
          playing ? video.pause() : video.play()
          break
        case 'ArrowLeft':
          e.preventDefault()
          video.currentTime = Math.max(0, video.currentTime - 5)
          break
        case 'ArrowRight':
          e.preventDefault()
          video.currentTime = Math.min(video.duration, video.currentTime + 5)
          break
        case 'ArrowUp':
          e.preventDefault()
          setVolume(v => { const n = Math.min(1, v + 0.1); video.volume = n; setMuted(false); return n })
          break
        case 'ArrowDown':
          e.preventDefault()
          setVolume(v => { const n = Math.max(0, v - 0.1); video.volume = n; return n })
          break
        case 'f': case 'F':
          e.preventDefault()
          if (document.fullscreenElement) document.exitFullscreen()
          else containerRef.current?.requestFullscreen()
          break
        case 'm': case 'M':
          e.preventDefault()
          setMuted(m => !m)
          break
        case ',':
          e.preventDefault()
          setPlaybackRate(r => { const i = Math.max(0, SPEEDS.indexOf(r) - 1); const n = SPEEDS[i]; video.playbackRate = n; return n })
          break
        case '.':
          e.preventDefault()
          setPlaybackRate(r => { const i = Math.min(SPEEDS.length - 1, SPEEDS.indexOf(r) + 1); const n = SPEEDS[i]; video.playbackRate = n; return n })
          break
        case 'c': case 'C':
          if (transcript && transcript.length > 0) setShowTranscript(s => !s)
          break
        case '?':
          e.preventDefault()
          setShowShortcuts(s => !s)
          break
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [playing, transcript, videoError])

  // ── Helpers ──
  const formatTime = (s: number) => {
    if (!isFinite(s) || s < 0) return '0:00'
    const m = Math.floor(s / 60)
    const sec = Math.floor(s % 60)
    return m + ':' + sec.toString().padStart(2, '0')
  }

  const onProgressHover = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!progressRef.current) return
    const rect = progressRef.current.getBoundingClientRect()
    const pos = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
    setHoverPos(pos)
    setHoverTime(pos * duration)
  }
  const onProgressLeave = () => setHoverTime(null)

  const changeVolume = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = parseFloat(e.target.value)
    setVolume(v)
    const vv = videoRef.current
    if (vv) { vv.volume = v; setMuted(v === 0) }
  }

  const changePlaybackRate = (rate: number) => {
    setPlaybackRate(rate)
    if (videoRef.current) videoRef.current.playbackRate = rate
    setShowSpeedMenu(false)
  }

  const currentCaption = transcript?.find(c => currentTime >= c.start && currentTime <= c.end)

  // ═══════════════════════════════════════════════════════════
  // ── PiP ──
  const handlePiP = useCallback(async () => {
    const video = videoRef.current
    if (!video || videoError) return
    try {
      if (document.pictureInPictureElement) {
        await document.exitPictureInPicture()
      } else {
        await video.requestPictureInPicture()
      }
    } catch (e) {
      console.warn('PiP failed:', e)
    }
  }, [videoError])

  // ── Screenshot ──
  const handleScreenshot = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const link = document.createElement('a')
    link.download = 'screenshot-' + (currentAsset?.id || Date.now()) + '.png'
    link.href = canvas.toDataURL('image/png')
    link.click()
  }, [currentAsset])

  // ═══════════════════════════════════════════════════════════
  // Render
  // ═══════════════════════════════════════════════════════════
  return (
    <div
      ref={containerRef}
      style={{ aspectRatio: canvasAspect }} className={'relative bg-black rounded-lg overflow-hidden group max-h-[55vh] max-w-full w-[calc(55vh_*_16_/_9)] mx-auto ' + className}
      onMouseMove={showCtrl}
      onMouseLeave={() => { if (playing) setControlsVisible(false) }}
      onTouchStart={showCtrl}
    >
      {/* Hidden video — decoder only */}
      <video
        ref={videoRef}
        muted
        playsInline
        preload="metadata"
        style={{ position: 'absolute', width: 0, height: 0, opacity: 0, pointerEvents: 'none', overflow: 'hidden' }}
      >
        {sourceList.map((s, i) => (
          <source key={i} src={s.src} type={s.type} />
        ))}
      </video>

      {/* Visible canvas */}
      <canvas
        ref={canvasRef}
        className={'block mx-auto' + (canvasReady ? '' : ' invisible')}
        style={{ cursor: 'pointer' }}
        onClick={togglePlay}
      />

      {/* Loading spinner */}
      {(loading || !canvasReady) && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
          <div className="w-10 h-10 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {/* Resolution warning */}
      {resWarn && !videoError && (
        <div className="absolute top-3 left-3 flex items-center gap-1 px-2 py-1 bg-amber-900/60 text-amber-300 text-xs rounded-full border border-amber-700/50 backdrop-blur-sm pointer-events-none z-10">
          <Monitor className="w-3 h-3" />
          <span>High-res source</span>
        </div>
      )}

      {/* Error overlay */}
      {videoError && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80 gap-3 px-6 z-20">
          <AlertCircle className="w-10 h-10 text-red-400" />
          <p className="text-sm text-gray-300 text-center max-w-md">{errorMessage}</p>
          <button
            onClick={retryPlayback}
            className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Retry
          </button>
        </div>
      )}

      {/* Caption overlay */}
      {currentCaption && showTranscript && !videoError && (
        <div className="absolute bottom-16 left-0 right-0 flex justify-center px-4 pointer-events-none z-10">
          <div className="bg-black/85 text-white text-sm px-4 py-2 rounded-lg max-w-xl text-center backdrop-blur-sm">
            {currentCaption.text}
          </div>
        </div>
      )}

      {/* Big play button */}
      {!playing && !currentCaption && !videoError && !loading && canvasReady && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
          <div className="w-16 h-16 rounded-full bg-black/50 flex items-center justify-center">
            <Play className="w-8 h-8 text-white ml-1" />
          </div>
        </div>
      )}

      {/* Controls */}
      <div
        className={'absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/95 via-black/60 to-transparent pt-12 pb-3 px-3 transition-opacity duration-300 z-20 ' + (controlsVisible && !videoError ? 'opacity-100' : 'opacity-0 pointer-events-none')}
        onMouseEnter={keepCtrl}
      >
        {/* Progress bar */}
        <div
          ref={progressRef}
          className="relative h-1.5 bg-gray-700 rounded-full cursor-pointer mb-2.5 group/progress hover:h-2.5 transition-all"
          onClick={seek}
          onMouseMove={onProgressHover}
          onMouseLeave={onProgressLeave}
        >
          <div
            className="h-full bg-indigo-500 rounded-full transition-all"
            style={{ width: (duration ? (currentTime / duration) * 100 : 0) + '%' }}
          />
          {hoverTime != null && (
            <>
              <div
                className="absolute top-0 h-full w-0.5 bg-white/70 -translate-x-1/2 pointer-events-none"
                style={{ left: (hoverPos * 100) + '%' }}
              />
              <div
                className="absolute -top-8 -translate-x-1/2 bg-black/85 text-white text-xs font-mono px-2 py-1 rounded pointer-events-none whitespace-nowrap"
                style={{ left: (hoverPos * 100) + '%' }}
              >
                {formatTime(hoverTime)}
              </div>
            </>
          )}
          <div
            className="absolute top-0 h-full bg-white/15 rounded-full pointer-events-none"
            style={{ width: (duration ? Math.min(100, ((videoRef.current?.buffered.length ? videoRef.current.buffered.end(videoRef.current.buffered.length - 1) : currentTime + 10) / duration) * 100) : 0) + '%' }}
          />
        </div>

        <div className="flex items-center gap-1.5">
          <button onClick={togglePlay} className="text-white hover:text-indigo-400 transition-colors p-1" title={playing ? 'Pause (Space)' : 'Play (Space)'}>
            {playing ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
          </button>
          <button onClick={() => seekSeconds(-5)} className="text-gray-400 hover:text-white transition-colors p-1" title={'Rewind 5s (\u2190)'}>
            <SkipBack className="w-4 h-4" />
          </button>
          <button onClick={() => seekSeconds(5)} className="text-gray-400 hover:text-white transition-colors p-1" title={'Forward 5s (\u2192)'}>
            <SkipForward className="w-4 h-4" />
          </button>
          <span className="text-xs text-gray-300 font-mono min-w-[100px] tabular-nums">
            {formatTime(currentTime)} / {formatTime(duration)}
          </span>
          <div className="flex-1" />

          {/* Volume */}
          <div className="flex items-center gap-1 group/vol">
            <button onClick={() => setMuted(m => !m)} className="text-gray-400 hover:text-white transition-colors p-1" title={muted ? 'Unmute (M)' : 'Mute (M)'}>
              {muted || volume === 0 ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
            </button>
            <div className="w-0 overflow-hidden group-hover/vol:w-20 transition-all duration-200">
              <input
                type="range"
                min="0" max="1" step="0.05"
                value={muted ? 0 : volume}
                onChange={changeVolume}
                className="w-20 h-1 appearance-none bg-gray-600 rounded-full cursor-pointer accent-indigo-500 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white"
              />
            </div>
          </div>

          {/* Speed */}
          <div className="relative">
            <button onClick={() => setShowSpeedMenu(s => !s)} className="text-xs text-gray-400 hover:text-white font-mono transition-colors px-2 py-1 rounded hover:bg-gray-800" title="Playback speed">
              {playbackRate}x
            </button>
            {showSpeedMenu && (
              <div className="absolute bottom-full right-0 mb-2 bg-gray-900 border border-gray-700 rounded-lg shadow-xl overflow-hidden z-50 min-w-[72px]">
                {SPEEDS.map(rate => (
                  <button
                    key={rate}
                    onClick={() => changePlaybackRate(rate)}
                    className={'block w-full text-left px-3 py-1.5 text-sm hover:bg-gray-800 transition-colors ' + (rate === playbackRate ? 'text-indigo-400 bg-indigo-900/30' : 'text-gray-300')}
                  >
                    {rate}x
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* CC */}
          {transcript && transcript.length > 0 && (
            <button
              onClick={() => setShowTranscript(!showTranscript)}
              className={'text-xs flex items-center gap-1 transition-colors p-1 ' + (showTranscript ? 'text-indigo-400' : 'text-gray-400 hover:text-white')}
              title="Closed captions (C)"
            >
              <Scissors className="w-4 h-4" />
              {t('videoPlayer.cc')}
            </button>
          )}

          <button onClick={() => containerRef.current?.requestFullscreen()} className="text-gray-400 hover:text-white transition-colors p-1" title="Fullscreen (F)">
            <Maximize className="w-4 h-4" />
          </button>
          <button onClick={handlePiP} className="text-gray-400 hover:text-white transition-colors p-1" title="Picture in Picture (PiP)">
            <PictureInPicture2 className="w-4 h-4" />
          </button>
          <button onClick={handleScreenshot} className="text-gray-400 hover:text-white transition-colors p-1" title="Screenshot">
            <Camera className="w-4 h-4" />
          </button>
        </div>
      </div>
      {/* Shortcut help overlay */}
      {showShortcuts && (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/70" onClick={() => setShowShortcuts(false)}>
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-5 max-w-xs w-full mx-4 shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-white">Keyboard Shortcuts</h3>
              <button onClick={() => setShowShortcuts(false)} className="text-gray-500 hover:text-white"><Keyboard className="w-4 h-4" /></button>
            </div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-gray-400">Play / Pause</span><kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-xs text-gray-300">Space</kbd></div>
              <div className="flex justify-between"><span className="text-gray-400">Rewind 5s</span><kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-xs text-gray-300">&larr;</kbd></div>
              <div className="flex justify-between"><span className="text-gray-400">Forward 5s</span><kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-xs text-gray-300">&rarr;</kbd></div>
              <div className="flex justify-between"><span className="text-gray-400">Volume Up</span><kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-xs text-gray-300">&uarr;</kbd></div>
              <div className="flex justify-between"><span className="text-gray-400">Volume Down</span><kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-xs text-gray-300">&darr;</kbd></div>
              <div className="flex justify-between"><span className="text-gray-400">Fullscreen</span><kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-xs text-gray-300">F</kbd></div>
              <div className="flex justify-between"><span className="text-gray-400">Mute</span><kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-xs text-gray-300">M</kbd></div>
              <div className="flex justify-between"><span className="text-gray-400">Speed Down</span><kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-xs text-gray-300">,</kbd></div>
              <div className="flex justify-between"><span className="text-gray-400">Speed Up</span><kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-xs text-gray-300">.</kbd></div>
              <div className="flex justify-between"><span className="text-gray-400">CC Toggle</span><kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-xs text-gray-300">C</kbd></div>
              <div className="flex justify-between"><span className="text-gray-400">Shortcuts</span><kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-xs text-gray-300">?</kbd></div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
