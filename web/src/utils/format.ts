export function formatCount(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M"
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K"
  return String(n)
}
export function formatRelativeTime(dateStr?: string, t?: (key: string, options?: any) => string): string {
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
}
export function formatSize(bytes: number): string {
  if (bytes < 1e6) return `${(bytes / 1e3).toFixed(0)} KB`
  if (bytes < 1e9) return `${(bytes / 1e6).toFixed(1)} MB`
  return `${(bytes / 1e9).toFixed(2)} GB`
}

export function formatDuration(s: number): string {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m} min`
}
