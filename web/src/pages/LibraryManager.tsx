import { useState, useEffect, useRef } from 'react'
import { Library, Plus, Trash2, Scan, FolderOpen, Film, Loader2, ExternalLink, ArrowLeft, X, Circle, CheckCircle, AlertCircle, Clock, PauseCircle, Play, Pencil, Save, SkipForward, Image, Settings } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '../stores/app'
import { api } from '../api/client'
import type { Library as LibraryType, LibrarySettings, ScanJobInfo } from '../api/client'
import { useTranslation } from 'react-i18next'
 
export function LibraryManager() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const libraries = useStore((s) => s.libraries)
  const loadLibraries = useStore((s) => s.loadLibraries)
  const selectLibrary = useStore((s) => s.selectLibrary)
  const loadStats = useStore((s) => s.loadStats)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newPaths, setNewPaths] = useState('')
  const [scanning, setScanning] = useState<string | null>(null)
  const [pausing, setPausing] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [editingLib, setEditingLib] = useState<LibraryType | null>(null)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editImportMode, setEditImportMode] = useState('reference')
  const [editAutoScan, setEditAutoScan] = useState(true)
  const [editCustomVideoExtensions, setEditCustomVideoExtensions] = useState('')
  const [editExcludedExtensions, setEditExcludedExtensions] = useState('')
  const [editNewPath, setEditNewPath] = useState('')
  const [saving, setSaving] = useState(false)
  const [repairing, setRepairing] = useState(false)
  const [autoScanEnabled, setAutoScanEnabled] = useState(true)
  const [scanInterval, setScanInterval] = useState(300)
  const [autoScanSaving, setAutoScanSaving] = useState(false)
  const [scanStatus, setScanStatus] = useState<Record<string, { pending_import: number; recent_jobs: ScanJobInfo[] }>>({})
  const pollingRef = useRef<Record<string, ReturnType<typeof setInterval>>>({})
 
  const handleCreate = async () => {
    if (!newName.trim()) return
    setLoading(true)
    try {
      const paths = newPaths.split('\n').map((p) => p.trim()).filter(Boolean)
      await api.createLibrary({ name: newName, import_mode: 'reference', paths })
      setShowCreate(false)
      setNewName('')
      setNewPaths('')
      await loadLibraries()
      await loadStats()
    } catch (e) {
      console.error('Failed to create library:', e)
    } finally {
      setLoading(false)
    }
  }
 
  const startPolling = (libId: string) => {
    const poll = async () => {
      try {
        const status = await api.getLibraryScanStatus(libId)
        setScanStatus((prev) => ({ ...prev, [libId]: status }))
      } catch {}
    }
    poll()
    pollingRef.current[libId] = setInterval(poll, 3000)
  }
 
  const stopPolling = (libId: string) => {
    if (pollingRef.current[libId]) {
      clearInterval(pollingRef.current[libId])
      delete pollingRef.current[libId]
    }
  }
 
  useEffect(() => {
    return () => {
      Object.values(pollingRef.current).forEach(clearInterval)
    }
  }, [])
 
  const initialCheckDone = useRef(false)
  useEffect(() => {
    if (libraries.length === 0) return
    if (initialCheckDone.current && pollingRef.current) {
      libraries.forEach((lib) => {
        api.getLibraryScanStatus(lib.id).then((status) => {
          setScanStatus((prev) => ({ ...prev, [lib.id]: status }))
        }).catch(() => {})
      })
      return
    }
    initialCheckDone.current = true
    const checkAll = async () => {
      for (const lib of libraries) {
        try {
          const status = await api.getLibraryScanStatus(lib.id)
          setScanStatus((prev) => ({ ...prev, [lib.id]: status }))
          const hasActiveJob = status.recent_jobs.some(
            (j) => j.status === "running" || j.status === "queued"
          )
          if (hasActiveJob && !pollingRef.current[lib.id]) {
            pollingRef.current[lib.id] = setInterval(async () => {
              try {
                const s = await api.getLibraryScanStatus(lib.id)
                setScanStatus((prev) => ({ ...prev, [lib.id]: s }))
              } catch {}
            }, 3000)
          }
        } catch {}
      }
    }
    checkAll()
  }, [libraries])
 
  const handleScan = async (lib: LibraryType) => {
    setScanning(lib.id)
    try {
      const result = await api.scanLibrary(lib.id)
      startPolling(lib.id)
      await loadLibraries()
      await loadStats()
    } catch (e) {
      console.error('Scan failed:', e)
    } finally {
      setScanning(null)
    }
  }
 
  const handlePause = async (libId: string) => {
    setPausing(libId)
    try {
      await api.scanPause(libId)
      const status = await api.getLibraryScanStatus(libId)
      setScanStatus((prev) => ({ ...prev, [libId]: status }))
      await loadLibraries()
      await loadStats()
    } catch (e) {
      console.error('Pause scan failed:', e)
    } finally {
      setPausing(null)
    }
  }
 
  const handleResume = async (libId: string) => {
    setPausing(libId)
    try {
      const result = await api.scanResume(libId)
      startPolling(libId)
      await loadLibraries()
      await loadStats()
    } catch (e) {
      console.error('Resume scan failed:', e)
    } finally {
      setPausing(null)
    }
  }
 
  const handleRepairThumbnails = async () => {
    if (!confirm(t('libraryManager.repairConfirm'))) return
    setRepairing(true)
    try {
      const result = await api.repairThumbnails()
      alert(t('libraryManager.repairSuccess', { repaired: result.repaired, failed: result.failed }))
    } catch (e) {
      console.error('Repair thumbnails failed:', e)
      alert(t('libraryManager.repairFailed'))
    } finally {
      setRepairing(false)
    }
  }
 
  const loadAutoScanSettings = async () => {
    try {
      const data = await api.getScanSettings()
      setScanInterval(data.scan_interval_seconds)
    } catch (e) {
      console.error("Failed to load auto-scan settings:", e)
    }
  }

  const handleSaveAutoScan = async () => {
    setAutoScanSaving(true)
    try {
      await api.setScanSettings({
        scan_interval_seconds: scanInterval,
      })
      setTimeout(() => setAutoScanSaving(false), 1500)
    } catch (e) {
      console.error("Failed to save auto-scan settings:", e)
      setAutoScanSaving(false)
    }
  }

  const handleEditOpen = (lib: LibraryType) => {
    setEditingLib(lib)
    setEditName(lib.name)
    setEditDescription(lib.description || '')
    setEditImportMode(lib.import_mode)
    setEditAutoScan(lib.auto_scan)
    const libSettings = (lib.settings || {}) as LibrarySettings
    setEditCustomVideoExtensions((libSettings.custom_video_extensions || []).join(', '))
    setEditExcludedExtensions((libSettings.excluded_extensions || []).join(', '))
    setEditNewPath('')
  }
 
  const handleEditClose = () => {
    setEditingLib(null)
    setSaving(false)
  }
 
  const handleEditSave = async () => {
    if (!editingLib) return
    setSaving(true)
    try {
      const scanSettings: Record<string, unknown> = {}
      if (editCustomVideoExtensions.trim()) {
        scanSettings.custom_video_extensions = editCustomVideoExtensions.split(',').map(s => s.trim()).filter(Boolean)
      }
      if (editExcludedExtensions.trim()) {
        scanSettings.excluded_extensions = editExcludedExtensions.split(',').map(s => s.trim()).filter(Boolean)
      }
      await api.updateLibrary(editingLib.id, {
        name: editName.trim(),
        description: editDescription.trim() || undefined,
        import_mode: editImportMode,
        auto_scan: editAutoScan,
        settings: Object.keys(scanSettings).length > 0 ? scanSettings : undefined,
      })
      await loadLibraries()
      await loadStats()
      handleEditClose()
    } catch (e) {
      console.error('Failed to update library:', e)
    } finally {
      setSaving(false)
    }
  }
 
  const handleAddPath = async () => {
    if (!editingLib || !editNewPath.trim()) return
    try {
      await api.addLibraryPath(editingLib.id, editNewPath.trim())
      setEditNewPath('')
      const updated = await api.getLibrary(editingLib.id)
      setEditingLib(updated)
      setEditName(updated.name)
      setEditDescription(updated.description || '')
      setEditImportMode(updated.import_mode)
      setEditAutoScan(updated.auto_scan)
      const updatedSettings = (updated.settings || {}) as LibrarySettings
      setEditCustomVideoExtensions((updatedSettings.custom_video_extensions || []).join(', '))
      setEditExcludedExtensions((updatedSettings.excluded_extensions || []).join(', '))
    } catch (e) {
      console.error('Failed to add path:', e)
    }
  }
 
  const handleRemovePath = async (pathId: string) => {
    if (!editingLib) return
    try {
      await api.removeLibraryPath(editingLib.id, pathId)
      const updated = await api.getLibrary(editingLib.id)
      setEditingLib(updated)
      setEditName(updated.name)
      setEditDescription(updated.description || '')
      setEditImportMode(updated.import_mode)
      setEditAutoScan(updated.auto_scan)
      const updatedSettings = (updated.settings || {}) as LibrarySettings
      setEditCustomVideoExtensions((updatedSettings.custom_video_extensions || []).join(', '))
      setEditExcludedExtensions((updatedSettings.excluded_extensions || []).join(', '))
    } catch (e) {
      console.error('Failed to remove path:', e)
    }
  }
 
  const handleDelete = async (lib: LibraryType) => {
    if (!confirm(t('libraryManager.deleteConfirm', { name: lib.name }))) return
    try {
      await api.deleteLibrary(lib.id)
      await loadLibraries()
      await loadStats()
    } catch (e) {
      console.error('Delete failed:', e)
    }
  }
 
  const formatSize = (bytes: number) => {
    if (bytes < 1e6) return `${(bytes / 1e3).toFixed(0)} KB`
    if (bytes < 1e9) return `${(bytes / 1e6).toFixed(1)} MB`
    return `${(bytes / 1e9).toFixed(2)} GB`
  }
 
  const formatDuration = (s: number) => {
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    if (h > 0) return `${h}${t('libraryManager.h')} ${m}${t('libraryManager.m')}`
    return `${m} ${t('libraryManager.min')}`
  }
 
  return (
    <>
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/')} className="text-gray-400 hover:text-white transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-white">{t('libraryManager.title')}</h1>
            <p className="text-sm text-gray-500">{t('libraryManager.count', { count: libraries.length })}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Interval Select */}
          <span className="text-xs text-gray-400 whitespace-nowrap">{t('libraryManager.autoScan')}</span>
          {/* Interval Select */}
          <select
            value={scanInterval}
            onChange={(e) => { setScanInterval(Number(e.target.value)); null }}
            className="bg-gray-900 border border-gray-800 rounded-lg px-2 py-1.5 text-xs text-gray-300 focus:outline-none focus:border-indigo-500/60 cursor-pointer"
          >
            <option value={60}>1{t('libraryManager.min')}</option>
            <option value={300}>5{t('libraryManager.min')}</option>
            <option value={600}>10{t('libraryManager.min')}</option>
            <option value={1800}>30{t('libraryManager.min')}</option>
            <option value={3600}>1{t('libraryManager.h')}</option>
          </select>
          {/* Save Button */}
          <button
            onClick={handleSaveAutoScan}
            disabled={autoScanSaving}
            className={'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ' + (autoScanSaving ? 'bg-emerald-600 text-white' : 'bg-indigo-600 hover:bg-indigo-700 text-white')}
          >
            {autoScanSaving ? (
              <><Loader2 className="w-3 h-3 animate-spin" />{t('libraryManager.saved')}</>
            ) : (
              <><Save className="w-3 h-3" />{t('libraryManager.save')}</>
            )}
          </button>
          {/* Repair Thumbnails */}
          <button
            onClick={handleRepairThumbnails}
            disabled={repairing}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-300 rounded-lg text-xs transition-colors"
          >
            {repairing ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Image className="w-3 h-3" />
            )}
            {t('libraryManager.repairThumbnails')}
          </button>
          {/* New Library */}
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs transition-colors"
          >
            <Plus className="w-3 h-3" />
            {t('libraryManager.newLibrary')}
          </button>
        </div>
      </div>
      {showCreate && (
        <div className="mb-6 bg-gray-900 rounded-lg p-4 border border-gray-800">
          <h3 className="text-sm font-medium text-gray-200 mb-3">{t('libraryManager.createTitle')}</h3>
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">{t('libraryManager.name')}</label>
              <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder={t('libraryManager.namePlaceholder')} className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">{t('libraryManager.paths')}</label>
              <textarea value={newPaths} onChange={(e) => setNewPaths(e.target.value)} placeholder={t('libraryManager.pathsPlaceholder')} rows={3} className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500 font-mono" />
            </div>
            <div className="flex gap-2">
              <button onClick={handleCreate} disabled={loading} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-lg text-sm transition-colors">{loading ? t('libraryManager.creating') : t('libraryManager.create')}</button>
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition-colors">{t('libraryManager.cancel')}</button>
            </div>
          </div>
        </div>
      )}
      {libraries.length === 0 && !showCreate && (
        <div className="flex flex-col items-center justify-center py-24 text-gray-500">
          <Library className="w-12 h-12 mb-3 text-gray-700" />
          <p className="text-gray-400 text-lg mb-1">{t('libraryManager.noLibraries')}</p>
          <p className="text-sm text-gray-600 mb-4">{t('libraryManager.emptyHint')}</p>
          <button onClick={() => setShowCreate(true)} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm transition-colors">{t('libraryManager.createLibrary')}</button>
        </div>
      )}
      <div className="space-y-3">
        {libraries.map((lib) => (
          <div key={lib.id} className="bg-gray-900 rounded-lg border border-gray-800 hover:border-gray-700 transition-colors ">
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
                  {(() => {
                    const jobs = scanStatus[lib.id]?.recent_jobs
                    const latestJob = jobs && jobs.length > 0 ? jobs[0] : null
                    const hasRunningJob = latestJob && (latestJob.status === 'running' || latestJob.status === 'queued')
                    const hasPausedJob = latestJob && latestJob.status === 'paused'
                    return (
                      <>
                      {hasPausedJob && (
                        <button onClick={() => handleResume(lib.id)} disabled={pausing === lib.id} className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-700 hover:bg-amber-600 disabled:opacity-50 text-white rounded-lg text-xs transition-colors">
                          {pausing === lib.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                          {t('scan.resume')}
                        </button>
                      )}
                      {hasRunningJob && (
                        <button onClick={() => handlePause(lib.id)} disabled={pausing === lib.id} className="flex items-center gap-1.5 px-3 py-1.5 bg-yellow-700 hover:bg-yellow-600 disabled:opacity-50 text-white rounded-lg text-xs transition-colors">
                          {pausing === lib.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <PauseCircle className="w-3 h-3" />}
                          {t('scan.pause')}
                        </button>
                      )}
                      </>
                    )
                  })()}
                  <button
                    onClick={(e) => { e.stopPropagation(); handleScan(lib) }}
                    disabled={scanning === lib.id}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-300 rounded-lg text-xs transition-colors"
                  >
                    {scanning === lib.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Scan className="w-3 h-3" />}
                    {t('libraryManager.scan')}
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleEditOpen(lib) }}
                    className="p-1.5 text-gray-500 hover:text-indigo-400 transition-colors"
                    title={t('libraryManager.edit')}
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDelete(lib) }}
                    className="p-1.5 text-gray-500 hover:text-red-400 transition-colors"
                  >
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
              {scanStatus[lib.id] && (
                <div className="mt-3 pt-3 border-t border-gray-800">
                  {scanStatus[lib.id].pending_import > 0 && (
                    <div className="flex items-center gap-2 text-xs text-amber-400 mb-2">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      <span>{t('scan.processingAssets', { count: scanStatus[lib.id].pending_import })}</span>
                      <button onClick={() => { stopPolling(lib.id); setScanStatus((prev) => { const p = { ...prev }; delete p[lib.id]; return p }) }} className="text-gray-500 hover:text-gray-300 ml-auto"><X className="w-3 h-3" /></button>
                    </div>
                  )}
                  {scanStatus[lib.id].recent_jobs.length > 0 && (
                    <div>
                      <p className="text-xs text-gray-500 mb-1.5">{t('scan.recentJobs')}</p>
                      <div className="space-y-1">
                        {scanStatus[lib.id].recent_jobs.slice(0, 3).map((job) => (
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
        ))}
      </div>
    </div>
    {editingLib && (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={handleEditClose}>
        <div className="bg-gray-900 rounded-lg border border-gray-800 w-full max-w-lg mx-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between p-4 border-b border-gray-800">
            <h3 className="text-base font-medium text-white">{t('libraryManager.editTitle')}</h3>
            <button onClick={handleEditClose} className="text-gray-500 hover:text-white transition-colors"><X className="w-4 h-4" /></button>
          </div>
          <div className="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
            <div>
              <label className="block text-xs text-gray-500 mb-1">{t('libraryManager.name')}</label>
              <input type="text" value={editName} onChange={(e) => setEditName(e.target.value)} className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">{t('libraryManager.description')}</label>
              <textarea value={editDescription} onChange={(e) => setEditDescription(e.target.value)} rows={2} className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">{t('libraryManager.importMode')}</label>
              <select value={editImportMode} onChange={(e) => setEditImportMode(e.target.value)} className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500">
                <option value="reference">{t('libraryManager.importModeReference')}</option>
                <option value="copy">{t('libraryManager.importModeCopy')}</option>
                <option value="move">{t('libraryManager.importModeMove')}</option>
              </select>
            </div>
            <div className="flex items-center gap-3">
              <input type="checkbox" id="edit-auto-scan" checked={editAutoScan} onChange={(e) => setEditAutoScan(e.target.checked)} className="rounded bg-gray-800 border-gray-700 text-indigo-600 focus:ring-indigo-500" />
              <label htmlFor="edit-auto-scan" className="text-sm text-gray-300">{t('libraryManager.autoScan')}</label>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">{t('libraryManager.customVideoExtensions')}</label>
              <input type="text" value={editCustomVideoExtensions} onChange={(e) => setEditCustomVideoExtensions(e.target.value)} placeholder=".mp4, .mov, .avi" className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500" />
              <p className="text-[10px] text-gray-600 mt-1">{t('libraryManager.customExtensionsHint')}</p>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">{t('libraryManager.excludedExtensions')}</label>
              <input type="text" value={editExcludedExtensions} onChange={(e) => setEditExcludedExtensions(e.target.value)} placeholder=".txt, .jpg, .png" className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500" />
              <p className="text-[10px] text-gray-600 mt-1">{t('libraryManager.excludedExtensionsHint')}</p>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">{t('libraryManager.paths')}</label>
              <div className="space-y-1.5 mb-2">
                {(editingLib.path_details || []).map((p) => (
                  <div key={p.id} className="flex items-center gap-2 text-xs text-gray-400 font-mono bg-gray-800 rounded px-2 py-1.5">
                    <FolderOpen className="w-3 h-3 shrink-0 text-gray-500" />
                    <span className="truncate flex-1">{p.path}</span>
                    <button onClick={() => handleRemovePath(p.id)} className="text-gray-600 hover:text-red-400 transition-colors shrink-0" title="Remove"><X className="w-3 h-3" /></button>
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <input type="text" value={editNewPath} onChange={(e) => setEditNewPath(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddPath(); } }} placeholder="/nas-media/..." className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500" />
                <button onClick={handleAddPath} disabled={!editNewPath.trim()} className="px-3 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-300 rounded-lg text-sm transition-colors">{t('libraryManager.addPath')}</button>
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-2 p-4 border-t border-gray-800">
            <button onClick={handleEditClose} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition-colors">{t('libraryManager.cancel')}</button>
            <button onClick={handleEditSave} disabled={saving || !editName.trim()} className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-lg text-sm transition-colors">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {t('libraryManager.save')}
            </button>
          </div>
        </div>
      </div>
    )}
    </>
  )
}
