



import { useState, useEffect, useMemo } from 'react'
import { VideoCard } from '../components/VideoCard'
import type { Asset } from '../api/client'
import { Film, Loader2, ArrowLeft, Image, MessageSquareText, Tag, FileText } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAssetStore } from '../stores/asset'

type StatusFilter = 'all' | 'scene' | 'transcript' | 'yolo' | 'ocr'

const FILTER_DEFS: { key: StatusFilter; labelKey: string; icon: typeof Image }[] = [
  { key: 'all', labelKey: 'processedAssets.filterAll', icon: Film },
  { key: 'scene', labelKey: 'processedAssets.filterScene', icon: Image },
  { key: 'transcript', labelKey: 'processedAssets.filterTranscript', icon: MessageSquareText },
  { key: 'yolo', labelKey: 'processedAssets.filterYolo', icon: Tag },
  { key: 'ocr', labelKey: 'processedAssets.filterOcr', icon: FileText },
]

function assetMatchesFilter(asset: Asset, f: StatusFilter): boolean {
  switch (f) {
    case 'all': return true
    case 'scene': return asset.scene_status === 'success'
    case 'transcript': return asset.transcript_status === 'success'
    case 'yolo': return asset.has_yolo_tags === true
    case 'ocr': return asset.has_ocr_text === true
  }
}

function assetCountForFilter(asset: Asset, f: StatusFilter): boolean {
  switch (f) {
    case 'scene': return asset.scene_status === 'success'
    case 'transcript': return asset.transcript_status === 'success'
    case 'yolo': return asset.has_yolo_tags === true
    case 'ocr': return asset.has_ocr_text === true
    default: return false
  }
}

export function ProcessedAssets() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const assets = useAssetStore((s) => s.processedAssets)
  const loading = useAssetStore((s) => s.processedAssetsLoading)
  const total = useAssetStore((s) => s.processedAssetsTotal)
  const loadProcessedAssets = useAssetStore((s) => s.loadProcessedAssets)
  const [filter, setFilter] = useState<StatusFilter>('all')

  useEffect(() => {
    loadProcessedAssets()
  }, [loadProcessedAssets])

  const filteredAssets = useMemo(() => {
    return assets.filter((a) => assetMatchesFilter(a, filter))
  }, [assets, filter])

  const filterCounts = useMemo(() => {
    const counts: Record<StatusFilter, number> = { all: assets.length, scene: 0, transcript: 0, yolo: 0, ocr: 0 }
    for (const a of assets) {
      if (assetCountForFilter(a, 'scene')) counts.scene++
      if (assetCountForFilter(a, 'transcript')) counts.transcript++
      if (assetCountForFilter(a, 'yolo')) counts.yolo++
      if (assetCountForFilter(a, 'ocr')) counts.ocr++
    }
    return counts
  }, [assets])

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <div className="max-w-screen-2xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => navigate('/ai')}
            className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-lg font-semibold text-gray-100">{t('processedAssets.title')}</h1>
            <p className="text-xs text-gray-500 mt-0.5">
              {t('aiEngine.videosProcessed')}: {total}
            </p>
          </div>
        </div>

        {/* Filter bar */}
        <div className="flex flex-wrap gap-2 mb-5">
          {FILTER_DEFS.map((f) => {
            const active = filter === f.key
            const count = filterCounts[f.key]
            return (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  active
                    ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-500/30'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200'
                }`}
              >
                <f.icon className="w-3.5 h-3.5" />
                <span>{t(f.labelKey)}</span>
                <span className={`ml-0.5 text-[10px] ${active ? 'text-indigo-200' : 'text-gray-600'}`}>
                  {count}
                </span>
              </button>
            )
          })}
        </div>

        {/* Content */}
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <Loader2 className="w-8 h-8 animate-spin text-purple-500" />
          </div>
        ) : filteredAssets.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-gray-500">
            <Film className="w-12 h-12 mb-3 text-gray-700" />
            <p className="text-sm">
              {filter === 'all' ? t('processedAssets.noProcessedVideos') : t('processedAssets.noFilteredVideos')}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
            {filteredAssets.map((asset) => (
              <VideoCard key={asset.id} asset={asset} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
