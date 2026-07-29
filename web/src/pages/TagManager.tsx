import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Tag, Plus, Trash2, Edit2, Wand2, Search, Loader2, X, CheckCircle, ExternalLink, ChevronDown, ChevronRight } from 'lucide-react'
import { api, type TagInfo } from '../api/client'
import { useTranslation } from 'react-i18next'

import { logger } from '../utils/logger';


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

export function TagManager() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [tags, setTags] = useState<TagInfo[]>([])
  const [autoTagIds, setAutoTagIds] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [filterCategory, setFilterCategory] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [sourceFilter, setSourceFilter] = useState<'all' | 'auto' | 'manual'>('all')
  const [selectedTagIds, setSelectedTagIds] = useState<Set<string>>(new Set())
  const [expandedCategories, setExpandedCategories] = useState<Record<string, boolean>>({})
  const [autoGenerating, setAutoGenerating] = useState(false)
  const [autoGenResult, setAutoGenResult] = useState<string | null>(null)
  const [batchDeleting, setBatchDeleting] = useState(false)
  const [batchDeleteResult, setBatchDeleteResult] = useState<string | null>(null)

  const [formName, setFormName] = useState('')
  const [formCategory, setFormCategory] = useState('general')
  const [formColor, setFormColor] = useState('#6366f1')

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [tagData, autoData] = await Promise.all([
        api.listTags(filterCategory || undefined, searchQuery || undefined),
        api.getAutoTagIds(),
      ])
      setTags(tagData)
      setAutoTagIds(new Set(autoData.auto_tag_ids))
    } catch (e) {
      logger.error('Failed to load tags:', e)
    } finally {
      setLoading(false)
    }
  }, [filterCategory, searchQuery])

  useEffect(() => { loadData() }, [loadData])

  const resetForm = () => {
    setFormName('')
    setFormCategory('general')
    setFormColor('#6366f1')
  }

  const handleCreate = async () => {
    if (!formName.trim()) return
    try {
      await api.createTag({ name: formName, category: formCategory, color: formColor })
      resetForm()
      setShowCreate(false)
      await loadData()
    } catch (e) {
      logger.error('Failed to create tag:', e)
    }
  }

  const handleUpdate = async (id: string) => {
    if (!formName.trim()) return
    try {
      await api.updateTag(id, { name: formName, category: formCategory, color: formColor })
      setEditingId(null)
      resetForm()
      await loadData()
    } catch (e) {
      logger.error('Failed to update tag:', e)
    }
  }

  const navigateToBrowse = (tagName: string) => {
    navigate('/tags/browse?tag=' + encodeURIComponent(tagName))
  }

  const handleDelete = async (tag: TagInfo) => {
    if (!confirm(t('tags.deleteConfirm', { name: tag.name }))) return
    try {
      await api.deleteTag(tag.id)
      await loadData()
    } catch (e) {
      logger.error('Failed to delete tag:', e)
    }
  }

  const handleBatchDelete = async () => {
    if (selectedTagIds.size === 0) return
    if (!confirm(t('tags.batchDeleteConfirm', { count: selectedTagIds.size }))) return
    setBatchDeleting(true)
    setBatchDeleteResult(null)
    try {
      const result = await api.batchDeleteTags(Array.from(selectedTagIds))
      setBatchDeleteResult(t('tags.batchDeleteResult', { count: result.count }))
      setSelectedTagIds(new Set())
      await loadData()
      setTimeout(() => setBatchDeleteResult(null), 3000)
    } catch (e) {
      logger.error('Batch delete failed:', e)
    } finally {
      setBatchDeleting(false)
    }
  }

  const handleAutoGenerate = async () => {
    setAutoGenerating(true)
    setAutoGenResult(null)
    try {
      await api.autoGenerateTags()
      setAutoGenResult(t('tags.autoGenerateStarted'))
      setTimeout(() => { loadData(); setAutoGenResult(null) }, 4000)
    } catch (e) {
      logger.error('Auto-generate failed:', e)
    } finally {
      setAutoGenerating(false)
    }
  }

  const startEdit = (tag: TagInfo) => {
    setEditingId(tag.id)
    setFormName(tag.name)
    setFormCategory(tag.category)
    setFormColor(tag.color || '#6366f1')
  }

  const toggleTagSelection = (tagId: string) => {
    setSelectedTagIds((prev) => {
      const next = new Set(prev)
      if (next.has(tagId)) next.delete(tagId)
      else next.add(tagId)
      return next
    })
  }

  const selectAllAuto = () => {
    const autoIds = tags.filter((t) => autoTagIds.has(t.id)).map((t) => t.id)
    setSelectedTagIds(new Set(autoIds))
  }

  const deselectAll = () => {
    setSelectedTagIds(new Set())
  }

  const selectAllInCategory = (_category: string, catTags: TagInfo[]) => {
    const allSelected = catTags.every((t) => selectedTagIds.has(t.id))
    setSelectedTagIds((prev) => {
      const next = new Set(prev)
      for (const t of catTags) {
        if (allSelected) next.delete(t.id)
        else next.add(t.id)
      }
      return next
    })
  }

  const toggleCategory = (cat: string) => {
    setExpandedCategories((prev) => ({ ...prev, [cat]: !prev[cat] }))
  }

  // Derive visible tag list based on source filter
  const filteredBySource = sourceFilter === 'auto'
    ? tags.filter((t) => autoTagIds.has(t.id))
    : sourceFilter === 'manual'
      ? tags.filter((t) => !autoTagIds.has(t.id))
      : tags

  // Get unique categories
  const categoryOptions = [...new Set(tags.filter(t => t.category).map(t => t.category))].sort()

  const groupedTags = filteredBySource.reduce<Record<string, TagInfo[]>>((acc, tag) => {
    const cat = tag.category || 'general'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(tag)
    return acc
  }, {})

  const autoCount = tags.filter((t) => autoTagIds.has(t.id)).length
  const manualCount = tags.length - autoCount

  // Auto-expand categories with content
  useEffect(() => {
    const cats = Object.keys(groupedTags)
    if (cats.length > 0) {
      setExpandedCategories((prev) => {
        const next = { ...prev }
        for (const cat of cats) {
          if (next[cat] === undefined) next[cat] = true
        }
        return next
      })
    }
  }, [filteredBySource.length])

  return (
    <div className="p-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">{t('tags.title')}</h1>
          <p className="text-sm text-gray-500 mt-1">
            {t('tags.assetCount', { count: tags.length })}
            <span className="mx-2">·</span>
            <span className="text-amber-400">{autoCount} auto</span>
            <span className="mx-1">·</span>
            <span className="text-indigo-400">{manualCount} manual</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleAutoGenerate}
            disabled={autoGenerating}
            className="flex items-center gap-2 px-3 py-2 bg-amber-600/20 hover:bg-amber-600/30 text-amber-400 rounded-lg text-sm transition-colors disabled:opacity-50"
          >
            {autoGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
            {autoGenerating ? t('tags.autoGenerating') : t('tags.autoGenerate')}
          </button>
          <button
            onClick={() => { resetForm(); setShowCreate(true) }}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm transition-colors"
          >
            <Plus className="w-4 h-4" />
            {t('tags.newTag')}
          </button>
        </div>
      </div>

      {/* Status messages */}
      {autoGenResult && (
        <div className="mb-4 px-4 py-2 bg-green-900/30 border border-green-800/50 rounded-lg text-sm text-green-400 flex items-center gap-2">
          <CheckCircle className="w-4 h-4" />
          {autoGenResult}
        </div>
      )}
      {batchDeleteResult && (
        <div className="mb-4 px-4 py-2 bg-red-900/30 border border-red-800/50 rounded-lg text-sm text-red-400 flex items-center gap-2">
          <CheckCircle className="w-4 h-4" />
          {batchDeleteResult}
        </div>
      )}

      {/* Create/Edit form */}
      {(showCreate || editingId) && (
        <div className="mb-6 bg-gray-900 rounded-lg p-4 border border-gray-800">
          <h3 className="text-sm font-medium text-gray-200 mb-3">
            {showCreate ? t('tags.newTag') : t('tags.edit')}
          </h3>
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <label className="block text-xs text-gray-500 mb-1">{t('tags.name')}</label>
              <input
                type="text"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">{t('tags.category')}</label>
              <select
                value={formCategory}
                onChange={(e) => setFormCategory(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500"
              >
                {categoryOptions.map((cat) => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">{t('tags.color')}</label>
              <input
                type="color"
                value={formColor}
                onChange={(e) => setFormColor(e.target.value)}
                className="w-10 h-9 bg-gray-800 border border-gray-700 rounded-lg cursor-pointer"
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={showCreate ? handleCreate : () => editingId && handleUpdate(editingId)}
                className="px-3 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm transition-colors"
              >
                {showCreate ? t('tags.create') : t('tags.save')}
              </button>
              <button
                onClick={() => { setShowCreate(false); setEditingId(null); resetForm() }}
                className="p-2 text-gray-400 hover:text-gray-200 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Filters + Batch bar */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('tags.search')}
            className="w-full bg-gray-900 border border-gray-800 rounded-lg pl-9 pr-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500"
          />
        </div>
        <select
          value={sourceFilter}
          onChange={(e) => { setSourceFilter(e.target.value as 'all' | 'auto' | 'manual'); setSelectedTagIds(new Set()) }}
          className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-indigo-500"
        >
          <option value="all">{t('tags.filterAll')} ({tags.length})</option>
          <option value="auto">{t('tags.filterAuto')} ({autoCount})</option>
          <option value="manual">{t('tags.filterManual')} ({manualCount})</option>
        </select>
        <select
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value)}
          className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-indigo-500"
        >
          <option value="">{t('tags.filterByCategory')}</option>
          {categoryOptions.map((cat) => (
            <option key={cat} value={cat}>{cat}</option>
          ))}
        </select>
      </div>

      {/* Batch action bar */}
      <div className="flex items-center gap-2 mb-4 px-3 py-2 bg-gray-900 rounded-lg border border-gray-800">
        <button
          onClick={selectAllAuto}
          className="text-xs px-2.5 py-1 rounded bg-amber-600/20 text-amber-400 hover:bg-amber-600/30 transition-colors"
        >
          {t('tags.selectAuto')}
        </button>
        <button
          onClick={deselectAll}
          className="text-xs px-2.5 py-1 rounded bg-gray-800 text-gray-400 hover:bg-gray-700 transition-colors"
        >
          {t('tags.deselectAll')}
        </button>
        <div className="flex-1" />
        {selectedTagIds.size > 0 && (
          <>
            <span className="text-xs text-gray-500">
              {t('tags.selectedCount', { count: selectedTagIds.size })}
            </span>
            <button
              onClick={handleBatchDelete}
              disabled={batchDeleting}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg text-xs transition-colors disabled:opacity-50"
            >
              {batchDeleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
              {t('tags.deleteSelected')}
            </button>
          </>
        )}
      </div>

      {/* Tag list */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
        </div>
      ) : Object.keys(groupedTags).length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-gray-500">
          <Tag className="w-12 h-12 mb-3 text-gray-700" />
          <p className="text-gray-400 text-lg mb-1">
            {sourceFilter === 'auto' ? t('tags.noAutoTags') : sourceFilter === 'manual' ? t('tags.noManualTags') : t('tags.noTags')}
          </p>
          <p className="text-sm text-gray-600">{t('tags.emptyHint')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {Object.entries(groupedTags).map(([category, catTags]) => {
            const isExpanded = expandedCategories[category]
            const color = CATEGORY_COLORS[category] || '#6b7280'
            const allSelected = catTags.every((t) => selectedTagIds.has(t.id))
            return (
              <div key={category} className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
                {/* Category header */}
                <button
                  onClick={() => toggleCategory(category)}
                  className="w-full flex items-center gap-2 px-4 py-3 text-sm font-medium text-gray-300 hover:text-white hover:bg-gray-800/50 transition-colors"
                >
                  {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                  <span className="uppercase tracking-wider">{category}</span>
                  <span className="text-xs text-gray-600">({catTags.length})</span>
                  <div className="flex-1" />
                  <label
                    onClick={(e) => e.stopPropagation()}
                    className="flex items-center gap-1.5 cursor-pointer mr-2"
                  >
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={() => selectAllInCategory(category, catTags)}
                      className="w-3.5 h-3.5 rounded bg-gray-800 border-gray-700 text-indigo-600 focus:ring-indigo-600"
                    />
                    <span className="text-xs text-gray-500">{t('tags.selectAll')}</span>
                  </label>
                </button>
                {/* Tags */}
                {isExpanded && (
                  <div className="px-4 pb-4">
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-1.5">
                      {catTags.map((tag) => {
                        const isAuto = autoTagIds.has(tag.id)
                        const isSelected = selectedTagIds.has(tag.id)
                        return (
                          <div
                            key={tag.id}
                            className={'group flex items-center gap-1.5 px-2 py-1.5 rounded-lg border text-sm transition-all cursor-pointer ' + (isSelected ? 'bg-indigo-600/15 border-indigo-600/40' : 'bg-gray-800/40 border-gray-700/40 hover:border-gray-600/60')}
                            onClick={() => navigateToBrowse(tag.name)}
                          >
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={(e) => { e.stopPropagation(); toggleTagSelection(tag.id) }}
                              onClick={(e) => e.stopPropagation()}
                              className="w-3.5 h-3.5 rounded bg-gray-800 border-gray-700 text-indigo-600 focus:ring-indigo-600 flex-shrink-0"
                            />
                            <div
                              className="w-2 h-2 rounded-full flex-shrink-0"
                              style={{ backgroundColor: tag.color || color }}
                            />
                            <span className="text-xs text-gray-200 truncate flex-1">{tag.name}</span>
                            <span className="text-xs text-gray-600 flex-shrink-0">{tag.usage_count}</span>
                            {isAuto && (
                              <span className="text-[10px] text-amber-500/70 flex-shrink-0" title={t('tags.generated')}>auto</span>
                            )}
                            <div className="hidden group-hover:flex items-center gap-0.5 ml-1 flex-shrink-0">
                              <button
                                onClick={(e) => { e.stopPropagation(); navigateToBrowse(tag.name) }}
                                className="p-0.5 text-gray-500 hover:text-indigo-400 transition-colors"
                                title={t('tags.browseTag')}
                              >
                                <ExternalLink className="w-2.5 h-2.5" />
                              </button>
                              <button
                                onClick={(e) => { e.stopPropagation(); startEdit(tag) }}
                                className="p-0.5 text-gray-500 hover:text-indigo-400 transition-colors"
                              >
                                <Edit2 className="w-2.5 h-2.5" />
                              </button>
                              <button
                                onClick={(e) => { e.stopPropagation(); handleDelete(tag) }}
                                className="p-0.5 text-gray-500 hover:text-red-400 transition-colors"
                              >
                                <Trash2 className="w-2.5 h-2.5" />
                              </button>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
