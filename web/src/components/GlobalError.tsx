import { X } from 'lucide-react'
import { useStore } from '../stores/app'

/**
 * GlobalError — displays the store.error message as a dismissable banner
 * Iron Rule ⑩: All API .catch() must give user-visible feedback.
 * Iron Rule ⑪: Unified error type and display location.
 */
export function GlobalError() {
  const error = useStore((s) => s.error)
  const clearError = useStore((s) => s.clearError)

  if (!error) return null

  return (
    <div className="bg-red-900/20 border-b border-red-800/30 px-6 py-2.5 flex items-start gap-3">
      <p className="text-sm text-red-400 flex-1 leading-relaxed">{error}</p>
      <button
        onClick={clearError}
        className="text-red-400 hover:text-red-300 transition-colors shrink-0 mt-0.5"
        aria-label="关闭错误提示"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}
