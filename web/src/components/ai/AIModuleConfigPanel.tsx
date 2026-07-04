import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  Video, Search, Type, Camera, Mic, Users,
  ChevronDown, ChevronRight, Save, Loader2,
  CheckCircle2, XCircle, Settings2,
} from "lucide-react"
import { useAIStore } from "../../stores/ai"

// ── Module Metadata ──

interface FieldDef {
  key: string
  label: string
  type: "boolean" | "number" | "float" | "string" | "select"
  options?: { label: string; value: string }[]
  min?: number
  max?: number
  step?: number
  placeholder?: string
}

interface ModuleDef {
  id: string
  label: string
  icon: any
  desc: string
  fields: FieldDef[]
}

const MODULES: ModuleDef[] = [
  {
    id: "scene", label: "场景切割", icon: Video,
    desc: "基于镜头切换检测的视频片段分割",
    fields: [
      { key: "enabled", label: "启用", type: "boolean" },
      { key: "threshold", label: "检测阈值", type: "float", min: 0, max: 1, step: 0.01 },
      { key: "min_scene_len", label: "最小场景长度 (帧)", type: "number", min: 1 },
      { key: "device", label: "计算设备", type: "select",
        options: [{ label: "CUDA", value: "cuda" }, { label: "CPU", value: "cpu" }] },
    ],
  },
  {
    id: "yolo", label: "YOLO 目标检测", icon: Search,
    desc: "识别视频中的物体、人物等目标",
    fields: [
      { key: "enabled", label: "启用", type: "boolean" },
      { key: "model_name", label: "模型名称", type: "string", placeholder: "yolov8n.pt" },
      { key: "confidence_threshold", label: "置信度阈值", type: "float", min: 0, max: 1, step: 0.01 },
      { key: "iou_threshold", label: "IOU 阈值", type: "float", min: 0, max: 1, step: 0.01 },
      { key: "max_detections", label: "最大检测数", type: "number", min: 1 },
      { key: "device", label: "计算设备", type: "select",
        options: [{ label: "CUDA", value: "cuda" }, { label: "CPU", value: "cpu" }] },
    ],
  },
  {
    id: "ocr", label: "OCR 文字识别", icon: Type,
    desc: "从视频帧中提取可见文本",
    fields: [
      { key: "enabled", label: "启用", type: "boolean" },
      { key: "lang", label: "语言", type: "string", placeholder: "ch" },
      { key: "confidence_threshold", label: "置信度阈值", type: "float", min: 0, max: 1, step: 0.01 },
      { key: "use_gpu", label: "使用 GPU", type: "boolean" },
      { key: "max_text_length", label: "最大文本长度", type: "number", min: 1 },
      { key: "det_db_threshold", label: "检测阈值", type: "float", min: 0, max: 1, step: 0.01 },
    ],
  },
  {
    id: "clip", label: "CLIP 语义理解", icon: Camera,
    desc: "通过 CLIP 模型分析视频帧语义内容",
    fields: [
      { key: "enabled", label: "启用", type: "boolean" },
      { key: "model_name", label: "模型名称", type: "string", placeholder: "ViT-B-16" },
      { key: "pretrained", label: "预训练权重", type: "string", placeholder: "laion2b_s34b_b88k" },
      { key: "batch_size", label: "批处理大小", type: "number", min: 1 },
      { key: "default_top_k", label: "默认 Top-K", type: "number", min: 1 },
    ],
  },
  {
    id: "whisper", label: "Whisper 语音转文字", icon: Mic,
    desc: "OpenAI Whisper 语音识别和转录",
    fields: [
      { key: "enabled", label: "启用", type: "boolean" },
      { key: "model_size", label: "模型大小", type: "select",
        options: [
          { label: "tiny", value: "tiny" }, { label: "base", value: "base" },
          { label: "small", value: "small" }, { label: "medium", value: "medium" },
          { label: "large", value: "large" },
        ] },
      { key: "language", label: "语言", type: "string", placeholder: "zh" },
      { key: "compute_type", label: "计算精度", type: "select",
        options: [
          { label: "float16", value: "float16" }, { label: "float32", value: "float32" },
          { label: "int8", value: "int8" },
        ] },
      { key: "device", label: "计算设备", type: "select",
        options: [{ label: "CUDA", value: "cuda" }, { label: "CPU", value: "cpu" }] },
      { key: "beam_size", label: "Beam 搜索大小", type: "number", min: 1 },
      { key: "vad_filter", label: "VAD 过滤", type: "boolean" },
    ],
  },
  {
    id: "diarization", label: "说话人分离", icon: Users,
    desc: "识别视频中不同说话人并标注其发言段落",
    fields: [
      { key: "enabled", label: "启用", type: "boolean" },
      { key: "pipeline_name", label: "管道名称", type: "string", placeholder: "pyannote/speaker-diarization-3.1" },
      { key: "cluster_threshold", label: "聚类阈值", type: "float", min: 0, max: 1, step: 0.01 },
      { key: "num_speakers", label: "说话人数量（0=自动检测）", type: "number", min: 0 },
    ],
  },
]

