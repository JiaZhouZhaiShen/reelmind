import { useState, FormEvent } from 'react'
import { LogIn, UserPlus, Eye, EyeOff, AlertCircle } from 'lucide-react'
import { useStore } from '../stores/app'
import { useTranslation } from 'react-i18next'

export default function LoginPage() {
  const { t } = useTranslation()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const login = useStore((s) => s.login)
  const register = useStore((s) => s.register)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (mode === 'login') {
        await login(username, password)
      } else {
        await register(username, password)
      }
    } catch (err: any) {
      setError(err.message || 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
       <div className="text-center mb-8">
          <img src="/logo.png" alt="ReelMind" className="inline-block w-14 h-14 rounded-xl mb-4 object-cover" />
         <h1 className="text-2xl font-bold text-white tracking-tight">ReelMind</h1>
         <p className="text-sm text-gray-500 mt-1">嘉州宅神 · Jiazhou Hermit</p>
          <p className="text-[11px] text-indigo-400/70 font-mono font-medium mt-2">v{__APP_VERSION__}</p>
       </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="bg-gray-900 rounded-xl p-6 border border-gray-800 space-y-4">
          <div className="text-center">
            <h2 className="text-lg font-semibold text-white">{mode === 'login' ? t('login.title') : t('login.registerTitle')}</h2>
            <p className="text-sm text-gray-500 mt-1">{mode === 'login' ? t('login.subtitle') : t('login.registerSubtitle')}</p>
          </div>

          {error && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-red-900/30 border border-red-800/50 text-red-400 text-sm">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">{t('login.username')}</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent text-sm"
              placeholder={t('login.usernamePlaceholder')}
              required
              minLength={2}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">{t('login.password')}</label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2 pr-10 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent text-sm"
                placeholder={t('login.passwordPlaceholder')}
                required
                minLength={6}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800/50 text-white rounded-lg font-medium transition-colors text-sm"
          >
            {loading ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : mode === 'login' ? (
              <LogIn className="w-4 h-4" />
            ) : (
              <UserPlus className="w-4 h-4" />
            )}
            {mode === 'login' ? t('login.title') : t('login.registerTitle')}
          </button>

          <div className="text-center text-sm text-gray-500">
            {mode === 'login' ? (
              <>
                {t('login.noAccount')}{' '}
                <button type="button" onClick={() => { setMode('register'); setError('') }} className="text-indigo-400 hover:text-indigo-300 font-medium">
                  {t('login.registerLink')}
                </button>
              </>
            ) : (
              <>
                {t('login.hasAccount')}{' '}
                <button type="button" onClick={() => { setMode('login'); setError('') }} className="text-indigo-400 hover:text-indigo-300 font-medium">
                  {t('login.signInLink')}
                </button>
              </>
            )}
          </div>
        </form>

       <div className="mt-6 text-center">
         <p className="text-xs text-gray-600 mt-1">{t('login.firstUserHint')}</p>
     </div>
      </div>
    </div>
  )
}





