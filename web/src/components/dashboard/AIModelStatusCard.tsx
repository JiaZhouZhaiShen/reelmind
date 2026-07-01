import { Eye, FileText, MessageSquareText, Tag, Volume2, Film, Brain } from "lucide-react"
import { useStore } from "../../stores/app"

const MODELS_DEF = [
  { key: "transnet", name: "TransNetV2", icon: Film, desc: "场景检测" },
  { key: "clip", name: "OpenCLIP", icon: Eye, desc: "语义搜索" },
  { key: "yolo", name: "YOLOv8n", icon: Tag, desc: "目标检测" },
  { key: "ocr", name: "PaddleOCR", icon: FileText, desc: "文字识别" },
  { key: "whisper", name: "faster-whisper", icon: MessageSquareText, desc: "语音识别" },
  { key: "diarization", name: "pyannote", icon: Volume2, desc: "说话人识别" },
]

export function AIModelStatusCard() {
  const sysStatus = useStore((s) => s.systemStatus)
  const loading = useStore((s) => s.sysStatusLoading)
  const models = sysStatus?.models ?? null
  const loadedCount = models ? Object.values(models).filter(Boolean).length : 0
  const totalCount = MODELS_DEF.length

  return (
    <div className="bg-gray-900/80 border border-gray-800 rounded-lg p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-purple-900/30 flex items-center justify-center">
            <Brain className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-300">AI 引擎</h3>
            <p className="text-xs text-gray-500">AI Engine Status</p>
          </div>
        </div>
        {loading ? (
          <div className="w-20 h-6 bg-gray-800 rounded animate-pulse" />
        ) : (
          <div className="text-right">
            <span className="text-lg font-bold text-gray-200">{loadedCount}<span className="text-sm text-gray-500">/{totalCount}</span></span>
            <p className="text-[10px] text-gray-600">已加载</p>
          </div>
        )}
      </div>

      {/* Model grid */}
      <div className="grid grid-cols-3 gap-2">
        {MODELS_DEF.map((m) => {
          const isLoaded = models ? models[m.key] : false
          const isUnknown = models === null && !loading

          return (
            <div
              key={m.key}
              className={`relative flex flex-col items-center gap-1.5 py-3 px-2 rounded-lg border transition-all duration-300 ${
                loading
                  ? "bg-gray-900/40 border-gray-800"
                  : isLoaded
                    ? "bg-emerald-900/15 border-emerald-800/40"
                    : isUnknown
                      ? "bg-gray-900/40 border-gray-800"
                      : "bg-gray-900/40 border-gray-800 opacity-60"
              }`}
            >
              {/* Glow dot */}
              <div
                className={`w-2 h-2 rounded-full transition-all duration-500 ${
                  loading
                    ? "bg-yellow-500 animate-pulse"
                    : isLoaded
                      ? "bg-emerald-400 shadow-sm shadow-emerald-400/60"
                      : "bg-gray-600"
                }`}
              />

              {/* Icon */}
              <div className={`transition-colors duration-300 ${
                loading ? "text-yellow-400/60" : isLoaded ? "text-emerald-400" : "text-gray-600"
              }`}>
                <m.icon className="w-5 h-5" />
              </div>

              {/* Name */}
              <span className={`text-[11px] font-medium text-center leading-tight ${
                loading ? "text-gray-500" : isLoaded ? "text-gray-200" : "text-gray-500"
              }`}>
                {m.name}
              </span>

              {/* Badge */}
              <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${
                loading
                  ? "bg-yellow-900/20 text-yellow-600"
                  : isLoaded
                    ? "bg-emerald-900/30 text-emerald-400"
                    : isUnknown
                      ? "bg-gray-800 text-gray-500"
                      : "bg-gray-800 text-gray-600"
              }`}>
                {loading ? "..." : isLoaded ? "已加载" : "未加载"}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
