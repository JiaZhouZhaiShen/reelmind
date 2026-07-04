import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Sparkles, Zap } from "lucide-react"
import { useSearchStore } from '../../stores/search'

export function AISearchBar() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const setSearchQuery = useSearchStore((s) => s.setSearchQuery)
  const [searchInput, setSearchInput] = useState("")

  const handleSearch = () => {
    if (searchInput.trim()) {
      setSearchQuery(searchInput.trim())
      navigate("/search")
    }
  }

  return (
    <div className="bg-gray-900/30 rounded-lg border border-gray-800 p-4">
      <div className="flex items-center gap-2 mb-3">
        <Zap className="w-4 h-4 text-gray-400" />
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">{t('aiSearchBar.title')}</h2>
      </div>
      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-xl">
          <Sparkles className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input type="text" value={searchInput} onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder={t("aiEngine.searchPlaceholder")}
            className="w-full pl-9 pr-4 py-2 bg-gray-900 border border-gray-700 rounded-xl text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500/50" />
        </div>
        <button onClick={handleSearch}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg">
          <Zap className="w-4 h-4 inline-block mr-1.5 -mt-0.5" />{t("aiEngine.searchBtn")}
        </button>
      </div>
    </div>
  )
}
