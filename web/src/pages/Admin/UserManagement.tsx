import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { api } from "../../api/client"
import type { AdminUser } from "../../api/client"
import { Users, Plus, Shield, User, Trash2, Loader2, X } from "lucide-react"

export default function UserManagementPage() {
  const { t } = useTranslation()
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newUser, setNewUser] = useState({ username: "", password: "", role: "user" })
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => { loadUsers() }, [])

  const loadUsers = async () => {
    setLoading(true)
    try {
      const data = await api.listAdminUsers()
      setUsers(data)
    } catch (e) {
      console.error("Failed to load users:", e)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    if (!newUser.username || newUser.password.length < 6) {
      setError(t("admin.userValidationError"))
      return
    }
    setCreating(true)
    setError("")
    try {
      await api.createAdminUser(newUser)
      setShowCreate(false)
      setNewUser({ username: "", password: "", role: "user" })
      await loadUsers()
    } catch (e: any) {
      setError(e.message || t("admin.failedToCreate"))
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (userId: string) => {
    if (!confirm(t("admin.deleteUserConfirm"))) return
    try {
      await api.deleteAdminUser(userId)
      await loadUsers()
    } catch (e) {
      console.error("Failed to delete user:", e)
    }
  }

  const handleRoleChange = async (userId: string, role: string) => {
    try {
      await api.updateAdminUser(userId, { role })
      await loadUsers()
    } catch (e) {
      console.error("Failed to update user:", e)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
      </div>
    )
  }

  return (
    <div className="p-6 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">{t("admin.userManagement")}</h1>
          <p className="text-sm text-gray-500 mt-1">{t("admin.userManagementDesc")}</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          {t("admin.addUser")}
        </button>
      </div>

      {/* Users list */}
      <div className="space-y-2">
        {users.map((u) => (
          <div key={u.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-indigo-600/20 flex items-center justify-center">
                <User className="w-5 h-5 text-indigo-400" />
              </div>
              <div>
                <p className="text-sm font-medium text-white">{u.username}</p>
                <div className="flex items-center gap-1.5 mt-0.5">
                  {u.role === "admin" ? (
                    <Shield className="w-3 h-3 text-amber-400" />
                  ) : (
                    <User className="w-3 h-3 text-gray-500" />
                  )}
                  <span className={`text-xs ${u.role === "admin" ? "text-amber-400" : "text-gray-500"}`}>
                    {u.role}
                  </span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <select
                value={u.role}
                onChange={(e) => handleRoleChange(u.id, e.target.value)}
                className="px-2 py-1 bg-gray-800 border border-gray-700 rounded text-xs text-gray-300 focus:border-indigo-600 outline-none"
              >
                <option value="user">user</option>
                <option value="admin">admin</option>
              </select>
              <button
                onClick={() => handleDelete(u.id)}
                className="p-2 rounded-lg text-gray-500 hover:text-red-400 hover:bg-red-900/20 transition-colors"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}
        {users.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-gray-500">
            <Users className="w-12 h-12 mb-3 text-gray-700" />
            <p className="text-sm">{t("admin.noUsers")}</p>
          </div>
        )}
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white">{t("admin.createUser")}</h3>
              <button onClick={() => setShowCreate(false)} className="text-gray-500 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>
            {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">{t("admin.username")}</label>
                <input
                  value={newUser.username}
                  onChange={(e) => setNewUser((p) => ({ ...p, username: e.target.value }))}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white focus:border-indigo-600 outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">{t("admin.password")}</label>
                <input
                  type="password"
                  value={newUser.password}
                  onChange={(e) => setNewUser((p) => ({ ...p, password: e.target.value }))}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white focus:border-indigo-600 outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">{t("admin.role")}</label>
                <select
                  value={newUser.role}
                  onChange={(e) => setNewUser((p) => ({ ...p, role: e.target.value }))}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white focus:border-indigo-600 outline-none"
                >
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
              >
                {t("admin.cancel")}
              </button>
              <button
                onClick={handleCreate}
                disabled={creating}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
              >
                {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : t("admin.create")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
