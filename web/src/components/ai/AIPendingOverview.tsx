import { useTranslation } from "react-i18next";
import { memo } from 'react'
import {
  BarChart3,
  Scissors,
  ScanSearch,
  TextSearch,
  Image,
  Subtitles,
  Mic2,
  CircleAlert,
} from "lucide-react";
import { formatCount } from "../../utils/format";
import { useAIStore } from "../../stores/ai";

const ENGINE_CONFIG = [
  {
    key: "scene",
    labelKey: "aiEngine.transnetDesc",
    icon: Scissors,
    color: "text-gray-200",
    bar: "bg-gray-400",
    bg: "bg-gray-800",
  },
  {
    key: "yolo",
    labelKey: "aiEngine.yolo",
    icon: ScanSearch,
    color: "text-gray-200",
    bar: "bg-gray-400",
    bg: "bg-gray-800",
  },
  {
    key: "ocr",
    labelKey: "aiEngine.ocr",
    icon: TextSearch,
    color: "text-gray-200",
    bar: "bg-gray-400",
    bg: "bg-gray-800",
  },
  {
    key: "clip",
    labelKey: "aiEngine.clip",
    icon: Image,
    color: "text-gray-200",
    bar: "bg-gray-400",
    bg: "bg-gray-800",
  },
  {
    key: "transcript",
    labelKey: "aiEngine.whisper",
    icon: Subtitles,
    color: "text-gray-200",
    bar: "bg-gray-400",
    bg: "bg-gray-800",
  },
  {
    key: "diarization",
    labelKey: "aiEngine.diarization",
    icon: Mic2,
    color: "text-gray-200",
    bar: "bg-gray-400",
    bg: "bg-gray-800",
  },
];

