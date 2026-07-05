"""ReelMind Search API -- unified search + legacy smart search."""
from __future__ import annotations

import asyncio
import logging
from typing import Any
import os

from fastapi import APIRouter, Depends, Query
import httpx
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..schemas.search import SearchQuery
from ..core.search_engine import search_assets, search_transcripts

from sqlalchemy import select as sa_select
from sqlalchemy import func
from ..models.ai_engine_job import AIEngineJob

logger = logging.getLogger(__name__)

AI_SERVICE_URL = os.environ.get("AI_SERVICE_URL", "http://reelmind-ai:2589")

router = APIRouter(prefix="/search", tags=["Search"])


class UnifiedSearchRequest(BaseModel):
    query: str
    top_k: int = 50


@router.post("")
async def unified_search(req: UnifiedSearchRequest):
    """Unified AI search: parallel subtitle/visual/object/OCR search, dedup and sort by score."""
    q = req.query
    top_k = req.top_k
    results = []

    # --- Subtitle search ---
    try:
        from ..models.ai import Subtitle, get_ai_session
        session = get_ai_session()
        subtitle_hits = session.query(Subtitle).filter(Subtitle.text.contains(q)).limit(top_k).all()
        session.close()
        for s in subtitle_hits:
            results.append({
                "video_id": s.video_id,
                "source": "subtitle",
                "text": s.text[:200],
                "time_sec": s.start,
                "score": 0.9,
            })
    except Exception as e:
        logger.debug("Subtitle search error: %s", e)

    # --- Scene tag search ---
    try:
        from ..models.ai import SceneTag, Scene, get_ai_session
        session = get_ai_session()
        tag_hits = session.query(SceneTag).filter(SceneTag.label.contains(q)).limit(top_k).all()
        for t in tag_hits:
            scene = session.query(Scene).filter(Scene.id == t.scene_id).first()
            results.append({
                "video_id": scene.video_id if scene else "",
                "source": "object",
                "text": f"{t.label} (conf={t.confidence})",
                "time_sec": scene.start_time if scene else 0,
                "score": 0.7,
            })
        session.close()
    except Exception as e:
        logger.debug("Tag search error: %s", e)

    # --- OCR text search ---
    try:
        from ..models.ai import SceneOCR, Scene, get_ai_session
        session = get_ai_session()
        ocr_hits = session.query(SceneOCR).filter(SceneOCR.text.contains(q)).limit(top_k).all()
        for ocr in ocr_hits:
            scene = session.query(Scene).filter(Scene.id == ocr.scene_id).first()
            row = {
                "video_id": scene.video_id if scene else "",
                "source": "ocr",
                "text": ocr.text,
                "time_sec": scene.start_time if scene else 0,
                "score": 0.6,
                "ocr_bbox": {
                    "x": ocr.bbox_x, "y": ocr.bbox_y,
                    "w": ocr.bbox_w, "h": ocr.bbox_h,
                },
            }
            results.append(row)
        session.close()
    except Exception as e:
        logger.debug("OCR search error: %s", e)

    # --- CLIP semantic search (via AI container) ---
    try:
        clip_resp = httpx.post(f"{AI_SERVICE_URL}/clip/search", json={"query": q, "top_k": 20}, timeout=5)
        if clip_resp.status_code == 200:
            clip_results = clip_resp.json().get("results", [])
            for cr in clip_results:
                results.append({
                    "video_id": cr["video_id"],
                    "source": "visual",
                    "text": f"Visual match ({cr['score']:.2f})",
                    "time_sec": cr["time_sec"],
                    "score": cr["score"] * 0.8,
                    "frame_path": cr["frame_path"],
                })
    except Exception as e:
        logger.debug("CLIP search error: %s", e)

    # Dedup by (video_id, time_sec) keeping highest score
    seen = {}
    for r in results:
        key = (r.get("video_id", ""), r.get("time_sec", 0))
        if key not in seen or r["score"] > seen[key]["score"]:
            seen[key] = r

    merged = sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:top_k]

    # Enrich with video info (batch query)
    try:
        from ..models.ai import Video, get_ai_session
        session = get_ai_session()
        video_ids = list({r.get("video_id", "") for r in merged if r.get("video_id")})
        if video_ids:
            videos = {v.id: v for v in session.query(Video).filter(Video.id.in_(video_ids)).all()}
            for r in merged:
                vid = videos.get(r.get("video_id", ""))
                if vid:
                    r["file_name"] = vid.file_name
                    r["file_path"] = vid.file_path
                    r["duration"] = vid.duration
        session.close()
    except Exception as e:
        logger.debug("Video enrichment error: %s", e)

    return {"results": merged, "total": len(merged)}


