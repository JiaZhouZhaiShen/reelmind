import { memo } from 'react'
import { Menu, Film, Heart, Library, Search, BarChart3, Settings, User, LogOut, Shield, UserCircle, Languages, Tags, Tag, Users, Activity, Calendar, FolderTree, Sparkles, FileText, Scan } from 'lucide-react'
import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useLibraryStore } from '../stores/library'
import { useAssetStore } from '../stores/asset'
import { useAuthStore } from '../stores/auth'
import { useTranslation } from 'react-i18next'
import i18n from '../i18n/config'

export const Sidebar = memo(function Sidebar() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const libraries = useLibraryStore((s) => s.libraries)
  const selectedLibraryId = useLibraryStore((s) => s.selectedLibraryId)
  const selectLibrary = useLibraryStore((s) => s.selectLibrary)
  const showFavorites = useAssetStore((s) => s.showFavorites)
  const toggleShowFavorites = useAssetStore((s) => s.toggleShowFavorites)
  const stats = useLibraryStore((s) => s.stats)
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const [collapsed, setCollapsed] = useState(window.innerWidth < 640)
  useEffect(() => {
    const onResize = () => setCollapsed(window.innerWidth < 640)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const isActive = (path: string) => location.pathname === path

 const handleLibrarySelect = (id: string | null) => {
   selectLibrary(id)
   navigate('/')
    // AssetGrid handles its own data loading via fetchPage — no need to preload here
 }

  return (
    <>
    <style>{`.collapsed .sl{display:none}.collapsed .sh{display:none}`}</style>
    <aside className={`bg-gray-900 border-r border-gray-800 flex flex-col h-full transition-all duration-200 ${collapsed ? "w-16 collapsed" : "w-64"}`}>
      {/* Logo */}
      <div className="px-6 py-5 border-b border-gray-800 shrink-0">
        <div className="flex flex-col items-center gap-1">
          <div className="flex items-center gap-3">
            <div className="relative shrink-0">
            <div className="absolute inset-0 rounded-lg bg-gradient-to-br from-indigo-500/40 to-purple-500/20 blur-sm" />
            <img src="/logo.png" alt="ReelMind" className="relative w-8 h-8 rounded-lg ring-1 ring-white/10 object-cover" />
            </div>
            <h1 className="text-xl font-extrabold tracking-wide bg-gradient-to-r from-white via-indigo-100 to-indigo-400 bg-clip-text text-transparent leading-tight">
              ReelMind
            </h1>
          </div>
          <p className="text-[11px] text-gray-400 flex items-center gap-1.5">
            <span className="sl">{t('app.author')}</span>
            <span className="text-gray-600">·</span>
            <span className="text-indigo-400/80 font-mono font-medium">v{__APP_VERSION__}</span>
          </p>
        </div>
        <button onClick={() => setCollapsed((p) => !p)} className="mt-2 w-full flex items-center justify-center px-2 py-1.5 rounded-lg text-gray-400 hover:text-indigo-400 hover:bg-indigo-900/20 transition-colors"><Menu className="w-4 h-4" /></button>
      </div>

      {/* Scrollable middle */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {/* Main Nav */}
        <nav className="px-3 py-4 space-y-1">
        <button
       onClick={() => { selectLibrary(null); if (!showFavorites) navigate('/'); else toggleShowFavorites() }}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
            isActive('/') && !selectedLibraryId && !showFavorites
              ? 'bg-indigo-600/20 text-indigo-400'
              : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
          }`}
        >
          <Film className="w-4 h-4" />
          <span className="sl">{t('sidebar.allVideos')}</span>
          {stats && <span className="ml-auto text-xs text-gray-600">{stats.total_assets}</span>}
        </button>

        <button
          onClick={() => { selectLibrary(null); toggleShowFavorites(); navigate("/") }}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
            showFavorites
              ? 'bg-indigo-600/20 text-indigo-400'
              : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
          }`}
        >
          <Heart className="w-4 h-4" />
          <span className="sl">{t('sidebar.favorites')}</span>
        </button>

        <button
          onClick={() => { if (showFavorites) toggleShowFavorites(); selectLibrary(null); navigate('/tags/browse') }}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${location.pathname.startsWith('/tags/browse') ? 'bg-indigo-600/20 text-indigo-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'}`}
        >
          <Tags className="w-4 h-4" />
          <span className="sl">{t('sidebar.browseTags')}</span>
        </button>
        <button
          onClick={() => { if (showFavorites) toggleShowFavorites(); selectLibrary(null); navigate('/yolo-tags/browse') }}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${location.pathname.startsWith('/yolo-tags/browse') ? 'bg-amber-600/20 text-amber-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'}`}
        >
          <Scan className="w-4 h-4" />
          <span className="sl">YOLO 标签</span>
        </button>

        {/* Timeline */}
        <button
          onClick={() => { if (showFavorites) toggleShowFavorites(); selectLibrary(null); navigate('/timeline') }}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${isActive('/timeline') ? 'bg-indigo-600/20 text-indigo-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'}`}
        >
          <Calendar className="w-4 h-4" />
          <span className="sl">{t('sidebar.timeline')}</span>
        </button>

        {/* Directory */}
        <button
          onClick={() => { if (showFavorites) toggleShowFavorites(); selectLibrary(null); navigate('/directory') }}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${isActive('/directory') ? 'bg-indigo-600/20 text-indigo-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'}`}
        >
          <FolderTree className="w-4 h-4" />
          <span className="sl">{t('sidebar.directory')}</span>
        </button>

        <button
          onClick={() => { if (showFavorites) toggleShowFavorites(); navigate('/search') }}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
            isActive('/search') ? 'bg-indigo-600/20 text-indigo-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
          }`}
        >
         <Search className="w-4 h-4" />
         <span className="sl">{t('sidebar.search')}</span>
       </button>


        <button
          onClick={() => { if (showFavorites) toggleShowFavorites(); navigate('/libraries') }}
          className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
            isActive('/libraries') ? 'bg-indigo-600/20 text-indigo-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
          }`}
        >
          <Library className="w-4 h-4" />
          <span className="sl">{t('sidebar.libraries')}</span>
        </button>
      </nav>

      {/* Libraries */}
      <div className="px-3 py-2 border-t border-gray-800">
        <h2 className="sh px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">{t('sidebar.librariesSection')}</h2>
        <div className="space-y-1 max-h-48 overflow-y-auto">
          {libraries.map((lib) => (
            <button
              key={lib.id}
              onClick={() => handleLibrarySelect(lib.id)}
              className={`w-full flex items-center gap-3 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                selectedLibraryId === lib.id
                  ? 'bg-indigo-600/20 text-indigo-400'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
              }`}
            >
              <div className="w-1.5 h-1.5 rounded-full bg-gray-600" />
              <span className="sl truncate">{lib.name}</span>
              <span className="ml-auto text-xs text-gray-600">{lib.total_assets}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Admin Section (admin only) */}
      {user?.role === 'admin' && (
        <div className="px-3 py-2 border-t border-gray-800">
          <h2 className="sh px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">{t('sidebar.admin')}</h2>
          <div className="space-y-1">
            <button onClick={() => { navigate('/admin') }} className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${location.pathname === '/admin' ? 'bg-indigo-600/20 text-indigo-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'}`}><BarChart3 className="w-4 h-4" /><span className="sl">{t('admin.dashboard')}</span></button>
            <button onClick={() => { navigate('/ai') }} className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${location.pathname === '/ai' ? 'bg-indigo-600/20 text-indigo-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'}`}><Sparkles className="w-4 h-4" /><span className="sl">{t('sidebar.aiEngine')}</span></button>
           <button
             onClick={() => { if (showFavorites) toggleShowFavorites(); navigate('/tags/manage') }}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${location.pathname === '/tags/manage' ? 'bg-indigo-600/20 text-indigo-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'}`}
            >
              <Tag className="w-4 h-4" />
              <span className="sl">{t('sidebar.tags')}</span>
            </button>
            <button onClick={() => { navigate('/admin/settings') }} className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${location.pathname === '/admin/settings' ? 'bg-indigo-600/20 text-indigo-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'}`}><Settings className="w-4 h-4" /><span className="sl">{t('sidebar.settings')}</span></button>
            <button onClick={() => { navigate('/admin/users') }} className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${location.pathname === '/admin/users' ? 'bg-indigo-600/20 text-indigo-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'}`}><Users className="w-4 h-4" /><span className="sl">{t('admin.userManagement')}</span></button>
           <button onClick={() => { navigate('/admin/jobs') }} className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${location.pathname === '/admin/jobs' ? 'bg-indigo-600/20 text-indigo-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'}`}><Activity className="w-4 h-4" /><span className="sl">{t('admin.jobManagement')}</span></button>
            <button onClick={() => { navigate('/admin/logs') }} className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${location.pathname === '/admin/logs' ? 'bg-indigo-600/20 text-indigo-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'}`}><FileText className="w-4 h-4" /><span className="sl">{t('sidebar.logs')}</span></button>
          </div>
        </div>
      )}
      </div>
      {/* User Section */}
      <div className="mt-auto px-3 py-3 border-t border-gray-800 shrink-0">
        {user && (
          <div className="px-3 py-2 rounded-lg bg-gray-800/50 mb-2">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-full bg-indigo-600/30 flex items-center justify-center">
                <User className="w-3.5 h-3.5 text-indigo-400" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="sl text-sm font-medium text-gray-200 truncate">{user.username}</p>
                <div className="flex items-center gap-1 mt-0.5">
                  {user.role === 'admin' ? (
                    <Shield className="w-3 h-3 text-amber-400" />
                  ) : (
                    <UserCircle className="w-3 h-3 text-gray-500" />
                  )}
                  <span className={`text-xs font-medium ${user.role === 'admin' ? 'text-amber-400' : 'text-gray-500'}`}>
                    {user.role === 'admin' ? t('sidebar.roleAdmin') : t('sidebar.roleUser')}
                  </span>
                </div>
              </div>
            </div>
            <button
              onClick={() => { logout(); navigate('/') }}
              className="w-full mt-2 flex items-center justify-center gap-2 px-3 py-1.5 rounded-lg text-sm text-gray-400 hover:text-red-400 hover:bg-red-900/20 transition-colors border border-gray-700 hover:border-red-800/50"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span className="sl">{t('sidebar.signOut')}</span>
            </button>
          </div>
        )}
        <div className="px-3 py-2 rounded-lg bg-gray-800/50">
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <BarChart3 className="w-3 h-3" />
            <span>{stats ? `${(stats.total_size_bytes / 1e9).toFixed(1)} ${t('sidebar.storage')}` : '...'}</span>
          </div>
          {stats && stats.pending_jobs > 0 && (
            <div className="text-xs text-amber-400 mt-1">{stats.pending_jobs} {t('sidebar.jobsRunning')}</div>
          )}
          <button
            onClick={() => i18n.changeLanguage(i18n.language === 'zh' ? 'en' : 'zh')}
            className="mt-2 w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-gray-400 hover:text-indigo-400 hover:bg-indigo-900/20 transition-colors border border-gray-700 hover:border-indigo-800/30"
          >
            <Languages className="w-3.5 h-3.5" />
            <span className="sl">{t('language.switchTo')}</span>
          </button>
        </div>
      </div>
    </aside>
    </>
  )
});



