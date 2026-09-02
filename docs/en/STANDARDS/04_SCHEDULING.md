# 04 Scheduling Standard

> Rules: R4.1-R4.2 (EN mirror of `docs/规范/04_调度规范.md`; the Chinese file is authoritative)
> Purpose: status/result boundaries for the AI pipeline scheduling (Server / Orchestrator / AI Worker).

---

## R4.1 Separate Status from Results

Boundary:

| Data | Where | Purpose |
|------|-------|---------|
| `processing_state`, `ai_engine_jobs.status` | PG | scheduling, progress, retries |
| Scene frames, tags, OCR, subtitles | SQLite | frontend display, search |
| CLIP vectors | PG (pgvector) | semantic search |

Principle: status drives scheduling; results drive display. The two never mix and are never dual-written.

## R4.2 Display Depends on results_ready

Boundary: the frontend never reads engine `ai_engine_jobs.status` directly. It always obtains display evidence through the backend `results-ready` endpoint.

```json
GET /api/media/{id}/status
{
    "state": "completed",
    "results_ready": { "scenes": true, "ocr": false, "subtitle": true, "tags": true }
}
```

Why: `status` means "did the engine finish running"; `results_ready` means "are results displayable". They are not the same (e.g., an engine may finish with zero results).

Implementation state (measured 2026-09-02): `get_results_ready()` in `server/app/api/ai/pipeline.py` currently derives `results_ready` from PG `ai_engine_jobs.status == 'completed'` (the code comment explains that engines such as OCR may legitimately produce zero results, and SQLite presence checks would misjudge "finished but empty" as "not finished"). The function docstring claiming "based on actual SQLite data" does not match the implementation and is a documentation defect. The backend owns the derivation and must document it honestly; the frontend only consumes the results-ready endpoint and never reads status directly.

> Note: R4.2 was revised accordingly on 2026-09-02. If "derive by actual data presence" is required in the future, that is a backend change to be scoped separately.
