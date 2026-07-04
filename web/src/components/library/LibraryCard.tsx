import { memo } from 'react'
import { Library, Film, Scan, Loader2, Pencil, Trash2, FolderOpen, X, Play, PauseCircle, CheckCircle, AlertCircle, Clock, SkipForward } from 'lucide-react'
import { useAssetStore } from '../../stores/asset'
import { formatSize, formatDuration } from '../../utils/format'
import { useTranslation } from 'react-i18next'
import type { Library as LibraryType } from '../../api/client'

interface LibraryCardProps {
  lib: LibraryType
  scanning: boolean
  pausing: boolean
  onScan: () => void
  onPause: () => void
  onResume: () => void
  onEdit: () => void
  onDelete: () => void
  onDismissStatus: () => void
}

export const LibraryCard = memo(function LibraryCard({
  lib, scanning, pausing, onScan, onPause, onResume, onEdit, onDelete, onDismissStatus
}: LibraryCardProps) {
  const { t } = useTranslation()
  const libraryScanStatus = useAssetStore((s) => s.libraryScanStatus)
  const status = libraryScanStatus[lib.id]

  const jobs = status?.recent_jobs
  const latestJob = jobs && jobs.length > 0 ? jobs[0] : null
  const hasRunningJob = latestJob && (latestJob.status === 'running' || latestJob.status === 'queued')
  const hasPausedJob = latestJob && latestJob.status === 'paused'

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 hover:border-gray-700 transition-colors">
      <div className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-indigo-900/30 flex items-center justify-center">
              <Library className="w-5 h-5 text-indigo-400" />
            </div>
            <div>
              <h3 className="text-base font-medium text-white">{lib.name}</h3>
              {lib.description && <p className="text-xs text-gray-500 mt-0.5">{lib.description}</p>}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {hasPausedJob && (
              <button onClick={onResume} disabled={pausing}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-700 hover:bg-amber-600 disabled:opacity-50 text-white rounded-lg text-xs transition-colors">
                {pausing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                {t('scan.resume')}
              </button>
            )}
            {hasRunningJob && (
              <button onClick={onPause} disabled={pausing}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-yellow-700 hover:bg-yellow-600 disabled:opacity-50 text-white rounded-lg text-xs transition-colors">
                {pausing ? <Loader2 className="w-3 h-3 animate-spin" /> : <PauseCircle className="w-3 h-3" />}
                {t('scan.pause')}
              </button>
            )}
            <button onClick={onScan} disabled={scanning}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-300 rounded-lg text-xs transition-colors">
              {scanning ? <Loader2 className="w-3 h-3 animate-spin" /> : <Scan className="w-3 h-3" />}
              {t('libraryManager.scan')}
            </button>
            <button onClick={onEdit} className="p-1.5 text-gray-500 hover:text-indigo-400 transition-colors" title={t('libraryManager.edit')}>
              <Pencil className="w-4 h-4" />
            </button>
            <button onClick={onDelete} className="p-1.5 text-gray-500 hover:text-red-400 transition-colors">
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
        <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
          <span className="flex items-center gap-1"><Film className="w-3 h-3" />{lib.total_assets} {t('libraryManager.assets')}</span>
          <span>{formatSize(lib.total_size_bytes)}</span>
          <span>{formatDuration(lib.total_duration_seconds)}</span>
          <span className="capitalize">{lib.import_mode}</span>
        </div>
        {status && (
          <div className="mt-3 pt-3 border-t border-gray-800">
            {status.pending_import > 0 && (
              <div className="flex items-center gap-2 text-xs text-amber-400 mb-2">
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>{t('scan.processingAssets', { count: status.pending_import })}</span>
                <button onClick={onDismissStatus} className="text-gray-500 hover:text-gray-300 ml-auto"><X className="w-3 h-3" /></button>
              </div>
            )}
            {status.recent_jobs.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 mb-1.5">{t('scan.recentJobs')}</p>
                <div className="space-y-1">
                  {status.recent_jobs.slice(0, 3).map((job) => (
                    <div key={job.id} className="flex items-center gap-2 text-xs">
                      {job.status === 'completed' && <CheckCircle className="w-3 h-3 text-green-500 shrink-0" />}
                      {job.status === 'running' && <Loader2 className="w-3 h-3 animate-spin text-indigo-400 shrink-0" />}
                      {job.status === 'queued' && <Clock className="w-3 h-3 text-gray-400 shrink-0" />}
                      {job.status === 'paused' && <PauseCircle className="w-3 h-3 text-amber-400 shrink-0" />}
                      {job.status === 'failed' && <AlertCircle className="w-3 h-3 text-red-500 shrink-0" />}
                      {job.status === "superseded" && <SkipForward className="w-3 h-3 text-gray-600 shrink-0" />}
                      {job.status === 'pending' && <Clock className="w-3 h-3 text-gray-500 shrink-0" />}
                      <span className="text-gray-400 truncate">{job.status === "failed" ? (job.error ? `${job.message || job.status} — ${job.error}` : job.message || job.status) : (job.message || job.status)}</span>
                      {job.progress > 0 && job.progress < 100 && <span className="text-gray-500 ml-auto">{job.progress}%</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
        {lib.paths.length > 0 && (
          <div className="mt-3 space-y-1">
            {lib.paths.map((p, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-gray-600 font-mono">
                <FolderOpen className="w-3 h-3 shrink-0" />
                <span className="truncate">{p}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
})
