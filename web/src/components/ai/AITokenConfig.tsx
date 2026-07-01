import { useTranslation } from "react-i18next"
import { KeyRound } from "lucide-react"
import { useAIStore } from "../../stores/ai"

export function AITokenConfig() {
  const { t } = useTranslation()
  const hfToken = useAIStore((s) => s.hfToken)
  const hfTokenSet = useAIStore((s) => s.hfTokenSet)
  const setHfToken = useAIStore((s) => s.setHfToken)
  const saveHfToken = useAIStore((s) => s.saveHfToken)

  const handleSave = async () => {
    await saveHfToken()
    alert(t("aiEngine.hfSaved"))
  }

  return (
    <div className="bg-gray-900/30 rounded-lg border border-gray-800 p-4">
      <div className="flex items-center gap-2 mb-3">
        <KeyRound className="w-4 h-4 text-gray-400" />
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">TOKEN 配置</h2>
      </div>
      <div>
        <h3 className="text-sm font-medium text-gray-200 mb-3 flex items-center gap-2">
          {t("aiEngine.hfToken")}
          <span className={"inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full " + (hfTokenSet ? "bg-emerald-900/30 text-emerald-400" : "bg-gray-800 text-gray-500")}>
            <span className={"w-1.5 h-1.5 rounded-full " + (hfTokenSet ? "bg-emerald-400" : "bg-gray-600")} />
            {hfTokenSet ? t("aiEngine.hfConfigured") : t("aiEngine.hfNotConfigured")}
          </span>
        </h3>
        <p className="text-xs text-gray-500 mb-3">{t("aiEngine.hfTokenDesc")} <a href="https://huggingface.co/settings/tokens" target="_blank" rel="noreferrer" className="text-indigo-400 hover:underline">{t("aiEngine.hfTokenLink")}</a> {t("aiEngine.hfTokenCreate")}</p>
        <div className="flex items-center gap-2">
          <input type="password" value={hfToken} onChange={(e) => setHfToken(e.target.value)}
            placeholder={t("aiEngine.hfTokenPlaceholder")}
            className="flex-1 max-w-md px-3 py-2 bg-gray-900 border border-gray-700 rounded-xl text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500/50" />
          <button onClick={handleSave}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg">{t("aiEngine.save")}</button>
        </div>
      </div>
    </div>
  )
}
