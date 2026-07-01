import { PipelineConfigPanel } from "./PipelineConfigPanel"

/** Backward-compatible wrapper — delegates to the new 3-tab PipelineConfigPanel */
export function AIPipelineConfig() {
  return <PipelineConfigPanel />
}
