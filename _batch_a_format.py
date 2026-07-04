import re

# === utils/format.ts ===
with open("D:\\DockerData\\reelmind\\web\\src\\utils\\format.ts", "r", encoding="utf-8") as f:
    content = f.read()

old_func = """export function formatRelativeTime(dateStr?: string): string {
  if (!dateStr) return "-"
  const now = Date.now()
  const date = new Date(dateStr).getTime()
  const diffMs = now - date
  const diffSec = Math.floor(diffMs / 1000)

  if (diffSec < 0) return "\u521a\u521a"
  if (diffSec < 60) return `${diffSec}\u79d2\u524d`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}\u5206\u949f\u524d`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour}\u5c0f\u65f6\u524d`

  const d = new Date(dateStr)
  const nowYear = new Date().getFullYear()
  if (d.getFullYear() === nowYear) {
    return `${d.getMonth() + 1}\u6708${d.getDate()}\u65e5`
  }
  return `${d.getFullYear()}\u5e74${d.getMonth() + 1}\u6708`
}"""

new_func = """export function formatRelativeTime(dateStr?: string, t?: (key: string, options?: any) => string): string {
  if (!dateStr) return "-"
  const now = Date.now()
  const date = new Date(dateStr).getTime()
  const diffMs = now - date
  const diffSec = Math.floor(diffMs / 1000)

  if (diffSec < 0) return t ? t("format.justNow") : "Just now"
  if (diffSec < 60) return t ? t("format.secondsAgo", { count: diffSec }) : `${diffSec}s ago`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return t ? t("format.minutesAgo", { count: diffMin }) : `${diffMin}m ago`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return t ? t("format.hoursAgo", { count: diffHour }) : `${diffHour}h ago`

  const d = new Date(dateStr)
  const nowYear = new Date().getFullYear()
  if (d.getFullYear() === nowYear) {
    return t
      ? t("format.monthDay", { month: d.getMonth() + 1, day: d.getDate() })
      : `${d.getMonth() + 1}/${d.getDate()}`
  }
  return t
    ? t("format.yearMonth", { year: d.getFullYear(), month: d.getMonth() + 1 })
    : `${d.getFullYear()}/${d.getMonth() + 1}`
}"""

content = content.replace(old_func, new_func)

with open("D:\\DockerData\\reelmind\\web\\src\\utils\\format.ts", "w", encoding="utf-8") as f:
    f.write(content)
print("format.ts done")
