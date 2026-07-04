import { useTranslation } from "react-i18next"

interface Props {
  totalPending: number
  completed: number
  failed: number
  status: string
}

export function AutoRunProgressBar({ totalPending, completed, failed, status }: Props) {
  const { t } = useTranslation()
  const progress = totalPending > 0 ? Math.round((completed + failed) / totalPending * 100) : 0
  if (totalPending === 0 && completed === 0 && failed === 0) return null

  return (
    <div className="space-y-1">
      <div className="w-full bg-gray-800 rounded-full h-2">
        <div className={"h-2 rounded-full transition-all duration-300 " + (
          status === "running" ? "bg-indigo-500" :
          status === "completed" ? "bg-emerald-500" :
          status === "error" ? "bg-red-500" :
          "bg-gray-700"
        )}
        style={{ width: progress + "%" }} />
      </div>
      {totalPending > 0 && (
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="text-emerald-400">{completed} {t("aiEngine.completedCount")}</span>
          {failed > 0 && <><span className="text-gray-600">/</span><span className="text-red-400">{failed} {t("aiEngine.failedCount")}</span></>}
          <span className="text-gray-600">/</span>
          <span className="text-gray-400">{t("aiEngine.pending")} {totalPending - completed - failed}</span>
        </div>
      )}
    </div>
  )
}
