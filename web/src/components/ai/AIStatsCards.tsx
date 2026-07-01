import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import {
  Film,
  Image,
  MessageSquareText,
  Tag,
  FileText,
  Volume2,
  BarChart3,
  ChevronRight,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";

interface AIStats {
  videos_processed: number;
  total_scenes: number;
  total_subtitles: number;
  total_tags: number;
  total_ocr_texts: number;
  total_frames: number;
  speakers_found: number;
}

interface Props {}

export function AIStatsCards(_props: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [stats, setStats] = useState<AIStats | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const load = async () => {
      try {
        const data = await api.getAIStats();
        setStats(data);
      } catch {
        setStats(null);
      } finally {
        setLoading(false);
      }
    };
    load();
    const iv = setInterval(load, 10000);
    return () => clearInterval(iv);
  }, []);
  const cards = [
    {
      icon: Film,
      label: t("aiEngine.videosProcessed"),
      value: stats?.videos_processed ?? "-",
      color: "text-indigo-400",
      bg: "bg-indigo-900/20",
      route: "/processed",
    },
    {
      icon: Image,
      label: t("aiEngine.totalScenes"),
      value: stats?.total_scenes ?? "-",
      color: "text-gray-200",
      bg: "bg-gray-800",
      route: "/",
    },
    {
      icon: MessageSquareText,
      label: t("aiEngine.totalSubtitles"),
      value: stats?.total_subtitles ?? "-",
      color: "text-blue-400",
      bg: "bg-blue-900/20",
      route: "/search",
    },
    {
      icon: Tag,
      label: t("aiEngine.objectTags"),
      value: stats?.total_tags ?? "-",
      color: "text-emerald-400",
      bg: "bg-emerald-900/20",
      route: "/tags/browse",
    },
    {
      icon: FileText,
      label: t("aiEngine.ocrTexts"),
      value: stats?.total_ocr_texts ?? "-",
      color: "text-amber-400",
      bg: "bg-amber-900/20",
      route: "/search",
    },
    {
      icon: Volume2,
      label: t("aiEngine.speakers"),
      value: stats?.speakers_found ?? "-",
      color: "text-pink-400",
      bg: "bg-pink-900/20",
      route: "/search",
    },
  ];
  if (loading)
    return (
      <div className="bg-gray-900/30 rounded-lg border border-gray-800 p-4">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-4 h-4 bg-gray-800 rounded animate-pulse" />
          <div className="w-16 h-4 bg-gray-800 rounded animate-pulse" />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div
              key={i}
              className="bg-gray-900 rounded-lg p-4 border border-gray-800"
            >
              <div className="w-8 h-8 rounded-lg bg-gray-800 animate-pulse mb-3" />
              <div className="w-16 h-3 bg-gray-800 rounded animate-pulse mb-1" />
              <div className="w-12 h-6 bg-gray-800 rounded animate-pulse" />
            </div>
          ))}
        </div>
      </div>
    );
  return (
    <div className="bg-gray-900/30 rounded-lg border border-gray-800 p-4">
      <div className="flex items-center gap-2 mb-3">
        <BarChart3 className="w-4 h-4 text-gray-400" />
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
          {t("aiEngine.statsTitle") || "数据模块"}
        </h2>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {cards.map((c) => (
          <button
            key={c.label}
            onClick={() => navigate(c.route)}
            className="bg-gray-900 rounded-lg p-4 border border-gray-800 hover:border-gray-600 transition-all text-left cursor-pointer group"
          >
            <div
              className={
                "w-8 h-8 rounded-lg flex items-center justify-center mb-3 " +
                c.bg
              }
            >
              <c.icon className={"w-4 h-4 " + c.color} />
            </div>
            <p className="text-xs text-gray-500 mb-0.5">{c.label}</p>
            <div className="flex items-center justify-between">
              <p className={"text-xl font-semibold " + c.color}>{c.value}</p>
              <ChevronRight className="w-4 h-4 text-gray-700 group-hover:text-gray-400 transition-colors" />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
