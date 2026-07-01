import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Folder, FolderOpen, ChevronRight, ChevronDown, Film, Loader2, ArrowUpDown, Download } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api, type Asset } from '../api/client'
import { useStore } from '../stores/app'
import { VideoCard } from '../components/VideoCard'
import { BatchToolbar } from '../components/BatchToolbar'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useMarqueeSelection } from '../hooks/useMarqueeSelection'

// ═══════════════════════════════════════════════════════════════════════
// Performance config — all tunable
// ═══════════════════════════════════════════════════════════════════════
const PAGE_SIZE = 80          // 每批加载量 — 滚动到底部自动加载下一页。可在此调整
const OVERSCAN = 4            // 视口外缓冲区行数 (≈ 4×6×2 = ≤48 张卡片)
const GRID_ROW_HEIGHT = 204   // 每行像素高度 (匹配 VideoCard 高度)
const LOAD_MORE_THRESHOLD = 600  // 距离底部多少像素时触发加载

// 每行卡片数: 根据视口宽度自适应
const COL_BREAKPOINTS = [
  [1536, 6], [1280, 5], [1024, 4], [768, 3], [0, 2],
] as const
// ═══════════════════════════════════════════════════════════════════════

// ── Helper: 分割数组为行 ──
function chunkArr<T>(arr: T[], size: number): T[][] {
  const r: T[][] = []
  for (let i = 0; i < arr.length; i += size) r.push(arr.slice(i, i + size))
  return r
}

// ── 骨架屏 ──
function SkeletonCard() {
  return (
    <div className="bg-gray-900 rounded-lg overflow-hidden border border-gray-800 animate-pulse">
      <div className="aspect-video bg-gray-800 relative" style={{ minHeight: 112 }}>
        <div className="absolute inset-0 bg-gray-800/50" />
      </div>
      <div className="p-3 space-y-2">
        <div className="h-3 bg-gray-800 rounded w-3/4" />
        <div className="h-2 bg-gray-800 rounded w-1/2" />
      </div>
    </div>
  )
}

// ── 虚拟滚动行类型 ──
type VirtualRow =
  | { type: 'grid'; key: string; assets: Asset[] }
  | { type: 'loading'; key: string }

// ── 树节点接口 ──
interface TreeNode {
  name: string
  depth: number
  children?: TreeNode[]
}

interface FlatItem {
  name: string
  depth: number
  path: string
  hasChildren: boolean
}

function formatCount(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M"
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K"
  return String(n)
}



