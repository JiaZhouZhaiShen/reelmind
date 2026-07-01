import { useState } from "react"
import { VideoCard } from "./VideoCard"
import { Image, MessageSquareText, Tag, FileText, Sparkles, ChevronDown, ChevronUp, Clock, ArrowRight } from "lucide-react"
import { useNavigate } from "react-router-dom"
import type { SearchResult } from "../api/client"


const SOURCE_ICONS: Record<string, typeof MessageSquareText> = {
  transcript: MessageSquareText,
  object: Tag,
  ocr: FileText,
  visual: Image,
  metadata: Sparkles,
}

const SOURCE_LABELS: Record<string, string> = {
  transcript: "字幕",
  object: "物体",
  ocr: "文字",
  visual: "画面",
  metadata: "元数据",
}

const SOURCE_COLORS: Record<string, { bg: string; text: string }> = {
  transcript: { bg: "bg-gray-800", text: "text-gray-400" },
  object: { bg: "bg-gray-800", text: "text-gray-400" },
  ocr: { bg: "bg-gray-800", text: "text-gray-400" },
  visual: { bg: "bg-gray-800", text: "text-gray-400" },
  metadata: { bg: "bg-gray-700/90", text: "text-gray-400" },
}

interface SearchResultCardProps {
  result: SearchResult
}

export function SearchResultCard({ result }: SearchResultCardProps) {
  const [expanded, setExpanded] = useState(false)
  const navigate = useNavigate()

  const sources = result.match_sources ?? []

  const handleSeek = (timeSec: number) => {
    navigate(`/asset/${result.id}?seek=${timeSec}`)
  }

  return (
    <div className="relative">
      {/* VideoCard */}
      <VideoCard assetId={result.id} />

      {/* Match source badges — overlaid on thumbnail */}
      {sources.length > 0 && (
        <div className="absolute top-2 right-2 flex flex-col gap-1 z-10">
          {sources.map((src) => {
           const Icon = SOURCE_ICONS[src] || Sparkles
            const colors = SOURCE_COLORS[src] || { bg: "bg-gray-800", text: "text-gray-400" }
            const label = SOURCE_LABELS[src] || src
            return (
              <div
                key={src}
                className={`${colors.bg} rounded p-1 flex items-center gap-1`}
                title={`匹配: ${label}`}
              >
                <Icon className={`w-3 h-3 ${colors.text}`} />
              </div>
            )
          })}
        </div>
      )}

      {/* Match summary + expand — always present for consistent card height */}
      <div className="px-3 pb-2 min-h-[32px]">
        <div className="flex items-center gap-1.5 mt-1.5 text-xs text-gray-400 flex-wrap">
          {(result.match_sources?.length ?? 0) > 0 && result.match_sources.slice(0, 3).map((src) => {
           const Icon = SOURCE_ICONS[src] || Sparkles
              const colors = SOURCE_COLORS[src] || { bg: "bg-gray-800", text: "text-gray-400" }
              return (
                <span
                  key={src}
                  className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded ${colors.bg.replace("/90", "/70")} ${colors.text}`}
                >
                  <Icon className="w-3 h-3" />
                  {SOURCE_LABELS[src] || src}
                </span>
              )
            })}
            {result.match_sources.length > 3 && (
              <span className="text-gray-600">+{result.match_sources.length - 3}</span>
            )}
            <button
              onClick={() => setExpanded(!expanded)}
              className="ml-auto text-gray-500 hover:text-gray-400 transition-colors"
            >
              {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          </div>

          {/* Expandable detail drawer */}
          {expanded && (
            <div className="mt-2 space-y-1 border border-gray-800 rounded-lg p-2 bg-gray-900/80">
              {result.matches.map((m, i) => {
                const Icon = SOURCE_ICONS[m.source] || Sparkles
              const colors = SOURCE_COLORS[m.source] || { bg: "bg-gray-800", text: "text-gray-400" }
                return (
                  <div
                    key={i}
                    className="flex items-start gap-2 p-1.5 rounded hover:bg-gray-800/60 cursor-pointer transition-colors group"
                    onClick={() => handleSeek(m.time_sec)}
                  >
                    <div className={`shrink-0 w-6 h-6 rounded flex items-center justify-center ${colors.bg.replace("/90", "/60")}`}>
                      <Icon className={`w-3 h-3 ${colors.text}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-medium ${colors.text}`}>
                          {SOURCE_LABELS[m.source] || m.source}
                        </span>
                        <span className="text-[10px] text-gray-500 font-mono flex items-center gap-0.5">
                          <Clock className="w-2.5 h-2.5" />
                          {Math.floor(m.time_sec / 60)}:{String(Math.floor(m.time_sec % 60)).padStart(2, "0")}
                        </span>
                      </div>
                      <p className="text-xs text-gray-400 truncate mt-0.5">{m.snippet}</p>
                    </div>
                    <ArrowRight className="w-3 h-3 text-gray-600 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-1" />
                  </div>
                )
              })}
            </div>
          )}
        </div>
    </div>
  )
}


