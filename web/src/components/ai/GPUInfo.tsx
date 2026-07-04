import { useTranslation } from "react-i18next";
import { memo } from 'react'
import { Cpu } from "lucide-react";
import { useAIStore } from "../../stores/ai";

export const GPUInfo = memo(function GPUInfo() {
 const { t } = useTranslation()
 const gpuInfo = useAIStore((s) => s.gpuInfo);
  const gpuInfoLoading = useAIStore((s) => s.gpuInfoLoading);
  if (!gpuInfoLoading && gpuInfo.total === 0) {
    return (
      <div className="bg-gray-900/30 rounded-lg border border-gray-800 p-4">
        <h3 className="text-sm font-medium text-gray-200 mb-3 flex items-center gap-2">
          <Cpu className="w-4 h-4 text-gray-400" /> {t("aiEngine.gpuMonitor")}
        </h3>
        <div className="flex flex-col items-center py-8 text-gray-500">
          <Cpu className="w-10 h-10 mb-2" />
          <p className="text-sm">{t('gpuInfo.noGpu')}</p>
          <p className="text-xs text-gray-600 mt-1">
            {t("aiEngine.gpuDriverHint") ||
              t('gpuInfo.ensureDriver')}
          </p>
        </div>
      </div>
    );
  }
  return (
    <div className="bg-gray-900/30 rounded-lg border border-gray-800 p-4">
      <h3 className="text-sm font-medium text-gray-200 mb-3 flex items-center gap-2">
        <Cpu className="w-4 h-4 text-gray-400" /> {t("aiEngine.gpuMonitor")}
      </h3>
      <div>
        <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
          <span>{t("aiEngine.totalGpuUsage")}</span>
          <span className="text-gray-200 font-mono">
            {gpuInfoLoading
              ? t("aiEngine.detectingGpu")
              : gpuInfo.used.toFixed(1) +
                " / " +
                gpuInfo.total.toFixed(1) +
                " GB"}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex-1">
            <div className="w-full bg-gray-800 rounded-full h-2.5">
              <div
                className={
                  "h-2.5 rounded-full transition-all duration-500 " +
                  (gpuInfoLoading
                    ? "bg-gray-700 animate-pulse"
                    : "bg-gradient-to-r from-emerald-500 to-amber-500")
                }
                style={{
                  width: (gpuInfoLoading ? 100 : gpuInfo.percent) + "%",
                }}
              />
            </div>
          </div>
          <span className="text-xs text-gray-500 font-mono shrink-0 w-12 text-right">
            {gpuInfoLoading ? "..." : gpuInfo.percent + "%"}
          </span>
        </div>
      </div>
      <p className="text-xs text-gray-600 mt-2">{t("aiEngine.gpuDesc")}</p>
    </div>
  );
});
