import { useTranslation } from "react-i18next"
import { memo } from 'react'
import { Cpu, Eye, FileText, MessageSquareText, Tag, Volume2, Film } from "lucide-react"
import { useAIStore } from "../../stores/ai"

const modelList = [
  { name: "TransNetV2", icon: Film, key: "transnet", desc: "" },
  { name: "YOLOv8n", icon: Tag, key: "yolo", desc: "" },
  { name: "PaddleOCR", icon: FileText, key: "ocr", desc: "" },
  { name: "OpenCLIP", icon: Eye, key: "clip", desc: "ViT-B-16 / laion2b" },
  { name: "faster-whisper", icon: MessageSquareText, key: "whisper", desc: "large-v3 / float16" },
  { name: "pyannote-audio", icon: Volume2, key: "diarization", desc: "" },
]

export const AIModelStatus = memo(function AIModelStatus() {
  const { t } = useTranslation()
  const modelStatus = useAIStore((s) => s.modelStatus)
  const modelStatusLoading = useAIStore((s) => s.modelStatusLoading)

  const resolvedModels = modelList.map(m => ({
    ...m,
    desc: m.desc || (
      m.key === "transnet" ? t('aiEngine.transnetDesc') :
      m.key === "yolo" ? t('aiEngine.yoloDesc') :
      m.key === "ocr" ? t('aiEngine.ocrDesc') :
      m.key === "diarization" ? t('aiEngine.diarizationDesc') : m.desc
    )
  }))

  const isInitialLoading = modelStatusLoading && modelStatus === null

  return (
    <div className="bg-gray-900/30 rounded-lg border border-gray-800 p-4">
      <div className="flex items-center gap-2 mb-3">
        <Cpu className="w-4 h-4 text-gray-400" />
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">{t('aiModelStatus.title')}</h2>
        <span className="text-[10px] text-gray-600 ml-auto">Model Status</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        {resolvedModels.map((m) => {
          const isLoaded = modelStatus ? modelStatus[m.key] : false
          return (
            <div key={m.name} className="flex items-center gap-3 bg-gray-900/50 rounded-lg p-3 border border-gray-800">
              <div className={"w-8 h-8 rounded-lg flex items-center justify-center " + (isLoaded ? "bg-emerald-900/20" : "bg-gray-800")}>
                <m.icon className={"w-4 h-4 " + (isLoaded ? "text-emerald-400" : "text-gray-600")} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-200 truncate">{m.name}</p>
                <p className="text-xs text-gray-500">{m.desc}</p>
              </div>
              <div className={"w-2 h-2 rounded-full shrink-0 transition-colors " + (isLoaded
                ? "bg-emerald-500 shadow-sm shadow-emerald-500/50"
                : "bg-gray-700")} />
            </div>
          )
        })}
      </div>
      {isInitialLoading && (
        <p className="text-xs text-gray-500 mt-2 text-center">Loading model status...</p>
      )}
    </div>
  )
});