@router.get("/smart")
async def smart_search(
    q: str = Query(""),
    library_id: str | None = Query(None),
    include_archived: bool = Query(False),
    tags: str = Query(""),
    min_duration: float | None = Query(None),
    max_duration: float | None = Query(None),
    min_file_size: int | None = Query(None),
    max_file_size: int | None = Query(None),
    has_audio: bool | None = Query(None),
    sort_by: str = Query("relevance"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
   source_engine: str | None = Query(None),
    orientation: str = Query(""),
   session: AsyncSession = Depends(get_session),
):
    query = SearchQuery(
        q=q, library_id=library_id,
        include_archived=include_archived,
        tags=tags.split(",") if tags else [],
        min_duration=min_duration, max_duration=max_duration,
        min_file_size=min_file_size, max_file_size=max_file_size,
        has_audio=has_audio, sort_by=sort_by, sort_order=sort_order,
       source_engine=source_engine,
        orientation=orientation,
       page=page, page_size=page_size,
    )
    assets, total = await search_assets(session, query)

    # Build job_dict from ai_engine_jobs for status fields
    job_dict = {}
    if assets:
        asset_ids_list = [a.id for a in assets]
        job_q = sa_select(AIEngineJob).where(AIEngineJob.media_id.in_(asset_ids_list))
        job_r = await session.execute(job_q)
        for j in job_r.scalars().all():
            job_dict.setdefault(str(j.media_id), {})[j.engine_name] = j.status

    # Phase 1: Build result list from PG + transcripts
    results = []
    for a in assets:
        ajobs = (job_dict or {}).get(str(a.id), {})
        scene_st = ajobs.get('scene', 'pending') or ""
        trans_st = ajobs.get('transcript', 'pending') or ""
        yolo_ok = ajobs.get('yolo', 'pending') == "completed"
        ocr_ok  = ajobs.get('ocr', 'pending') == "completed"
        results.append({
            "id": str(a.id), "file_name": a.file_name,
            "duration": a.duration, "thumbnail_path": a.thumbnail_path,
            "media_date": a.media_date.isoformat() if a.media_date else None,
            "file_size": a.file_size,
            "codec": a.codec,
            "width": a.width,
            "height": a.height,
            "is_favorite": a.is_favorite,
            "is_archived": a.is_archived,
            "match_type": "metadata", "score": 1.0,
            "match_sources": ["metadata"],
            "matches": [],
            "scene_status": scene_st,
            "clip_status": ajobs.get("clip", "pending") or "",
            "transcript_status": trans_st,
            "diarization_status": ajobs.get('diarization', 'pending') or "",
            "has_yolo_tags": yolo_ok,
            "has_ocr_text": ocr_ok,
        })
    # O(1) lookup by id
    results_by_id: dict[str, dict] = {r["id"]: r for r in results}

    if q:
        transcript_hits = await search_transcripts(session, q, limit=page_size)
        for asset, text, start_time in transcript_hits:
            aid = str(asset.id)
            entry = results_by_id.get(aid)
            if entry is None:
                new_entry = {
                    "id": aid, "file_name": asset.file_name,
                    "duration": asset.duration, "thumbnail_path": asset.thumbnail_path,
                    "media_date": asset.media_date.isoformat() if asset.media_date else None,
                    "file_size": asset.file_size,
                    "codec": asset.codec,
                    "width": asset.width,
                    "height": asset.height,
                    "is_favorite": asset.is_favorite,
                    "is_archived": asset.is_archived,
                    "match_type": "transcript", "score": 0.85,
                    "match_sources": ["transcript"],
                    "matches": [{"source": "transcript", "snippet": text[:200], "time_sec": start_time}],
                    "scene_status": "",
                    "clip_status": "",
                    "transcript_status": "",
                    "diarization_status": "",
                    "has_yolo_tags": False,
                    "has_ocr_text": False,
                }
                results.append(new_entry)
                results_by_id[aid] = new_entry
            else:
                entry["match_sources"].append("transcript")
                entry["matches"].append({"source": "transcript", "snippet": text[:200], "time_sec": start_time})
                if 0.85 > entry["score"]:
                    entry["score"] = 0.85

    # Phase 2: AI SQLite search (SceneTag / SceneOCR) — uses O(1) dict lookup
    if q:
        try:
            from ..models.ai import Scene, SceneTag, SceneOCR, Video, get_ai_session
            ai_session = get_ai_session()
            # Collect unmatched video_ids for batch Video lookup
            unmatched_video_ids: set[str] = set()

            # SceneTag (YOLO objects) — score 0.7
            _tag_distinct = await asyncio.to_thread(
                lambda: ai_session.query(Scene.video_id)
                    .join(SceneTag, SceneTag.scene_id == Scene.id)
                    .filter(SceneTag.label.contains(q))
                    .distinct()
                    .order_by(Scene.video_id)
                    .offset((page - 1) * page_size * 2).limit(page_size * 2)
                    .all()
            )
            _tag_video_ids = [row[0] for row in _tag_distinct]
            tag_hits = await asyncio.to_thread(
                lambda: ai_session.query(SceneTag.label, SceneTag.confidence, Scene.video_id, Scene.start_time)
                    .join(Scene, Scene.id == SceneTag.scene_id)
                    .filter(Scene.video_id.in_(_tag_video_ids))
                    .order_by(Scene.start_time)
                    .all()
            ) if _tag_video_ids else []
            for label, conf, video_id, start_time in tag_hits:
                entry = results_by_id.get(video_id)
                if entry is not None:
                    entry["match_sources"].append("object")
                    entry["matches"].append({"source": "object", "snippet": f"{label} (conf={conf:.2f})", "time_sec": start_time})
                    if 0.7 > entry["score"]:
                        entry["score"] = 0.7
                else:
                    unmatched_video_ids.add(video_id)

            # SceneOCR (in-frame text) — score 0.6
            _ocr_distinct = await asyncio.to_thread(
                lambda: ai_session.query(Scene.video_id)
                    .join(SceneOCR, SceneOCR.scene_id == Scene.id)
                    .filter(SceneOCR.text.contains(q))
                    .distinct()
                    .order_by(Scene.video_id)
                    .offset((page - 1) * page_size).limit(page_size)
                    .all()
            )
            _ocr_video_ids = [row[0] for row in _ocr_distinct]
            ocr_hits = await asyncio.to_thread(
                lambda: ai_session.query(SceneOCR.text, SceneOCR.confidence, Scene.video_id, Scene.start_time)
                    .join(Scene, Scene.id == SceneOCR.scene_id)
                    .filter(Scene.video_id.in_(_ocr_video_ids))
                    .order_by(Scene.start_time)
                    .all()
            ) if _ocr_video_ids else []
            ocr_unmatched: set[str] = set()
            for text, conf, video_id, start_time in ocr_hits:
                entry = results_by_id.get(video_id)
                if entry is not None:
                    entry["match_sources"].append("ocr")
                    entry["matches"].append({"source": "ocr", "snippet": text[:120], "time_sec": start_time})
                    if 0.6 > entry["score"]:
                        entry["score"] = 0.6
                else:
                    ocr_unmatched.add(video_id)

            unmatched_video_ids |= ocr_unmatched

            # Batch query unmatched video info from AI Video table
            if unmatched_video_ids:
                video_rows = await asyncio.to_thread(
                    lambda: ai_session.query(Video).filter(Video.id.in_(list(unmatched_video_ids))).all()
                )
                videos = {v.id: v for v in video_rows}

                # Append tag-only results
                for label, conf, video_id, start_time in tag_hits:
                    if video_id in unmatched_video_ids and video_id in videos:
                        vid = videos[video_id]
                        if results_by_id.get(video_id) is None:
                            new_entry = {
                                "id": video_id, "file_name": vid.file_name,
                                "duration": vid.duration, "thumbnail_path": None,
                                "media_date": None, "file_size": 0, "codec": None,
                                "width": vid.width, "height": vid.height,
                                "is_favorite": False, "is_archived": False,
                            "match_type": "object", "score": 0.7,
                            "match_sources": ["object"],
                            "matches": [{"source": "object", "snippet": f"{label} (conf={conf:.2f})", "time_sec": start_time}],
            "scene_status": "",
            "clip_status": "",
            "transcript_status": "",
                    "diarization_status": "",
            "has_yolo_tags": False,
            "has_ocr_text": False,
                        }
                        results.append(new_entry)
                        results_by_id[video_id] = new_entry

                # Append OCR-only results (skip if already added by tags)
                for text, conf, video_id, start_time in ocr_hits:
                    if video_id in unmatched_video_ids and video_id in videos:
                        entry = results_by_id.get(video_id)
                        if entry is not None:
                            if "ocr" not in entry["match_sources"]:
                                entry["match_sources"].append("ocr")
                                entry["matches"].append({"source": "ocr", "snippet": text[:120], "time_sec": start_time})
                        else:
                            vid = videos[video_id]
                            new_entry = {
                                "id": video_id, "file_name": vid.file_name,
                                "duration": vid.duration, "thumbnail_path": None,
                                "media_date": None, "file_size": 0, "codec": None,
                                "width": vid.width, "height": vid.height,
                                "is_favorite": False, "is_archived": False,
                            "match_type": "ocr", "score": 0.6,
                            "match_sources": ["ocr"],
                            "matches": [{"source": "ocr", "snippet": text[:120], "time_sec": start_time}],
            "scene_status": "",
            "clip_status": "",
            "transcript_status": "",
                    "diarization_status": "",
            "has_yolo_tags": False,
            "has_ocr_text": False,
                        }
                        results.append(new_entry)
                        results_by_id[video_id] = new_entry

            ai_session.close()
        except Exception as e:
            logger.debug("AI SQLite search error: %s", e)

        # Phase 3: CLIP visual search (via AI container) — score 0.8 * clip_score
        try:
            clip_resp = httpx.post(f"{AI_SERVICE_URL}/clip/search", json={"query": q, "top_k": min(page_size, 100)}, timeout=5)
            if clip_resp.status_code == 200:
                clip_results = clip_resp.json().get("results", [])
                clip_unmatched: set[str] = set()
                for cr in clip_results:
                    video_id = cr.get("video_id", "")
                    clip_score = cr.get("score", 0)
                    time_sec = cr.get("time_sec", 0)
                    frame_path = cr.get("frame_path", "")
                    final_score = clip_score * 0.8
                    entry = results_by_id.get(video_id)
                    if entry is not None:
                        entry["match_sources"].append("visual")
                        entry["matches"].append({"source": "visual", "snippet": f"Visual match ({clip_score:.2f})", "time_sec": time_sec})
                        if final_score > entry["score"]:
                            entry["score"] = final_score
                    else:
                        clip_unmatched.add(video_id)

                if clip_unmatched:
                    from ..models.ai import Video
                    ai_session2 = get_ai_session()
                    clip_video_rows = await asyncio.to_thread(
                        lambda: ai_session2.query(Video).filter(Video.id.in_(list(clip_unmatched))).all()
                    )
                    clip_videos = {v.id: v for v in clip_video_rows}
                    for cr in clip_results:
                        video_id = cr.get("video_id", "")
                        if video_id not in clip_unmatched:
                            continue
                        vid = clip_videos.get(video_id)
                        if vid:
                            clip_score = cr.get("score", 0)
                            time_sec = cr.get("time_sec", 0)
                            frame_path = cr.get("frame_path", "")
                            final_score = clip_score * 0.8
                            entry = results_by_id.get(video_id)
                            if entry is None:
                                new_entry = {
                                    "id": video_id, "file_name": vid.file_name,
                                    "duration": vid.duration, "thumbnail_path": frame_path or None,
                                    "media_date": None, "file_size": 0, "codec": None,
                                    "width": vid.width, "height": vid.height,
                                    "is_favorite": False, "is_archived": False,
                            "match_type": "visual", "score": final_score,
                            "match_sources": ["visual"],
                            "matches": [{"source": "visual", "snippet": f"Visual match ({clip_score:.2f})", "time_sec": time_sec}],
            "scene_status": "",
            "clip_status": "",
            "transcript_status": "",
                    "diarization_status": "",
            "has_yolo_tags": False,
            "has_ocr_text": False,
                        }
                        results.append(new_entry)
                        results_by_id[video_id] = new_entry
                    ai_session2.close()
        except Exception as e:
            logger.debug("CLIP search error: %s", e)

    # Dedup match_sources per result
    for r in results:
        r["match_sources"] = list(dict.fromkeys(r["match_sources"]))

    # Batch-fill AI status for Phase 2/3 entries (from ai_engine_jobs)
    try:
        import uuid as _uuid2
        missing = [r for r in results if not r.get("scene_status") and not r.get("transcript_status")]
        if missing:
            missing_ids = [_uuid2.UUID(r["id"]) for r in missing]
            stmt = sa_select(
                AIEngineJob.media_id, AIEngineJob.engine_name, AIEngineJob.status
            ).where(AIEngineJob.media_id.in_(missing_ids))
            rows = await session.execute(stmt)
            job_statuses = {}
            for row in rows:
                mid = str(row[0])
                ename = row[1]
                st = row[2]
                job_statuses.setdefault(mid, {})[ename] = st
            for r in results:
                eng_status = job_statuses.get(r["id"])
                if eng_status is None:
                    continue
                if not r.get("scene_status"):
                    r["scene_status"] = eng_status.get("scene", "") or ""
                if not r.get("transcript_status"):
                    r["transcript_status"] = eng_status.get("transcript", "") or ""
                if not r.get("has_yolo_tags"):
                    r["has_yolo_tags"] = eng_status.get("yolo", "") == "done"
                if not r.get("has_ocr_text"):
                    r["has_ocr_text"] = eng_status.get("ocr", "") == "done"
                if not r.get("clip_status"):
                    r["clip_status"] = eng_status.get("clip", "") or ""
                if not r.get("diarization_status"):
                    r["diarization_status"] = eng_status.get("diarization", "") or ""
    except Exception as e:
        logger.debug("Batch AI status fill error: %s", e)

    try:
        missing_thumb = [r for r in results if not r.get("thumbnail_path")]
        if missing_thumb:
            import uuid as _uuid
            from ..models.asset import Asset
            missing_ids = []
            for r in missing_thumb:
                try:
                    missing_ids.append(_uuid.UUID(r["id"]))
                except Exception:
                    pass
            if missing_ids:
                stmt = sa_select(Asset.id, Asset.thumbnail_path).where(Asset.id.in_(missing_ids))
                rows = await session.execute(stmt)
                thumb_map = {str(row[0]): row[1] for row in rows}
                for r in results:
                    tp = thumb_map.get(r.get("id", ""))
                    if tp:
                        r["thumbnail_path"] = tp
    except Exception as e:
        logger.debug("Batch thumbnail fill error: %s", e)

    # ── File size fill & filter for Phase 2/3 entries (transcript/AI/CLIP fallback) ──
    if query.min_file_size is not None or query.max_file_size is not None:
        try:
            import uuid as _uuid3
            zero_size = [r for r in results if r.get("file_size", 0) == 0]
            if zero_size:
                fs_ids = []
                for r in zero_size:
                    try:
                        fs_ids.append(_uuid3.UUID(r["id"]))
                    except Exception:
                        pass
                if fs_ids:
                    from ..models.asset import Asset
                    stmt = sa_select(Asset.id, Asset.file_size).where(Asset.id.in_(fs_ids))
                    rows = await session.execute(stmt)
                    fs_map = {str(row[0]): row[1] for row in rows}
                    for r in results:
                        real_fs = fs_map.get(r["id"])
                        if real_fs is not None:
                            r["file_size"] = real_fs
            before = len(results)
            results = [
                r for r in results
                if not (query.min_file_size is not None and (r.get("file_size") or 0) < query.min_file_size)
                and not (query.max_file_size is not None and (r.get("file_size") or 0) > query.max_file_size)
            ]
            filtered_out = before - len(results)
            if filtered_out:
                logger.debug("File size filter removed %d results from Phase 2/3", filtered_out)
        except Exception as e:
            logger.debug("File size fill/filter error: %s", e)
    # ── Duration filter for Phase 2/3 entries (transcript/AI/CLIP fallback) ──
    if query.min_duration is not None or query.max_duration is not None:
        try:
            import uuid as _uuid4
            null_dur = [r for r in results if r.get("duration") is None]
            if null_dur:
                dur_ids = []
                for r in null_dur:
                    try:
                        dur_ids.append(_uuid4.UUID(r["id"]))
                    except Exception:
                        pass
                if dur_ids:
                    from ..models.asset import Asset
                    stmt = sa_select(Asset.id, Asset.duration).where(Asset.id.in_(dur_ids))
                    rows = await session.execute(stmt)
                    dur_map = {str(row[0]): row[1] for row in rows}
                    for r in results:
                        real_dur = dur_map.get(r["id"])
                        if real_dur is not None:
                            r["duration"] = real_dur
            before = len(results)
            results = [
                r for r in results
                if not (query.min_duration is not None and (r.get("duration") or 0) < query.min_duration)
                and not (query.max_duration is not None and (r.get("duration") or 0) > query.max_duration)
            ]
            filtered_out = before - len(results)
            if filtered_out:
                logger.debug("Duration filter removed %d results from Phase 2/3", filtered_out)
        except Exception as e:
            logger.debug("Duration fill/filter error: %s", e)
    # ── Orientation filter for Phase 2/3 entries ──
    if orientation == "landscape":
        results = [r for r in results if r.get("width") and r.get("height") and r["width"] > r["height"]]
    elif orientation == "portrait":
        results = [r for r in results if r.get("width") and r.get("height") and r["width"] < r["height"]]
    # Sort by score descending
    results.sort(key=lambda x: x.get("score", 0), reverse=True)

    # total: pure filter uses DB count, text search uses runtime list
    if q:
        return_total = max(total, len(results))
    else:
        return_total = total
    # ── Compute per-engine completed counts (filter-only mode) ──
    source_totals = {}
    if q:
        try:
            from ..models.asset import Asset
            if not include_archived:
                asset_filter = sa_select(Asset.id)
                asset_filter = asset_filter.where(Asset.is_archived == False)
            else:
                asset_filter = sa_select(Asset.id)
            q_like = f"%{q}%"
            asset_filter = asset_filter.where(
                (Asset.file_name.ilike(q_like)) | (Asset.notes.ilike(q_like))
            )
            if library_id:
                asset_filter = asset_filter.where(Asset.library_id == library_id)
            if min_duration is not None:
                asset_filter = asset_filter.where(Asset.duration >= min_duration)
            if max_duration is not None:
                asset_filter = asset_filter.where(Asset.duration <= max_duration)
            if min_file_size is not None:
                asset_filter = asset_filter.where(Asset.file_size >= min_file_size)
            if max_file_size is not None:
                asset_filter = asset_filter.where(Asset.file_size <= max_file_size)
            if orientation == "landscape":
                asset_filter = asset_filter.where(Asset.width > Asset.height)
            elif orientation == "portrait":
                asset_filter = asset_filter.where(Asset.width < Asset.height)

            for ename in ['scene','yolo','ocr','clip','transcript','diarization']:
                cnt = (await session.execute(
                    sa_select(func.count(AIEngineJob.id))
                    .where(AIEngineJob.engine_name == ename, AIEngineJob.status == 'completed', AIEngineJob.media_id.in_(asset_filter))
                )).scalar() or 0
                source_totals[ename] = cnt
        except Exception as e:
            logger.debug('Source totals error: %s', e)
    elif not q:
        try:
            from ..models.asset import Asset
            asset_filter = sa_select(Asset.id)
            if not include_archived:
                asset_filter = asset_filter.where(Asset.is_archived == False)
            if library_id:
                asset_filter = asset_filter.where(Asset.library_id == library_id)
            if min_duration is not None:
                asset_filter = asset_filter.where(Asset.duration >= min_duration)
            if max_duration is not None:
                asset_filter = asset_filter.where(Asset.duration <= max_duration)
            if min_file_size is not None:
                asset_filter = asset_filter.where(Asset.file_size >= min_file_size)
            if max_file_size is not None:
               asset_filter = asset_filter.where(Asset.file_size <= max_file_size)
            if orientation == "landscape":
                asset_filter = asset_filter.where(Asset.width > Asset.height)
            elif orientation == "portrait":
                asset_filter = asset_filter.where(Asset.width < Asset.height)
 
            for ename in ['scene','yolo','ocr','clip','transcript','diarization']:
                cnt = (await session.execute(
                    sa_select(func.count(AIEngineJob.id))
                    .where(AIEngineJob.engine_name == ename, AIEngineJob.status == 'completed', AIEngineJob.media_id.in_(asset_filter))
                )).scalar() or 0
                source_totals[ename] = cnt
        except Exception as e:
            logger.debug('Source totals error: %s', e)


    return {"results": results, "total": return_total, "source_totals": source_totals}
