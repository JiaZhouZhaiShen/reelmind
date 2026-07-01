import { Download } from 'lucide-react'
import { useStore } from '../stores/app'
import { api } from '../api/client'

interface BatchToolbarProps {
  /** 当前页面的资产列表 — 用于"全选当前页"判断 */
  currentAssets: { id: string }[]
  /** 批量操作完成后的刷新回调 */
  onRefresh?: () => void
}

export function BatchToolbar({ currentAssets, onRefresh }: BatchToolbarProps) {
  const selectedAssetIds = useStore((s) => s.selectedAssetIds)
  const clearSelection = useStore((s) => s.clearSelection)
  const selectAllAssets = useStore((s) => s.selectAllAssets)

  if (selectedAssetIds.length === 0) return null

  const allSelected = selectedAssetIds.length >= currentAssets.length && currentAssets.length > 0

  return (
    <div className="flex items-center gap-3 mb-4 px-4 py-3 bg-indigo-900/20 border border-indigo-800/30 rounded-lg">
      <span className="text-sm text-indigo-300 font-medium">
        {selectedAssetIds.length} 已选
        {allSelected ? (
          <button onClick={() => clearSelection()} className="ml-2 text-xs font-medium text-indigo-400 hover:text-indigo-300 underline">
            取消全选
          </button>
        ) : (
          <button onClick={() => selectAllAssets(currentAssets.map((a) => a.id))} className="ml-2 text-xs font-medium text-indigo-400 hover:text-indigo-300 underline">
            全选当前页 ({currentAssets.length})
          </button>
        )}
      </span>
      <div className="flex items-center gap-2 ml-4">
        <button
          onClick={async () => {
            await api.batchUpdateAssets(selectedAssetIds, { is_favorite: true })
            clearSelection()
            onRefresh?.()
          }}
          className="px-3 py-1.5 text-xs font-medium rounded-lg bg-indigo-600/20 text-indigo-400 hover:bg-indigo-600/30 border border-indigo-700/50"
        >
          收藏
        </button>
        <button
          onClick={async () => {
            await api.batchUpdateAssets(selectedAssetIds, { is_favorite: false })
            clearSelection()
            onRefresh?.()
          }}
          className="px-3 py-1.5 text-xs font-medium rounded-lg bg-indigo-600/20 text-indigo-400 hover:bg-indigo-600/30 border border-indigo-700/50"
        >
          取消收藏
        </button>
        <button
          onClick={() => api.downloadSelectedAssets(selectedAssetIds)}
          className="px-3 py-1.5 text-xs font-medium rounded-lg bg-indigo-600/20 text-indigo-400 hover:bg-indigo-600/30 border border-indigo-700/50 flex items-center gap-1"
        >
          <Download className="w-3.5 h-3.5" />
          下载
        </button>
        <button
          onClick={async () => {
            if (!confirm('确定删除?')) return
            await api.batchDeleteAssets(selectedAssetIds)
            clearSelection()
            onRefresh?.()
          }}
          className="px-3 py-1.5 text-xs font-medium rounded-lg bg-red-600/20 text-red-400 hover:bg-red-600/30 border border-red-700/50"
        >
          删除
        </button>
        <button
          onClick={async () => {
            await api.batchUpdateAssets(selectedAssetIds, { is_archived: false })
            clearSelection()
            onRefresh?.()
          }}
          className="px-3 py-1.5 text-xs font-medium rounded-lg bg-indigo-600/20 text-indigo-400 hover:bg-indigo-600/30 border border-indigo-700/50"
        >
          取消归档
        </button>
        <button
          onClick={async () => {
            await api.batchUpdateAssets(selectedAssetIds, { is_archived: true })
            clearSelection()
            onRefresh?.()
          }}
          className="px-3 py-1.5 text-xs font-medium rounded-lg bg-indigo-600/20 text-indigo-400 hover:bg-indigo-600/30 border border-indigo-700/50"
        >
          归档
        </button>
        <button
         onClick={() => clearSelection()}
         className="px-3 py-1.5 text-xs font-medium rounded-lg text-gray-400 hover:text-gray-200 border border-gray-700 hover:border-gray-600"
       >
         清除
       </button>
        <button
          onClick={async () => {
            if (!confirm(`确定重置 ${selectedAssetIds.length} 个视频的AI处理数据？`)) return
            await api.batchResetAssetAI(selectedAssetIds)
            clearSelection()
            onRefresh?.()
          }}
          className="px-3 py-1.5 text-xs font-medium rounded-lg bg-indigo-600/20 text-indigo-400 hover:bg-indigo-600/30 border border-indigo-700/50"
        >
          重置AI
        </button>
      </div>
    </div>
  )
}
