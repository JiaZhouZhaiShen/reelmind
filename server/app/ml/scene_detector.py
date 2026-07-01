from pathlib import Path
from typing import Any

from ..config import settings


def detect_scenes(video_path: str | Path) -> list[dict[str, Any]]:
    try:
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector
    except ImportError:
        return []

    video = open_video(str(video_path))
    scene_manager = SceneManager()
    scene_manager.add_detector(
        ContentDetector(threshold=settings.SCENE_THRESHOLD)
    )
    scene_manager.detect_scenes(video)
    scene_list = scene_manager.get_scene_list()

    segments = []
    for i, (start, end) in enumerate(scene_list):
        segments.append({
            "start_time": start.get_seconds(),
            "end_time": end.get_seconds(),
            "scene_label": f"scene_{i:04d}",
            "source": "auto",
        })
    return segments
