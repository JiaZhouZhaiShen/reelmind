import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SearchBar } from '../components/SearchBar'
import { BatchToolbar } from '../components/BatchToolbar'
import { Archive, RotateCcw, Filter, X, ArrowUpDown, Monitor, Smartphone, Square } from 'lucide-react'
import { useLibraryStore } from '../stores/library'
import { useAssetStore } from '../stores/asset'
import { useGridStore } from '../stores/grid'
import { AI_FILTER_DEFS, StatusFilter } from './AssetGridUtils'
import type { Asset } from '../api/client'

interface AssetGridFiltersProps {
  display: Asset[]
  heading?: string
  countText?: string
}

export function AssetGridFilters({ display, heading, countText }: AssetGridFiltersProps) {
  const [showFilter, setShowFilter] = useState(false)
  const filterTags = useGridStore((s) => s.gridFilterTags)
  const availTags = useGridStore((s) => s.gridAvailTags)
  const toggleGridTag = useGridStore((s) => s.toggleGridTag)
  const aiFilter = useGridStore((s) => s.gridAiFilter)
  const setGridAiFilter = useGridStore((s) => s.setGridAiFilter)
  const orientationFilter = useGridStore((s) => s.gridOrientationFilter)
  const setGridOrientationFilter = useGridStore((s) => s.setGridOrientationFilter)
  const sortOrder = useGridStore((s) => s.gridSortOrder)
  const toggleGridSort = useGridStore((s) => s.toggleGridSort)
  const showArchived = useAssetStore((s) => s.showArchived)
  const toggleShowArchived = useAssetStore((s) => s.toggleShowArchived)
  const { t } = useTranslation()

  const toggleTag = (n: string) => toggleGridTag(n)

 return (
   <>
      <div className="relative flex items-center shrink-0 px-4 pt-3 pb-2 border-b border-gray-800">
        <div className="flex items-center gap-1.5">
          <div className="flex flex-col shrink-0 mr-3">
          {heading && (
            <span className="text-base font-semibold text-white">{heading}</span>
          )}
            {countText && (
              <p className="text-sm text-gray-500 leading-tight">{countText}</p>
            )}
          </div>
        </div>
        <div className="absolute left-1/2 -translate-x-1/2 w-80 max-w-full">
          <SearchBar compact />
        </div>
        <div className="flex items-center gap-2 ml-auto">
          <div className="relative shrink-0">
            <button onClick={() => setShowFilter(!showFilter)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm border transition-colors ${filterTags.length ? 'bg-indigo-600/20 text-indigo-400 border-indigo-700/50' : 'text-gray-400 border-gray-700 hover:text-gray-200 hover:border-gray-600'}`}>
              <Filter className="w-4 h-4" />
              <span>{filterTags.length ? filterTags.length + ' ' : ''}{t('common.tag')}</span>
            </button>
            {showFilter && <div className="fixed inset-0 z-10" onClick={() => setShowFilter(false)} />}
            {showFilter && (
              <div className="absolute right-0 top-full mt-1 z-20 w-72 bg-gray-900 border border-gray-700 rounded-lg shadow-sm max-h-80 overflow-y-auto">
                <div className="p-3 border-b border-gray-800">
                  <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">{t('filter.tags')}</p>
                </div>
                <div className="p-2 space-y-0.5">
                  {!availTags.length && <p className="px-3 py-2 text-sm text-gray-500">{t('common.noTags')}</p>}
                  {availTags.map((tag) => {
                    const sel = filterTags.includes(tag.name)
                    return (
                      <button key={tag.id} onClick={() => toggleTag(tag.name)}
                        className={`w-full flex items-center gap-2 px-3 py-1.5 rounded text-sm transition-colors ${sel ? 'bg-indigo-600/20 text-indigo-300' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'}`}>
                        <div className={`w-1.5 h-1.5 rounded-full ${sel ? 'bg-indigo-400' : 'bg-gray-600'}`} />
                        <span className="flex-1 text-left">{tag.name}</span>
                        <span className="text-xs text-gray-600">{tag.category}</span>
                        {sel && <X className="w-3 h-3 text-indigo-400" />}
                      </button>
                    )
                  })}
                </div>
                {filterTags.length > 0 && (
                  <div className="p-2 border-t border-gray-800">
                    <button onClick={() => { useGridStore.getState().resetGridState(); setShowFilter(false) }}
                      className="w-full px-3 py-1.5 text-xs text-gray-500 hover:text-gray-400 transition-colors rounded">{t('common.clearFilter')}</button>
                  </div>
                )}
              </div>
            )}
          </div>
          <button onClick={toggleShowArchived}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm border transition-colors ${showArchived ? 'bg-indigo-600/20 text-indigo-400 border-indigo-700/50' : 'text-gray-400 border-gray-700 hover:text-gray-200 hover:border-gray-600'}`}>
            {showArchived ? <RotateCcw className="w-4 h-4" /> : <Archive className="w-4 h-4" />}
            <span>{showArchived ? t('common.activeVideos') : t('common.archived')}</span>
          </button>
        </div>
      </div>
      <div className="flex items-center gap-1.5 px-4 mb-5">
        <button onClick={() => setGridOrientationFilter('all')}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${orientationFilter === 'all' ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-500/30' : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200'}`}
          title={t('common.all')}><Square className="w-3.5 h-3.5" /><span>{t('common.all')}</span></button>
        <div className="w-px h-5 bg-gray-700 mx-1" />
      {AI_FILTER_DEFS.map((f: { key: StatusFilter; labelKey: string; icon: React.ComponentType<{className?: string}> }) => {
          const active = aiFilter === f.key
          return (
            <button key={f.key} onClick={() => setGridAiFilter(aiFilter === f.key ? 'all' : f.key)}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${active ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-500/30' : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200'}`}>
              <f.icon className="w-3.5 h-3.5" />
              <span>{t(f.labelKey)}</span>
            </button>
          )
        })}
        <button onClick={() => setGridOrientationFilter('landscape')}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${orientationFilter === 'landscape' ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-500/30' : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200'}`}
          title={t('common.landscape')}><Monitor className="w-3.5 h-3.5" /><span>{t('common.landscape')}</span></button>
        <button onClick={() => setGridOrientationFilter('portrait')}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${orientationFilter === 'portrait' ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-500/30' : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200'}`}
          title={t('common.portrait')}><Smartphone className="w-3.5 h-3.5" /><span>{t('common.portrait')}</span></button>
        <button onClick={() => setGridOrientationFilter('square')}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${orientationFilter === 'square' ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-500/30' : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200'}`}
          title={t('common.square')}><Square className="w-3.5 h-3.5" /><span>{t('common.square')}</span></button>
        <div className="w-px h-5 bg-gray-700 mx-1" />
        <button onClick={() => toggleGridSort()}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${sortOrder === 'desc' ? 'bg-indigo-600/20 text-indigo-400 shadow-sm shadow-indigo-500/30' : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200'}`}
          title={t('common.sort')}>
          <ArrowUpDown className="w-3.5 h-3.5" />
          <span>{sortOrder === 'desc' ? t('common.sortNewest') : t('common.sortOldest')}</span>
        </button>
      </div>
      <BatchToolbar currentAssets={display} onRefresh={() => { const s = useLibraryStore.getState(); const g = useGridStore.getState(); const a = useAssetStore.getState(); g.fetchGridAssets(s.selectedLibraryId, g.gridSortOrder, a.showFavorites, g.gridAiFilter, g.gridOrientationFilter, g.gridPage, false) }} />
      {filterTags.length > 0 && (
        <div className="flex items-center gap-2 mb-4 px-4 flex-wrap">
          {filterTags.map((n: string) => (
            <span key={n} className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-full bg-indigo-900/30 text-indigo-300 border border-indigo-800/30">
              {n}
              <button onClick={() => toggleTag(n)} className="hover:text-white ml-0.5"><X className="w-3 h-3" /></button>
            </span>
          ))}
        </div>
      )}
    </>
  )
}
