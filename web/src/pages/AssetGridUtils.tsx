import { Image, Tag, FileText, Brain, AudioLines, Users } from 'lucide-react'
import type { Asset } from '../api/client'
// ═══════════════════════════════════════════════════════════════════════
// Performance config — all tunable
 // ═══════════════════════════════════════════════════════════════════════
export const GRID_ROW_HEIGHT = 204   // px per grid row
export const HEADER_ROW_HEIGHT = 40  // px per date header row
export const LOAD_MORE_THRESHOLD = 800  // px from bottom to trigger next page
export const BATCH_SIZE = 5              // pages to load in parallel when navigating to a year
// Max DOM nodes ≈ OVERSCAN × 2 × cols + viewport rows × cols
// With OVERSCAN=4, cols=6 → 4×2×6 + ~5×6 ≈ 78 cards < 100 ✅
export const COL_BREAKPOINTS = [
  [1536, 6], [1280, 5], [1024, 4], [768, 3], [0, 2],
] as const
// ═══════════════════════════════════════════════════════════════════════
// ── Types ────────────────────────────────────────────────────────────
export type VirtualRow =
  | { type: 'header'; key: string; dateKey: string; dayLabel: string; count: number; year: number }
  | { type: 'grid'; key: string; dateKey: string; assets: Asset[] }
  | { type: 'loading'; key: string }
export interface DateGroup {
  dateKey: string
  year: number
  month: number
  day: number
  dayLabel: string
  assets: Asset[]
}
// ── Orientation helpers ──────────────────────────────────────────────
export type Orientation = 'landscape' | 'portrait' | 'square'
export type OrientationFilter = 'all' | 'landscape' | 'portrait' | 'square'
export function getOrientation(w?: number, h?: number): Orientation | undefined {
  if (!w || !h) return undefined
  if (w === h) return 'square'
  return w > h ? 'landscape' : 'portrait'
}
export function matchOrientation(asset: Asset, filter: OrientationFilter): boolean {
  if (filter === 'all') return true
  if (asset.tags?.includes('横屏')) return filter === 'landscape'
  if (asset.tags?.includes('竖屏')) return filter === 'portrait'
  const o = getOrientation(asset.width, asset.height)
  return o === filter
}
// ─────────────────────────────────────────────────────────────────────
// ── Helpers ──────────────────────────────────────────────────────────
export function chunkArr<T>(arr: T[], size: number): T[][] {
  const r: T[][] = []
  for (let i = 0; i < arr.length; i += size) r.push(arr.slice(i, i + size))
  return r
}
export function groupByDate(assets: Asset[], dir: 'asc' | 'desc') {
  const map = new Map<string, Asset[]>()
  const noDate: Asset[] = []
  for (const a of assets) {
    if (!a.media_date) { noDate.push(a); continue }
    const d = new Date(a.media_date)
    const k = [
      d.getFullYear(),
      String(d.getMonth() + 1).padStart(2, '0'),
      String(d.getDate()).padStart(2, '0'),
    ].join('-')
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(a)
  }
  const gs: DateGroup[] = []
  for (const [k, v] of map) {
    const [y, m, day] = k.split('-').map(Number)
    gs.push({
      dateKey: k,
      year: y,
      month: m,
      day,
      dayLabel: `${y}/${m}/${day}`,
      assets: v,
    })
  }
  gs.sort((a, b) => (dir === 'desc' ? -1 : 1) * a.dateKey.localeCompare(b.dateKey))
  return { groups: gs, noDate }
}
export function buildTimeline(gs: DateGroup[], dir: 'asc' | 'desc') {
  const ym = new Map<
    number,
    { year: number; months: Map<number, { month: number; days: Set<number> }> }
  >()
  for (const g of gs) {
    if (!ym.has(g.year)) ym.set(g.year, { year: g.year, months: new Map() })
    const y = ym.get(g.year)!
    if (!y.months.has(g.month)) y.months.set(g.month, { month: g.month, days: new Set() })
    y.months.get(g.month)!.days.add(g.day)
  }
  return Array.from(ym.values()).sort((a, b) =>
    dir === 'desc' ? b.year - a.year : a.year - b.year,
  )
}
// Skeleton card placeholder (no layout shift — fixed aspect-ratio)
export function formatCount(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M"
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K"
  return String(n)
}

export function SkeletonCard() {
  return (
    <div className="bg-gray-900 rounded-lg overflow-hidden border border-gray-800 animate-pulse">
      <div className="bg-gray-800 relative" style={{ minHeight: 112 }}>
        <div className="absolute inset-0 bg-gray-800/50" />
      </div>
      <div className="p-3 space-y-2">
        <div className="h-3 bg-gray-800 rounded w-3/4" />
        <div className="h-2 bg-gray-800 rounded w-1/2" />
      </div>
    </div>
  )
}
// Helper: page number range for pagination footer
export type StatusFilter = 'all' | 'scene' | 'yolo' | 'ocr' | 'clip' | 'transcript' | 'diarization'
 export const AI_FILTER_DEFS: { key: StatusFilter; labelKey: string; icon: typeof Image }[] = [
  { key: 'scene' as StatusFilter, labelKey: 'common.scene', icon: Image },
  { key: 'yolo' as StatusFilter, labelKey: 'common.tagLabel', icon: Tag },
  { key: 'ocr' as StatusFilter, labelKey: 'aiEngine.ocr', icon: FileText },
  { key: 'clip' as StatusFilter, labelKey: 'aiEngine.clip', icon: Brain },
  { key: 'transcript' as StatusFilter, labelKey: 'common.subtitle', icon: AudioLines },
  { key: 'diarization' as StatusFilter, labelKey: 'aiEngine.diarization', icon: Users },
]
export function assetMatchesAIFilter(asset: Asset, f: StatusFilter): boolean {
  switch (f) {
    case 'all': return true
    case 'scene': return asset.scene_status === 'completed'
    case 'yolo': return asset.yolo_status === 'completed'
    case 'ocr': return asset.ocr_status === 'completed'
    case 'clip': return asset.clip_status === 'completed'
    case 'transcript': return asset.transcript_status === 'completed'
    case 'diarization': return asset.diarization_status === 'completed'
    default: return false
  }
}