export function DirectoryView() {
  const [assets, setAssets] = useState<Asset[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [hasMore, setHasMore] = useState(true)
  const [initLoading, setInitLoading] = useState(false)
  const [moreLoading, setMoreLoading] = useState(false)
 const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')
 const [error, setError] = useState<string | null>(null)
  const [selectedPath, setSelectedPath] = useState('')
  const [subdirs, setSubdirs] = useState<string[]>([])
  const [tree, setTree] = useState<TreeNode[]>([])
  const [treeLoading, setTreeLoading] = useState(true)
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set())
  const selectedLibraryId = useStore((s) => s.selectedLibraryId)

  // ── Refs ──
  const scrollRef = useRef<HTMLDivElement>(null)
  const contRef = useRef<HTMLDivElement>(null)

  useMarqueeSelection(scrollRef)
  const [contW, setContW] = useState(1200)

  // ── 自适应列数 ──
  // 调整每行卡片数：修改 COL_BREAKPOINTS 数组
  const cols = useMemo(() => {
    for (const [minW, c] of COL_BREAKPOINTS) {
      if (contW >= minW) return c
    }
    return 2
  }, [contW])

  // ── ResizeObserver 监听容器宽度变化 ──
  useEffect(() => {
    if (!contRef.current) return
    const ro = new ResizeObserver((es) => {
      for (const e of es) setContW(e.contentRect.width)
    })
    ro.observe(contRef.current)
    return () => ro.disconnect()
  }, [])

  // ── 加载目录树 ──
  const loadTree = useCallback(async () => {
    setTreeLoading(true)
    try {
      const data = await api.directoryTree(selectedLibraryId || undefined)
      setTree(data as TreeNode[])
   } catch (e) {
     console.error('Failed to load directory tree:', e)
      setError('无法加载目录树: ' + ((e as any).message || e))
   } finally {
      setTreeLoading(false)
    }
  }, [selectedLibraryId])

  useEffect(() => { loadTree() }, [loadTree])

  // ── 分页加载某路径的视频 ──
  const fetchPathPage = useCallback(
    async (path: string, p: number, append: boolean) => {
      if (append) setMoreLoading(true)
      else setInitLoading(true)
      setError(null)
      try {
        const r = await api.browsePathPaginated(
          path,
          selectedLibraryId || undefined,
          p,
          PAGE_SIZE,
          'media_date',
          sortOrder,
        )
       const items = r.items || []
        const byId: Record<string, Asset> = {}
        for (const item of items) byId[item.id] = item
        useStore.setState((s) => ({ assetsById: { ...s.assetsById, ...byId } }))
       if (append) {
          setAssets((prev) => [...prev, ...items])
        } else {
          setAssets(items)
        }
        setTotal(r.total)
        setHasMore(items.length >= PAGE_SIZE && p * PAGE_SIZE < r.total)
        setPage(p)
      } catch (e: any) {
        setError(e?.message || '加载失败')
      } finally {
        setInitLoading(false)
        setMoreLoading(false)
      }
    },
    [selectedLibraryId, sortOrder],
  )

  // ── 点击文件夹 ──
  const handleFolderClick = useCallback(
    async (path: string) => {
      setSelectedPath(path)
      setSubdirs([])
      setAssets([])
      setPage(1)
      setHasMore(true)
      setError(null)
      try {
        const [dirData] = await Promise.all([
          api.browsePathDirectories(path, selectedLibraryId || undefined),
          fetchPathPage(path, 1, false),
        ])
        setSubdirs(dirData)
     } catch (e) {
       console.error('Failed to load path:', e)
        setError('无法加载文件夹: ' + ((e as any).message || e))
     }
    },
    [selectedLibraryId, fetchPathPage],
  )

  // ── 加载更多（无限滚动）──
  const loadNext = useCallback(() => {
    if (moreLoading || !hasMore || initLoading || !selectedPath) return
    fetchPathPage(selectedPath, page + 1, true).catch((e) => {
      setError('加载下一页失败: ' + ((e as any).message || e))
    })
  }, [page, moreLoading, hasMore, initLoading, selectedPath, fetchPathPage])

  // ── 滚动检测 ──
  const handleScroll = useCallback(() => {
    if (!scrollRef.current || !hasMore || moreLoading || initLoading) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    if (scrollHeight - scrollTop - clientHeight < LOAD_MORE_THRESHOLD) {
      loadNext()
    }
  }, [hasMore, moreLoading, initLoading, loadNext])

  // ── 排序切换 ──
  const toggleSort = useCallback(() => {
    setSortOrder((p) => (p === 'asc' ? 'desc' : 'asc'))
  }, [])

  // 排序变化时重新加载
  useEffect(() => {
    if (selectedPath) {
      setAssets([])
      setPage(1)
      setHasMore(true)
      fetchPathPage(selectedPath, 1, false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sortOrder])

  // ── 目录树展开/折叠 ──
  const toggleExpand = (path: string) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const buildFlatList = (nodes: TreeNode[], basePath = ''): FlatItem[] => {
    const result: FlatItem[] = []
    for (const node of nodes) {
      const fullPath = basePath ? `${basePath}/${node.name}` : node.name
      const hasChildren = (node.children?.length ?? 0) > 0
      result.push({ name: node.name, depth: node.depth, path: fullPath, hasChildren })
      if (expandedPaths.has(fullPath) && node.children) {
        result.push(...buildFlatList(node.children, fullPath))
      }
    }
    return result
  }

  const flatList = buildFlatList(tree)

  // ── 面包屑 ──
  const breadcrumbParts = selectedPath ? selectedPath.split('/').filter(Boolean) : []

  // ── 构建虚拟滚动行 ──
  // 控制同时渲染的卡片数量：每行 cols 个卡片，virtualizer 最多渲染 (视口行数 + 2*OVERSCAN) 行
  const virtualRows = useMemo((): VirtualRow[] => {
    if (!assets.length) return []
    const rs: VirtualRow[] = []
    for (const [i, ch] of chunkArr(assets, cols).entries()) {
      rs.push({ type: 'grid', key: 'g-' + i, assets: ch })
    }
    if (hasMore) {
      rs.push({ type: 'loading', key: 'lm' })
    }
    return rs
  }, [assets, cols, hasMore])

  const estimateSize = useCallback(() => GRID_ROW_HEIGHT, [])

  // ═══ @tanstack/react-virtual 虚拟滚动器 ═══
  // 核心：只挂载 (视口行数 + 2*OVERSCAN) 行到 DOM，其余用 padding-top 占位
  // 10000 条数据时，视口最多显示 ~5 行 + 2*4 行缓冲区 = 13 行 × 6 列 = 78 张卡片 < 100 ✅
  const rowVirtualizer = useVirtualizer({
    count: virtualRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize,
    overscan: OVERSCAN,
    getItemKey: (i: number) => virtualRows[i]?.key ?? String(i),
    measureElement: (el) => el.getBoundingClientRect().height,
  })

  const empty = selectedPath && !initLoading && !error && assets.length === 0 && total === 0
  const showSkeleton = initLoading && !error

  return (
    <div className="flex h-full">
      {/* ═══ 左侧目录树 ═══ */}
      <div className="w-72 bg-gray-900/50 border-r border-gray-800 overflow-y-auto shrink-0">
        <div className="p-4 border-b border-gray-800">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-2">
            <Folder className="w-4 h-4" />
            <span>文件夹</span>
          </h2>
        </div>
       {treeLoading ? (
          <div className="py-4 space-y-0.5">
            {Array.from({ length: 8 }, (_, i) => (
              <div key={i} className="flex items-center gap-2 px-4 py-2 animate-pulse">
                <div className="w-4 h-4 bg-gray-800 rounded shrink-0" />
                <div className="h-3 bg-gray-800 rounded w-3/4" />
              </div>
            ))}
          </div>
       ) : flatList.length === 0 ? (
          <div className="p-4 text-sm text-gray-500 text-center py-12">
            <Folder className="w-8 h-8 mx-auto mb-2 text-gray-500" />
            <p>暂无文件夹</p>
          </div>
        ) : (
          <div className="py-2">
            {flatList.map((item, idx) => (
              <div
                key={`${item.path}-${idx}`}
                className="flex items-center group"
                style={{ paddingLeft: `${item.depth * 20 + 12}px` }}
              >
                {item.hasChildren ? (
                  <button
                    onClick={() => toggleExpand(item.path)}
                    className="p-0.5 hover:bg-gray-800 rounded transition-colors shrink-0"
                  >
                    {expandedPaths.has(item.path) ? (
                      <ChevronDown className="w-3.5 h-3.5 text-gray-500" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5 text-gray-500" />
                    )}
                  </button>
                ) : (
                  <div className="w-4 shrink-0" />
                )}
                <button
                  onClick={() => handleFolderClick(item.path)}
                  className={`flex items-center gap-2 px-2 py-1.5 rounded text-sm transition-colors flex-1 text-left ${
                    selectedPath === item.path
                      ? 'bg-indigo-600/20 text-indigo-300'
                      : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                  }`}
                >
                  {selectedPath === item.path ? (
                    <FolderOpen className="w-4 h-4 shrink-0 text-indigo-400" />
                  ) : (
                    <Folder className="w-4 h-4 shrink-0 text-gray-500" />
                  )}
                  <span className="truncate">{item.name}</span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ═══ 右侧内容区 ═══ */}
      <div
        ref={contRef}
        className="flex-1 flex flex-col min-w-0 overflow-hidden max-w-7xl mx-auto w-full"
        style={{ contain: 'layout size style' }}
      >
        {!selectedPath && !treeLoading && (
          <div className="flex flex-col items-center justify-center flex-1 text-gray-500">
            <Folder className="w-16 h-16 mb-4 text-gray-500" />
            <p className="text-lg text-gray-400 mb-1">请选择一个文件夹</p>
            <p className="text-sm text-gray-500">从左侧目录树选择要浏览的文件夹</p>
          </div>
        )}

        {selectedPath && (
          <>
            {/* ── 面包屑导航 ── */}
            {breadcrumbParts.length > 0 && (
              <div className="flex items-center gap-1.5 px-4 pt-4 pb-2 text-sm text-gray-400 flex-wrap shrink-0">
                 <button onClick={() => handleFolderClick('')} className="hover:text-gray-200 transition-colors">
                  根目录
                </button>
                {breadcrumbParts.map((part, idx) => (
                  <span key={idx} className="flex items-center gap-1.5">
                    <ChevronRight className="w-3.5 h-3.5 text-gray-500" />
                    <span className={idx < breadcrumbParts.length - 1 ? 'text-gray-500' : 'text-gray-200 font-medium'}>
                      {part}
                    </span>
                  </span>
                ))}
              </div>
            )}

            {/* ── 排序栏 ── */}
            <div className="flex items-center justify-between px-4 py-2 shrink-0">
              <div className="flex items-center gap-3">
                <button
                  onClick={toggleSort}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border border-gray-700 text-gray-400 hover:text-gray-200 hover:border-gray-600 transition-colors"
                >
                  <ArrowUpDown className="w-4 h-4" />
                  <span className="text-xs">{sortOrder === 'asc' ? '最早' : '最新'}</span>
                </button>
                {!initLoading && (
                  <span className="text-xs text-gray-500">
                    共 {formatCount(total)} 个视频 — 已加载 {formatCount(assets.length)}
                  </span>
                )}
              </div>
            </div>

            {/* ── 子目录按钮 ── */}
            {subdirs.length > 0 && (
              <div className="px-4 pb-3 shrink-0">
                 <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                  {subdirs.map((dir) => (
                    <button
                      key={dir}
                      onClick={() => handleFolderClick(
                        selectedPath ? `${selectedPath}/${dir}` : dir
                      )}
                       className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-900 border border-gray-800 hover:border-gray-600 text-gray-400 hover:text-gray-200 transition-all text-sm"
                    >
                      <Folder className="w-4 h-4 shrink-0 text-gray-500" />
                      <span className="truncate">{dir}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* ── 骨架屏加载 ── */}
            {showSkeleton && (
              <div className="flex-1 overflow-hidden px-4 pb-4">
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-4">
                  {Array.from({ length: cols * 3 }).map((_, i) => (
                    <SkeletonCard key={i} />
                  ))}
                </div>
              </div>
            )}

            {/* ── 错误状态 ── */}
            {error && !initLoading && (
              <div className="flex flex-col items-center justify-center flex-1 text-gray-400">
                <p className="text-sm mb-3 text-red-400">{error}</p>
                <button
                  onClick={() => fetchPathPage(selectedPath, 1, false)}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm"
                >
                  重试
                </button>
              </div>
            )}

          <BatchToolbar currentAssets={assets} onRefresh={() => { setAssets([]); setPage(1); setHasMore(true); fetchPathPage(selectedPath, 1, false) }} />
            {/* ═══ 虚拟滚动视频列表（核心性能区域）═══
             *
             * 性能保证：
             * • Virtualizer 始终挂载 ≤100 个 DOM 节点（视口 + 缓冲区）
             * • `contain: 'strict'` 隔离布局/绘制到本容器
             * • 固定行高 — 滚动时无布局重排
             * • <img loading="lazy" decoding="async"> 阻止离屏下载
             * • 无 filter:drop-shadow() 或大面积 box-shadow
             */}
            {!showSkeleton && !error && assets.length > 0 && (
              <div
                ref={scrollRef}
                onScroll={handleScroll}
                className="max-w-none flex-1 overflow-y-auto px-4"
                style={{ contain: 'strict' }}
              >
                <div
                  style={{
                    height: rowVirtualizer.getTotalSize() + 'px',
                    width: '100%',
                    position: 'relative',
                  }}
                >
                  {rowVirtualizer.getVirtualItems().map((virtualItem) => {
                    const row = virtualRows[virtualItem.index]
                    if (!row) return null
                    return (
                      <div
                        key={virtualItem.key}
                        data-index={virtualItem.index}
                        ref={rowVirtualizer.measureElement}
                        style={{
                          position: 'absolute',
                          top: 0,
                          left: 0,
                          width: '100%',
                          transform: `translateY(${virtualItem.start}px)`,
                          willChange: 'transform',
                        }}
                      >
                        {row.type === 'grid' && (
                          <div
                            style={{
                              display: 'grid',
                              gridTemplateColumns: `repeat(${cols}, 1fr)`,
                              gap: '1rem',
                            }}
                          >
                            {row.assets.map((a) => (
                              <VideoCard key={a.id} assetId={a.id} />
                            ))}
                          </div>
                        )}
                        {row.type === 'loading' && (
                          <div className="flex items-center justify-center" style={{ height: '60px' }}>
                            {moreLoading ? (
                              <>
                                <Loader2 className="w-5 h-5 animate-spin text-indigo-400 mr-2" />
                                <span className="text-sm text-gray-400">加载中...</span>
                              </>
                            ) : (
                              <span className="text-sm text-gray-400">滚动加载更多...</span>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* ── 空文件夹 ── */}
            {empty && (
              <div className="flex flex-col items-center justify-center flex-1 text-gray-500 px-4 pb-4">
                <Film className="w-12 h-12 mb-3 text-gray-500" />
                <p className="text-gray-400">此文件夹中没有视频</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}


