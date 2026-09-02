# 01 Backend Standard

> Rules: R1.1-R1.5 (EN mirror of `docs/规范/01_后端规范.md`; the Chinese file is authoritative)
> Purpose: architecture boundaries and check methods for the FastAPI backend (`server/`) and AI service (`ai_service/`).

---

## R1.1 Server Forwards Only, Never Computes AI

Boundary:
- The Server loads no AI models (torch/transformers/model weights).
- The Server does no GPU inference; AI requests are HTTP-proxied to the AI container (2589).

```python
# OK: forwarding
result = await _ai_post("/pipeline/start", {...})
# NOT OK: model inference inside the server
```

Check:
```bash
grep -rn "torch\|transformers\|model\.predict\|model\.encode" server/app/
```

Exception: the Server may do non-AI business computation (aggregation, state derivation, file scanning).

## R1.2 Two Databases, One Job Each

| Data | Where | Writes | Reads |
|------|-------|--------|-------|
| Asset metadata, pipeline state | PG | Server + Orchestrator + AI Worker | Server |
| AI inference results (scenes/subtitles/tags/OCR) | SQLite | AI Worker | Server |
| CLIP vector index | PG (pgvector) | AI Worker | Server |

Boundary: no single datum is written to two databases. Dual writes indicate a design problem.

## R1.3 Single Status Write Entry

Boundary: each container has exactly one status write module. Server = `app/core/job_helpers.py`; AI = `ai_service/job_helpers.py`. All other code is forbidden from writing `ai_engine_jobs` / `processing_state` directly. Atomic batch writes (claim / recover / reclaim / mark-completed) are encapsulated inside `job_helpers`.

```python
# OK
from app.core.job_helpers import set_job_status
set_job_status(session, media_id, "scene", "completed")
# OK: AI container (ai_service/job_helpers.py is its only write entry)
from job_helpers import set_job_status
set_job_status(media_id, "scene", "completed")
# NOT OK
cur.execute("UPDATE ai_engine_jobs SET status = 'completed' WHERE id = ?")
```

Check:
```bash
grep -rnE "INSERT INTO ai_engine_jobs|UPDATE[[:space:]]+ai_engine_jobs|DELETE FROM ai_engine_jobs|UPDATE[[:space:]]+processing_state" server --include="*.py" | grep -vE "alembic|migration|job_helpers\.py"
```

## R1.4 Single-Responsibility APIs

Boundary: `api/*.py` <= 1000 lines; non-api files (e.g. `core/`) should also be kept under control. A file handling several unrelated responsibilities should be split before line count forces it.

> Note: the previous 500-line limit was too tight for large endpoints and was raised to 1000 on 2026-09-02 (consistent with frontend R2.10). It remains a hard ceiling; split beyond it.

Check:
```bash
find server/app/api -name "*.py" -exec wc -l {} \; | awk '$1 > 1000'
```

Current state (measured 2026-09-02): `core/indexer.py` 1323 and `ai_service/pipeline.py` 1010 exceed 1000 and await convergence; `api/ai/pipeline.py` 701 and `api/search.py` 650 are compliant under the 1000-line threshold.

## R1.5 Backend Does No Rendering Math

- Signals for the frontend: converting numbers to percentages, computing progress bars, formatting time.
- Signals for the backend: parsing logic that needs internal protocol details (e.g. step string formats).

```python
# OK: backend returns raw data
{"engines": {"scene": "completed", "yolo": "running"}, "step": "YOLO [5/10]"}
# NOT OK: backend writes 40 lines of progress math
```

Exception: business aggregation and state derivation (e.g. results_ready derivation) may stay backend-side.
