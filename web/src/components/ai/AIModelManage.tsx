import { useTranslation } from "react-i18next"
import { Wrench, Eye, FileText, MessageSquareText, Tag, Volume2, Film, Loader2 } from "lucide-react"
import { useAIStore } from "../../stores/ai"

const MODEL_SIZES: Record<string, string> = {
  whisper: "2.9 GB",
  clip: "600 MB",
  transnet: "120 MB",
  yolo: "6 MB",
  ocr: "200 MB",
  diarization: "1.1 GB",
}

const modelList = [
  { name: "TransNetV2", icon: Film, key: "transnet", desc: "" },
  { name: "YOLOv8n", icon: Tag, key: "yolo", desc: "" },
  { name: "PaddleOCR", icon: FileText, key: "ocr", desc: "" },
  { name: "OpenCLIP", icon: Eye, key: "clip", desc: "ViT-B-16 / laion2b" },
  { name: "faster-whisper", icon: MessageSquareText, key: "whisper", desc: "large-v3 / float16" },
  { name: "pyannote-audio", icon: Volume2, key: "diarization", desc: "" },
]

export function AIModelManage() {
  const { t } = useTranslation()
  const modelStatus = useAIStore((s) => s.modelStatus)
  const modelStatusLoading = useAIStore((s) => s.modelStatusLoading)
  const downloadingSet = useAIStore((s) => s.downloadingSet)
  const handleModelAction = useAIStore((s) => s.handleModelAction)

  const resolvedModels = modelList.map(m => ({
    ...m,
    desc: m.desc || (
      m.key === "transnet" ? t("aiEngine.transnetDesc") :
      m.key === "yolo" ? t("aiEngine.yoloDesc") :
      m.key === "ocr" ? t("aiEngine.ocrDesc") :
      m.key === "diarization" ? t("aiEngine.diarizationDesc") : m.desc
    )
  }))

  return (
    <div className="bg-gray-900/30 rounded-lg border border-gray-800 p-4">
      <div className="flex items-center gap-2 mb-3">
        <Wrench className="w-4 h-4 text-gray-400" />
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">模型管理</h2>
      </div>
      <div className="space-y-2">
        {resolvedModels.map((m) => {
          const isLoaded = modelStatus ? modelStatus[m.key] : false
          const isLoading = modelStatusLoading && modelStatus === null
          const isDownloading = downloadingSet.has(m.key)
          const size = MODEL_SIZES[m.key]
          return (
            <div key={m.name} className="flex items-center gap-3 bg-gray-900/50 rounded-lg p-3 border border-gray-800">
              <div className="flex-1 flex items-center gap-3 min-w-0">
                <div className={"w-8 h-8 rounded-lg flex items-center justify-center " + (isLoaded ? "bg-emerald-900/20" : (isLoading ? "bg-yellow-900/20" : "bg-gray-800"))}>
                  <m.icon className={"w-4 h-4 " + (isLoaded ? "text-emerald-400" : (isLoading ? "text-yellow-400" : "text-gray-600"))} />
                </div>
                <div>
                  <p className="text-sm text-gray-200">{m.name}</p>
                  <p className="text-xs text-gray-500">{isLoading ? t("aiEngine.modelDetecting") : isDownloading ? t("aiEngine.loading") : isLoaded ? t("aiEngine.loaded") + " | " + size : size}</p>
                </div>
              </div>
              {isDownloading ? <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
                : <button onClick={() => handleModelAction(m.key, isLoaded ? "unload" : "load")}
                    className={"px-3 py-1.5 text-xs font-medium rounded-lg transition-colors " + (isLoaded ? "bg-red-900/30 text-red-400 hover:bg-red-900/50" : "bg-emerald-900/30 text-emerald-400 hover:bg-emerald-900/50")}>
                  {isLoading ? t("aiEngine.modelDetecting") : isLoaded ? t("aiEngine.unload") : t("aiEngine.load")}
                </button>}
              <div className={"w-2 h-2 rounded-full shrink-0 transition-colors " + (isLoading ? "bg-yellow-500 animate-pulse" : isLoaded ? "bg-emerald-500" : "bg-gray-700")} />
            </div>
          )
        })}
      </div>
    </div>
  )
}
