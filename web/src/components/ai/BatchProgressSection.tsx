import { Loader2, RefreshCw } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { BatchCheckpointInfo } from "../../types/ai"

export const ENGINE_NAMES: Record<string, string> = {
  scene: "Scene Cut",
  yolo: "YOLO",
  ocr: "OCR",
  clip: "CLIP",
  transcript: "Speech-to-Text",
  diarization: "Speaker Diarization",
}

export const ENGINE_ORDER = ["scene", "yolo", "ocr", "clip", "transcript", "diarization"]

// ── Block Bar (per-engine micro progress) ──

function BlockBar({ completed, total, running }: { completed: number; total: number; running: number }) {
  const BLOCKS = 20
  const pct = total > 0 ? completed / total : 0
  const filledBlocks = Math.round(pct * BLOCKS)
  const inProgressBlock = running > 0 && filledBlocks < BLOCKS ? filledBlocks : -1

  return (
    <div className="flex gap-[2px] items-stretch h-full">
      {Array.from({ length: BLOCKS }).map((_, i) => {
        let cls = "w-2 h-3.5 rounded-[1px] "
        if (i < filledBlocks) {
          cls += "bg-emerald-500"
        } else if (i === inProgressBlock) {
          cls += "bg-emerald-400/70 animate-pulse"
        } else {
          cls += "bg-gray-700/50"
        }
        return <div key={i} className={cls} />
      })}
    </div>
  )
}

// ── Batch Progress Section ──

export function BatchProgressSection({
  checkpoints,
  engineProgress,
  chunkSize,
}: {
  checkpoints: BatchCheckpointInfo[]
  engineProgress: Record<string, Record<string, number>>
  chunkSize: number
}) {
  const { t } = useTranslation()
  const runningCp = checkpoints.find((cp) => cp.status === "running")
  const displayCp = runningCp || checkpoints[0]
  const isRunning = !!runningCp

  if (!displayCp) return null

  // Use engine progress to show smoother overall progress within a chunk
  const completedInChunk = engineProgress?.scene?.completed || 0
  const virtualProcessed = displayCp.processed + completedInChunk

  const hasEngineProgress = engineProgress && Object.keys(engineProgress).length > 0 &&
    Object.values(engineProgress).some((e: any) => (e.completed || 0) > 0 || (e.running || 0) > 0)

  return (
    <div className="rounded-lg border border-gray-700/40 bg-gray-800/40 p-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={
            "w-2 h-2 rounded-full " +
            (isRunning ? "bg-emerald-500 animate-pulse" :
             displayCp.status === "completed" ? "bg-emerald-500" :
             displayCp.status === "error" ? "bg-red-500" : "bg-gray-500")
          } />
          <span className="text-sm font-semibold text-gray-200">
            {displayCp.task_label} {displayCp.id.slice(0, 8)}
          </span>
          <span className={
            "text-xs font-medium " +
            (displayCp.status === "completed" ? "text-emerald-400" :
             isRunning ? "text-emerald-300" :
             displayCp.status === "error" ? "text-red-400" :
             displayCp.status === "cancelled" ? "text-gray-400" : "text-gray-400")
          }>
            · {displayCp.status === "completed" ? "✓ " + t('batchProgress.completed') :
               isRunning ? t('batchProgress.running') :
               displayCp.status === "error" ? t('common.failed') :
               displayCp.status === "cancelled" ? t('batchProgress.cancelled') : displayCp.status}
          </span>
        </div>
        <button
          onClick={() => window.location.reload()}
          className="text-gray-500 hover:text-gray-300 transition-colors p-1"
          title={t('common.refresh')}
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Per-engine progress */}
      {isRunning && hasEngineProgress && (
        <div className="space-y-1.5 mb-3">
          {ENGINE_ORDER.filter(e => engineProgress[e]).map((eng) => {
            const e = engineProgress[eng]
            const completed = e.completed || 0
            const running = e.running || 0
            const total = chunkSize || completed + running + (e.pending || 0) || 1
            const statusLabel =
              completed >= total ? "✓" :
              running > 0 ? t('common.processing') :
              completed > 0 ? t('common.waiting') : t('common.waiting')
            const statusColor =
              completed >= total ? "text-emerald-400" :
              running > 0 ? "text-emerald-300" : "text-gray-500"
            return (
              <div key={eng} className="flex items-center gap-2">
                <span className="w-14 text-xs text-gray-400 text-right shrink-0">{t('batchProgress.engine.' + eng)}</span>
                <div className="flex-1 h-full min-h-[18px]">
                  <BlockBar completed={completed} total={total} running={running} />
                </div>
                <span className={"text-xs font-mono shrink-0 w-14 text-right " + statusColor}>
                  {completed}/{total}
                </span>
                <span className={"text-xs shrink-0 w-12 text-right " + statusColor}>
                  {statusLabel}
                </span>
              </div>
            )
          })}
        </div>
      )}

      {/* Between chunks */}
      {isRunning && (!hasEngineProgress) && (
        <div className="text-xs text-gray-500 mb-2.5 flex items-center gap-1.5">
          <Loader2 className="w-3 h-3 animate-spin" />
          {displayCp.processed > 0 ? t('common.prepareNext') : t('common.waitingForAI')}
        </div>
      )}

      {/* Overall progress bar */}
      <div className="w-full h-3 bg-gray-700/40 rounded-sm overflow-hidden mb-1.5">
        <div
          className={
            "h-full transition-all duration-1000 ease-out " +
            (displayCp.status === "completed" ? "bg-emerald-500" :
             isRunning ? "bg-gradient-to-r from-emerald-600 to-emerald-400" :
             displayCp.status === "cancelled" ? "bg-gray-500" :
             "bg-emerald-500/60")
          }
          style={{
            width: isRunning && chunkSize > 0
              ? Math.min(100, Math.round((completedInChunk / chunkSize) * 100)) + "%"
              : Math.min(100, Math.round((virtualProcessed / displayCp.total_videos) * 100)) + "%"
          }}
        />
      </div>

      {/* Summary line */}
      <div className="text-xs text-gray-500">
        {isRunning || displayCp.status === "cancelled" ? (
          <>
            <span>{t("batchProgress.totalProgress", { completed: virtualProcessed, total: displayCp.total_videos })}</span>
            {isRunning && chunkSize > 0 && (
              <span className="text-gray-500"> · {t("batchProgress.chunkProgress", { completed: completedInChunk, total: chunkSize })} ({Math.round(completedInChunk / chunkSize * 100)}%)</span>
            )}
          </>
        ) : displayCp.status === "completed" ? (
          <>{t('batchProgress.allCompleted', { count: displayCp.total_videos })}</>
        ) : (
          <>{displayCp.processed}/{displayCp.total_videos}</>
        )}
      </div>
    </div>
  )
}
