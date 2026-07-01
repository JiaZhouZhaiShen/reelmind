import { Search, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '../stores/app'
import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'

export function SearchBar({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation()
  const storeQuery = useStore((s) => s.searchQuery)
  const [query, setQuery] = useState(storeQuery || '')
 const setSearchQuery = useStore((s) => s.setSearchQuery)
 const navigate = useNavigate()

  const handleSearch = useCallback((e: React.FormEvent) => {
    e.preventDefault()
   if (!query.trim()) return
   setSearchQuery(query)
   navigate('/search')
 }, [query, navigate, setSearchQuery])

  return (
    <form onSubmit={handleSearch} className={`relative ${compact ? 'w-full max-w-sm' : 'w-full max-w-2xl'}`}>
      <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t('searchBar.placeholder')}
        className={`w-full bg-gray-800/80 border border-gray-700/80 rounded-xl pl-10 pr-8 text-gray-200 placeholder-gray-500 focus:outline-none focus:border-indigo-500/60 focus:ring-2 focus:ring-indigo-500/20 focus:bg-gray-800 transition-all duration-200 ${
          compact ? 'py-1.5 text-sm' : 'py-3 text-base'
        }`}
      />
      {query && (
        <button
          type="button"
          onClick={() => setQuery('')}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </form>
  )
}
