import { useState, memo } from 'react'
import { useTranslation } from 'react-i18next'
import { Film, Clock, Maximize2, Heart, Archive, RotateCcw, CheckSquare, Square, Monitor, Smartphone, ImagePlay, Text, Tag, ScanEye, Brain, Users } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAssetStore } from '../stores/asset'
import { useSearchStore } from '../stores/search'

function formatDuration(seconds?: number): string {
  if (!seconds) return '--:--'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatSize(bytes: number): string {
  if (bytes < 1e6) return `${(bytes / 1e3).toFixed(0)} KB`
  if (bytes < 1e9) return `${(bytes / 1e6).toFixed(1)} MB`
  return `${(bytes / 1e9).toFixed(2)} GB`
}

export const SearchVideoCard = memo(function SearchVideoCard({ resultId }: { resultId: string }) {
  const { t } = useTranslation()
 const toggleAssetSelection = useAssetStore((s) => s.toggleAssetSelection)
 const result = useSearchStore(s => s.searchResults.find(r => r.id === resultId))
  if (!result) return null
  const isSelected = useAssetStore((s) => s.selectedAssetIds.includes(result.id))
  const navigate = useNavigate()
  const [archived, setArchived] = useState(result.is_archived)
  const [thumbError, setThumbError] = useState(false)

  const thumbSrc = result.thumbnail_path
    ? api.thumbnailUrl(result.id)
    : undefined

  const handleClick = (e: React.MouseEvent) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault()
      e.stopPropagation()
      toggleAssetSelection(result.id)
    } else {
      navigate(`/asset/${result.id}`)
    }
  }

  const handleArchive = async (e: React.MouseEvent) => {
    e.stopPropagation()
    const updated = await api.updateAsset(result.id, { is_archived: !archived })
    setArchived(updated.is_archived)
  }

  return (
    <div
      data-asset-id={result.id}
      onClick={handleClick}
      className="group relative bg-gray-900 rounded-lg overflow-hidden border border-gray-800 hover:border-indigo-500/50 transition-all cursor-pointer"
    >
      {/* Selection checkbox */}
      <div
        onClick={(e) => {
          e.stopPropagation();
          toggleAssetSelection(result.id);
        }}
        className={`absolute top-2 left-2 z-10 w-6 h-6 rounded flex items-center justify-center transition-all ${isSelected ? 'bg-indigo-600' : 'bg-black/40 hover:bg-black/60'}`}
      >
        {isSelected ? (
          <CheckSquare className="w-4 h-4 text-white" />
        ) : (
          <Square className="w-4 h-4 text-white/60" />
        )}
      </div>

      {isSelected && (
        <div className="absolute inset-0 ring-2 ring-indigo-500 ring-inset z-5 pointer-events-none rounded-lg" />
      )}

      {/* Thumbnail */}
      <div className="aspect-video bg-gray-800 relative overflow-hidden">
        {thumbSrc && !thumbError ? (
          <img
            src={thumbSrc}
            alt={result.file_name}
            className="w-full h-full object-cover"
            loading="lazy"
            onError={() => setThumbError(true)}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-600">
            <Film className="w-8 h-8" />
          </div>
        )}

        {/* Overlay info */}
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-2">
          <div className="flex items-center gap-2 text-xs text-white/80">
            <Clock className="w-3 h-3" />
            <span>{formatDuration(result.duration)}</span>
            {result.width && result.height && (
              <>
                <span className="text-white/40">|</span>
                <Maximize2 className="w-3 h-3" />
                <span>{result.width}x{result.height}</span>
              </>
            )}
            {(() => {
              const w = result.width
              const h = result.height
              if (!w || !h) return null
              if (w === h) return null
              const isLandscape = w > h
              const Icon = isLandscape ? Monitor : Smartphone
              return (
                <>
                  <span className="text-white/40">|</span>
                  <Icon className="w-3 h-3 text-gray-400" />
                  <span className="text-gray-400">{isLandscape ? t('searchVideoCard.landscape') : t('searchVideoCard.portrait')}</span>
                </>
              )
            })()}
          </div>
        </div>

        {/* Top-right indicators */}
        <div className="absolute top-2 right-2 flex flex-col gap-1">
          {/* Processing status badges */}
          <div className="flex gap-1">
           {result.scene_status === 'completed' && (
             <span title={t('searchVideoCard.scene')}><ImagePlay className="w-3.5 h-3.5 text-cyan-400" /></span>
           )}
           {result.has_yolo_tags && (
             <span title={t('searchVideoCard.tags')}><Tag className="w-3.5 h-3.5 text-amber-300" /></span>
           )}
           {result.has_ocr_text && (
             <span title={t('searchVideoCard.ocr')}><ScanEye className="w-3.5 h-3.5 text-violet-400" /></span>
           )}
            {result.clip_status === 'completed' && (
              <span title={t('searchVideoCard.vectorSearch')}><Brain className="w-3.5 h-3.5 text-emerald-400" /></span>
            )}
            {result.transcript_status === 'completed' && (
              <span title={t('searchVideoCard.transcript')}><Text className="w-3.5 h-3.5 text-pink-400" /></span>
            )}
            {result.diarization_status === 'completed' && (
              <span title={t('searchVideoCard.speakerDiarization')}><Users className="w-3.5 h-3.5 text-orange-400" /></span>
            )}
          </div>
          <div className="flex gap-1">
            {archived && (
              <div className="bg-gray-800 rounded p-1" title={t('searchVideoCard.archived')}>
                <Archive className="w-3.5 h-3.5 text-gray-400" />
              </div>
            )}
            {result.is_favorite && (
              <Heart className="w-4 h-4 fill-red-500 text-red-500" />
            )}
          </div>
        </div>
      </div>

      {/* Info */}
      <div className="p-3">
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-sm font-medium text-gray-200 truncate group-hover:text-white transition-colors">
            {result.file_name}
          </h3>
          <button
            onClick={handleArchive}
            className={`shrink-0 transition-colors ${archived ? 'text-gray-400 hover:text-gray-200' : 'text-gray-600 hover:text-indigo-400 opacity-0 group-hover:opacity-100'}`}
            title={archived ? t('searchVideoCard.unarchive') : t('searchVideoCard.archive')}
          >
            {archived ? <RotateCcw className="w-3.5 h-3.5" /> : <Archive className="w-3.5 h-3.5" />}
          </button>
        </div>
        <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
          <span>{formatSize(result.file_size)}</span>
          {result.codec && (
            <>
              <span>|</span>
              <span className="uppercase">{result.codec}</span>
            </>
          )}
          {result.scene_status && result.scene_status !== "pending" && (
            <span className="ml-auto">
              {result.scene_status === "completed" && <span className="text-emerald-600 font-medium">{t('searchVideoCard.processed')}</span>}
              {result.scene_status === "running" && <span className="text-gray-400 font-medium animate-pulse">{t('searchVideoCard.processing')}</span>}
              {result.scene_status === "error" && <span className="text-red-400 font-medium">{t('searchVideoCard.failed')}</span>}
            </span>
          )}
        </div>
      </div>
    </div>
  )
});