// ── Field Input ──

function FieldInput({ field, label, value, onChange }: { field: FieldDef; label: string; value: any; onChange: (v: any) => void }) {
  if (field.type === "boolean") {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-400 w-24 shrink-0">{label}</span>
        <div
          className={"w-8 h-4 rounded-full transition-colors relative cursor-pointer " + (value ? "bg-indigo-600" : "bg-gray-700")}
          onClick={() => onChange(!value)}
        >
          <div className={"w-3.5 h-3.5 rounded-full bg-white absolute top-0.5 transition-transform " + (value ? "translate-x-4" : "translate-x-0.5")} />
        </div>
      </div>
    )
  }

  if (field.type === "select") {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-400 w-24 shrink-0 truncate">{label}</span>
        <select
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
          className="flex-1 px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-xs text-gray-200 focus:outline-none focus:border-indigo-600"
        >
          {(field.options || []).map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>
    )
  }

  if (field.type === "string") {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-400 w-24 shrink-0 truncate">{label}</span>
        <input
          type="text"
          value={value ?? ""}
          placeholder={field.placeholder}
          onChange={(e) => onChange(e.target.value)}
          className="flex-1 px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-xs text-gray-200 focus:outline-none focus:border-indigo-600"
        />
      </div>
    )
  }

  const isFloat = field.type === "float"
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-400 w-24 shrink-0 truncate">{label}</span>
      <input
        type="number"
        min={field.min}
        max={field.max}
        step={isFloat ? field.step ?? 0.01 : 1}
        value={value ?? ""}
        onChange={(e) => {
          const v = e.target.value === "" ? (field.min ?? 0) : isFloat ? parseFloat(e.target.value) : parseInt(e.target.value)
          onChange(v)
        }}
        className="flex-1 px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-xs text-gray-200 focus:outline-none focus:border-indigo-600"
      />
    </div>
  )
}

// ── Main Component ──

