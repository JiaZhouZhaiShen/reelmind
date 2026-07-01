import { useTranslation } from "react-i18next"
import { Settings as SettingsIcon } from "lucide-react"

interface Props {
  pipelineConfig: Record<string, boolean | number>
  setPipelineConfig: (fn: (prev: Record<string, boolean | number>) => Record<string, boolean | number>) => void
}

export function AISettings({ pipelineConfig, setPipelineConfig }: Props) {
  const { t } = useTranslation()

  const pipelineLabelMap: Record<string, string> = {
    diarization: t('aiEngine.diarization'),
    whisper: t('aiEngine.whisper'),
    clip: t('aiEngine.clip'),
    transnet: t('aiEngine.transnetDesc'),
    yolo: t('aiEngine.yolo'),
    ocr: "OCR",
  }

  return (
    <div className="space-y-4">
      {/* Pipeline Steps */}
      <div className="bg-gray-900/30 rounded-lg border border-gray-800 p-4">
        <h3 className="text-sm font-medium text-gray-200 mb-3">{t('aiEngine.stepsTitle')}</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
          {Object.entries(pipelineConfig).filter(([k]) => k !== "autoRun" && k !== "batchSize" && !k.startsWith("autoRun")).map(([key, enabled]) => (
            <label key={key} className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={enabled as boolean}
                onChange={() => setPipelineConfig(p => ({ ...p, [key]: !(p as any)[key] }))}
                className="rounded border-gray-600 text-indigo-500 focus:ring-indigo-500/40 bg-gray-800" />
              <span className="text-xs text-gray-400">{pipelineLabelMap[key] || key}</span>
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}