export const AIPendingOverview = memo(function AIPendingOverview() {
  const { t } = useTranslation();
  const d = useAIStore((s) => s.pendingCounts);
  const loading = useAIStore((s) => s.pendingLoading);
  const qs = useAIStore((s) => s.queueStatus);
  const batchActive = qs.status === "running" || qs.status === "paused";
  const useBatch =
    batchActive &&
    qs.total > 0 &&
    qs.model_progress &&
    Object.keys(qs.model_progress).length > 0;
  if (loading)
    return (
      <div className="bg-gray-900/30 rounded-lg border border-gray-800 p-4">
        <div className="flex items-center gap-2 mb-4">
          <BarChart3 className="w-4 h-4 text-gray-400" />
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
            {t("aiEngine.pendingOverview")}
          </h2>
        </div>
        <div className="bg-gray-900/60 rounded-lg border border-gray-800 p-5 mb-4">
          <div className="flex gap-10">
            {[1, 2, 3].map((i) => (
              <div key={i} className="space-y-2">
                <div className="w-16 h-3 bg-gray-800 rounded animate-pulse" />
                <div className="w-20 h-8 bg-gray-800 rounded animate-pulse" />
              </div>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div
              key={i}
              className="bg-gray-900/60 rounded-lg border border-gray-800 p-3"
            >
              <div className="flex items-center gap-2 mb-2">
                <div className="w-6 h-6 rounded-md bg-gray-800 animate-pulse" />
                <div className="w-12 h-3 bg-gray-800 rounded animate-pulse" />
              </div>
              <div className="w-16 h-6 bg-gray-800 rounded animate-pulse mb-2" />
              <div className="w-full h-1.5 bg-gray-800 rounded-full animate-pulse" />
            </div>
          ))}
        </div>
      </div>
    );
  if (!d)
    return (
      <div className="bg-gray-900/30 rounded-lg border border-gray-800 p-4">
        <div className="flex items-center gap-2 mb-4">
          <BarChart3 className="w-4 h-4 text-gray-400" />
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
            {t("aiEngine.pendingOverview")}
          </h2>
        </div>
        <div className="flex items-center justify-center py-8">
          <BarChart3 className="w-10 h-10 mb-3" />
          <p className="text-sm">
            {t("aiEngine.noData") || "\u6ca1\u6709 AI \u6570\u636e"}
          </p>
          <p className="text-xs text-gray-600 mt-1">
            {t("aiEngine.waitForData") ||
              "\u7b49\u5f85\u670d\u52a1\u5668\u8fd4\u56de\u6570\u636e\uff0c\u6216\u68c0\u67e5\u670d\u52a1\u662f\u5426\u6b63\u5e38\u8fd0\u884c"}
          </p>
        </div>
      </div>
    );
  const done = useBatch
    ? (qs.completed ?? 0)
    : (d?.total_assets ?? 0) - (d?.total_pending ?? 0);
  const totalVideos = useBatch ? (qs.total ?? 0) : (d?.total_assets ?? 0);
  const maxVal = useBatch
    ? Math.max(
        ...ENGINE_CONFIG.map(
          (cfg) => (qs.model_progress as any)?.[cfg.key]?.current ?? 0,
        ),
        1,
      )
    : Math.max(
        ...ENGINE_CONFIG.map(
          (cfg) => (d as any)?.[cfg.key + "_done_count"] ?? 0,
        ),
        1,
      );
  return (
    <div className="bg-gray-900/30 rounded-lg border border-gray-800 p-4">
      <div className="flex items-center gap-2 mb-4">
        <BarChart3 className="w-4 h-4 text-gray-400" />
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
          {t("aiEngine.pendingOverview")}
        </h2>
        <span className="ml-auto text-[10px] text-gray-600">
          {t("aiEngine.autoRefreshLabel")}
        </span>
      </div>
      {/* Summary row */}
      <div className="bg-gray-900/60 rounded-lg border border-gray-800 p-5 mb-4">
        <div className="flex items-center justify-between">
          <div className="flex gap-10">
            <div>
              <p className="text-xs text-gray-500 mb-1">
                {t("aiEngine.totalVideos") || "\u603b\u89c6\u9891\u6570"}
              </p>
              <p className="text-3xl font-bold text-white">
                {formatCount(totalVideos)}
              </p>
            </div>
            <div className="w-px bg-gray-800 self-stretch" />
            <div>
              <p className="text-xs text-gray-500 mb-1">
                {t("aiEngine.processedVideos") ||
                  "\u5df2\u5904\u7406\u89c6\u9891"}
              </p>
              <p className="text-3xl font-bold text-gray-200">
                {formatCount(done)}
              </p>
              <p className="text-[11px] text-gray-600 mt-1">
                {useBatch
                  ? "\u5f53\u524d\u6279\u6b21\u5df2\u5b8c\u6210"
                  : "\u81f3\u5c11\u4e00\u4e2a AI \u5f15\u64ce\u5df2\u5904\u7406"}
              </p>
            </div>
            <div className="w-px bg-gray-800 self-stretch" />
            <div>
              <p className="text-xs text-gray-500 mb-1">
                {t("aiEngine.pendingVideos") ||
                  "\u5f85\u5904\u7406\u89c6\u9891"}
              </p>
              <p className="text-3xl font-bold text-gray-200">
                {(useBatch
                  ? Math.max(0, totalVideos - done)
                  : (d?.total_pending ?? 0)
                ).toLocaleString()}
              </p>
              <p className="text-[11px] text-gray-600 mt-1">
                {useBatch
                  ? "\u5f53\u524d\u6279\u6b21\u5f85\u5904\u7406"
                  : "\u6240\u6709 AI \u5f15\u64ce\u5747\u672a\u5904\u7406\u8fc7"}
              </p>
            </div>
          </div>
          <div className="w-14 h-14 rounded-xl bg-gray-800 flex items-center justify-center">
            <CircleAlert className="w-7 h-7 text-gray-400" />
          </div>
        </div>
      </div>
      {/* Per-engine cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {ENGINE_CONFIG.map((cfg) => {
          const mp = useBatch ? (qs.model_progress as any)?.[cfg.key] : null;
          const mpTotal = mp?.total ?? 0;
          const mpCurrent = mp?.current ?? 0;
          const count = useBatch
            ? Math.max(0, mpTotal - mpCurrent)
            : ((d as any)[cfg.key + "_pending"] ?? 0);
          const doneCnt = useBatch
            ? mpCurrent
            : ((d as any)[cfg.key + "_done_count"] ?? 0);
          const success = useBatch
            ? mpCurrent
            : ((d as any)[cfg.key + "_success"] ?? 0);
          const error = useBatch ? 0 : ((d as any)[cfg.key + "_error"] ?? 0);
          const pct = (doneCnt / maxVal) * 100;
          return (
            <div
              key={cfg.key}
              className="bg-gray-900/60 rounded-lg border border-gray-800 p-3 hover:border-gray-600 transition-colors"
            >
              <div className="flex items-center gap-2 mb-2">
                <div
                  className={
                    "w-6 h-6 rounded-md flex items-center justify-center " +
                    cfg.bg
                  }
                >
                  <cfg.icon className={"w-3.5 h-3.5 " + cfg.color} />
                </div>
                <span className="text-xs text-gray-400">
                  {t(cfg.labelKey as any)}
                </span>
              </div>
              <p className={"text-lg font-semibold mb-1.5 " + cfg.color}>
                {formatCount(doneCnt)}
              </p>
              <div className="w-full h-1.5 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className={
                    "h-full rounded-full transition-all duration-500 " + cfg.bar
                  }
                  style={{ width: pct + "%" }}
                />
              </div>
              <p className="text-[10px] text-gray-600 mt-1.5 flex justify-between gap-1">
                <span>
                  {t("aiEngine.pending") || "\u5f85\u5904\u7406"}{" "}
                  <span className={"font-medium " + cfg.color}>
                    {formatCount(count)}
                  </span>
                </span>
                <span>
                  {t("aiEngine.done") || "\u5df2\u6267\u884c"}{" "}
                  <span className="text-gray-200 font-medium">
                    {formatCount(doneCnt)}
                  </span>
                </span>
              </p>
              <p className="text-[9px] text-gray-500 mt-0.5 flex justify-end gap-3">
                <span>
                  {t("aiEngine.successLabel") || "\u6210\u529f"}{" "}
                  <span className="text-gray-200">
                    {formatCount(success)}
                  </span>
                </span>
                <span>
                  {t("aiEngine.failedLabel") || "\u5931\u8d25"}{" "}
                  <span className="text-red-400">{formatCount(error)}</span>
                </span>
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
});


