import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { Sparkles } from "lucide-react"
import { useAIStore } from "../stores/ai"
import { X } from "lucide-react"
import { AISearchBar } from "../components/ai/AISearchBar"
import { AIPendingOverview } from "../components/ai/AIPendingOverview"
import { AITokenConfig } from "../components/ai/AITokenConfig"
import { AIPipelineConfig } from "../components/ai/AIPipelineConfig"
import { AIModuleConfigPanel } from "../components/ai/AIModuleConfigPanel"
import { GPUInfo } from "../components/ai/GPUInfo"
import { AIModelStatus } from "../components/ai/AIModelStatus"
import { AIModelManage } from "../components/ai/AIModelManage"
import { ErrorBoundary } from "../components/ErrorBoundary"

export function AIEnginePage() {
  const { t } = useTranslation()
  const error = useAIStore((s) => s.error)
  const clearError = useAIStore((s) => s.clearError)

  // Single lifecycle: start polling + SSE on mount, clean up on unmount
  useEffect(() => {
    const store = useAIStore.getState()
    const stopPolling = store.startPolling()
    const stopSSE = store.startSSE()
    return () => { stopPolling(); stopSSE() }
  }, [])

  return (
    <ErrorBoundary>
      <div className="h-full flex flex-col">
        <div className="px-6 py-4 border-b border-gray-800 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gray-800 flex items-center justify-center">
              <Sparkles className="w-4 h-4 text-indigo-400" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-white">{t("aiEngine.title")}</h1>
              <p className="text-xs text-gray-500">{t("aiEngine.subtitle")}</p>
            </div>
          </div>
        </div>

        {error && (
          <div className="px-6 py-2 bg-red-900/40 border-b border-red-800/50 flex items-center gap-2 text-xs text-red-300">
            <span className="flex-1">{error}</span>
            <button onClick={clearError} className="p-0.5 hover:bg-red-800/50 rounded transition-colors">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          <div className="max-w-7xl mx-auto p-6 space-y-6">
            <AISearchBar />
            <AIPendingOverview />
            <AIModelStatus />
            <AIPipelineConfig />            <AIModuleConfigPanel />
            <GPUInfo />
            <AIModelManage />
            <AITokenConfig />
          </div>
        </div>
      </div>
    </ErrorBoundary>
  )
}