export function AIModuleConfigPanel() {
  const { t } = useTranslation()
  // UI state only
  const [localCfg, setLocalCfg] = useState<Record<string, any> | null>(null)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [dirty, setDirty] = useState(false)
  const [saveMsg, setSaveMsg] = useState<"idle" | "ok" | "fail">("idle")

  // Business state from store
  const storeCfg = useAIStore((s) => s.moduleConfig)
  const loading = useAIStore((s) => s.moduleConfigLoading)
  const saving = useAIStore((s) => s.moduleConfigSaving)
  const fetchModuleConfig = useAIStore((s) => s.fetchModuleConfig)
  const saveModuleConfig = useAIStore((s) => s.saveModuleConfig)

  // Load on mount
  useEffect(() => { if (!storeCfg) fetchModuleConfig() }, [])

  // Sync store config → local editable copy when not dirty
  useEffect(() => {
    if (storeCfg && !dirty && !localCfg) {
      setLocalCfg(JSON.parse(JSON.stringify(storeCfg)))
    }
  }, [storeCfg, dirty, localCfg])

  const patch = (modId: string, key: string, val: any) => {
    setLocalCfg((prev) => ({
      ...prev,
      [modId]: { ...(prev?.[modId] || {}), [key]: val },
    }))
    setDirty(true)
  }

  const handleSave = async () => {
    if (!localCfg || !dirty) return
    setSaveMsg("idle")
    const ok = await saveModuleConfig(localCfg)
    setSaveMsg(ok ? "ok" : "fail")
    if (ok) setDirty(false)
    setTimeout(() => setSaveMsg("idle"), ok ? 2000 : 3000)
  }

  if (loading && !storeCfg) {
    return (
      <div className="bg-gray-900/30 rounded-lg border border-gray-800 p-6">
        <div className="flex items-center justify-center text-gray-500">
          <Loader2 className="w-5 h-5 animate-spin mr-2" />
          {t('aiModuleConfig.loading')}
        </div>
      </div>
    )
  }

  return (
    <div className="bg-gray-900/30 rounded-lg border border-gray-800">
      {/* header */}
      <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-3">
        <div className="w-7 h-7 rounded-lg bg-gray-800 flex items-center justify-center">
          <Settings2 className="w-4 h-4 text-indigo-400" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-white">{t('aiModuleConfig.title')}</h3>
          <p className="text-xs text-gray-500">{t('aiModuleConfig.subtitle')}</p>
        </div>
        {dirty && (
          <span className="text-xs text-amber-400 font-medium bg-amber-900/30 px-2 py-0.5 rounded-full">
            {t('aiModuleConfig.unsaved')}
          </span>
        )}
      </div>

      <div className="p-4 space-y-3">
        {MODULES.map((mod) => {
          const modCfg = localCfg?.[mod.id] || {}
          const on = modCfg.enabled !== false
          const open = expanded[mod.id] ?? false
          const Icon = mod.icon

          return (
            <div key={mod.id} className="rounded-lg border border-gray-800 bg-gray-800/20 overflow-hidden">
              <div
                className="flex items-center gap-3 px-3.5 py-2.5 cursor-pointer select-none hover:bg-gray-800/40 transition-colors"
                onClick={() => setExpanded((p) => ({ ...p, [mod.id]: !p[mod.id] }))}
              >
                {open ? <ChevronDown className="w-4 h-4 text-gray-500 shrink-0" /> : <ChevronRight className="w-4 h-4 text-gray-500 shrink-0" />}
                <div className="w-7 h-7 rounded-md bg-gray-800 flex items-center justify-center shrink-0">
                  <Icon className="w-4 h-4 text-indigo-400" />
                </div>
                <span className="flex-1 text-sm font-medium text-gray-200">{t('aiModuleConfig.' + mod.id + '.label')}</span>
                <span className="text-xs text-gray-500 mr-2">{t('aiModuleConfig.' + mod.id + '.desc')}</span>
                <label
                  onClick={(e) => { e.stopPropagation(); patch(mod.id, "enabled", !on) }}
                  className={"w-9 h-5 rounded-full transition-colors relative cursor-pointer shrink-0 " + (on ? "bg-indigo-600" : "bg-gray-700")}
                >
                  <div className={"w-4 h-4 rounded-full bg-white absolute top-0.5 transition-transform " + (on ? "translate-x-4" : "translate-x-0.5")} />
                </label>
              </div>

              {open && (
                <div className="px-3.5 pb-3.5 pt-1 border-t border-gray-800/40 grid grid-cols-2 gap-x-4 gap-y-2.5">
                  {mod.fields.filter((f) => f.key !== "enabled").map((f) => (
                    <FieldInput key={f.key} field={f} label={t('aiModuleConfig.' + mod.id + '.fields.' + f.key)} value={modCfg[f.key]} onChange={(v) => patch(mod.id, f.key, v)} />
                  ))}
                </div>
              )}
            </div>
          )
        })}

        {/* save bar */}
        <div className="flex items-center gap-3 pt-2 border-t border-gray-800">
          <div className="flex-1 min-w-0">
            {saveMsg === "ok" && <span className="text-xs text-emerald-400 flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" /> {t('aiModuleConfig.saved')}</span>}
            {saveMsg === "fail" && <span className="text-xs text-red-400 flex items-center gap-1"><XCircle className="w-3.5 h-3.5" /> {t('aiModuleConfig.saveFailed')}</span>}
            {saving && <span className="text-xs text-gray-400 flex items-center gap-1"><Loader2 className="w-3.5 h-3.5 animate-spin" /> {t('aiModuleConfig.saving')}</span>}
          </div>
          <button
            onClick={handleSave}
            disabled={saving || !dirty}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-40 transition-all"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            {saving ? t('aiModuleConfig.saving') : t('aiModuleConfig.save')}
          </button>
        </div>
      </div>
    </div>
  )
}
