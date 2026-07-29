import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Tag, Film, Loader2, Search, ArrowLeft, X, Layers, Monitor, Smartphone } from 'lucide-react'
import { api } from '../api/client'
import { getYoloTagVideos } from '../api/ai'
import { VideoCard } from '../components/VideoCard'
import { BatchToolbar } from '../components/BatchToolbar'
import { useMarqueeSelection } from '../hooks/useMarqueeSelection'

import { logger } from '../utils/logger';


// ── Semantic YOLO category classification ──
const CATEGORY_DEFS: Array<{ id: string; label: string; color: string; labels: string[] }> = [
  { id: 'people',     label: '\u4eba\u7269',     color: '#ec4899', labels: ['person'] },
  { id: 'vehicles',   label: '\u4ea4\u901a\u5de5\u5177', color: '#f59e0b', labels: ['car','truck','bus','train','bicycle','motorcycle','airplane','boat'] },
  { id: 'animals',    label: '\u52a8\u7269',     color: '#10b981', labels: ['bird','cat','dog','horse','cow','sheep','elephant','bear','zebra','giraffe'] },
  { id: 'food',       label: '\u98df\u7269',     color: '#f97316', labels: ['cake','pizza','sandwich','donut','hot dog','carrot','orange','apple','banana','broccoli'] },
  { id: 'dining',     label: '\u9910\u996e\u5668\u5177', color: '#8b5cf6', labels: ['bottle','cup','bowl','wine glass','dining table','knife','fork','spoon'] },
  { id: 'furniture',  label: '\u5bb6\u5177',     color: '#06b6d4', labels: ['chair','bench','bed','toilet'] },
  { id: 'electronics',label: '\u7535\u5b50\u8bbe\u5907', color: '#6366f1', labels: ['tv','laptop','cell phone','keyboard','mouse','remote'] },
  { id: 'appliances', label: '\u5bb6\u7535',     color: '#14b8a6', labels: ['refrigerator','oven','microwave','sink','clock'] },
  { id: 'sports',     label: '\u8fd0\u52a8',     color: '#22c55e', labels: ['frisbee','skis','snowboard','sports ball','kite','baseball glove','skateboard','surfboard','tennis racket'] },
  { id: 'outdoor',    label: '\u6237\u5916\u8bbe\u65bd', color: '#a855f7', labels: ['umbrella','traffic light','fire hydrant','stop sign','parking meter'] },
  { id: 'personal',   label: '\u4e2a\u4eba\u7269\u54c1', color: '#f43f5e', labels: ['tie','handbag','backpack','suitcase','book','toothbrush','scissors','vase','potted plant','teddy bear'] },
]

// Build reverse lookup: label -> category id
const LABEL_TO_CAT: Record<string, string> = {}
CATEGORY_DEFS.forEach(c => c.labels.forEach(l => { LABEL_TO_CAT[l] = c.id }))

// Get category id for any label (fallback 'other')
function catId(label: string): string {
  return LABEL_TO_CAT[label] || 'other'
}

interface LabelEntry {
  label: string
  total_count: number
  scene_count: number
  video_count: number
  avg_confidence: number
}

interface VideoEntry {
  id: string
  file_name: string
  duration: number
  thumbnail_path: string
  tag_count: number
  scene_count: number
}

type OrientationFilter = 'all' | 'landscape' | 'portrait'

type ViewState = 'labels' | 'assets'

