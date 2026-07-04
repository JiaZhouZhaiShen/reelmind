import { useState, useEffect } from 'react'
import { X, Save, Loader2, FolderOpen } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Library as LibraryType, LibrarySettings } from '../../api/client'

interface LibraryEditDialogProps {
  editingLib: LibraryType | null
  onClose: () => void
  onSave: (libId: string, data: {
    name: string
    description?: string
    import_mode: string
    auto_scan: boolean
    settings?: Record<string, unknown>
  }) => Promise<void>
  onAddPath: (libId: string, path: string) => Promise<void>
  onRemovePath: (libId: string, pathId: string) => Promise<void>
  saving: boolean
}

export function LibraryEditDialog({ editingLib, onClose, onSave, onAddPath, onRemovePath, saving }: LibraryEditDialogProps) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [importMode, setImportMode] = useState('reference')
  const [autoScan, setAutoScan] = useState(true)
  const [customExts, setCustomExts] = useState('')
  const [excludedExts, setExcludedExts] = useState('')
  const [newPath, setNewPath] = useState('')
  const [currentLibId, setCurrentLibId] = useState<string | null>(null)

  useEffect(() => {
    if (editingLib && editingLib.id !== currentLibId) {
      setName(editingLib.name)
      setDescription(editingLib.description || '')
      setImportMode(editingLib.import_mode)
      setAutoScan(editingLib.auto_scan)
      const settings = (editingLib.settings || {}) as LibrarySettings
      setCustomExts((settings.custom_video_extensions || []).join(', '))
      setExcludedExts((settings.excluded_extensions || []).join(', '))
      setNewPath('')
      setCurrentLibId(editingLib.id)
    }
  }, [editingLib, currentLibId])

  if (!editingLib) return null

  const handleSave = () => {
    const scanSettings: Record<string, unknown> = {}
    if (customExts.trim()) {
      scanSettings.custom_video_extensions = customExts.split(',').map(s => s.trim()).filter(Boolean)
    }
    if (excludedExts.trim()) {
      scanSettings.excluded_extensions = excludedExts.split(',').map(s => s.trim()).filter(Boolean)
    }
    onSave(editingLib.id, {
      name: name.trim(),
      description: description.trim() || undefined,
      import_mode: importMode,
      auto_scan: autoScan,
      settings: Object.keys(scanSettings).length > 0 ? scanSettings : undefined,
    })
  }

  const handleAddPath = () => {
    if (newPath.trim()) {
      onAddPath(editingLib.id, newPath.trim())
      setNewPath('')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-gray-900 rounded-lg border border-gray-800 w-full max-w-lg mx-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-4 border-b border-gray-800">
          <h3 className="text-base font-medium text-white">{t('libraryManager.editTitle')}</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
          <div>
            <label className="block text-xs text-gray-500 mb-1">{t('libraryManager.name')}</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">{t('libraryManager.description')}</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">{t('libraryManager.importMode')}</label>
            <select value={importMode} onChange={(e) => setImportMode(e.target.value)} className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500">
              <option value="reference">{t('libraryManager.importModeReference')}</option>
              <option value="copy">{t('libraryManager.importModeCopy')}</option>
              <option value="move">{t('libraryManager.importModeMove')}</option>
            </select>
          </div>
          <div className="flex items-center gap-3">
            <input type="checkbox" id="edit-auto-scan" checked={autoScan} onChange={(e) => setAutoScan(e.target.checked)} className="rounded bg-gray-800 border-gray-700 text-indigo-600 focus:ring-indigo-500" />
            <label htmlFor="edit-auto-scan" className="text-sm text-gray-300">{t('libraryManager.autoScan')}</label>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">{t('libraryManager.customVideoExtensions')}</label>
            <input type="text" value={customExts} onChange={(e) => setCustomExts(e.target.value)} placeholder=".mp4, .mov, .avi" className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500" />
            <p className="text-[10px] text-gray-600 mt-1">{t('libraryManager.customExtensionsHint')}</p>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">{t('libraryManager.excludedExtensions')}</label>
            <input type="text" value={excludedExts} onChange={(e) => setExcludedExts(e.target.value)} placeholder=".txt, .jpg, .png" className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500" />
            <p className="text-[10px] text-gray-600 mt-1">{t('libraryManager.excludedExtensionsHint')}</p>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">{t('libraryManager.paths')}</label>
            <div className="space-y-1.5 mb-2">
              {(editingLib.path_details || []).map((p) => (
                <div key={p.id} className="flex items-center gap-2 text-xs text-gray-400 font-mono bg-gray-800 rounded px-2 py-1.5">
                  <FolderOpen className="w-3 h-3 shrink-0 text-gray-500" />
                  <span className="truncate flex-1">{p.path}</span>
                  <button onClick={() => onRemovePath(editingLib.id, p.id)} className="text-gray-600 hover:text-red-400 transition-colors shrink-0"><X className="w-3 h-3" /></button>
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <input type="text" value={newPath} onChange={(e) => setNewPath(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddPath(); } }} placeholder="/nas-media/..." className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500" />
              <button onClick={handleAddPath} disabled={!newPath.trim()} className="px-3 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-300 rounded-lg text-sm transition-colors">{t('libraryManager.addPath')}</button>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 p-4 border-t border-gray-800">
          <button onClick={onClose} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition-colors">{t('libraryManager.cancel')}</button>
          <button onClick={handleSave} disabled={saving || !name.trim()} className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-lg text-sm transition-colors">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {t('libraryManager.save')}
          </button>
        </div>
      </div>
    </div>
  )
}
