UPDATE ai_engine_jobs
SET status = 'completed', updated_at = NOW()
WHERE engine = 'ocr' AND status = 'pending'
  AND asset_id IN (
    SELECT DISTINCT asset_id FROM scene_ocr
  );

SELECT COUNT(*) AS fixed_rows
FROM ai_engine_jobs
WHERE engine = 'ocr' AND status = 'completed'
  AND asset_id IN (
    SELECT DISTINCT asset_id FROM scene_ocr
  );
