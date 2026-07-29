import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { api } from "../../api/client"
import type { AdminSettingValue, MetadataFieldDef } from "../../api/client"
 import { Save, Loader2, ChevronDown, ChevronRight } from "lucide-react"

import { logger } from '../../utils/logger';


export default function SystemSettingsPage() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<Record<string, AdminSettingValue>>({})
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [metadataFields, setMetadataFields] = useState<MetadataFieldDef[]>([])
  const [metadataGroups, setMetadataGroups] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
   const [expandedCategories, setExpandedCategories] = useState<Record<string, boolean>>({
     scanning: true, indexing: true,
   })

  useEffect(() => {
    loadSettings()
    loadMetadataFields()
  }, [])
   const loadMetadataFields = async () => {
    try {
      const data = await api.getMetadataFieldDefinitions()
      setMetadataFields(data.fields)
      setMetadataGroups(data.groups)
    } catch (e) {
      logger.error("Failed to load metadata fields:", e)
    }
  }

  const loadSettings = async () => {
    setLoading(true)
    try {
      const data = await api.getAdminSettings()
      setSettings(data)
      const initial: Record<string, string> = {}
      Object.entries(data).forEach(([k, v]) => { initial[k] = v.value })
      setEdits(initial)
    } catch (e) {
      logger.error("Failed to load settings:", e)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setSaveError(null)
    try {
      await api.updateAdminSettings(edits)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      logger.error("Failed to save settings:", e)
      setSaveError(e instanceof Error ? e.message : "保存失败，请查看控制台")
    } finally {
      setSaving(false)
    }
  }

   const categories = ["scanning", "indexing"]


  const toggleCat = (cat: string) => {
    setExpandedCategories((prev) => ({ ...prev, [cat]: !prev[cat] }))
  }

  // Metadata field selection helpers
  const currentMetadataFieldKeys = (): string[] => {
    const raw = edits["metadata_fields"] ?? ""
    return raw.split(",").map((s) => s.trim()).filter(Boolean)
  }

  const isFieldSelected = (fieldKey: string): boolean => {
    return currentMetadataFieldKeys().includes(fieldKey)
  }

  const toggleField = (fieldKey: string) => {
    const selected = new Set(currentMetadataFieldKeys())
    if (selected.has(fieldKey)) selected.delete(fieldKey)
    else selected.add(fieldKey)
    setEdits((prev) => ({ ...prev, metadata_fields: [...selected].join(",") }))
  }

  const isAllGroupSelected = (group: string): boolean => {
    const groupFields = metadataFields.filter((f) => f.group === group)
    const selected = currentMetadataFieldKeys()
    return groupFields.length > 0 && groupFields.every((f) => selected.includes(f.key))
  }

  const toggleGroup = (group: string) => {
    const groupFields = metadataFields.filter((f) => f.group === group)
    const selected = new Set(currentMetadataFieldKeys())
    const allSelected = isAllGroupSelected(group)
    for (const f of groupFields) {
      if (allSelected) selected.delete(f.key)
      else selected.add(f.key)
    }
    setEdits((prev) => ({ ...prev, metadata_fields: [...selected].join(",") }))
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
      </div>
    )
  }

  const grouped: Record<string, [string, AdminSettingValue][]> = {}
  Object.entries(settings).forEach(([k, val]) => {
    const cat = val.category || "general"
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push([k, val])
  })

  return (
    <div className="p-6 max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">{t("admin.systemSettings")}</h1>
          <p className="text-sm text-gray-500 mt-1">{t("admin.systemSettingsDesc")}</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className={"flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors " + (saved ? "bg-emerald-600 text-white" : "bg-indigo-600 hover:bg-indigo-700 text-white")}
        >
          {saving ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : saved ? (
            <Save className="w-4 h-4" />
          ) : (
            <Save className="w-4 h-4" />
          )}
          {saving ? t("admin.saving") : saved ? t("admin.saved") : t("admin.saveSettings")}
        </button>
      </div>
      {saveError && (
        <div className="text-red-400 text-sm mt-2">{saveError}</div>
      )}



      {categories.map((cat) => {
        const items = grouped[cat] || []
        if (items.length === 0 && cat !== "indexing") return null
        const isExpanded = expandedCategories[cat]
        return (
          <div key={cat} className="mb-4 bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
            <button
              onClick={() => toggleCat(cat)}
              className="w-full flex items-center gap-2 px-4 py-3 text-sm font-medium text-gray-300 hover:text-white hover:bg-gray-800/50 transition-colors"
            >
             {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
              <span className="uppercase tracking-wider">{t("admin.category." + cat)}</span>
            </button>
            {isExpanded && (
              <div className="px-4 pb-4 space-y-4">
                {cat === "indexing" && (
                  <div className="space-y-3">
                    <div className="text-xs text-gray-500 mb-2">
                      {t("admin.indexingMetadataHint")}
                    </div>
                    {metadataGroups.map((group) => {
                      const groupFields = metadataFields.filter((f) => f.group === group)
                      if (groupFields.length === 0) return null
                      return (
                        <div key={group} className="bg-gray-800/50 rounded-lg p-3">
                          <label className="flex items-center gap-2 cursor-pointer mb-2">
                            <input
                              type="checkbox"
                              checked={isAllGroupSelected(group)}
                              onChange={() => toggleGroup(group)}
                              className="rounded bg-gray-800 border-gray-700 text-indigo-600 focus:ring-indigo-600"
                            />
                            <span className="text-sm font-medium text-gray-300 uppercase tracking-wider">
                              {t("admin.metadataFieldGroup." + group, group)}
                            </span>
                          </label>
                          <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5 ml-5">
                            {groupFields.map((f) => (
                              <label key={f.key} className="flex items-center gap-1.5 cursor-pointer py-0.5">
                                <input
                                  type="checkbox"
                                  checked={isFieldSelected(f.key)}
                                  onChange={() => toggleField(f.key)}
                                  className="rounded bg-gray-800 border-gray-700 text-indigo-600 focus:ring-indigo-600 w-3.5 h-3.5"
                                />
                                <span className="text-xs text-gray-400 truncate" title={f.description}>
                                  {f.label}
                                </span>
                              </label>
                            ))}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
                 {items.map(([k, v]) => {
                  return k === "metadata_fields" ? null : (
                    <div key={k}>
                      <label className="block text-sm font-medium text-gray-400 mb-1">
                        {t("admin.settingLabel." + k, k)}
                        {v.description && (
                          <span className="ml-2 text-xs text-gray-600 font-normal">({v.description})</span>
                        )}
                      </label>
                      {(v.value_type === "string" || v.value_type === "int" || v.value_type === "float") && (
                        <input
                          type={v.value_type === "int" ? "number" : v.value_type === "float" ? "number" : "text"}
                          step={v.value_type === "float" ? "0.1" : "1"}
                          value={edits[k] ?? v.value}
                          onChange={(e) => setEdits((prev) => ({ ...prev, [k]: e.target.value }))}
                          className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-200 focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 outline-none"
                        />
                      )}
                      {v.value_type === "bool" && (
                        <div className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={edits[k] === "true"}
                            onChange={(e) => setEdits((prev) => ({ ...prev, [k]: e.target.checked ? "true" : "false" }))}
                            className="rounded bg-gray-800 border-gray-700 text-indigo-600 focus:ring-indigo-600"
                          />
                          <span className="text-sm text-gray-400">{t("admin.enabled")}</span>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
