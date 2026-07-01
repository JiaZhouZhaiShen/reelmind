import { useState } from 'react'
import { Film, Clock, Maximize2, Heart, Archive, RotateCcw, CheckSquare, Square, Monitor, Smartphone, ImagePlay, Text, Tag, ScanEye } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Asset } from '../api/client'
import { useTranslation } from 'react-i18next'
import { useStore } from '../stores/app'

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

export function VideoCard({ assetId, asset: propAsset }: { 
  assetId?: string
  asset?: Asset 
}) {
  const storeAsset = useStore((s) => assetId ? s.assetsById[assetId] : undefined)
  const asset = propAsset || storeAsset
  const toggleAssetSelection = useStore((s) => s.toggleAssetSelection)
  const isSelected = useStore((s) => s.selectedAssetIds.includes(asset?.id ?? ''))
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [archived, setArchived] = useState(asset?.is_archived ?? false)
  const [thumbError, setThumbError] = useState(false)
  if (!asset) {
    return (
      <div className="bg-gray-900 rounded-lg overflow-hidden border border-gray-800 animate-pulse">
        <div className="aspect-video bg-gray-800" style={{ minHeight: 112 }} />
        <div className="p-3 space-y-2">
          <div className="h-3 bg-gray-800 rounded w-3/4" />
          <div className="h-2 bg-gray-800 rounded w-1/2" />
        </div>
      </div>
    )
  }
  const thumbSrc = asset.thumbnail_path
    ? api.thumbnailUrl(asset.id)
    : undefined

 const handleClick = (e: React.MouseEvent) => {
    if (e.ctrlKey || e.metaKey) {
     e.preventDefault()
     e.stopPropagation()
     toggleAssetSelection(asset.id)
    } else {
      navigate(`/asset/${asset.id}`)
    }
  }

  const handleArchive = async (e: React.MouseEvent) => {
    e.stopPropagation()
    const updated = await api.updateAsset(asset.id, { is_archived: !archived })
    setArchived(updated.is_archived)
  }

  return (
   <div
      data-asset-id={asset.id}
     onClick={handleClick}
     className="group relative bg-gray-900 rounded-lg overflow-hidden border border-gray-800 hover:border-indigo-500/50 transition-all cursor-pointer"
    >
      {/* Selection checkbox */}
      <div
        onClick={(e) => {
          e.stopPropagation();
          toggleAssetSelection(asset.id);
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
            alt={asset.file_name}
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
            <span>{formatDuration(asset.duration)}</span>
            {asset.width && asset.height && (
              <>
                <span className="text-white/40">|</span>
                <Maximize2 className="w-3 h-3" />
                <span>{asset.width}x{asset.height}</span>
              </>
            )}
            {(() => {
              const isLandscape = asset.tags?.includes('横屏')
              const isPortrait = asset.tags?.includes('竖屏')
              const hasDbTag = isLandscape || isPortrait
              const w = asset.width
              const h = asset.height
              const showLandscape = hasDbTag ? isLandscape : (w != null && h != null && w > h)
              const showPortrait = hasDbTag ? isPortrait : (w != null && h != null && w < h)
             if (!showLandscape && !showPortrait) return null
             const label = showLandscape ? '横屏' : '竖屏'
              const cls = 'text-gray-400'
             const Icon = showLandscape ? Monitor : Smartphone
              return (
                <>
                  <span className="text-white/40">|</span>
                  <Icon className={"w-3 h-3 " + cls} />
                  <span className={cls}>{label}</span>
                </>
              )
            })()}
          </div>
        </div>

        {/* Top-right indicators */}
        <div className="absolute top-2 right-2 flex flex-col gap-1">
          {/* Processing status badges */}
         <div className="flex gap-1">
          {asset.scene_status === 'completed' && (
              <span title="场景"><ImagePlay className="w-3.5 h-3.5 text-cyan-400" /></span>
           )}
          {asset.transcript_status === 'completed' && (
              <span title="字幕"><Text className="w-3.5 h-3.5 text-pink-400" /></span>
           )}
           {asset.yolo_status === 'completed' && (
              <span title="标识"><Tag className="w-3.5 h-3.5 text-amber-300" /></span>
           )}
           {asset.ocr_status === 'completed' && (
              <span title="OCR"><ScanEye className="w-3.5 h-3.5 text-violet-400" /></span>
           )}
         </div>
          <div className="flex gap-1">
            {archived && (
              <div className="bg-gray-800 rounded p-1" title={t('videoCard.archived')}>
                <Archive className="w-3.5 h-3.5 text-gray-400" />
              </div>
            )}
            {asset.is_favorite && (
              <Heart className="w-4 h-4 fill-red-500 text-red-500" />
            )}
          </div>
        </div>
      </div>

      {/* Info */}
      <div className="p-3">
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-sm font-medium text-gray-200 truncate group-hover:text-white transition-colors">
            {asset.file_name}
          </h3>
          <button
            onClick={handleArchive}
            className={`shrink-0 transition-colors ${archived ? 'text-gray-400 hover:text-gray-200' : 'text-gray-600 hover:text-indigo-400 opacity-0 group-hover:opacity-100'}`}
            title={archived ? t('videoCard.unarchive') : t('videoCard.archive')}
          >
            {archived ? <RotateCcw className="w-3.5 h-3.5" /> : <Archive className="w-3.5 h-3.5" />}
          </button>
        </div>
       <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
         <span>{formatSize(asset.file_size)}</span>
         {asset.codec && (
           <>
             <span>|</span>
             <span className="uppercase">{asset.codec}</span>
           </>
         )}
         {asset.scene_status && asset.scene_status !== "pending" && (
           <span className="ml-auto">
{asset.scene_status === "completed" && <span className="text-emerald-600 font-medium">已处理</span>}
             {asset.scene_status === "running" && <span className="text-gray-400 font-medium animate-pulse">处理中</span>}
             {asset.scene_status === "error" && <span className="text-red-400 font-medium">失败</span>}
            </span>
          )}
       </div>
        {(asset.tags?.length ?? 0) > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {(asset.tags ?? []).slice(0, 3).map((tag) => (
              <span key={tag} className="px-1.5 py-0.5 text-xs rounded bg-gray-800 text-gray-400">
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}



