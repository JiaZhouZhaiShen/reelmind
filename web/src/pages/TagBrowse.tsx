import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Tags, Tag, Layers, Film, Loader2, ArrowLeft, Grid3X3, Hash, Monitor, Smartphone, Download
} from 'lucide-react'
import { api, type Asset } from '../api/client'
import { VideoCard } from '../components/VideoCard'
import { BatchToolbar } from '../components/BatchToolbar'
import { useTranslation } from 'react-i18next'
import { useMarqueeSelection } from '../hooks/useMarqueeSelection'

const CATEGORY_COLORS: Record<string, string> = {
  resolution: '#8b5cf6',
  codec: '#06b6d4',
  duration: '#f59e0b',
  fps: '#10b981',
  audio: '#ec4899',
  aspect_ratio: '#6366f1',
  file_type: '#14b8a6',
  quality: '#f97316',
  workflow: '#8b5cf6',
  camera: '#a855f7',
  location: '#22c55e',
  color: '#f97316',
  general: '#6b7280',
}


type OrientationFilter = 'all' | 'landscape' | 'portrait'
function getOrientation(w?: number, h?: number): 'landscape' | 'portrait' | 'square' | undefined {
  if (!w || !h) return undefined
  if (w === h) return 'square'
  return w > h ? 'landscape' : 'portrait'
}
interface TagCategory {
  category: string
  count: number
}

interface TagEntry {
  id: string
  name: string
  category: string
  color?: string
  usage_count: number
}

type ViewState = 'categories' | 'tags' | 'categoryTags' | 'assets'

