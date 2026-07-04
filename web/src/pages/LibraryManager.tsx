import { useState, useEffect, useRef } from 'react'
import { Plus, ArrowLeft, Save, Loader2, Library, Image } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useLibraryStore } from '../stores/library'
import { useAssetStore } from '../stores/asset'
import { api } from '../api/client'
import type { Library as LibraryType } from '../api/client'
import { useTranslation } from 'react-i18next'
import { LibraryCard } from '../components/library/LibraryCard'
import { LibraryEditDialog } from '../components/library/LibraryEditDialog'
 
export function LibraryManager() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const libraries = useLibraryStore((s) => s.libraries)
  const loadLibraries = useLibraryStore((s) => s.loadLibraries)
  const loadStats = useLibraryStore((s) => s.loadStats)

  const setLibraryScanStatus = useAssetStore((s) => s.setLibraryScanStatus)
  const clearLibraryScanStatus = useAssetStore((s) => s.clearLibraryScanStatus)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newPaths, setNewPaths] = useState('')
  const [scanning, setScanning] = useState<string | null>(null)
  const [pausing, setPausing] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [editingLib, setEditingLib] = useState<LibraryType | null>(null)
  const [saving, setSaving] = useState(false)
  const [repairing, setRepairing] = useState(false)
  const [scanInterval, setScanInterval] = useState(300)
  const [autoScanSaving, setAutoScanSaving] = useState(false)
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
        setLibraryScanStatus(libId, status)
      } catch (e) {
        console.error("Scan poll failed:", e)
      }
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
          setLibraryScanStatus(lib.id, status)
        }).catch((e) => console.error("Initial scan check failed:", e))
      })
      return
    }
    initialCheckDone.current = true
    const checkAll = async () => {
      for (const lib of libraries) {
        try {
          const status = await api.getLibraryScanStatus(lib.id)
          setLibraryScanStatus(lib.id, status)
          const hasActiveJob = status.recent_jobs.some(
            (j) => j.status === "running" || j.status === "queued"
          )
          if (hasActiveJob && !pollingRef.current[lib.id]) {
            pollingRef.current[lib.id] = setInterval(async () => {
              try {
                const s = await api.getLibraryScanStatus(lib.id)
                setLibraryScanStatus(lib.id, s)
              } catch (e) {
                console.error("Scan poll failed:", e)
              }
            }, 3000)
          }
        } catch (e) {
          console.error("Library init failed:", e)
        }
      }
    }
    checkAll()
  }, [libraries])
 
  const handleScan = async (lib: LibraryType) => {
    setScanning(lib.id)
    try {
      await api.scanLibrary(lib.id)
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
      setLibraryScanStatus(libId, status)
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
      await api.scanResume(libId)
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
  }
 
  const handleEditClose = () => {
    setEditingLib(null)
    setSaving(false)
  }
 
  const handleEditSave = async (libId: string, data: {
    name: string; description?: string; import_mode: string; auto_scan: boolean; settings?: Record<string, unknown>
  }) => {
    setSaving(true)
    try {
      await api.updateLibrary(libId, data)
      await loadLibraries()
      await loadStats()
      handleEditClose()
    } catch (e) {
      console.error('Failed to update library:', e)
    } finally {
      setSaving(false)
    }
  }
 
  const handleAddPath = async (libId: string, path: string) => {
    try {
      await api.addLibraryPath(libId, path)
      const updated = await api.getLibrary(libId)
      setEditingLib(updated)
    } catch (e) {
      console.error('Failed to add path:', e)
    }
  }
 
  const handleRemovePath = async (libId: string, pathId: string) => {
    try {
      await api.removeLibraryPath(libId, pathId)
      const updated = await api.getLibrary(libId)
      setEditingLib(updated)
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
          <LibraryCard
            key={lib.id}
            lib={lib}
            scanning={scanning === lib.id}
            pausing={pausing === lib.id}
            onScan={() => handleScan(lib)}
            onPause={() => handlePause(lib.id)}
            onResume={() => handleResume(lib.id)}
            onEdit={() => handleEditOpen(lib)}
            onDelete={() => handleDelete(lib)}
            onDismissStatus={() => { stopPolling(lib.id); clearLibraryScanStatus(lib.id); }}
          />
        ))}
      </div>
    </div>
    <LibraryEditDialog
      editingLib={editingLib}
      onClose={handleEditClose}
      onSave={handleEditSave}
      onAddPath={handleAddPath}
      onRemovePath={handleRemovePath}
      saving={saving}
    />
    </>
  )
}