export function YoloTagBrowse() {
  const [view, setView] = useState<ViewState>('labels')
  const [labels, setLabels] = useState<LabelEntry[]>([])
  const scrollRef = useRef<HTMLDivElement>(null)
  const sentinelRef = useRef<HTMLDivElement>(null)
  const [orientationFilter, setOrientationFilter] = useState<OrientationFilter>('all')

  const [selectedLabel, setSelectedLabel] = useState<string>('')
  const [assets, setAssets] = useState<VideoEntry[]>([])
  const [totalAssets, setTotalAssets] = useState(0)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [sort, setSort] = useState<'count' | 'alpha'>('count')
  // 'categorized' = grouped by semantic category; 'flat' = flat cloud
  const [groupMode, setGroupMode] = useState<'categorized' | 'flat'>('categorized')

  const loadLabels = useCallback(async (search?: string) => {
    setLoading(true)
    try {
      const data = await api.getYoloTagBrowse(search || undefined, sort)
      setLabels(data.labels)
      setTotal(data.total)
    } catch (e) {
      logger.error('Failed to load YOLO labels:', e)
    } finally {
      setLoading(false)
    }
  }, [sort])

  useEffect(() => { loadLabels(searchQuery) }, [loadLabels, searchQuery])
  useMarqueeSelection(scrollRef)

  const loadAssetsByLabel = useCallback(async (label: string, pageNum: number = 1) => {
    setLoading(true)
    setSelectedLabel(label)
    try {
      const data = await getYoloTagVideos(label, pageNum)
      if (pageNum === 1) {
        setAssets(data.assets)
      } else {
        setAssets(prev => [...prev, ...data.assets])
      }
      setTotalAssets(data.total)
      setPage(pageNum)
      setView('assets')
    } catch (e) {
      logger.error('Failed to load videos for label:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  const filteredAssets = useMemo(() => {
    if (orientationFilter === 'all') return assets
    return assets
  }, [assets, orientationFilter])

  const loadMore = () => {
    loadAssetsByLabel(selectedLabel, page + 1)
  }

  useEffect(() => {
    if (!sentinelRef.current) return
    const el = sentinelRef.current
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && filteredAssets.length < totalAssets && !loading) {
          loadMore()
        }
      },
      { rootMargin: "200px" }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [filteredAssets.length, totalAssets, loading, page])

  const handleBack = () => {
    setSelectedLabel('')
    setView('labels')
    loadLabels(searchQuery)
  }

  const searchedLabels = useMemo(() => {
    if (!searchQuery.trim()) return labels
    return labels.filter(l => l.label.toLowerCase().includes(searchQuery.toLowerCase()))
  }, [labels, searchQuery])

  // Group labels by semantic category (preserving CATEGORY_DEFS order)
  const groupedLabels = useMemo(() => {
    const groups: Record<string, LabelEntry[]> = {}
    // Also collect uncategorized labels
    CATEGORY_DEFS.forEach(c => { groups[c.id] = [] })
    groups['other'] = []
    searchedLabels.forEach(l => {
      const cid = catId(l.label)
      if (!groups[cid]) groups[cid] = []
      groups[cid].push(l)
    })
    // Build ordered result: CATEGORY_DEFS order, then 'other' at the end if non-empty
    const result: Array<{ id: string; label: string; color: string; items: LabelEntry[] }> = []
    CATEGORY_DEFS.forEach(c => {
      if (groups[c.id] && groups[c.id].length > 0) {
        result.push({ id: c.id, label: c.label, color: c.color, items: groups[c.id] })
      }
    })
    if (groups['other'] && groups['other'].length > 0) {
      result.push({ id: 'other', label: '\u5176\u4ed6', color: '#6b7280', items: groups['other'] })
    }
    return result
  }, [searchedLabels])

  const statsLine = useMemo(() => {
    if (labels.length === 0) return ''
    const totalDetections = labels.reduce((s, l) => s + l.total_count, 0)
    return `${labels.length} labels · ${totalDetections} detections`
  }, [labels])

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        {view === 'assets' && (
          <button onClick={handleBack} className="text-gray-400 hover:text-white transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </button>
        )}
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-white">
            <span className="flex items-center gap-2">
              <Tag className="w-5 h-5 text-amber-400" />
 <span>YOLO 标签</span>
              <span className="text-sm font-normal text-gray-500">({total} total)</span>
            </span>
          </h1>
          {view === 'labels' && statsLine && (
            <p className="text-xs text-gray-500 mt-1 ml-7">{statsLine}</p>
          )}
          {view === 'assets' && (
            <p className="text-xs text-gray-500 mt-1 ml-7">
              {filteredAssets.length} / {totalAssets} 个视频包含 &quot;{selectedLabel}&quot;
            </p>
          )}
        </div>
        {view === 'labels' && labels.length > 0 && (
          <button
            onClick={() => setGroupMode(g => g === 'categorized' ? 'flat' : 'categorized')}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-indigo-400 transition-colors"
          >
            {groupMode === 'categorized' ? (
              <><Tag className="w-3.5 h-3.5" /> 平铺</>
            ) : (
              <><Layers className="w-3.5 h-3.5" /> 分类</>
            )}
          </button>
        )}
      </div>

      {/* Search + sort bar */}
      {view === 'labels' && (
        <div className="flex items-center gap-3 mb-4">
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="\u641c\u7d22\u6807\u7b7e..."
              className="w-full bg-gray-900 border border-gray-800 rounded-lg pl-9 pr-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500"
            />
          </div>
          <button
            onClick={() => setSort(s => s === 'count' ? 'alpha' : 'count')}
            className="px-3 py-2 bg-gray-900 border border-gray-800 rounded-lg text-sm text-gray-400 hover:text-gray-200 transition-colors"
          >
            {sort === 'count' ? '\u6309\u6b21\u6570 \u2193' : '\u6309\u5b57\u6bcd A-Z'}
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-24">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
        </div>
      )}

      {/* Empty state */}
      {!loading && view === 'labels' && searchedLabels.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-gray-500">
          <Tag className="w-12 h-12 mb-3 text-gray-700" />
          <p className="text-gray-400 text-lg mb-1">暂无 YOLO 标签</p>
          <p className="text-sm text-gray-600">运行 YOLO 检测管线以识别物体</p>
        </div>
      )}

      {/* 平铺 cloud */}
      {!loading && view === 'labels' && groupMode === 'flat' && searchedLabels.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {searchedLabels.map((item) => (
            <button
              key={item.label}
              onClick={() => loadAssetsByLabel(item.label)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm transition-all bg-gray-800/50 border-gray-700/50 text-gray-300 hover:bg-gray-700/50 hover:border-gray-600"
            >
              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: (CATEGORY_DEFS.find(c => c.id === catId(item.label))?.color || "#6b7280") }} />
              <span>{item.label}</span>
 <span className="text-xs text-gray-500">视频 {item.video_count}</span>
            </button>
          ))}
        </div>
      )}

      {/* Categorized view — like /tags/browse category layout */}
      {!loading && view === 'labels' && groupMode === 'categorized' && (
        <div className="space-y-6">
          {groupedLabels.map((group) => (
            <div key={group.id}>
              <div className="flex items-center gap-2 mb-3">
                <Layers className="w-4 h-4" style={{ color: group.color }} />
                <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
                  {group.label}
                </h3>
                <span className="text-xs text-gray-600">({group.items.length})</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {group.items.map((item) => (
                  <button
                    key={item.label}
                    onClick={() => loadAssetsByLabel(item.label)}
                    className="flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm transition-all bg-gray-800/50 border-gray-700/50 text-gray-300 hover:bg-gray-700/50 hover:border-gray-600"
                  >
                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: group.color }} />
                    <span>{item.label}</span>
 <span className="text-xs text-gray-500">视频 {item.video_count}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Assets grid */}
      {!loading && view === 'assets' && (
        <>
          <BatchToolbar currentAssets={assets} onRefresh={() => loadAssetsByLabel(selectedLabel)} />
          <div className="flex items-center gap-1 mb-4">
            <button
              onClick={() => setOrientationFilter('all')}
              className={
                'px-2.5 py-1 text-xs rounded transition-colors ' +
                (orientationFilter === 'all'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-200')
              }
            >
              全部
            </button>
            <button
              onClick={() => setOrientationFilter('landscape')}
              className={
                'px-2.5 py-1 text-xs rounded transition-colors flex items-center gap-1 ' +
                (orientationFilter === 'landscape'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-200')
              }
            >
              <Monitor className="w-3.5 h-3.5" />
              横屏
            </button>
            <button
              onClick={() => setOrientationFilter('portrait')}
              className={
                'px-2.5 py-1 text-xs rounded transition-colors flex items-center gap-1 ' +
                (orientationFilter === 'portrait'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-200')
              }
            >
              <Smartphone className="w-3.5 h-3.5" />
              竖屏
            </button>
          </div>

          <div className="flex items-center gap-2 mb-4 flex-wrap">
            <span className="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-full bg-amber-900/30 text-amber-300 border border-amber-800/30">
              {selectedLabel}
              <button onClick={handleBack} className="hover:text-white ml-1">
                <X className="w-3 h-3" />
              </button>
            </span>
            <button onClick={handleBack} className="text-xs text-gray-500 hover:text-gray-300 transition-colors">清除</button>
          </div>

          {filteredAssets.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-gray-500">
              <Film className="w-12 h-12 mb-3 text-gray-700" />
              <p className="text-gray-400">暂时没有找到包含此标签的视频</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-4">
              {filteredAssets.map((asset) => (
                <VideoCard key={asset.id} asset={{
                  id: asset.id,
                  file_name: asset.file_name,
                  duration: asset.duration,
                  thumbnail_path: asset.thumbnail_path,
                  library_id: '', original_path: '', file_size: 0,
                  mime_type: undefined, width: undefined, height: undefined,
                  fps: undefined, codec: undefined, audio_codec: undefined,
                  has_audio: false, proxy_path: undefined,
                  transcript_status: '', clip_status: '', scene_status: '',
                  is_imported: false, is_archived: false, is_favorite: false,
                  notes: undefined, file_hash: undefined,
                  created_at: '', updated_at: '', tags: [],
                } as any} />
              ))}
            </div>
          )}
          {filteredAssets.length < totalAssets && (
            <div ref={sentinelRef} className="flex justify-center py-6">
              <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
            </div>
          )}
        </>
      )}
    </div>
  )
}