export function TagBrowse() {
  const { t } = useTranslation()
  const [view, setView] = useState<ViewState>('categories')
  const [categories, setCategories] = useState<TagCategory[]>([])
  const [tags, setTags] = useState<TagEntry[]>([])
  const [allTags, setAllTags] = useState<TagEntry[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [selectedCategory, setSelectedCategory] = useState<string>('')
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [assetCount, setAssetCount] = useState(0)
  const [orientationFilter, setOrientationFilter] = useState<OrientationFilter>('all')
  const scrollRef = useRef<HTMLDivElement>(null)

  useMarqueeSelection(scrollRef)

  const loadCategories = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listTagCategories()
      setCategories(data)
      setView('categories')
    } catch (e) {
      console.error('Failed to load categories:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadAllTags = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listTags()
      setAllTags(data)
      api.listTagCategories().then(c => setCategories(c)).catch(() => {})
      setView('tags')
    } catch (e) {
      console.error('Failed to load tags:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadTagsByCategory = useCallback(async (category: string) => {
    setLoading(true)
    setSelectedCategory(category)
    try {
      const data = await api.listTags(category)
      setTags(data)
      setView('categoryTags')
    } catch (e) {
      console.error('Failed to load tags:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadAssetsByTags = useCallback(async (tagNames: string[]) => {
    setLoading(true)
    try {
      const result = await api.smartSearch({
        tags: tagNames.join(','),
        page_size: 100,
      })
      setAssets(result.results.map((r) => ({
        id: r.id,
        file_name: r.file_name,
        duration: r.duration,
        thumbnail_path: r.thumbnail_path,
        library_id: '',
        original_path: '',
        file_size: 0,
        mime_type: undefined,
        width: undefined,
        height: undefined,
        fps: undefined,
        codec: undefined,
        audio_codec: undefined,
        has_audio: false,
        proxy_path: undefined,
        transcript_status: '',
        clip_status: '',
        scene_status: '',
        is_imported: false,
        is_archived: false,
        is_favorite: false,
        notes: undefined,
        file_hash: undefined,
        created_at: '',
        updated_at: '',
        tags: [],
      } as unknown as Asset)))
      setAssetCount(result.total)
      setView('assets')
    } catch (e) {
      console.error('Failed to search assets:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  const handleCategoryClick = (category: string) => {
    loadTagsByCategory(category)
  }

  const handleTagClick = (tagName: string) => {
    const newTags = selectedTags.includes(tagName)
      ? selectedTags.filter((t) => t !== tagName)
      : [...selectedTags, tagName]
    setSelectedTags(newTags)
    if (newTags.length > 0) {
      loadAssetsByTags(newTags)
    }
  }

  const filteredAssets = useMemo(() => {
    if (orientationFilter === 'all') return assets
    return assets.filter((a) => {
      if (a.tags?.includes('横屏')) return orientationFilter === 'landscape'
      if (a.tags?.includes('竖屏')) return orientationFilter === 'portrait'
      const o = getOrientation(a.width, a.height)
      return o === orientationFilter
    })
  }, [assets, orientationFilter])

  const handleBack = () => {
    if (view === 'categoryTags') {
      setView('tags')
    } else if (view === 'assets') {
      if (selectedCategory) {
        loadTagsByCategory(selectedCategory)
      } else {
        setView('tags')
      }
    }
  }

  // Read URL params for pre-selected tag (from TagManager click-through)
  const [searchParams] = useSearchParams()
  const urlTag = searchParams.get('tag')

  useEffect(() => {
    if (urlTag) {
      setLoading(true)
      api.listTags().then((allTags) => {
        const foundTag = allTags.find((t) => t.name === urlTag)
        if (foundTag) {
          setAllTags(allTags)
          setSelectedCategory(foundTag.category)
          setSelectedTags([urlTag])
          return api.smartSearch({ tags: urlTag, page_size: 100 }).then((result) => {
            setAssets(result.results.map((r) => ({
              id: r.id,
              file_name: r.file_name,
              duration: r.duration,
              thumbnail_path: r.thumbnail_path,
              library_id: '',
              original_path: '',
              file_size: 0,
              mime_type: undefined,
              width: undefined,
              height: undefined,
              fps: undefined,
              codec: undefined,
              audio_codec: undefined,
              has_audio: false,
              proxy_path: undefined,
              transcript_status: '',
              clip_status: '',
              scene_status: '',
              is_imported: false,
              is_archived: false,
              is_favorite: false,
              notes: undefined,
              file_hash: undefined,
              created_at: '',
              updated_at: '',
              tags: [],
            } as unknown as Asset)))
            setAssetCount(result.total)
            setView('assets')
            setLoading(false)
          })
        } else {
          setAllTags(allTags)
          setLoading(false)
          setView('tags')
        }
      }).catch(() => {
        setLoading(false)
        loadAllTags()
      })
    } else {
      loadAllTags()
    }
  }, [urlTag])

  // Group tags by category
  const groupedTags = allTags.reduce<Record<string, TagEntry[]>>((acc, tag) => {
    const cat = tag.category || 'general'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(tag)
    return acc
  }, {})

  return (
    <div ref={scrollRef} className="p-6">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        {view !== 'categories' && view !== 'tags' && (
          <button onClick={handleBack} className="text-gray-400 hover:text-white transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </button>
        )}
        {view === 'tags' && categories.length > 0 && (
          <button
            onClick={() => { api.listTagCategories().then(setCategories).catch(() => {}); setView('categories') }}
            className="ml-auto flex items-center gap-1.5 text-xs text-gray-500 hover:text-indigo-400 transition-colors"
            title="View by category grid"
          >
            <Grid3X3 className="w-3.5 h-3.5" />
            Categories
          </button>
        )}
        {view === 'categories' && (
          <button
            onClick={() => setView('tags')}
            className="ml-auto flex items-center gap-1.5 text-xs text-gray-500 hover:text-indigo-400 transition-colors"
            title="View all tags"
          >
            <Tag className="w-3.5 h-3.5" />
            All Tags
          </button>
        )}
        <div>
          <h1 className="text-2xl font-bold text-white">
            {view === 'categories' && t('sidebar.browseTags')}
            {view === 'tags' && (
              <span className="flex items-center gap-2">
                <Tag className="w-5 h-5 text-indigo-400" />
                <span>All Tags</span>
                <span className="text-sm font-normal text-gray-500">
                  ({allTags.length} total)
                </span>
              </span>
            )}
            {view === 'categoryTags' && selectedCategory && (
              <span className="flex items-center gap-2">
                <span className="capitalize">{selectedCategory}</span>
                <span className="text-sm font-normal text-gray-500">
                  ({tags.length} {t('tags.assetCount', { count: tags.length })})
                </span>
              </span>
            )}
            {view === 'assets' && (
              <span className="flex items-center gap-2">
                <span>{selectedTags.join(', ')}</span>
                <span className="text-sm font-normal text-gray-500">
                  ({filteredAssets.length} / {assetCount} {t('assetGrid.videoCount', { count: assetCount })})
                </span>
              </span>
            )}
          </h1>
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-24">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
        </div>
      )}

      {!loading && view === 'categories' && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {categories.map((cat) => {
            const color = CATEGORY_COLORS[cat.category] || '#6b7280'
            return (
              <button
                key={cat.category}
                onClick={() => handleCategoryClick(cat.category)}
                className="group bg-gray-900 rounded-lg border border-gray-800 hover:border-gray-700 p-5 text-left transition-all hover:bg-gray-800/80"
              >
                <div
                  className="w-10 h-10 rounded-lg flex items-center justify-center mb-3"
                  style={{ backgroundColor: `${color}20` }}
                >
                  <Layers className="w-5 h-5" style={{ color }} />
                </div>
                <h3 className="text-base font-medium text-gray-200 group-hover:text-white capitalize transition-colors">
                  {cat.category.replace(/_/g, ' ')}
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  {cat.count} {t('tags.assetCount', { count: cat.count })}
                </p>
              </button>
            )
          })}
        </div>
      )}

      {!loading && view === 'tags' && (
        <div className="space-y-6">
          {allTags.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-gray-500">
              <Tag className="w-12 h-12 mb-3 text-gray-700" />
              <p className="text-gray-400 text-lg mb-1">No tags yet</p>
              <p className="text-sm text-gray-600">
                <a href="/tags/manage" className="text-indigo-400 hover:text-indigo-300">Create or generate tags</a> to start browsing
              </p>
            </div>
          ) : (
            Object.entries(groupedTags).sort(([a], [b]) => a.localeCompare(b)).map(([category, catTags]) => {
              const color = CATEGORY_COLORS[category] || '#6b7280'
              return (
                <div key={category}>
                  <div className="flex items-center gap-2 mb-3">
                    <button
                      onClick={() => handleCategoryClick(category)}
                      className="flex items-center gap-2 hover:opacity-80 transition-opacity"
                    >
                      <Layers className="w-4 h-4" style={{ color }} />
                      <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
                        {category.replace(/_/g, ' ')}
                      </h3>
                    </button>
                    <span className="text-xs text-gray-600">({catTags.length})</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {catTags.map((tagItem) => {
                      const isSelected = selectedTags.includes(tagItem.name)
                      return (
                        <button
                          key={tagItem.id}
                          onClick={() => handleTagClick(tagItem.name)}
                          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm transition-all ${isSelected ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-300' : 'bg-gray-800/50 border-gray-700/50 text-gray-300 hover:bg-gray-700/50 hover:border-gray-600'}`}
                        >
                          <div
                            className="w-2 h-2 rounded-full"
                            style={{ backgroundColor: tagItem.color || CATEGORY_COLORS[tagItem.category] || '#6b7280' }}
                          />
                          <span>{tagItem.name}</span>
                          <span className="text-xs text-gray-500">({tagItem.usage_count})</span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )
            })
          )}
        </div>
      )}

      {!loading && view === 'categoryTags' && (
        <div className="flex flex-wrap gap-2">
          {tags.map((tag) => {
            const isSelected = selectedTags.includes(tag.name)
            const color = tag.color || CATEGORY_COLORS[tag.category] || '#6b7280'
            return (
              <button
                key={tag.id}
                onClick={() => handleTagClick(tag.name)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm transition-all ${isSelected ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-300' : 'bg-gray-800/50 border-gray-700/50 text-gray-300 hover:bg-gray-700/50 hover:border-gray-600'}`}
              >
                <div
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span>{tag.name}</span>
                <span className="text-xs text-gray-500">({tag.usage_count})</span>
              </button>
            )
          })}
        </div>
      )}

      {!loading && view === 'assets' && (
        <>
          <BatchToolbar currentAssets={filteredAssets} onRefresh={() => selectedTags.length > 0 ? loadAssetsByTags(selectedTags) : undefined} />
                    {/* Orientation filter */}
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
          {/* Selected tag chips */}
          <div className="flex items-center gap-2 mb-4 flex-wrap">
            {selectedTags.map((tagName) => (
              <span
                key={tagName}
                className="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-full bg-indigo-900/30 text-indigo-300 border border-indigo-800/30"
              >
                {tagName}
                <button onClick={() => handleTagClick(tagName)} className="hover:text-white">
                  {'×'}
                </button>
              </span>
            ))}
            <button
              onClick={() => { setSelectedTags([]); loadTagsByCategory(selectedCategory) }}
              className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              {t('filter.clear')}
            </button>
          </div>

          {filteredAssets.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-gray-500">
              <Film className="w-12 h-12 mb-3 text-gray-700" />
              <p className="text-gray-400">{t('searchPage.noResults')}</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-4">
              {filteredAssets.map((asset) => (
                <VideoCard key={asset.id} asset={asset} />
              ))}
            </div>
          )}
        </>
      )}

      {!loading && view === 'categories' && categories.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-gray-500">
          <Tags className="w-12 h-12 mb-3 text-gray-700" />
          <p className="text-gray-400 text-lg mb-1">No tag categories yet</p>
          <p className="text-sm text-gray-600">
            <a href="/tags/manage" className="text-indigo-400 hover:text-indigo-300">Generate or create tags</a> to start browsing
          </p>
        </div>
      )}
    </div>
  )
}
