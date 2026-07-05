import { Routes, Route } from 'react-router-dom'
import { ErrorBoundary } from './components/ErrorBoundary'
import { GlobalError } from './components/GlobalError'
 import { Sidebar } from './components/Sidebar'
 import AdminDashboardPage from './pages/Admin/Dashboard'
 import SystemSettingsPage from './pages/Admin/SystemSettings'
 import UserManagementPage from './pages/Admin/UserManagement'
import JobManagementPage from './pages/Admin/JobManagement'
import LogViewerPage from './pages/Admin/LogViewer'
import { AssetGrid } from './pages/AssetGrid'
import { AssetDetailV2 } from './pages/AssetDetailV2'
import { AIEnginePage } from './pages/AIEnginePage'
import { LibraryManager } from './pages/LibraryManager'
import { SearchPage } from './pages/SearchPage'
import { TagManager } from './pages/TagManager'
import { TagBrowse } from './pages/TagBrowse'
import { YoloTagBrowse } from './pages/YoloTagBrowse'
import { TimelineView } from './pages/TimelineView'
import { DirectoryView } from './pages/DirectoryView'
import { ProcessedAssets } from './pages/ProcessedAssets'
import LoginPage from './pages/Login'
import { useAuthStore } from './stores/auth'
import { useLibraryStore } from './stores/library'
 import { useEffect, useState } from 'react'
import i18n from './i18n/config'

export default function App() {
  const [, forceRender] = useState(0)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const authLoading = useAuthStore((s) => s.authLoading)
  const checkAuth = useAuthStore((s) => s.checkAuth)
  const loadLibraries = useLibraryStore((s) => s.loadLibraries)
  const loadStats = useLibraryStore((s) => s.loadStats)

  useEffect(() => {
    checkAuth()
  }, [])

  useEffect(() => {
    const onLanguageChanged = () => forceRender(n => n + 1)
    i18n.on('languageChanged', onLanguageChanged)
    return () => { i18n.off('languageChanged', onLanguageChanged) }
  }, [])

  // Load main data once authenticated
  useEffect(() => {
    if (isAuthenticated) {
      loadLibraries()
      loadStats()
    }
  }, [isAuthenticated])

  if (authLoading) {
    return (
      <div className="flex h-screen overflow-hidden bg-gray-950">
        {/* Sidebar skeleton */}
        <aside className="bg-gray-900 border-r border-gray-800 flex flex-col p-4 animate-pulse" style={{ width: 264 }}>
          <div className="h-6 w-24 bg-gray-800 rounded mb-8" />
          <div className="space-y-3">
            {Array.from({ length: 5 }, (_, i) => (
              <div key={i} className="h-9 bg-gray-800 rounded-lg" />
            ))}
          </div>
          <div className="mt-auto space-y-2">
            <div className="h-9 bg-gray-800 rounded-lg" />
            <div className="h-9 bg-gray-800 rounded-lg" />
          </div>
        </aside>
        {/* Content skeleton */}
        <main className="flex-1 p-6 animate-pulse">
          <div className="max-w-7xl mx-auto">
            <div className="flex items-center gap-3 mb-6">
              <div className="h-5 w-20 bg-gray-800 rounded" />
              <div className="h-5 w-32 bg-gray-800 rounded" />
              <div className="h-5 w-24 bg-gray-800 rounded ml-auto" />
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
              {Array.from({ length: 12 }, (_, i) => (
                <div key={i} className="bg-gray-900 rounded-lg overflow-hidden border border-gray-800">
                  <div className="aspect-video bg-gray-800" />
                  <div className="p-2 space-y-1.5">
                    <div className="h-3 bg-gray-800 rounded w-3/4" />
                    <div className="h-2.5 bg-gray-800 rounded w-1/2" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </main>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <LoginPage />
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <GlobalError />
        <ErrorBoundary>
        <Routes>
          <Route path="/" element={<ErrorBoundary><AssetGrid /></ErrorBoundary>} />
          <Route path="/asset/:id" element={<ErrorBoundary><AssetDetailV2 /></ErrorBoundary>} />
          <Route path="/asset-v2/:id" element={<ErrorBoundary><AssetDetailV2 /></ErrorBoundary>} />
          <Route path="/libraries" element={<ErrorBoundary><LibraryManager /></ErrorBoundary>} />
         <Route path="/search" element={<ErrorBoundary><SearchPage /></ErrorBoundary>} />
          <Route path="/ai" element={<ErrorBoundary><AIEnginePage /></ErrorBoundary>} />
          <Route path="/processed" element={<ErrorBoundary><ProcessedAssets /></ErrorBoundary>} />
          <Route path="/tags/browse" element={<ErrorBoundary><TagBrowse /></ErrorBoundary>} />
          <Route path="/yolo-tags/browse" element={<ErrorBoundary><YoloTagBrowse /></ErrorBoundary>} />
          <Route path="/tags/manage" element={<ErrorBoundary><TagManager /></ErrorBoundary>} />
         <Route path="/timeline" element={<ErrorBoundary><TimelineView /></ErrorBoundary>} />
         <Route path="/directory" element={<ErrorBoundary><DirectoryView /></ErrorBoundary>} />
         <Route path="/admin" element={<ErrorBoundary><AdminDashboardPage /></ErrorBoundary>} />
          <Route path="/admin/settings" element={<ErrorBoundary><SystemSettingsPage /></ErrorBoundary>} />
         <Route path="/admin/users" element={<ErrorBoundary><UserManagementPage /></ErrorBoundary>} />
         <Route path="/admin/jobs" element={<ErrorBoundary><JobManagementPage /></ErrorBoundary>} />
         <Route path="/admin/logs" element={<ErrorBoundary><LogViewerPage /></ErrorBoundary>} />
        </Routes>
        </ErrorBoundary>
      </main>
    </div>
  )
}

