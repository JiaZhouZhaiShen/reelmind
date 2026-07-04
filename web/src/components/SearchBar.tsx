import { Search, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useSearchStore } from '../stores/search'
import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'

export function SearchBar({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation()
  const storeQuery = useSearchStore((s) => s.searchQuery)
  const [query, setQuery] = useState(storeQuery || '')
const setSearchQuery = useSearchStore((s) => s.setSearchQuery)
 const triggerSearch = useSearchStore((s) => s.triggerSearch)
const navigate = useNavigate()

const handleSearch = useCallback((e: React.FormEvent) => {
  e.preventDefault()
 setSearchQuery(query)
  triggerSearch()
 navigate('/search')
}, [query, navigate, setSearchQuery, triggerSearch])

 return (
   <form onSubmit={handleSearch} className={`relative ${compact ? 'w-full max-w-sm' : 'w-full max-w-2xl'}`}>
     <input
       type="text"
       value={query}
       onChange={(e) => setQuery(e.target.value)}
       placeholder={t('searchBar.placeholder')}
        className={`w-full bg-gray-800/80 border border-gray-700/80 rounded-l-xl pl-10 pr-8 text-gray-200 placeholder-gray-500 focus:outline-none focus:border-indigo-500/60 focus:ring-2 focus:ring-indigo-500/20 focus:bg-gray-800 transition-all duration-200 ${
         compact ? 'py-1.5 text-sm' : 'py-3 text-base'
       }`}
     />
     {query && (
       <button
         type="button"
         onClick={() => { setQuery(''); setSearchQuery(''); }}
       className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
        style={{ right: compact ? '2.75rem' : '3.5rem' }}
      >
         <X className="w-4 h-4" />
       </button>
     )}
      <button
        type="submit"
        className={`absolute right-0 top-0 h-full flex items-center justify-center bg-indigo-600 hover:bg-indigo-500 text-white transition-colors rounded-r-xl ${
          compact ? 'px-3' : 'px-5'
        }`}
        title={t('common.search')}
      >
        <Search className={`${compact ? 'w-3.5 h-3.5' : 'w-4 h-4'}`} />
        {!compact && <span className="ml-1.5 text-sm">{t('common.search')}</span>}
      </button>
    </form>
  )
}
